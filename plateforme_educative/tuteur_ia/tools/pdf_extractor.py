"""
Extracteur PDF avec chunking récursif.

Pipeline :
  1. pdfplumber → texte brut page par page
  2. Nettoyage (lignes coupées, espaces parasites)
  3. Chunking récursif hiérarchique :
       sections → paragraphes → phrases → mots
  4. Retourne (full_text, chunks[])

Utilisé par le signal Django et la commande extraire_pdfs.
"""
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paramètres de chunking ────────────────────────────────────────────────────

CHUNK_SIZE    = 400   # Caractères max par chunk (optimal pour embeddings)
CHUNK_OVERLAP = 60    # Chevauchement entre chunks voisins


# ── Extraction ───────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extrait le texte brut d'un PDF avec pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Installez pdfplumber : pip install pdfplumber")

    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                pages.append(f"[Page {i}]\n{text.strip()}")

    if not pages:
        logger.warning(f"Aucun texte extrait de {pdf_path} — PDF scanné ?")

    return "\n\n".join(pages)


# ── Nettoyage ────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Nettoie le texte extrait."""
    text = re.sub(r'-\n(\w)',  r'\1',   text)   # Mots coupés en fin de ligne
    text = re.sub(r'\n{3,}',  '\n\n',  text)   # Sauts de ligne excessifs
    text = re.sub(r' +\n',    '\n',    text)   # Espaces en fin de ligne
    text = re.sub(r' {2,}',   ' ',     text)   # Espaces multiples
    text = re.sub(r'\f',      '\n\n',  text)   # Saut de page
    return text.strip()


# ── Chunking récursif ─────────────────────────────────────────────────────────

# Séparateurs du plus grossier (sections) au plus fin (mots)
_SEPARATORS = [
    r'\[Page \d+\]\n?',                          # Marqueurs de page
    r'\n(?=[A-ZÀÂÉÈÊÎÔÙÛÜ][A-ZÀÂÉÈÊÎÔÙÛÜ ]{5,}\n)',  # Lignes tout-caps (titres)
    r'\n\n',                                      # Paragraphes
    r'(?<=[.!?])\s+',                            # Fin de phrase
    r'[,;]\s+',                                  # Virgules / points-virgules
    r'\s+',                                      # Mots
]


def _split(text: str, pattern: str) -> list[str]:
    parts = re.split(pattern, text)
    return [p.strip() for p in parts if p and p.strip()]


def _chunk_recursive(text: str, sep_idx: int = 0) -> list[str]:
    """Découpe récursivement le texte jusqu'à chunk_size."""
    if not text.strip():
        return []
    if len(text) <= CHUNK_SIZE or sep_idx >= len(_SEPARATORS):
        return [text]

    parts = _split(text, _SEPARATORS[sep_idx])

    if len(parts) <= 1:
        # Ce séparateur n'a rien coupé → passer au suivant
        return _chunk_recursive(text, sep_idx + 1)

    result = []
    for part in parts:
        if len(part) <= CHUNK_SIZE:
            result.append(part)
        else:
            result.extend(_chunk_recursive(part, sep_idx + 1))
    return result


def _merge_with_overlap(pieces: list[str]) -> list[str]:
    """Fusionne les petits chunks et ajoute un chevauchement."""
    merged = []
    current = ""

    for piece in pieces:
        if not piece:
            continue
        if len(current) + 1 + len(piece) <= CHUNK_SIZE:
            current = (current + " " + piece).strip()
        else:
            if current:
                merged.append(current)
            # Démarrer le nouveau chunk avec le overlap du précédent
            overlap = current[-CHUNK_OVERLAP:] if current and CHUNK_OVERLAP > 0 else ""
            current = (overlap + " " + piece).strip() if overlap else piece

    if current:
        merged.append(current)

    return merged


def recursive_chunk(text: str) -> list[dict]:
    """
    Chunking récursif complet.

    Returns:
        Liste de dicts : [{id, text, char_count, page_hint}]
    """
    pieces = _chunk_recursive(text)
    merged = _merge_with_overlap(pieces)

    chunks = []
    for i, chunk_text in enumerate(merged):
        # Détecter la page d'origine
        page_match = re.search(r'\[Page (\d+)\]', chunk_text)
        page_hint = int(page_match.group(1)) if page_match else None

        # Nettoyer le marqueur de page dans le chunk
        clean_chunk = re.sub(r'\[Page \d+\]\n?', '', chunk_text).strip()
        if not clean_chunk:
            continue

        chunks.append({
            "id":         i,
            "text":       clean_chunk,
            "char_count": len(clean_chunk),
            "page_hint":  page_hint,
        })

    logger.info(f"Chunking : {len(merged)} pièces → {len(chunks)} chunks finaux")
    return chunks


# ── Point d'entrée ────────────────────────────────────────────────────────────

def extract_and_chunk_pdf(pdf_path: str) -> tuple[str, list[dict]]:
    """
    Pipeline complet : PDF → texte nettoyé + chunks.

    Returns:
        (full_text, chunks) où full_text → Document.contenu_extrait
                                 chunks  → ChromaDB
    """
    raw_text  = extract_text_from_pdf(pdf_path)
    full_text = clean_text(raw_text)
    chunks    = recursive_chunk(full_text)

    logger.info(
        f"PDF traité : {Path(pdf_path).name} "
        f"→ {len(full_text):,} chars, {len(chunks)} chunks"
    )
    return full_text, chunks
