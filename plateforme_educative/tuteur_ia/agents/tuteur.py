"""
Agent Tuteur Socratique - Pose des questions sans donner les réponses.
"""
import logging
import time
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from tuteur_ia.graph.state import StudyBuddyState
from tuteur_ia.prompts.tuteur import TUTOR_SYSTEM_PROMPT, TUTOR_USER_PROMPT_TEMPLATE
from tuteur_ia.agents.llm_factory import get_llm, with_language, language_directive, clip_rag

logger = logging.getLogger(__name__)


def _try_rag_enrichment(concept: str, chapitre_id: str) -> str:
    """Multi-requêtes RAG pour couvrir l'ensemble du contenu PDF du chapitre."""
    try:
        from tuteur_ia.tools.chroma_store import search as chroma_search
        from tuteur_ia.tools.rag_tool import rag_search
        queries = [
            "concepts définitions introduction",
            "exemples propriétés caractéristiques",
            "applications pratiques",
        ]
        all_texts = []
        seen = set()
        for q in queries:
            for r in chroma_search(query=q, chapitre_id=chapitre_id, n_results=3):
                t = r.get("text", "").strip()
                if t and t not in seen:
                    seen.add(t)
                    all_texts.append(t)
        if all_texts:
            return "\n\n---\n\n".join(all_texts)
        # Fallback
        return rag_search(concept, chapitre_id=chapitre_id) or ""
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la récupération du contexte RAG pour '{concept}': {e}")
        return ""


def _strip_repeated_prefix(content: str, previous_ai_message: str) -> str:
    """Retire le préfixe si l'IA répète exactement son dernier message."""
    if not previous_ai_message or not content:
        return content
    prev = previous_ai_message.strip()
    curr = content.strip()
    if curr.startswith(prev) and len(curr) > len(prev):
        return curr[len(prev):].strip()
    return content

def tuteur_node(state: StudyBuddyState) -> dict[str, Any]:
    """
    Nœud Tuteur : pose une question socratique pour guider l'étudiant.
    N'utilise jamais la réponse directe — guide par le questionnement.
    """
    # max_tokens court : la consigne (TUTOR_SYSTEM_PROMPT) demande 2 phrases +
    # 1 question max — un plafond bas évite qu'un petit modèle local ne parte
    # en digression (voir diagnostiqueur_node pour le détail du problème observé).
    llm = get_llm(temperature=0.7, max_tokens=250)

    rag_content = state.get("rag_context")
    if not rag_content:
        t0 = time.perf_counter()
        rag_content = _try_rag_enrichment(
            state["current_concept"],
            chapitre_id=state["chapitre_id"],
        )
        logger.info(f"[TIMING] tuteur RAG search: {time.perf_counter() - t0:.2f}s")


    recent_messages = ""
    last_ai_message = ""
    if state.get("messages"):
        for msg in state["messages"][-4:]:
            role = "Étudiant" if getattr(msg, "type", "") == "human" else "Tuteur"
            content = getattr(msg, "content", str(msg))
            recent_messages += f"{role}: {content}\n"
            if role == "Tuteur":
                last_ai_message = content

    user_prompt = TUTOR_USER_PROMPT_TEMPLATE.format(
        etudiant_email=state.get("etudiant_id", "unknown"),
        current_concept=state["current_concept"],
        student_niveau=state.get("niveau", "DEBUTANT"),
        mastery_background=", ".join(state["student_profile"].get("mastered_concepts", [])) or "aucun concept maîtrisé",
        rag_content=clip_rag(rag_content) or "[Pas de contenu de référence disponible]",
        recent_messages=recent_messages or "[Début de la session]",
    )

    # La consigne de langue est répétée à la fin du prompt utilisateur : les
    # petits modèles locaux mirroir la langue de leur dernière entrée (ici un
    # gabarit en français), la consigne système seule ne suffit pas.
    messages = [
        SystemMessage(content=with_language(TUTOR_SYSTEM_PROMPT)),
        HumanMessage(content=f"{user_prompt}\n\n{language_directive()}"),
    ]

    t0 = time.perf_counter()
    response = llm.invoke(messages)
    logger.info(f"[TIMING] tuteur LLM invoke: {time.perf_counter() - t0:.2f}s")
    
    response.content = _strip_repeated_prefix(response.content, last_ai_message)

    return {
        "messages": [response],
        "iteration": state.get("iteration", 0) + 1,
        "next_action": "evaluate",
        "rag_context": rag_content,
    }
