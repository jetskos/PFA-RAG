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


logger = logging.getLogger(__name__)

# Modèle Groq à jour (avril 2025+)
GROQ_MODEL   = "openai/gpt-oss-20b"
OPENAI_MODEL = "gpt-4o-mini"
OLLAMA_MODEL     = os.getenv("OLLAMA_MODEL", os.getenv("LOCAL_LLM_MODEL", "qwen2.5:1.5b-instruct"))
OLLAMA_BASE_URL  = os.getenv("OLLAMA_BASE_URL", os.getenv("LOCAL_LLM_URL", "http://localhost:11434"))
# Garde le modèle chargé en RAM en continu : évite les 10-20s de rechargement
# qu'Ollama impose par défaut après 5 min d'inactivité entre deux messages.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
# Plafonne la longueur de génération (au lieu de laisser le moteur local tourner
# sans limite jusqu'à la fenêtre de contexte). 1024 tokens laisse assez de marge
# pour le cas le plus long — les 8 questions QCM en JSON (views_qcm.py, ~900
# tokens, qui passe de toute façon un max_tokens explicite) — tout en bornant un
# tuteur/assistant/évaluateur qui partirait en digression : sur CPU chaque token
# superflu coûte ~50-100 ms.
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "1024"))
# Fenêtre de contexte : RAG + prompt système + historique. 4096 suffit sur CPU
# (au-delà, les buffers de calcul grossissent pour rien).
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
# Longueur max d'un contexte RAG injecté dans un prompt agent. Les nœuds
# socratiques concatènent jusqu'à ~9 chunks (4-5k car.) : au-delà de cette borne
# le prefill CPU explose sans gain pédagogique. ~1800 car. ≈ 500 tokens.
RAG_MAX_CHARS = int(os.getenv("RAG_MAX_CHARS", "1800"))
# Délai max d'UN appel au moteur local. Une génération QCM légitime sur CPU
# peut prendre ~40-60 s ; au-delà de OLLAMA_TIMEOUT le modèle est considéré
# bloqué et l'appel est abandonné (au lieu de figer le worker web à l'infini).
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "90"))
# Laisse Ollama auto-détecter GPU/CPU par défaut (ne pas fixer num_gpu).
# Testé sur machine de dev : forcer le CPU (num_gpu=0) s'est avéré NETTEMENT
# plus lent et instable (17-32s/appel) que l'auto-détection GPU (1,5-1,9s
# stable) — contre-intuitif, mais mesuré. Sur un serveur cible sans GPU
# (ex. Intel N100/RPi4 du cahier des charges), ça n'a aucun effet puisqu'il
# n'y a pas de GPU à détecter. Positionner OLLAMA_NUM_GPU=0 explicitement
# pour forcer le CPU si un test sur le matériel cible réel montre l'inverse.
_ollama_num_gpu_env = os.getenv("OLLAMA_NUM_GPU")
OLLAMA_NUM_GPU = int(_ollama_num_gpu_env) if _ollama_num_gpu_env is not None else None


# Cache global des instances LLM
_llm_cache = {}

def _has_internet() -> bool:
    """Groq est-il joignable ? (TCP vers api.groq.com:443, mis en cache).

    Réutilise l'implémentation partagée `core.utils.has_internet` — même
    mécanisme de test + cache, mais pointé sur l'endpoint LLM."""
    from core.utils import has_internet
    return has_internet(host="api.groq.com", port=443, timeout=2.0, ttl=30.0)


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

    groq_key   = os.getenv("GROQ_API_KEY", "") or getattr(django_settings, "GROQ_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "") or getattr(django_settings, "OPENAI_API_KEY", "")
    
    force_offline = False
    force_provider = 'AUTO'
    try:
        from accounts.models import ConfigurationSysteme
        config = ConfigurationSysteme.objects.first()
        if config:
            force_offline = config.mode_hors_ligne
            force_provider = getattr(config, 'llm_provider', 'AUTO')
    except Exception:
        pass

    online = (groq_key or openai_key) and _has_internet() and not force_offline

    # Déterminer le fournisseur et le modèle
    if force_provider == 'OLLAMA' or (force_offline):
        provider = "ollama"
        model = OLLAMA_MODEL
    elif force_provider == 'GROQ' and groq_key and online:
        provider = "groq"
        model = model_name if model_name else GROQ_MODEL
    elif groq_key and online:
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
        from langchain_openai import ChatOpenAI
        
        # S'assurer que l'URL se termine par /v1 pour la compatibilité OpenAI (Ollama et llama-server)
        base_url = OLLAMA_BASE_URL
        if not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
            
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key="sk-no-key-required", # Ni Ollama ni llama-server ne requièrent de clé
            base_url=base_url,
            max_retries=1,
            timeout=OLLAMA_TIMEOUT,       # borne l'appel — un llama.cpp bloqué ne fige plus le worker
            max_tokens=max_tokens if max_tokens is not None else OLLAMA_NUM_PREDICT,
        )

    _llm_cache[cache_key] = llm
    return llm


# ── Localisation des réponses IA ────────────────────────────────────────────

_LANGUAGE_DIRECTIVES = {
    'fr': "IMPORTANT : réponds toujours en français, quelle que soit la langue de la question.",
    'en': "IMPORTANT: always answer in English, regardless of the language of the question.",
    'ar': "مهم: أجب دائمًا باللغة العربية بغض النظر عن لغة السؤال.",
}


def language_directive() -> str:
    """Consigne de langue à ajouter aux prompts système, selon la langue active de l'UI."""
    try:
        from django.utils.translation import get_language
        lang = (get_language() or 'fr').split('-')[0]
    except Exception:
        lang = 'fr'
    return _LANGUAGE_DIRECTIVES.get(lang, _LANGUAGE_DIRECTIVES['fr'])


def with_language(system_prompt: str) -> str:
    """Ajoute la consigne de langue active à un prompt système."""
    return f"{system_prompt}\n\n{language_directive()}"


def clip_rag(text: str) -> str:
    """Tronque un contexte RAG à RAG_MAX_CHARS — borne le coût de prefill CPU.

    Les agents socratiques concatènent plusieurs chunks sans limite ; un prompt
    trop long ralentit chaque appel (temps ∝ tokens) sans bénéfice pédagogique.
    """
    text = text or ""
    if len(text) <= RAG_MAX_CHARS:
        return text
    return text[:RAG_MAX_CHARS].rstrip() + "\n[...]"


# ── Détection « moteur LLM injoignable » ────────────────────────────────────

def is_llm_unavailable_error(exc: BaseException) -> bool:
    """True si l'exception vient d'un LLM injoignable (ni API en ligne, ni Ollama local)."""
    text = f"{type(exc).__name__}: {exc}".lower()
    needles = (
        "connection error", "connection refused", "connexion refus",
        "failed to establish a new connection", "max retries exceeded",
        "timed out", "timeout", "getaddrinfo failed", "name or service not known",
        "nameresolutionerror", "newconnectionerror", "apiconnectionerror",
        "connecterror", "[errno 111]", "[winerror 10061]", "no llm", "aucun llm",
    )
    return any(n in text for n in needles)

