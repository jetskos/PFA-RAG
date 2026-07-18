"""
Fabrique LLM centralisée — un seul endroit pour changer le modèle.
Modèle Groq actif : llama-3.3-70b-versatile (remplace mixtral-8x7b-32768 décommissionné).
"""
import os


# Modèle Groq à jour (avril 2025+)
GROQ_MODEL   = "llama-3.3-70b-versatile"
OPENAI_MODEL = "gpt-4o-mini"


# Cache global des instances LLM
_llm_cache = {}


def get_llm(temperature: float = 0.7, model_name: str = None):
    """
    Retourne le LLM configuré (avec mise en cache des instances pour préserver les connexions HTTP).
    Priorité : USE_LOCAL_LLM → GROQ_API_KEY → OPENAI_API_KEY → erreur.
    """
    global _llm_cache
    from django.conf import settings as django_settings

    groq_key   = os.getenv("GROQ_API_KEY", "") or getattr(django_settings, "GROQ_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "") or getattr(django_settings, "OPENAI_API_KEY", "")
    use_local  = str(os.getenv("USE_LOCAL_LLM", "")).lower() in ["1", "true", "yes"]

    # Déterminer le fournisseur et le modèle
    if use_local:
        provider = "local"
        model = model_name if model_name else "gemma-4-E4B-it"
    elif groq_key:
        provider = "groq"
        model = model_name if model_name else GROQ_MODEL
    elif openai_key:
        provider = "openai"
        model = model_name if model_name else OPENAI_MODEL
    else:
        raise EnvironmentError(
            "Aucun LLM configuré. Définissez USE_LOCAL_LLM, GROQ_API_KEY, ou OPENAI_API_KEY dans .env"
        )

    # Clé de cache unique pour ce modèle et cette température
    cache_key = (provider, model, temperature)
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    # Instancier et mettre en cache
    if provider == "local":
        from langchain_openai import ChatOpenAI
        local_url = os.getenv("LOCAL_LLM_URL", "http://172.17.0.1:8181/v1")
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key="sk-local-no-key",
            base_url=local_url,
            max_tokens=2048
        )
    elif provider == "groq":
        from langchain_groq import ChatGroq
        llm = ChatGroq(
            model=model,
            temperature=temperature,
            groq_api_key=groq_key,
        )
    else:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            api_key=openai_key,
        )

    _llm_cache[cache_key] = llm
    return llm

