"""
Tâches Celery pour le module apprentissage.
- indexer_document_task : indexation asynchrone d'un PDF dans ChromaDB
"""
import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30,
             name='apprentissage.tasks.indexer_document_task')
def indexer_document_task(self, document_id: str, pdf_path: str):
    """
    Extrait le texte d'un PDF et l'indexe dans ChromaDB de manière asynchrone.

    Args:
        document_id : UUID du Document en base de données.
        pdf_path    : Chemin absolu vers le fichier PDF sur le disque.
    """
    logger.info(f"[ChromaDB] Indexation démarrée — doc {document_id[:8]}...")
    try:
        from apprentissage.models import Document
        from tuteur_ia.tools.pdf_extractor import extract_and_chunk_pdf
        from tuteur_ia.tools.chroma_store import add_chunks

        # 1. Extraire et chunker le PDF
        full_text, chunks = extract_and_chunk_pdf(pdf_path)

        if not full_text:
            logger.warning(f"[ChromaDB] PDF vide ou scanné : {pdf_path}")
            return

        # 2. Mettre à jour contenu_extrait en base
        Document.objects.filter(pk=document_id).update(contenu_extrait=full_text)

        # 3. Récupérer métadonnées pour les filtres ChromaDB
        doc = Document.objects.get(pk=document_id)

        # 4. Indexer dans ChromaDB (remplace les anciens chunks si existants)
        add_chunks(
            chunks=chunks,
            document_id=document_id,
            document_titre=doc.titre,
            chapitre_id=str(doc.chapitre_id),
            cours_id=str(doc.chapitre.cours_id),
        )

        logger.info(
            f"[ChromaDB] ✓ '{doc.titre}' indexé : "
            f"{len(full_text):,} chars, {len(chunks)} chunks"
        )

    except Exception as exc:
        logger.error(
            f"[ChromaDB] ✗ Erreur indexation {document_id}: {exc}",
            exc_info=True,
        )
