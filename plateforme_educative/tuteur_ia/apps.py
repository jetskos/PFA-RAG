from django.apps import AppConfig
import threading
import logging

logger = logging.getLogger(__name__)


class TuteurIaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tuteur_ia'
    verbose_name = 'Tuteur IA'

    def ready(self):
        # Prevent preloading when running management commands like migrate, makemigrations, test, etc.
        import sys
        if any(cmd in sys.argv for cmd in ['migrate', 'makemigrations', 'test', 'shell', 'db', 'showmigrations']):
            return

        def preload_chroma():
            logger.info("Début du préchargement en arrière-plan de ChromaDB et du modèle d'embedding...")
            try:
                from tuteur_ia.tools.chroma_store import get_collection
                collection = get_collection()
                logger.info(f"Préchargement de ChromaDB réussi. {collection.count()} chunks prêts en mémoire.")
            except Exception as e:
                logger.warning(f"Impossible de précharger ChromaDB en arrière-plan : {e}")

        # Lancer le préchargement dans un thread daemon en arrière-plan
        threading.Thread(target=preload_chroma, daemon=True, name="ChromaPreloader").start()

