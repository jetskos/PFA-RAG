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
        # Ne jamais précharger pendant les commandes de gestion Django
        if any(cmd in sys.argv for cmd in
               ['migrate', 'makemigrations', 'test', 'shell', 'db',
                'showmigrations', 'collectstatic', 'check']):
            return

        # Préchargement ChromaDB activé par défaut au démarrage du serveur.
        # Lance le chargement du modèle d'embedding en arrière-plan (thread daemon)
        # pour éviter le cold-start de 2-5s lors du premier appel QCM ou RAG.
        # Désactivable avec PRELOAD_CHROMA=0 dans le .env
        import os
        if os.getenv('PRELOAD_CHROMA', '1') == '0':
            logger.info("Préchargement ChromaDB désactivé (PRELOAD_CHROMA=0).")
            return

        import threading

        def preload_chroma():
            try:
                from tuteur_ia.tools.chroma_store import get_collection
                collection = get_collection()
                logger.info(
                    f"[ChromaDB] Modèle d'embedding prêt à "
                    f"{collection.count()} chunks en mémoire."
                )
            except Exception as e:
                logger.warning(f"[ChromaDB] Préchargement impossible : {e}")

        threading.Thread(
            target=preload_chroma,
            daemon=True,
            name="ChromaPreloader",
        ).start()
        logger.info("[ChromaDB] Thread de préchargement lancé.")