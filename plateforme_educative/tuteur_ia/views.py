"""
Vues Django — Tuteur IA (chatbot socratique).
- 12 à 15 questions par session
- Feedback selon mastery_score : < 0.75 → réviser, >= 0.75 → félicitations + QCM
"""
import json
import time
import uuid as uuid_module
import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.translation import gettext
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
        welcome = gettext(
            "Prêt à explorer **%(chapitre)s** ? "
            "Dis-moi d'abord ce que tu sais déjà sur ce sujet."
        ) % {'chapitre': chapitre.titre}

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


def _reponse_from_payload(payload: dict):
    """Traduit le dict renvoyé par la tâche socratique en JsonResponse."""
    if payload.get('error'):
        code = 503 if payload.get('llm_unavailable') else (400 if payload.get('session_terminee') else 500)
        return JsonResponse(payload, status=code)
    return JsonResponse({
        "message":          payload.get("message") or gettext("Continue, tu es sur la bonne voie !"),
        "mastery_score":    payload.get("mastery_score", 0.0),
        "iteration":        payload.get("iteration", 0),
        "session_terminee": payload.get("session_terminee", False),
    })


@login_required
@require_http_methods(['POST'])
def repondre(request, session_id):
    """
    POST {'message': '...'} → un tour du tuteur socratique.

    Le graph (diagnostic → question → évaluation) est lourd (~50 s sur CPU).
    On le lance donc dans une tâche Celery :
      - serveur (worker + Redis) → 202 {task_id}, le front sonde `statut_tache`
      - local/offline (CELERY_TASK_ALWAYS_EAGER) → la tâche tourne inline,
        on renvoie directement le résultat (200).
    """
    from django.conf import settings
    from django.utils.translation import get_language
    from tuteur_ia.tasks import repondre_socratique_task

    session = get_object_or_404(SessionTuteur, id=session_id, etudiant=request.user)
    if session.statut != 'EN_COURS':
        return JsonResponse({"error": gettext("Session déjà terminée.")}, status=400)

    try:
        message = json.loads(request.body).get('message', '').strip()
    except json.JSONDecodeError:
        message = request.POST.get('message', '').strip()
    if not message:
        return JsonResponse({"error": "Message vide."}, status=400)

    async_result = repondre_socratique_task.delay(str(session.id), message, get_language() or 'fr')

    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        # eager (local/offline) : la tâche a tourné inline, le résultat est prêt
        try:
            payload = async_result.result
            if isinstance(payload, Exception):
                raise payload
            return _reponse_from_payload(payload or {})
        except Exception as e:
            logger.error("Tuteur socratique (eager) : %s", e, exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"task_id": async_result.id, "pending": True}, status=202)


