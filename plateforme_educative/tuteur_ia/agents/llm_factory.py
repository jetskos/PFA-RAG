"""
Fabrique LLM centralisée — un seul endroit pour changer le modèle.
Modèle Groq actif : llama-3.3-70b-versatile (remplace mixtral-8x7b-32768 décommissionné).
"""
import os


# Modèle Groq à jour (avril 2025+)
GROQ_MODEL   = "llama-3.3-70b-versatile"
OPENAI_MODEL = "gpt-4o-mini"


def get_llm(temperature: float = 0.7):
    """
    Retourne le LLM configuré.
    Priorité : GROQ_API_KEY → OPENAI_API_KEY → erreur.
    """
    groq_key   = os.getenv("GROQ_API_KEY", "")
    openai_key = os.getenv("OPENAI_API_KEY", "")

    if groq_key:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=GROQ_MODEL,
            temperature=temperature,
            groq_api_key=groq_key,
        )

    if openai_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=OPENAI_MODEL,
            temperature=temperature,
            api_key=openai_key,
        )

    raise EnvironmentError(
        "Aucun LLM configuré. Définissez GROQ_API_KEY ou OPENAI_API_KEY dans .env"
    )
