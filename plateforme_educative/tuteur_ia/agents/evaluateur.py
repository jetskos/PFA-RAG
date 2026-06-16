"""
Agent Évaluateur - Évalue la compréhension et calcule le score de maîtrise.
"""
import json
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from tuteur_ia.graph.state import StudyBuddyState
from tuteur_ia.prompts.evaluateur import EVALUATOR_SYSTEM_PROMPT, EVALUATOR_USER_PROMPT_TEMPLATE
from tuteur_ia.tools.rag_tool import rag_search
from tuteur_ia.agents.llm_factory import get_llm


def evaluateur_node(state: StudyBuddyState) -> dict[str, Any]:
    """
    Nœud Évaluateur : évalue la dernière réponse de l'étudiant.
    Calcule le mastery_score (0.0–1.0) et produit du feedback.
    """
    llm = get_llm(temperature=0.2)

    student_response = ""
    last_question = ""
    if state.get("messages"):
        for msg in reversed(state["messages"]):
            t = getattr(msg, "type", "")
            if t == "human" and not student_response:
                student_response = msg.content
            elif t == "ai" and not last_question:
                last_question = msg.content
            if student_response and last_question:
                break

    rag_content = ""
    try:
        rag_content = rag_search(state["current_concept"], chapitre_id=state["chapitre_id"])
    except Exception:
        pass

    user_prompt = EVALUATOR_USER_PROMPT_TEMPLATE.format(
        current_concept=state["current_concept"],
        student_niveau=state.get("niveau", "DEBUTANT"),
        last_question=last_question or "[Question non disponible]",
        student_response=student_response or "[Pas de réponse]",
        rag_content=rag_content or "[Pas de contenu de référence]",
    )

    messages = [
        SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)

    last_evaluation = {}
    mastery_score = state.get("mastery_score", 0.0)

    try:
        content = response.content.strip()
        start_idx = content.find('{')
        end_idx = content.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            last_evaluation = json.loads(content[start_idx:end_idx])
            mastery_score = float(last_evaluation.get("mastery_score", mastery_score))
            mastery_score = max(0.0, min(1.0, mastery_score))
    except (json.JSONDecodeError, ValueError):
        last_evaluation = {
            "understanding": "Évaluation en attente",
            "specific_confusion": None,
            "mastery_score": mastery_score,
            "next_micro_objective": state["current_concept"],
            "should_advance": mastery_score >= 0.75,
            "feedback_type": "neutral",
        }

    next_action = "memory" if mastery_score >= 0.75 or state.get("iteration", 0) >= 5 else "tutor"

    return {
        "last_evaluation": last_evaluation,
        "mastery_score": mastery_score,
        "messages": messages + [response],
        "next_action": next_action,
    }
