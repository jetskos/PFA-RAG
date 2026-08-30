"""
Agent Mémoire — Mise à jour du profil long-terme de l'étudiant.

CORRECTION : le JSON de mise à jour du profil n'est JAMAIS ajouté aux messages
affichés à l'étudiant. Seul un message propre de félicitations/encouragement
est retourné selon le score de maîtrise.
"""

import json
import logging
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from tuteur_ia.graph.state import StudyBuddyState
from tuteur_ia.prompts.memoire import (
    MEMORY_SYSTEM_PROMPT,
    MEMORY_USER_PROMPT_TEMPLATE,
)
from tuteur_ia.agents.llm_factory import get_llm, with_language

logger = logging.getLogger(__name__)


def _save_profile_django(etudiant_id: str, new_profile: dict):
    """Sauvegarde le profil dans ProfilEtudiantIA (import tardif Django)."""
    try:
        from tuteur_ia.models import ProfilEtudiantIA
        profil, _ = ProfilEtudiantIA.objects.get_or_create(etudiant_id=etudiant_id)
        profil.update_from_dict(new_profile)
        logger.info(f"Profil IA sauvegardé pour etudiant {etudiant_id}")
    except Exception as e:
        logger.error(f"Erreur sauvegarde profil IA : {e}")


def _message_fin(mastery_score: float, current_concept: str) -> str:
    """
    Retourne un message propre de fin de session selon le score.
    Ce message remplace le JSON brut dans le chat.
    """
    pct = int(mastery_score * 100)

    if mastery_score >= 0.75:
        return (
            f"Félicitations ! Tu as obtenu **{pct}%** de maîtrise "
            f"sur le chapitre *{current_concept}*.\n\n"
            f"Tu maîtrises bien ce chapitre ! Clique sur **Faire le QCM** "
            f"pour tester tes connaissances."
        )
    else:
        return (
            f"Session terminée avec un score de **{pct}%** "
            f"sur *{current_concept}*.\n\n"
            f"Tu n'as pas encore atteint 75%. "
            f"Relis le chapitre et recommence la session pour progresser !"
        )


def memoire_node(state: StudyBuddyState) -> dict[str, Any]:
    """
    Noeud Mémoire : met à jour le profil long-terme de l'étudiant.

    - Appelle le LLM pour calculer le nouveau profil (JSON interne uniquement)
    - Sauvegarde dans ProfilEtudiantIA (Django/MySQL)
    - Retourne un message PROPRE à l'étudiant (jamais le JSON brut)
    """
    llm = get_llm(temperature=0.3)

    last_eval = state.get("last_evaluation", {})
    mastery   = state.get("mastery_score", 0.0)
    concept   = state["current_concept"]

    user_prompt = MEMORY_USER_PROMPT_TEMPLATE.format(
        etudiant_email=state.get("etudiant_id", "unknown"),
        mastered_concepts=", ".join(state["student_profile"].get("mastered_concepts", [])) or "aucun",
        fragile_concepts=", ".join(state["student_profile"].get("fragile_concepts",  [])) or "aucun",
        common_errors=", ".join(state["student_profile"].get("common_errors",     [])) or "aucune",
        preferred_style=state["student_profile"].get("preferred_style", "textuel"),
        current_concept=concept,
        mastery_score=mastery,
        feedback_type=last_eval.get("feedback_type", "neutral"),
        specific_confusion=last_eval.get("specific_confusion") or "aucune",
    )

    # Appel LLM — usage interne uniquement, jamais affiché à l'étudiant
    new_profile = state["student_profile"].copy()
    try:
        response = llm.invoke([
            SystemMessage(content=with_language(MEMORY_SYSTEM_PROMPT)),
            HumanMessage(content=user_prompt),
        ])

        content = response.content.strip()
        start   = content.find('{')
        end     = content.rfind('}') + 1

        if start != -1 and end > start:
            parsed = json.loads(content[start:end])
            new_profile = {
                "mastered_concepts": parsed.get("mastered_concepts", new_profile.get("mastered_concepts", [])),
                "fragile_concepts":  parsed.get("fragile_concepts",  new_profile.get("fragile_concepts",  [])),
                "common_errors":     parsed.get("common_errors",     new_profile.get("common_errors",     [])),
                "preferred_style":   parsed.get("preferred_style",   new_profile.get("preferred_style",   "textuel")),
            }

    except Exception as e:
        logger.error(f"Erreur agent mémoire LLM : {e}", exc_info=True)

    # Sauvegarder dans Django (ProfilEtudiantIA)
    _save_profile_django(state["etudiant_id"], new_profile)

    # Action suivante
    next_action = "end" if (
        mastery >= 0.75 or state.get("iteration", 0) >= 15
    ) else "tutor"

    # IMPORTANT : message propre affiché à l'étudiant — PAS le JSON brut
    message_propre = _message_fin(mastery, concept)

    return {
        "student_profile": new_profile,
        "next_action":     next_action,
        "messages":        [AIMessage(content=message_propre)],
    }
