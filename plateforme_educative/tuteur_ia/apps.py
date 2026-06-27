from django.apps import AppConfig
import threading
import logging

logger = logging.getLogger(__name__)


class TuteurIaConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tuteur_ia'
    verbose_name = 'Tuteur IA'

def ready(self):
    import sys
    # On ne précharge JAMAIS pendant les commandes de gestion
    if any(cmd in sys.argv for cmd in
           ['migrate', 'makemigrations', 'test', 'shell', 'db', 'showmigrations', 'collectstatic']):
        return

    # Préchargement désactivé par défaut : il bloquait/ralentissait le runserver.
    # Pour le réactiver volontairement : PRELOAD_CHROMA=1 dans le .env
    import os
    if os.getenv('PRELOAD_CHROMA', '0') != '1':
        return

    import threading
    def preload_chroma():
        try:
            from tuteur_ia.tools.chroma_store import get_collection
            collection = get_collection()
            logger.info(f"Préchargement ChromaDB : {collection.count()} chunks prêts.")
        except Exception as e:
            logger.warning(f"Préchargement ChromaDB impossible : {e}")

    threading.Thread(target=preload_chroma, daemon=True, name="ChromaPreloader").start()