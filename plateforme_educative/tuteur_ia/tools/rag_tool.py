"""
RAG Tool — Recherche hybride BM25 + Sémantique avec RRF.

Pipeline :
  1. Recherche sémantique (ChromaDB / cosine similarity)
  2. Recherche lexicale   (BM25Okapi sur DocumentChunk)
  3. Fusion RRF           (Reciprocal Rank Fusion, k=60)
  4. Assemblage du contexte avec déduplication

Interface publique unique : rag_search(query, chapitre_id, cours_id)
"""
import logging

logger = logging.getLogger(__name__)


def rag_search(
    query: str,
    chapitre_id: str = None,
    cours_id: str = None,
    n_results: int = 4,
    *,
    semantic_weight: int = 1,   # Nombre de listes sémantiques (pour RRF)
    bm25_weight: int = 1,       # Nombre de listes BM25      (pour RRF)
) -> str:
    """
    Recherche hybride BM25 + Sémantique avec fusion RRF.

    Args:
        query:          Question ou concept à rechercher
        chapitre_id:    Filtre chapitre (prioritaire, plus précis)
        cours_id:       Filtre cours (portée plus large)
        n_results:      Nombre de chunks finaux retournés
        semantic_weight: Répétition de la liste sémantique dans RRF
                         (augmente son poids relatif)
        bm25_weight:    Répétition de la liste BM25 dans RRF

    Returns:
        Texte assemblé des chunks les plus pertinents,
        ou message si aucun document indexé.
    """
    try:
        from tuteur_ia.tools.chroma_store import search as semantic_search, get_stats
        from tuteur_ia.tools.bm25_store   import bm25_search
        from tuteur_ia.tools.rrf           import rrf_fuse

        # ── Vérification corpus ───────────────────────────────────────────────
        stats = get_stats()
        if stats.get("total_chunks", 0) == 0:
            return (
                "[Aucun document indexé. "
                "Uploadez un PDF dans le chapitre pour activer le RAG.]"
            )

        # ── 1. Recherche sémantique ───────────────────────────────────────────
        # On récupère plus de candidats qu'on en veut (2× n_results)
        # pour que RRF ait suffisamment de matière à fusionner.
        semantic_k = max(n_results * 2, 6)
        sem_raw = semantic_search(
            query=query,
            chapitre_id=chapitre_id,
            cours_id=cours_id,
            n_results=semantic_k,
        )

        # Normaliser : ajouter chunk_id synthétique (hash texte) si absent
        sem_results = []
        for i, r in enumerate(sem_raw):
            r.setdefault("chunk_id", f"sem_{i}_{hash(r['text'])}")
            # Renommer 'text' → 'text' (déjà bon), mais s'assurer de la cohérence
            sem_results.append(r)

        # ── 2. Recherche BM25 ─────────────────────────────────────────────────
        bm25_k = max(n_results * 2, 6)
        bm25_raw = bm25_search(
            query=query,
            chapitre_id=chapitre_id,
            cours_id=cours_id,
            n_results=bm25_k,
        )
        # Normaliser : BM25 retourne 'text' via la clé 'text'
        bm25_results = []
        for r in bm25_raw:
            bm25_results.append({
                "chunk_id":       r["chunk_id"],
                "text":           r["text"],
                "document_titre": r["document_titre"],
                "page_hint":      r["page_hint"],
                "chapitre_id":    r["chapitre_id"],
                "bm25_score":     r["bm25_score"],
            })

        # ── 3. Fusion RRF ─────────────────────────────────────────────────────
        if not sem_results and not bm25_results:
            if chapitre_id:
                return "[Aucun document indexé pour ce chapitre. Uploadez un PDF.]"
            return "[Aucun contenu pertinent trouvé dans les documents indexés.]"

        # Construire les listes pondérées pour RRF
        rrf_inputs = (
            [sem_results]  * semantic_weight +
            [bm25_results] * bm25_weight
        )

        fused = rrf_fuse(*rrf_inputs, id_key="chunk_id", n_results=n_results)

        # ── 4. Assemblage ─────────────────────────────────────────────────────
        parts = []
        seen_texts: set[str] = set()

        for chunk in fused:
            text = (chunk.get("text") or "").strip()
            if not text or text in seen_texts:
                continue
            seen_texts.add(text)

            source = chunk.get("document_titre", "Document")
            page   = chunk.get("page_hint", "")
            score  = chunk.get("rrf_score", 0)
            srcs   = "+".join(chunk.get("retrieval_sources", []))

            header = f"[{source}" + (f" — p.{page}" if page else "") + f" | RRF={score:.4f} ({srcs})]"
            parts.append(f"{header}\n{text}")

        if not parts:
            return "[Contenu vide après fusion et déduplication.]"

        logger.info(
            f"Hybrid RAG : {len(sem_results)} sémantique + {len(bm25_results)} BM25 "
            f"→ {len(fused)} fusionnés (RRF) pour '{query[:60]}'"
        )

        return "\n\n---\n\n".join(parts)

    except Exception as e:
        logger.error(f"Erreur rag_search hybride : {e}", exc_info=True)
        return f"[Erreur RAG : {e}]"
