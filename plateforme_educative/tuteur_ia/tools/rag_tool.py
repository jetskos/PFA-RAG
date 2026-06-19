"""
RAG Tool — Recherche sémantique dans ChromaDB.

Remplace la recherche par mots-clés par une recherche vectorielle
sur les chunks indexés depuis les PDFs uploadés.

Interface publique unique : rag_search(query, chapitre_id, cours_id)
"""
import logging

logger = logging.getLogger(__name__)


def rag_search(
    query: str,
    chapitre_id: str = None,
    cours_id: str = None,
    n_results: int = 4,
) -> str:
    """
    Recherche sémantique dans ChromaDB sur les chunks des PDFs.

    Args:
        query:       Question ou concept à rechercher
        chapitre_id: Filtre sur le chapitre (recommandé — plus précis)
        cours_id:    Filtre sur le cours entier (plus large)
        n_results:   Nombre de chunks retournés

    Returns:
        Texte assemblé des chunks les plus pertinents,
        ou message si aucun document indexé.
    """
    try:
        from tuteur_ia.tools.chroma_store import search, get_stats

        # Vérifier si la collection est vide
        stats = get_stats()
        if stats.get("total_chunks", 0) == 0:
            return (
                "[Aucun document indexé dans ChromaDB. "
                "Uploadez un PDF dans le chapitre et il sera automatiquement indexé.]"
            )

        results = search(
            query=query,
            chapitre_id=chapitre_id,
            cours_id=cours_id,
            n_results=n_results,
        )

        if not results:
            # Aucun résultat pour ce chapitre — NE PAS faire de recherche sans filtre.
            # Un fallback non filtré risque de ramener du contenu d'autres cours
            # (ex: cours Java pour du contenu IoT primaire).
            if chapitre_id:
                return "[Aucun document indexé pour ce chapitre. Uploadez un PDF dans ce chapitre.]"
            return "[Aucun contenu pertinent trouvé dans les documents indexés.]"

        # Assembler les chunks avec source
        parts = []
        seen_texts = set()
        for r in results:
            text = r["text"].strip()
            if not text or text in seen_texts:
                continue
            seen_texts.add(text)

            source = r.get("document_titre", "Document")
            page   = r.get("page_hint", "")
            header = f"[{source}" + (f" — p.{page}" if page else "") + "]"
            parts.append(f"{header}\n{text}")

        return "\n\n---\n\n".join(parts) if parts else "[Contenu vide après déduplication.]"

    except Exception as e:
        logger.error(f"Erreur rag_search : {e}", exc_info=True)
        return f"[Erreur RAG : {e}]"
