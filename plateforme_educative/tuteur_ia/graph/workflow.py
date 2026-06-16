"""
Workflow LangGraph - Orchestration des 4 agents pédagogiques.

CORRECTION : limite d'itérations passée de 5 à 15 pour permettre
12-15 questions par session comme requis.
"""

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from tuteur_ia.graph.state import StudyBuddyState
from tuteur_ia.agents.diagnostiqueur import diagnostiqueur_node
from tuteur_ia.agents.tuteur import tuteur_node
from tuteur_ia.agents.evaluateur import evaluateur_node
from tuteur_ia.agents.memoire import memoire_node

# Limite maximale d'itérations (questions) par session
MAX_ITERATIONS = 15


def route_after_evaluate(state: StudyBuddyState) -> str:
    """
    Route après évaluation :
    - mastery_score >= 0.75  → memory (maîtrisé)
    - iteration >= 15        → memory (limite atteinte)
    - sinon                  → tutor (continuer)
    """
    if state["mastery_score"] >= 0.75:
        return "memory"
    if state.get("iteration", 0) >= MAX_ITERATIONS:
        return "memory"
    return "tutor"


def route_after_memory(state: StudyBuddyState) -> str:
    if state.get("next_action") == "end":
        return END
    return "tutor"


# Singleton
_graph_instance = None


def get_graph():
    global _graph_instance

    if _graph_instance is None:
        workflow = StateGraph(StudyBuddyState)

        workflow.add_node("diagnose", diagnostiqueur_node)
        workflow.add_node("tutor",    tuteur_node)
        workflow.add_node("evaluate", evaluateur_node)
        workflow.add_node("memory",   memoire_node)

        workflow.add_edge(START, "diagnose")
        workflow.add_edge("diagnose", "tutor")
        workflow.add_edge("tutor", "evaluate")

        workflow.add_conditional_edges(
            "evaluate",
            route_after_evaluate,
            {"tutor": "tutor", "memory": "memory"},
        )
        workflow.add_conditional_edges(
            "memory",
            route_after_memory,
            {"tutor": "tutor", END: END},
        )

        checkpointer    = MemorySaver()
        _graph_instance = workflow.compile(
            checkpointer=checkpointer,
            interrupt_after=["tutor"],
        )

    return _graph_instance
