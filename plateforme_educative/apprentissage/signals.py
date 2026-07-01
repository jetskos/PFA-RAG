"""
Signals Django — apprentissage app.

Déclenchement AUTOMATIQUE à chaque upload/modification de PDF :
  1. Extraction texte (pdfplumber)
  2. Chunking récursif
  3. Embedding + indexation ChromaDB
  4. Sauvegarde dans Document.contenu_extrait

Logique de déclenchement :
  - Nouveau document                    → toujours indexer
  - Document modifié avec NOUVEAU PDF   → toujours réindexer
  - Document modifié SANS changer PDF   → skip (évite les doubles indexations)
  - Document supprimé                   → supprimer les chunks de ChromaDB
"""
import os
import logging

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _index_document_async(document_id: str, pdf_path: str):
    """
    Lance l'indexation de manière synchrone pour éviter la corruption multi-processus de ChromaDB.
    """
    from apprentissage.tasks import indexer_document_task
    indexer_document_task(document_id=document_id, pdf_path=pdf_path)



def _pdf_has_changed(instance) -> bool:
    """
    Détecte si le fichier PDF a changé par rapport à la version en base.
    Compare le nom du fichier stocké en base avec le nom actuel.
    Retourne True si c'est un nouveau fichier (upload ou remplacement).
    """
    try:
        from apprentissage.models import Document
        old = Document.objects.get(pk=instance.pk)
        # Fichier changé si le nom diffère
        return str(old.fichier_pdf) != str(instance.fichier_pdf)
    except Document.DoesNotExist:
        # Nouveau document → pas encore en base
        return True
    except Exception:
        return True


@receiver(post_save, sender='apprentissage.Document')
def on_document_save(sender, instance, created, **kwargs):
    """
    Déclenché automatiquement après chaque sauvegarde d'un Document.

    Cas couverts :
    ┌─────────────────────────────────────────┬──────────────┐
    │ Situation                               │ Indexation   │
    ├─────────────────────────────────────────┼──────────────┤
    │ Nouveau document uploadé (admin/API)    │ ✅ Toujours  │
    │ PDF remplacé par un nouveau fichier     │ ✅ Toujours  │
    │ Modification du titre/description seul │ ❌ Skip      │
    │ contenu_extrait vidé manuellement       │ ✅ Toujours  │
    └─────────────────────────────────────────┴──────────────┘
    """
    if not instance.fichier_pdf:
        return

    try:
        pdf_path = instance.fichier_pdf.path
    except Exception:
        return

    if not os.path.exists(pdf_path):
        logger.warning(f"[ChromaDB] PDF introuvable : {pdf_path}")
        return

    # Décider s'il faut indexer
    if created:
        # Toujours indexer un nouveau document
        reason = "nouveau document"
    elif not (instance.contenu_extrait or "").strip():
        # contenu_extrait vide = jamais indexé ou réinitialisation forcée
        reason = "contenu_extrait vide"
    elif _pdf_has_changed(instance):
        # Le fichier PDF lui-même a changé (remplacement)
        reason = "nouveau fichier PDF"
    else:
        # Juste une modification de métadonnées → pas besoin de réindexer
        logger.debug(f"[ChromaDB] Skip '{instance.titre}' — PDF inchangé")
        return

    logger.info(
        f"[ChromaDB] Signal déclenché pour '{instance.titre}' "
        f"— raison : {reason}"
    )
    _index_document_async(
        document_id=str(instance.pk),
        pdf_path=pdf_path,
    )


@receiver(post_delete, sender='apprentissage.Document')
def on_document_delete(sender, instance, **kwargs):
    """
    Supprime automatiquement les chunks ChromaDB quand un Document est supprimé.
    """
    try:
        from tuteur_ia.tools.chroma_store import delete_document
        delete_document(str(instance.pk))
        logger.info(f"[ChromaDB] Chunks supprimés pour '{instance.titre}'")
    except Exception as e:
        logger.error(f"[ChromaDB] Erreur suppression {instance.pk}: {e}")
