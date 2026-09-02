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
        # Ne jamais précharger pendant les commandes de gestion Django ni dans Celery.
        # Les commandes d'indexation/seed écrivent elles-mêmes dans ChromaDB : le
        # thread de préchargement qui ouvrirait la collection en parallèle crée une
        # course (vu en prod : « attempt to write a readonly database » pendant un
        # `indexer_pdfs --reset` qui supprime le dossier sous le thread).
        if any(cmd in sys.argv for cmd in
               ['migrate', 'makemigrations', 'test', 'shell', 'db',
                'showmigrations', 'collectstatic', 'check', 'celery',
                'indexer_pdfs', 'import_course', 'backfill_bm25',
                'seed_demo', 'seed_english_course', 'seed_iot_course']):
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

        # chromadb a un import circulaire interne qui déclenche un deadlock
        # ("_ModuleLock") si deux threads l'importent pour la première fois en
        # même temps — ça arrivait quand ce thread de préchargement démarrait
        # pendant qu'une requête importait aussi chromadb. `import chroma_store`
        # seul ne suffit pas : chromadb n'y est importé que paresseusement, à
        # l'intérieur des fonctions. On appelle donc get_collection() ici, de
        # façon SYNCHRONE dans le thread principal de démarrage Django (avant
        # toute requête et avant le thread ci-dessous), pour forcer réellement
        # l'import de chromadb une bonne fois pour toutes pendant le boot —
        # un coût ponctuel de ~2-3s au démarrage, acceptable pour éliminer
        # toute course d'import ensuite.
        try:
            from tuteur_ia.tools.chroma_store import get_collection, warm_up_embeddings
            get_collection()
        except Exception as e:
            logger.warning(f"[ChromaDB] Initialisation impossible au démarrage : {e}")
            return

        def preload_chroma():
            try:
                collection = get_collection()
                # Déclenche réellement le chargement du modèle ONNX (pas seulement
                # l'ouverture de la collection) pendant le démarrage du serveur,
                # plutôt que lors du premier message d'un élève.
                warm_up_embeddings()
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

        # Préchargement Ollama : le tout premier appel après un redémarrage
        # (ou après expiration de keep_alive) inclut le temps de chargement du
        # modèle en mémoire — observé jusqu'à plusieurs dizaines de secondes en
        # conditions réelles. On absorbe ce coût au démarrage du serveur plutôt
        # que lors du premier message d'un élève. Sans effet si Ollama n'est
        # pas installé/lancé (ex. déploiement cloud avec Groq uniquement).
        # Désactivable avec PRELOAD_OLLAMA=0.
        if os.getenv('PRELOAD_OLLAMA', '1') == '0':
            logger.info("Préchargement Ollama désactivé (PRELOAD_OLLAMA=0).")
            return

        def preload_ollama():
            try:
                from tuteur_ia.agents.llm_factory import (
                    OLLAMA_MODEL, OLLAMA_BASE_URL, OLLAMA_KEEP_ALIVE,
                    OLLAMA_NUM_CTX, OLLAMA_NUM_GPU,
                )
                from langchain_ollama import ChatOllama
                from langchain_core.messages import HumanMessage

                llm = ChatOllama(
                    model=OLLAMA_MODEL,
                    temperature=0.3,
                    base_url=OLLAMA_BASE_URL,
                    keep_alive=OLLAMA_KEEP_ALIVE,
                    num_predict=8,
                    num_ctx=OLLAMA_NUM_CTX,
                    num_gpu=OLLAMA_NUM_GPU,
                )
                llm.invoke([HumanMessage(content="Bonjour")])
                logger.info(f"[Ollama] Modèle {OLLAMA_MODEL} préchargé et prêt.")
            except Exception as e:
                logger.info(f"[Ollama] Préchargement impossible (Ollama non lancé ?) : {e}")

        threading.Thread(
            target=preload_ollama,
            daemon=True,
            name="OllamaPreloader",
        ).start()
        logger.info("[Ollama] Thread de préchargement lancé.")