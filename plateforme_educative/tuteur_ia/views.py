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
from django.http import JsonResponse, StreamingHttpResponse
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
    POST → crée la session INSTANTANÉMENT et retourne un message d'accueil.
            Le graph LangGraph (RAG + LLM) ne démarre qu'au premier vrai
            message de l'étudiant, dans la vue `repondre`.
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

    # POST — créer la session sans appeler le LLM
    try:
        thread_id = f"{str(request.user.id)[:8]}_{str(chapitre_id)[:8]}_{uuid_module.uuid4().hex[:8]}"

        session = SessionTuteur.objects.create(
            etudiant=request.user,
            chapitre=chapitre,
            thread_id=thread_id,
        )

        # Message d'accueil instantané — aucun appel LLM
        prenom = request.user.get_short_name()
        welcome = (
            f"Prêt à explorer **{chapitre.titre}** ? "
            f"Dis-moi d'abord ce que tu sais déjà sur ce sujet."
        )

        return JsonResponse({
            "session_id":    str(session.id),
            "message":       welcome,
            "mastery_score": 0.0,
            "iteration":     0,
            "cold_start":    True,   # indique que le graph n'est pas encore initialisé
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

        # Normaliser niveau étudiant
        def _get_niveau(user):
            lbl = getattr(user, 'niveau_label', '').upper()
            if 'DÉBUTANT' in lbl or 'DEBUTANT' in lbl:
                return 'DEBUTANT'
            if 'INTERMÉDIAIRE' in lbl or 'INTERMEDIAIRE' in lbl:
                return 'INTERMEDIAIRE'
            if 'AVANCÉ' in lbl or 'AVANCE' in lbl:
                return 'AVANCE'
            return 'DEBUTANT'

        profil_ia, _ = ProfilEtudiantIA.objects.get_or_create(etudiant=request.user)
        niveau = _get_niveau(request.user)
        chapitre = session.chapitre
        cours    = chapitre.cours

        # Vérifier si le graph a déjà un état (sessions existantes)
        state_obj = graph.get_state(config)
        graph_initialized = bool(state_obj.values and "current_concept" in state_obj.values)

        if not graph_initialized:
            # PREMIER MESSAGE : lancer le graph depuis zéro avec le message
            # de l'étudiant déjà inclus dans l'état initial.
            initial_state = {
                "messages":        [HumanMessage(content=message)],
                "subject":         cours.titre,
                "current_concept": chapitre.titre,
                "chapitre_id":     str(chapitre.id),
                "cours_id":        str(cours.id),
                "etudiant_id":     str(request.user.id),
                "niveau":          niveau,
                "diagnosis":       None,
                "last_evaluation": None,
                "mastery_score":   0.0,
                "iteration":       0,
                "student_profile": profil_ia.to_dict(),
                "next_action":     "tutor",
                "rag_context":     None,
            }
            final_state = None
            for event in graph.stream(initial_state, config, stream_mode="values"):
                final_state = event
        else:
            # TOURS SUIVANTS : injecter la réponse et continuer
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
            
            # --- SAUVEGARDE DU SCORE QCM DANS LE CARNET DE NOTES ---
            try:
                from apprentissage.models import Devoir, Soumission
                # Vérifier si un devoir IA existe déjà pour ce chapitre
                devoir_ia, created = Devoir.objects.get_or_create(
                    chapitre=session.chapitre,
                    titre=f"QCM Intelligence Artificielle - {session.chapitre.titre}",
                    defaults={
                        'consigne': "Évaluation générée automatiquement par le Tuteur IA.",
                        'note_max': 100,
                        'createur': session.chapitre.cours.createur,
                    }
                )
                
                # Créer ou mettre à jour la soumission pour l'étudiant
                soumission, s_created = Soumission.objects.get_or_create(
                    devoir=devoir_ia,
                    etudiant=session.etudiant,
                    defaults={
                        'note': min(mastery_score * 100, 100),
                        'feedback': "Score automatique par le Tuteur IA.",
                    }
                )
                if not s_created:
                    nouvelle_note = min(mastery_score * 100, 100)
                    if soumission.note is None or nouvelle_note > soumission.note:
                        soumission.note = nouvelle_note
                        soumission.save(update_fields=['note'])
            except Exception as e:
                logger.error(f"Erreur sauvegarde carnet de notes: {e}")
            # --------------------------------------------------------

        session.save()

        return JsonResponse({
            "message":          tutor_response or "Continue, tu es sur la bonne voie !",
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


from tuteur_ia.models import SessionAssistant
from django.utils import timezone

@login_required
def demarrer_assistant(request, chapitre_id):
    """
    Initialise ou charge la session de l'Assistant RAG pour un chapitre.
    Retourne l'ID de la session et l'historique des messages.
    """
    from apprentissage.models import Chapitre
    chapitre = get_object_or_404(Chapitre, id=chapitre_id, actif=True)
    
    session, created = SessionAssistant.objects.get_or_create(
        etudiant=request.user,
        chapitre=chapitre
    )
    
    return JsonResponse({
        "session_id": str(session.id),
        "messages": session.messages,
    })


@login_required
@require_http_methods(['POST'])
def poser_question(request, session_id):
    """
    Pose une question à l'Assistant RAG.
    Utilise le modèle rapide llama-3.1-8b-instant + contexte RAG limité pour des réponses rapides.
    """
    session = get_object_or_404(SessionAssistant, id=session_id, etudiant=request.user)

    try:
        data = json.loads(request.body)
        question = data.get('question', '').strip() or data.get('message', '').strip() or data.get('reponse', '').strip()
    except json.JSONDecodeError:
        question = request.POST.get('question', '').strip() or request.POST.get('message', '').strip() or request.POST.get('reponse', '').strip()

    if not question:
        return JsonResponse({"error": "Question vide."}, status=400)

    try:
        # ── Recherche RAG rapide (résultats limités pour réduire la taille du contexte) ──
        from tuteur_ia.tools.rag_tool import rag_search
        context = rag_search(
            query=question,
            chapitre_id=str(session.chapitre.id),
            cours_id=str(session.chapitre.cours.id),
            n_results=3,  # Limiter à 3 résultats au lieu de la valeur par défaut
        )
        # Tronquer le contexte à 1500 caractères max pour éviter les prompts trop longs
        if context and len(context) > 1500:
            context = context[:1500] + "\n[...]"

        # ── Historique limité aux 4 derniers échanges (mémoire courte pour la rapidité) ──
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        chat_history = []
        for msg in session.messages[-8:]:  # Max 4 tours (user+assistant)
            if msg.get('role') == 'user':
                chat_history.append(HumanMessage(content=msg.get('content', '')))
            elif msg.get('role') == 'assistant':
                # Tronquer les anciennes réponses longues
                content = msg.get('content', '')
                chat_history.append(AIMessage(content=content[:500] if len(content) > 500 else content))

        system_prompt = (
            f"Tu es le Tuteur Assistant du chapitre '{session.chapitre.titre}'.\n"
            "Extraits de référence :\n"
            f"{context or '[Aucun extrait disponible]'}\n\n"
            "Réponds en français, de façon claire et concise (max 3 paragraphes). "
            "Formate en Markdown si utile."
        )

        messages_to_send = [SystemMessage(content=system_prompt)] + chat_history + [HumanMessage(content=question)]

        # ── LLM rapide : llama-3.1-8b-instant (le plus rapide sur Groq) ──
        from tuteur_ia.agents.llm_factory import get_llm
        llm = get_llm(temperature=0.3, model_name="llama-3.1-8b-instant")
        response = llm.invoke(messages_to_send)
        reponse_content = response.content

        # ── Enregistrement historique ──
        session.messages.append({
            'role': 'user',
            'content': question,
            'timestamp': timezone.now().isoformat()
        })
        session.messages.append({
            'role': 'assistant',
            'content': reponse_content,
            'sources': context,
            'timestamp': timezone.now().isoformat()
        })
        # Garder seulement les 20 derniers messages pour ne pas alourdir la DB
        if len(session.messages) > 20:
            session.messages = session.messages[-20:]
        session.save()

        return JsonResponse({
            'reponse': reponse_content,
            'sources': context,
        })

    except Exception as e:
        logger.error(f"Erreur poser_question : {e}", exc_info=True)
        return JsonResponse({"error": str(e)}, status=500)

