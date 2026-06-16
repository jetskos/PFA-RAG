"""
Vues Django — Tuteur IA (chatbot socratique).
- 12 à 15 questions par session
- Feedback selon mastery_score : < 0.75 → réviser, >= 0.75 → félicitations + QCM
"""
import json
import uuid as uuid_module
import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from langchain_core.messages import HumanMessage

from tuteur_ia.models import ProfilEtudiantIA, SessionTuteur
from tuteur_ia.graph.workflow import get_graph

logger = logging.getLogger(__name__)

# Nb de questions min/max par session
MIN_QUESTIONS = 12
MAX_QUESTIONS = 15


def _get_last_ai_message(messages: list) -> str:
    for msg in reversed(messages):
        t = getattr(msg, 'type', None) or type(msg).__name__.lower()
        if t in ('ai', 'aimessage'):
            return msg.content
    return ""


@login_required
@require_http_methods(['GET', 'POST'])
def demarrer_session(request, chapitre_id):
    """
    GET  → page HTML de la session
    POST → initialise le graph et retourne la première question (JSON)
    """
    from apprentissage.models import Chapitre
    chapitre = get_object_or_404(Chapitre, id=chapitre_id, actif=True)
    cours    = chapitre.cours

    if request.method == 'GET':
        session_existante = SessionTuteur.objects.filter(
            etudiant=request.user, chapitre=chapitre, statut='EN_COURS'
        ).first()
        return render(request, 'tuteur_ia/session.html', {
            'chapitre': chapitre,
            'cours':    cours,
            'session_existante': session_existante,
        })

    # POST — démarrer
    try:
        profil_ia, _ = ProfilEtudiantIA.objects.get_or_create(etudiant=request.user)
        thread_id    = f"{str(request.user.id)[:8]}_{str(chapitre_id)[:8]}_{uuid_module.uuid4().hex[:8]}"

        session = SessionTuteur.objects.create(
            etudiant=request.user,
            chapitre=chapitre,
            thread_id=thread_id,
        )

        # Normaliser le niveau de l'étudiant
        niveau_label = getattr(request.user, 'niveau_label', '').upper()
        if 'DÉBUTANT' in niveau_label or 'DEBUTANT' in niveau_label:
            niveau = 'DEBUTANT'
        elif 'INTERMÉDIAIRE' in niveau_label or 'INTERMEDIAIRE' in niveau_label:
            niveau = 'INTERMEDIAIRE'
        elif 'AVANCÉ' in niveau_label or 'AVANCE' in niveau_label:
            niveau = 'AVANCE'
        else:
            niveau = 'DEBUTANT'  # Défaut

        graph = get_graph()
        initial_state = {
            "messages":       [],
            "subject":        cours.titre,
            "current_concept": chapitre.titre,
            "chapitre_id":    str(chapitre.id),
            "cours_id":       str(cours.id),
            "etudiant_id":    str(request.user.id),
            "niveau":         niveau,
            "diagnosis":      None,
            "last_evaluation": None,
            "mastery_score":  0.0,
            "iteration":      0,
            "student_profile": profil_ia.to_dict(),
            "next_action":    "tutor",
        }

        config = {"configurable": {"thread_id": session.thread_id}}
        final_state = None
        for event in graph.stream(initial_state, config, stream_mode="values"):
            final_state = event

        first_msg = _get_last_ai_message(final_state.get("messages", [])) if final_state else ""

        return JsonResponse({
            "session_id":   str(session.id),
            "message":      first_msg or "Bonjour ! Commençons cette session de tutorat.",
            "mastery_score": final_state.get("mastery_score", 0.0) if final_state else 0.0,
            "iteration":    final_state.get("iteration", 0) if final_state else 0,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(['POST'])
def repondre(request, session_id):
    """
    POST {'message': '...'} → inject réponse étudiant, retourne question suivante.
    Stoppe quand mastery_score >= 0.75 OU iteration >= MAX_QUESTIONS.
    """
    session = get_object_or_404(SessionTuteur, id=session_id, etudiant=request.user)

    if session.statut != 'EN_COURS':
        return JsonResponse({"error": "Session déjà terminée."}, status=400)

    try:
        data    = json.loads(request.body)
        message = data.get('message', '').strip()
    except json.JSONDecodeError:
        message = request.POST.get('message', '').strip()

    if not message:
        return JsonResponse({"error": "Message vide."}, status=400)

    try:
        graph  = get_graph()
        config = {"configurable": {"thread_id": session.thread_id}}

        graph.update_state(
            config,
            {"messages": [HumanMessage(content=message)]},
            as_node="tutor",
        )

        final_state = None
        for event in graph.stream(None, config, stream_mode="values"):
            final_state = event

        tutor_response = ""
        mastery_score  = 0.0
        iteration      = 0
        next_action    = "tutor"

        if final_state:
            tutor_response = _get_last_ai_message(final_state.get("messages", []))
            mastery_score  = final_state.get("mastery_score", 0.0)
            iteration      = final_state.get("iteration", 0)
            next_action    = final_state.get("next_action", "tutor")

        # Terminer la session si score atteint ou nb max de questions
        session_terminee = (
            mastery_score >= 0.75 or
            iteration >= MAX_QUESTIONS or
            next_action == "end"
        )

        session.mastery_score_final = mastery_score
        if session_terminee:
            session.statut = 'TERMINEE'
        session.save()

        return JsonResponse({
            "message":          tutor_response or "Merci pour votre réponse !",
            "mastery_score":    mastery_score,
            "iteration":        iteration,
            "session_terminee": session_terminee,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def statut_session(request, session_id):
    session = get_object_or_404(SessionTuteur, id=session_id, etudiant=request.user)

    try:
        graph  = get_graph()
        config = {"configurable": {"thread_id": session.thread_id}}
        state  = graph.get_state(config)
        values = state.values if state else {}
        mastery_score = values.get("mastery_score", session.mastery_score_final or 0.0)
        iteration     = values.get("iteration", 0)
    except Exception:
        mastery_score = session.mastery_score_final or 0.0
        iteration     = 0

    return JsonResponse({
        "session_id":      str(session.id),
        "statut":          session.statut,
        "mastery_score":   mastery_score,
        "iteration":       iteration,
        "session_terminee": session.statut == 'TERMINEE',
        "chapitre":        session.chapitre.titre,
        "cours":           session.chapitre.cours.titre,
    })

@login_required
def profil_etudiant_ia(request):
    profil, _ = ProfilEtudiantIA.objects.get_or_create(etudiant=request.user)
    return render(request, 'tuteur_ia/profil.html', {
        'profil': profil,
    })
