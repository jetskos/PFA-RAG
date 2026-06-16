"""
Agent Diagnostiqueur - Analyse initiale du niveau de l'étudiant.
"""
import json
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from tuteur_ia.graph.state import StudyBuddyState
from tuteur_ia.prompts.diagnostiqueur import (
    DIAGNOSTIC_SYSTEM_PROMPT,
    DIAGNOSTIC_USER_PROMPT_TEMPLATE,
)
from tuteur_ia.agents.llm_factory import get_llm


def diagnostiqueur_node(state: StudyBuddyState) -> dict[str, Any]:
    """
    Nœud diagnostic : analyse le niveau initial de l'étudiant.
    Produit un JSON avec les questions diagnostiques et les prérequis à vérifier.
    """
    llm = get_llm(temperature=0.3)

    user_prompt = DIAGNOSTIC_USER_PROMPT_TEMPLATE.format(
        etudiant_email=state.get("etudiant_id", "unknown"),
        niveau=state.get("niveau", "DEBUTANT"),
        concept=state["current_concept"],
        concepts_maitrises=", ".join(state["student_profile"].get("mastered_concepts", [])) or "aucun",
        concepts_fragiles=", ".join(state["student_profile"].get("fragile_concepts", [])) or "aucun",
    )

    messages = [
        SystemMessage(content=DIAGNOSTIC_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)

    diagnosis = {}
    try:
        content = response.content.strip()
        start_idx = content.find('{')
        end_idx = content.rfind('}') + 1
        if start_idx != -1 and end_idx > start_idx:
            diagnosis = json.loads(content[start_idx:end_idx])
    except (json.JSONDecodeError, ValueError):
        diagnosis = {
            "assessment": "Diagnostic initial en attente",
            "questions": [f"Qu'est-ce que vous savez déjà sur {state['current_concept']} ?"],
            "prerequisites_to_check": [],
            "confidence": 0.5,
        }

    return {
        "diagnosis": diagnosis,
        "mastery_score": 0.0,
        "iteration": 0,
        "messages": messages + [response],
        "next_action": "tutor",
    }
