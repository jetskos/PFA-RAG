"""
Fabrique LLM centralisée — un seul endroit pour changer le modèle.
Modèle Groq actif : llama-3.3-70b-versatile (remplace mixtral-8x7b-32768 décommissionné).

Solution hybride hors-ligne : si aucune connexion internet n'est détectée
(ou si aucune clé Groq/OpenAI n'est configurée), on bascule automatiquement
sur un modèle Ollama local (Gemma 4) — utile pour les élèves sans réseau.
"""
import logging
import os
import socket
import time


logger = logging.getLogger(__name__)

# Modèle Groq à jour (avril 2025+)
GROQ_MODEL   = "llama-3.3-70b-versatile"
OPENAI_MODEL = "gpt-4o-mini"
OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", "gemma4:e2b-it-qat")
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


# Cache global des instances LLM
_llm_cache = {}

# Cache de connectivité — évite de re-tester le réseau à chaque appel LLM
_connectivity_cache = {"online": None, "checked_at": 0.0}
CONNECTIVITY_TTL_SECONDS = 30
CONNECTIVITY_TIMEOUT_SECONDS = 2.0


def _has_internet() -> bool:
    """
    Test de connectivité rapide (connexion TCP vers l'API Groq), mis en cache
    quelques secondes pour ne pas ralentir chaque message avec un aller-retour réseau.
    """
    now = time.time()
    if (
        _connectivity_cache["online"] is not None
        and (now - _connectivity_cache["checked_at"]) < CONNECTIVITY_TTL_SECONDS
    ):
        return _connectivity_cache["online"]

    try:
        socket.create_connection(("api.groq.com", 443), timeout=CONNECTIVITY_TIMEOUT_SECONDS).close()
        online = True
    except OSError:
        online = False

    _connectivity_cache["online"] = online
    _connectivity_cache["checked_at"] = now
    return online


def get_llm(temperature: float = 0.7, model_name: str = None):
    """
    Retourne le LLM configuré (avec mise en cache des instances pour préserver les connexions HTTP).
    Priorité : GROQ_API_KEY (si en ligne) → OPENAI_API_KEY (si en ligne) → Ollama local (hors-ligne).

    `model_name` ne s'applique qu'aux fournisseurs Groq/OpenAI — en mode hors-ligne,
    c'est toujours OLLAMA_MODEL qui est utilisé (les noms de modèles Groq n'ont pas
    de sens pour Ollama).
    """
    global _llm_cache
    from django.conf import settings as django_settings

    groq_key   = os.getenv("GROQ_API_KEY", "") or getattr(django_settings, "GROQ_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "") or getattr(django_settings, "OPENAI_API_KEY", "")

    online = (groq_key or openai_key) and _has_internet()

    # Déterminer le fournisseur et le modèle
    if groq_key and online:
        provider = "groq"
        model = model_name if model_name else GROQ_MODEL
    elif openai_key and online:
        provider = "openai"
        model = model_name if model_name else OPENAI_MODEL
    else:
        provider = "ollama"
        model = OLLAMA_MODEL
        if not (groq_key or openai_key):
            logger.info("Aucune clé Groq/OpenAI configurée — utilisation d'Ollama (%s).", model)
        else:
            logger.warning("Pas de connexion internet détectée — repli sur Ollama local (%s).", model)

    # Clé de cache unique pour ce modèle et cette température
    cache_key = (provider, model, temperature)
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    # Instancier et mettre en cache
    if provider == "groq":
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model=model,
            temperature=temperature,
            groq_api_key=groq_key,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=openai_key,
        )
    else:
        from langchain_ollama import ChatOllama
        llm = ChatOllama(
            model=model,
            temperature=temperature,
            base_url=OLLAMA_BASE_URL,
            reasoning=False,  # évite que Gemma 4 ne consomme tout son budget en réflexion cachée
        )

    _llm_cache[cache_key] = llm
    return llm

