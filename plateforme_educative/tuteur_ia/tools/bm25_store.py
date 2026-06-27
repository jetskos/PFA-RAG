"""
BM25 Store — Recherche lexicale sur les chunks indexés.

Utilise rank_bm25 (BM25Okapi) sur le corpus Django (DocumentChunk).
Cache LRU par filtre (chapitre_id / cours_id) pour éviter de reconstruire
l'index à chaque requête.

L'index est invalidé automatiquement lors d'add/delete via invalidate_cache().
"""
import logging
import re
import unicodedata
from functools import lru_cache

logger = logging.getLogger(__name__)

# Cache global : {cache_key: (corpus_ids, BM25Okapi)}
_bm25_cache: dict = {}

# ── Tokeniseur French-aware ───────────────────────────────────────────────────

STOPWORDS_FR = {
    "le","la","les","un","une","des","de","du","d","l","et","en","au","aux",
    "ce","se","sa","son","ses","mon","ma","mes","ton","ta","tes","notre","votre",
    "leur","leurs","que","qui","quoi","dont","où","ou","et","est","sont","a",
    "y","il","elle","ils","elles","on","nous","vous","je","tu","par","pour",
    "sur","sous","dans","avec","sans","entre","vers","chez","plus","moins",
    "très","bien","avoir","être","fait","peut","si","car","mais","donc","or",
    "ni","ne","pas","plus","tout","tous","toute","toutes","même","aussi","comme",
    "quand","puis","après","avant","car","ainsi","selon","depuis","lors",
}


def _tokenize(text: str) -> list[str]:
    """
    Tokenise un texte pour BM25 :
    - Normalise les accents (NFD → supprime les diacritiques)
    - Met en minuscules
    - Extrait les mots alphanumériques (3 caractères minimum)
    - Supprime les stopwords français
    """
    # Normalisation NFD → garde les lettres de base sans accents
    nfd = unicodedata.normalize("NFD", text)
    ascii_text = nfd.encode("ascii", "ignore").decode("ascii")
    tokens = re.findall(r"[a-z0-9]{3,}", ascii_text.lower())
    return [t for t in tokens if t not in STOPWORDS_FR]


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_key(chapitre_id: str | None, cours_id: str | None) -> str:
    return f"ch:{chapitre_id or ''}|co:{cours_id or ''}"


def invalidate_cache(chapitre_id: str | None = None, cours_id: str | None = None):
    """
    Invalide le cache BM25 après un add/delete de chunks.
    Si aucun filtre fourni, vide tout le cache.
    """
    global _bm25_cache
    if chapitre_id is None and cours_id is None:
        _bm25_cache.clear()
        logger.debug("Cache BM25 entièrement vidé")
    else:
        key = _cache_key(chapitre_id, cours_id)
        _bm25_cache.pop(key, None)
        # Invalider aussi la clé cours seule si chapitre fourni
        if chapitre_id:
            _bm25_cache.pop(_cache_key(None, cours_id), None)
        logger.debug(f"Cache BM25 invalidé pour {key}")


def _build_index(chapitre_id: str | None, cours_id: str | None):
    """
    Construit (ou retourne du cache) l'index BM25 filtré.
    Retourne (chunks_qs, tokenized_corpus, BM25Okapi_index) ou None si vide.
    """
    from rank_bm25 import BM25Okapi
    from tuteur_ia.models import DocumentChunk

    key = _cache_key(chapitre_id, cours_id)
    if key in _bm25_cache:
        return _bm25_cache[key]

    # Filtrer les chunks selon la portée
    qs = DocumentChunk.objects.all()
    if chapitre_id:
        qs = qs.filter(chapitre_id=chapitre_id)
    elif cours_id:
        qs = qs.filter(cours_id=cours_id)

    chunks = list(qs.values("chunk_id", "texte", "document_titre", "page_hint", "chapitre_id"))

    if not chunks:
        _bm25_cache[key] = None
        return None

    tokenized = [_tokenize(c["texte"]) for c in chunks]
    index = BM25Okapi(tokenized)

    result = (chunks, tokenized, index)
    _bm25_cache[key] = result
    logger.debug(f"Index BM25 construit : {len(chunks)} chunks [{key}]")
    return result


# ── Interface publique ────────────────────────────────────────────────────────

def bm25_search(
    query: str,
    chapitre_id: str | None = None,
    cours_id: str | None = None,
    n_results: int = 4,
) -> list[dict]:
    """
    Recherche BM25 (lexicale) dans le corpus filtré.

    Returns:
        Liste de dicts {chunk_id, text, document_titre, page_hint,
                        chapitre_id, bm25_score}  triés par score décroissant.
    """
    try:
        cached = _build_index(chapitre_id, cours_id)
        if cached is None:
            return []

        chunks, _, index = cached
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = index.get_scores(query_tokens)

        # Associer scores aux chunks et trier
        scored = sorted(
            zip(scores, chunks),
            key=lambda x: x[0],
            reverse=True,
        )

        results = []
        for score, chunk in scored[:n_results]:
            if score <= 0:
                continue
            results.append({
                "chunk_id":       chunk["chunk_id"],
                "text":           chunk["texte"],
                "document_titre": chunk["document_titre"],
                "page_hint":      chunk["page_hint"],
                "chapitre_id":    chunk["chapitre_id"],
                "bm25_score":     float(score),
            })

        return results

    except ImportError:
        logger.warning("rank_bm25 non installé. pip install rank-bm25")
        return []
    except Exception as e:
        logger.error(f"Erreur BM25 search : {e}", exc_info=True)
        return []
