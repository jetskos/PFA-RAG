"""
Fabrique LLM centralisée — un seul endroit pour changer le modèle.
Modèle Groq actif : llama-3.3-70b-versatile (remplace mixtral-8x7b-32768 décommissionné).

Solution hybride hors-ligne : si aucune connexion internet n'est détectée
(ou si aucune clé Groq/OpenAI n'est configurée), on bascule automatiquement
sur un modèle Ollama local (Qwen2.5 1.5B Instruct) — utile pour les élèves
sans réseau. Choisi pour sa rapidité sur CPU (~2-4s/appel) et sa fiabilité
à produire du JSON structuré (requis par diagnostiqueur/évaluateur).
"""
import logging
import os
import socket
import time


logger = logging.getLogger(__name__)

# Modèle Groq à jour (avril 2025+)
GROQ_MODEL   = "llama-3.3-70b-versatile"
OPENAI_MODEL = "gpt-4o-mini"
LLAMACPP_MODEL     = os.getenv("LLAMACPP_MODEL", "qwen2.5:1.5b-instruct")
# Llama-server est déjà lancé sur le port 8181 de la station
LLAMACPP_BASE_URL  = os.getenv("LLAMACPP_BASE_URL", "http://172.17.0.1:8181/v1")

# Plafonne la longueur de génération (au lieu de laisser le modèle tourner sans
# limite jusqu'à la fenêtre de contexte). 1024 tokens laisse assez de marge
# pour le cas le plus long — les 8 questions QCM en JSON (views_qcm.py,
# ~900 tokens) — tout en bornant un tuteur/évaluateur qui partirait en boucle.
LLAMACPP_NUM_PREDICT = int(os.getenv("LLAMACPP_NUM_PREDICT", "512"))



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


def get_llm(temperature: float = 0.7, model_name: str = None, max_tokens: int = None):
    """
    Retourne le LLM configuré (avec mise en cache des instances pour préserver les connexions HTTP).
    Priorité : GROQ_API_KEY (si en ligne) → OPENAI_API_KEY (si en ligne) → Ollama local (hors-ligne).

    `model_name` ne s'applique qu'aux fournisseurs Groq/OpenAI — en mode hors-ligne,
    c'est toujours OLLAMA_MODEL qui est utilisé (les noms de modèles Groq n'ont pas
    de sens pour Ollama).

    `max_tokens` plafonne la longueur de génération pour CET appel (sinon
    OLLAMA_NUM_PREDICT par défaut, dimensionné pour le pire cas — le QCM 8
    questions). À fixer bas (~250-300) pour tuteur/diagnostic/évaluateur qui
    doivent rester courts par consigne : un petit modèle local peut parfois
    ignorer cette consigne et partir en digression, ce qui coûte cher en
    temps de génération hors-ligne si rien ne le plafonne.
    """
    global _llm_cache
    from django.conf import settings as django_settings
    from accounts.models import ConfigurationSysteme
    
    config = ConfigurationSysteme.get_config()

    groq_key   = os.getenv("GROQ_API_KEY", "") or getattr(django_settings, "GROQ_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "") or getattr(django_settings, "OPENAI_API_KEY", "")

    # Forcer la connexion sur False si mode_hors_ligne est activé manuellement
    online = False if config.mode_hors_ligne else ((groq_key or openai_key) and _has_internet())

    # Déterminer le fournisseur et le modèle selon la configuration
    if config.llm_provider == 'OLLAMA' or not online:
        provider = "llamacpp"
        model = LLAMACPP_MODEL
        if config.llm_provider == 'OLLAMA':
            logger.info("Llama.cpp forcé par la Configuration Système (remplace Ollama).")
        elif not online:
            logger.warning("Pas de connexion internet (ou mode hors-ligne activé) — repli sur Llama.cpp local (%s).", model)
    elif config.llm_provider == 'GROQ' and groq_key:
        provider = "groq"
        model = model_name if model_name else GROQ_MODEL
    elif config.llm_provider == 'OPENAI' and openai_key:
        provider = "openai"
        model = model_name if model_name else OPENAI_MODEL
    else:
        # AUTO (ou provider choisi indisponible faute de clé)
        if groq_key:
            provider = "groq"
            model = model_name if model_name else GROQ_MODEL
        elif openai_key:
            provider = "openai"
            model = model_name if model_name else OPENAI_MODEL
        else:
            provider = "llamacpp"
            model = LLAMACPP_MODEL

    # Clé de cache unique pour ce modèle, cette température et ce plafond de tokens
    cache_key = (provider, model, temperature, max_tokens)
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    # Instancier et mettre en cache
    if provider == "groq":
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model=model,
            temperature=temperature,
            groq_api_key=groq_key,
            # Sans timeout, un WiFi qui tombe pendant une session peut bloquer
            # l'appel très longtemps au lieu de basculer vite vers Ollama.
            timeout=8.0,
            max_retries=1,
            max_tokens=max_tokens,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=openai_key,
            timeout=8.0,
            max_retries=1,
            max_tokens=max_tokens,
        )
    else:
        # Mode LLAMACPP (utilise l'API compatible OpenAI de llama-server)
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key="sk-no-key-required", # Llama.cpp ne requiert pas de clé
            base_url=LLAMACPP_BASE_URL,
            max_retries=1,
            max_tokens=max_tokens if max_tokens is not None else LLAMACPP_NUM_PREDICT,
        )

    _llm_cache[cache_key] = llm
    return llm

