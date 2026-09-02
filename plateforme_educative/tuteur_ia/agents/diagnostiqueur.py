"""
Agent Diagnostiqueur - Analyse initiale du niveau de l'étudiant.
"""
import json
import logging
import time
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from tuteur_ia.graph.state import StudyBuddyState
from tuteur_ia.prompts.diagnostiqueur import (
    DIAGNOSTIC_SYSTEM_PROMPT,
    DIAGNOSTIC_USER_PROMPT_TEMPLATE,
)
from tuteur_ia.agents.llm_factory import get_llm, clip_rag

logger = logging.getLogger(__name__)


def diagnostiqueur_node(state: StudyBuddyState) -> dict[str, Any]:
    """
    Nœud diagnostic : analyse le niveau initial de l'étudiant.
    Produit un JSON avec les questions diagnostiques et les prérequis à vérifier.
    """
    # Récupérer le contenu du PDF lié au chapitre
    rag_content = state.get("rag_context")
    if not rag_content:
        from tuteur_ia.tools.chroma_store import search as chroma_search
        from tuteur_ia.tools.rag_tool import rag_search
        chapitre_id = state["chapitre_id"]
        t0 = time.perf_counter()
        try:
            # Multi-requêtes pour couvrir tout le contenu du PDF
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
            rag_content = "\n\n---\n\n".join(all_texts) if all_texts else rag_search(
                query="contenu principal",
                chapitre_id=chapitre_id,
                n_results=6,
            )
        except Exception as e:
            logger.error(f"Erreur lors de la recherche RAG dans diagnostiqueur: {e}")
            rag_content = ""
        finally:
            logger.info(f"[TIMING] diagnostiqueur RAG search: {time.perf_counter() - t0:.2f}s")

    t0 = time.perf_counter()
    # max_tokens court : la sortie attendue est un petit JSON (2-3 questions
    # courtes) — sans plafond bas, un petit modèle local peut partir en
    # digression et recopier de gros extraits du RAG (observé en test : 17s
    # pour un diagnostic au lieu de ~2s une fois plafonné).
    llm = get_llm(temperature=0.3, max_tokens=150)

    user_prompt = DIAGNOSTIC_USER_PROMPT_TEMPLATE.format(
        etudiant_email=state.get("etudiant_id", "unknown"),
        niveau=state.get("niveau", "DEBUTANT"),
        concept=state["current_concept"],
        concepts_maitrises=", ".join(state["student_profile"].get("mastered_concepts", [])) or "aucun",
        concepts_fragiles=", ".join(state["student_profile"].get("fragile_concepts", [])) or "aucun",
        rag_content=clip_rag(rag_content) or "[Pas de contenu de référence disponible]",
    )

    messages = [
        SystemMessage(content=DIAGNOSTIC_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    response = llm.invoke(messages)
    logger.info(f"[TIMING] diagnostiqueur LLM invoke: {time.perf_counter() - t0:.2f}s")

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
        "next_action": "tutor",
        "rag_context": rag_content,
    }