@login_required
@require_http_methods(['GET'])
def statut_tache_tuteur(request, task_id):
    """Polling du résultat d'un tour socratique lancé en tâche de fond."""
    try:
        uuid_module.UUID(str(task_id))
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'status': 'erreur', 'detail': gettext("Tâche introuvable.")}, status=404)

    try:
        from celery.result import AsyncResult
        res = AsyncResult(task_id)
        if res.state in ('PENDING', 'STARTED', 'RETRY'):
            return JsonResponse({'status': 'en_cours'})
        if res.state == 'SUCCESS':
            data = res.get() or {}
            reponse = _reponse_from_payload(data)
            body = json.loads(reponse.content)
            body['status'] = 'erreur' if data.get('error') else 'pret'
            return JsonResponse(body, status=reponse.status_code if data.get('error') else 200)
        if res.state == 'FAILURE':
            return JsonResponse({'status': 'erreur', 'detail': str(res.result)}, status=500)
        return JsonResponse({'status': 'en_cours'})
    except Exception as e:
        logger.error(f"statut_tache_tuteur {task_id} : {e}", exc_info=True)
        return JsonResponse({'status': 'erreur', 'detail': gettext("Erreur lors de la vérification.")}, status=500)


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
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Erreur lors de la récupération de l'état du graphe: {e}")
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
        # ── Recherche sémantique directe (ChromaDB, sans BM25/RRF) ──
        from tuteur_ia.tools.chroma_store import search as chroma_search, get_stats
        chapitre_id = str(session.chapitre.id)
        titre_chapitre = session.chapitre.titre

        # Recherche principale avec la question de l'élève
        raw_results = chroma_search(query=question, chapitre_id=chapitre_id, n_results=3)

        # Si la question est générale ("résume", "explique le chapitre"…),
        # ChromaDB ne trouve rien car ces mots ne sont pas dans le PDF.
        # Fallback : rechercher avec le titre du chapitre pour avoir du contexte.
        if not raw_results:
            raw_results = chroma_search(query=titre_chapitre, chapitre_id=chapitre_id, n_results=4)

        # Assembler le contexte
        context_parts = []
        for r in raw_results:
            text = (r.get("text") or "").strip()
            if text:
                source = r.get("document_titre", "Document")
                page   = r.get("page_hint", "")
                header = f"[{source}" + (f" — p.{page}" if page else "") + "]"
                context_parts.append(f"{header}\n{text}")
        context = "\n\n---\n\n".join(context_parts)

        # Tronquer à 1500 caractères pour un prompt léger
        if context and len(context) > 1500:
            context = context[:1500] + "\n[...]"

        # Si aucun document n'est indexé pour ce chapitre → pas de PDF disponible
        stats = get_stats()
        aucun_document = not raw_results or stats.get("total_chunks", 0) == 0

        # ── Historique limité aux 3 derniers échanges ──
        from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
        chat_history = []
        for msg in session.messages[-6:]:
            if msg.get('role') == 'user':
                chat_history.append(HumanMessage(content=msg.get('content', '')))
            elif msg.get('role') == 'assistant':
                content = msg.get('content', '')
                chat_history.append(AIMessage(content=content[:400] if len(content) > 400 else content))

        refus_hors_sujet = gettext(
            "❌ Je réponds uniquement aux questions concernant le contenu "
            "du chapitre **« %(chapitre)s »**. Cette question est hors sujet."
        ) % {'chapitre': titre_chapitre}

        if aucun_document:
            # Pas de PDF indexé → on ne peut pas répondre
            system_prompt = (
                f"Tu es le Tuteur Assistant du chapitre '{titre_chapitre}'.\n"
                "Aucun document PDF n'est encore indexé pour ce chapitre.\n"
                "Réponds EXACTEMENT : \"Aucun document n'est disponible pour ce chapitre. "
                "Veuillez contacter votre formateur pour qu'il uploade le contenu.\""
            )
        else:
            system_prompt = (
                f"Tu es le Tuteur Assistant Pédagogique du chapitre '{titre_chapitre}'.\n\n"
                "EXTRAITS DU DOCUMENT PDF (Source principale) :\n"
                "---\n"
                f"{context}\n"
                "---\n\n"
                "CONSIGNES ET RÈGLES :\n"
                "1. DEMANDES DE RÉSUMÉ ET DE SYNTHÈSE : Si l'élève demande de résumer le chapitre, d'expliquer le cours, "
                "ou de donner les points clés (ex: 'résume ce chapitre', 'explique le cours', 'points clés'), "
                "tu DOIS impérativement répondre en fournissant un résumé clair, bien structuré et synthétique "
                "basé sur les extraits de cours fournis ci-dessus.\n\n"
                "2. QUESTIONS CONCERNANT LE COURS : Réponds de façon concise, bienveillante et pédagogique "
                "en t'appuyant sur le contenu du document.\n\n"
                "3. QUESTIONS TOTALEMENT HORS SUJET : Uniquement si l'élève pose une question qui n'a AUCUN rapport avec le domaine du cours "
                "(ex: météo, célébrités, recettes de cuisine, sports), réponds :\n"
                f"\"{refus_hors_sujet}\""
            )

        from tuteur_ia.agents.llm_factory import get_llm, with_language, is_llm_unavailable_error
        messages_to_send = [SystemMessage(content=with_language(system_prompt))] + chat_history + [HumanMessage(content=question)]

        # ── LLM rapide : llama-3.1-8b-instant (le plus rapide sur Groq) ──
        # max_tokens plafonné : sans limite le moteur local (qwen 1.5B sur CPU)
        # part jusqu'à OLLAMA_NUM_PREDICT sur une demande de résumé — ~1-2 min.
        # 500 tokens ≈ 350 mots : suffisant pour un résumé de chapitre concis.
        llm = get_llm(temperature=0.0, max_tokens=500)
        try:
            response = llm.invoke(messages_to_send)
        except Exception as llm_err:
            if is_llm_unavailable_error(llm_err):
                logger.warning("Assistant IA indisponible (LLM injoignable) : %s", llm_err)
                return JsonResponse({
                    "error": gettext("Le tuteur IA n'est pas disponible pour le moment. Réessaie dans un instant ou préviens ton formateur."),
                    "llm_unavailable": True,
                }, status=503)
            raise
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

