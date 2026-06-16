"""
Agent Tuteur Socratique - Pose des questions sans donner les réponses.
"""
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from tuteur_ia.graph.state import StudyBuddyState
from tuteur_ia.prompts.tuteur import TUTOR_SYSTEM_PROMPT, TUTOR_USER_PROMPT_TEMPLATE
from tuteur_ia.tools.rag_tool import rag_search
from tuteur_ia.agents.llm_factory import get_llm


def _try_rag_enrichment(concept: str, chapitre_id: str) -> str:
    try:
        content = rag_search(concept, chapitre_id=chapitre_id)
        return content if content else ""
    except Exception:
        return ""


def tuteur_node(state: StudyBuddyState) -> dict[str, Any]:
    """
    Nœud Tuteur : pose une question socratique pour guider l'étudiant.
    N'utilise jamais la réponse directe — guide par le questionnement.
    """
    llm = get_llm(temperature=0.7)

    rag_content = _try_rag_enrichment(
        state["current_concept"],
        chapitre_id=state["chapitre_id"],
    )

    recent_messages = ""
    if state.get("messages"):
        for msg in state["messages"][-4:]:
            role = "Étudiant" if getattr(msg, "type", "") == "human" else "Tuteur"
            content = getattr(msg, "content", str(msg))
            recent_messages += f"{role}: {content}\n"

    user_prompt = TUTOR_USER_PROMPT_TEMPLATE.format(
        etudiant_email=state.get("etudiant_id", "unknown"),
        current_concept=state["current_concept"],
        student_niveau=state.get("niveau", "DEBUTANT"),
        mastery_background=", ".join(state["student_profile"].get("mastered_concepts", [])) or "aucun concept maîtrisé",
        rag_content=rag_content or "[Pas de contenu de référence disponible]",
        recent_messages=recent_messages or "[Début de la session]",
    )

    messages = [
        SystemMessage(content=TUTOR_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)

    return {
        "messages": messages + [response],
        "iteration": state.get("iteration", 0) + 1,
        "next_action": "evaluate",
    }
