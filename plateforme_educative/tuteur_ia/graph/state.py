"""
État LangGraph pour le système tuteur IA Study Buddy.
Adapté pour PFA-RAG avec chapitre_id et cours_id pour le RAG Django.
"""

from typing import TypedDict, Annotated, Literal, Optional
from langgraph.graph.message import add_messages


class StudentProfile(TypedDict):
    """Profil de l'étudiant avec informations pédagogiques."""
    mastered_concepts: list[str]
    fragile_concepts: list[str]
    common_errors: list[str]
    preferred_style: str


class StudyBuddyState(TypedDict):
    """État global pour le workflow LangGraph du tuteur IA."""
    messages: Annotated[list, add_messages]  # Historique des messages (HumanMessage + AIMessage)
    subject: str                             # Titre du cours
    current_concept: str                     # Titre du chapitre
    chapitre_id: str                         # UUID du chapitre (pour le RAG Django)
    cours_id: str                            # UUID du cours (pour le RAG Django)
    etudiant_id: str                         # UUID de l'étudiant (pour ProfilEtudiantIA)
    niveau: str                              # Niveau de l'étudiant (DEBUTANT, INTERMEDIAIRE, AVANCE)
    diagnosis: Optional[dict]                # Résultat du diagnostic initial
    last_evaluation: Optional[dict]          # Dernier résultat d'évaluation
    mastery_score: float                     # Score de maîtrise (0.0 - 1.0)
    iteration: int                           # Nombre d'itérations tutor-evaluate
    student_profile: StudentProfile          # Profil long-terme
    next_action: Literal["tutor", "evaluate", "memory", "end"]  # Action suivante
