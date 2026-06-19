"""
Vues QCM IA — génération automatique depuis le contenu du PDF.

Flux :
  1. GET  /tuteur/qcm/<chapitre_id>/         → affiche immédiatement la page avec un loader
  2. GET  /tuteur/qcm/<chapitre_id>/generer-api/ → endpoint AJAX qui renvoie le QCM (depuis le cache ou l'IA)
  3. POST /tuteur/qcm/<session_id>/corriger/ → corrige les réponses, calcule le score
  4. GET  /tuteur/qcm/<session_id>/resultats/→ page résultats avec feedback
"""
import json
import logging
import random

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from tuteur_ia.models import SessionQCM, QuestionCache
from apprentissage.mixins import ElevePropreDonneeMixin

logger = logging.getLogger(__name__)

LETTRES = ['A', 'B', 'C', 'D']


# ── Génération du QCM par IA ──────────────────────────────────────────────────

def _get_pdf_content_for_qcm(chapitre) -> str:
    """
    Récupère tout le contenu réel du PDF indexé pour ce chapitre depuis ChromaDB.
    Fait une recherche directe par filtre de métadonnées, sans passer par
    le modèle d'embeddings pour garantir un temps de réponse instantané (0-1ms).
    """
    from tuteur_ia.tools.chroma_store import get_collection
    try:
        collection = get_collection()
        res = collection.get(
            where={"chapitre_id": str(chapitre.id)},
            include=["documents", "metadatas"]
        )
        docs = res.get("documents", [])
        metas = res.get("metadatas", [])
        
        if docs:
            # Tri par index de chunk pour respecter l'ordre d'origine
            indexed_docs = []
            for doc, meta in zip(docs, metas):
                try:
                    idx = int(meta.get("chunk_index", 0))
                except (ValueError, TypeError):
                    idx = 0
                indexed_docs.append((idx, doc))
            
            indexed_docs.sort(key=lambda x: x[0])
            sorted_docs = [doc for _, doc in indexed_docs]
            
            logger.info(f"QCM content loaded directly from ChromaDB: {len(sorted_docs)} chunks")
            return "\n\n---\n\n".join(sorted_docs)
    except Exception as e:
        logger.error(f"Erreur extraction directe ChromaDB : {e}", exc_info=True)
    
    return ""


def _generer_questions_ia(chapitre, n_questions: int = 8) -> list[dict]:
    """
    Génère n questions QCM depuis le contenu ChromaDB du chapitre.
    Les questions sont basées STRICTEMENT sur le contenu des chunks PDF,
    pas sur le nom/titre du chapitre.
    Utilise le modèle Groq rapide llama-3.1-8b-instant.
    """
    from tuteur_ia.agents.llm_factory import get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    # Récupérer le contenu réel du PDF (lecture directe)
    contenu = _get_pdf_content_for_qcm(chapitre)

    if not contenu or contenu.startswith('['):
        logger.warning(f"Contenu PDF vide ou non indexé pour le chapitre {chapitre.id}")
        return []

    # Utilisation du modèle rapide de Groq avec contrôle de tokens
    llm = get_llm(temperature=0.4, model_name="llama-3.1-8b-instant")
    
    # Activer le format JSON si supporté par langchain_groq
    if hasattr(llm, 'bind'):
        try:
            llm = llm.bind(response_format={"type": "json_object"})
        except Exception as e:
            logger.warning(f"Impossible d'activer le response_format JSON : {e}")

    system_prompt = f"""Tu es un créateur de QCM pédagogique pour des élèves de primaire.
Tu crées des questions SIMPLES, CLAIRES et STRICTEMENT tirées du CONTENU TEXTUEL fourni.

RÈGLES ABSOLUES :
1. Tes questions DOIVENT être basées UNIQUEMENT sur le contenu textuel ci-dessous.
2. NE PAS inventer des questions à partir du titre du chapitre ou du cours.
3. NE PAS poser des questions sur des sujets non présents dans le texte fourni.
4. Chaque question doit avoir une réponse correcte qui se trouve EXPLICITEMENT dans le texte.
5. Exactement {n_questions} questions au total.
6. Chaque question a exactement 4 options (A, B, C, D) très courtes (maximum 5 mots par option).
7. Une seule bonne réponse par question.
8. Explication TRÈS COURTE (maximum 6 mots), tirée du texte.
9. Des questions simples et directes (maximum 10 mots par question).

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après :
{{
  "questions": [
    {{
      "question": "Question courte ?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "reponse_correcte": "Option A",
      "explication": "Explication courte."
    }}
  ]
}}"""

    user_prompt = f"""CONTENU DU PDF (source unique pour tes questions) :
{contenu}

Génère exactement {n_questions} questions QCM basées UNIQUEMENT sur ce contenu textuel.
Ne te base PAS sur le titre '{chapitre.titre}' pour inventer des questions."""

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        content = response.content.strip()
        start = content.find('{')
        end   = content.rfind('}') + 1
        if start != -1 and end > start:
            data = json.loads(content[start:end])
            questions = data.get('questions', [])
            valid = []
            for q in questions:
                if (q.get('question') and
                    isinstance(q.get('options'), list) and len(q['options']) == 4 and
                    q.get('reponse_correcte') and q.get('explication')):
                    valid.append(q)
            return valid[:n_questions]

    except Exception as e:
        logger.error(f"Erreur génération QCM IA : {e}", exc_info=True)

    return []


def _ajouter_lettres(questions: list[dict]) -> list[dict]:
    """
    Ajoute les lettres A/B/C/D à chaque option pour le template.
    """
    result = []
    for q in questions:
        q_copy = dict(q)
        q_copy['options_avec_lettres'] = [
            {'lettre': LETTRES[i], 'texte': opt}
            for i, opt in enumerate(q.get('options', []))
        ]
        result.append(q_copy)
    return result


# ── Vues ──────────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def demarrer_qcm(request, chapitre_id):
    """
    GET → Affiche immédiatement la page avec le loader HTML.
    La génération effective se fera de manière asynchrone via AJAX.
    """
    from apprentissage.models import Chapitre
    chapitre = get_object_or_404(Chapitre, id=chapitre_id, actif=True)
    tentative = SessionQCM.objects.filter(etudiant=request.user, chapitre=chapitre).count() + 1
    
    # QCM fixe de 8 questions
    n_questions = 8

    return render(request, 'tuteur_ia/qcm.html', {
        'chapitre':    chapitre,
        'cours':       chapitre.cours,
        'n_questions': n_questions,
        'tentative':   tentative,
        'session':     None,
        'questions':   [],
    })


@login_required
@require_http_methods(['GET'])
def generer_qcm_api(request, chapitre_id):
    """
    GET → Endpoint API appelé par AJAX.
    Récupère les questions depuis le cache ou appelle l'IA, crée la SessionQCM et renvoie le JSON.
    """
    from apprentissage.models import Chapitre
    chapitre = get_object_or_404(Chapitre, id=chapitre_id, actif=True)
    tentative = SessionQCM.objects.filter(etudiant=request.user, chapitre=chapitre).count() + 1
    
    # Toujours 8 questions
    n_questions = 8

    # Récupération / Création du cache
    cache, created = QuestionCache.objects.get_or_create(chapitre=chapitre)
    questions_pool = cache.questions or []

    # Vérifier si on a assez de questions en cache
    if len(questions_pool) >= n_questions:
        # Piocher aléatoirement dans la banque de questions existantes
        questions = random.sample(questions_pool, n_questions)
        logger.info(f"QCM chargé depuis le cache pour le chapitre {chapitre_id} (pool: {len(questions_pool)})")
    else:
        # Appeler le LLM pour générer de nouvelles questions
        questions = _generer_questions_ia(chapitre, n_questions=n_questions)
        if not questions:
            return JsonResponse({
                'error': 'Aucun document PDF indexé pour ce chapitre.',
                'detail': "Le formateur doit d'abord uploader un PDF dans ce chapitre pour que le QCM puisse être généré automatiquement.",
                'no_pdf': True,
            }, status=404)

        # Enricheur de cache : Ajouter les nouvelles questions sans doublons
        existing_texts = {q['question'].strip().lower() for q in questions_pool}
        added = 0
        for q in questions:
            if q['question'].strip().lower() not in existing_texts:
                questions_pool.append(q)
                added += 1
        
        if added > 0:
            cache.questions = questions_pool
            cache.save()
            logger.info(f"Cache enrichi de {added} nouvelles questions pour le chapitre {chapitre_id}")

    # Création de la session QCM uniquement lorsque les questions sont prêtes
    session = SessionQCM.objects.create(
        etudiant=request.user,
        chapitre=chapitre,
        questions=questions,
        tentative=tentative,
    )

    questions_template = _ajouter_lettres(questions)

    return JsonResponse({
        'session_id':           str(session.id),
        'questions':            questions_template,
        'n_questions':          len(questions),
        'tentative':            tentative,
    })


@login_required
@ElevePropreDonneeMixin.as_decorator()
@require_http_methods(['POST'])
def corriger_qcm(request, session_id):
    """
    Reçoit les réponses, calcule le score, retourne JSON.
    """
    session = get_object_or_404(SessionQCM, id=session_id)

    try:
        data     = json.loads(request.body)
        reponses = data.get('reponses', {})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalide'}, status=400)

    questions = session.questions
    total     = len(questions)
    correctes = 0
    details   = []

    for i, question in enumerate(questions):
        reponse_choisie = reponses.get(str(i), '')
        bonne_reponse   = question['reponse_correcte']
        est_correcte    = reponse_choisie.strip() == bonne_reponse.strip()

        if est_correcte:
            correctes += 1

        details.append({
            'question':        question['question'],
            'reponse_choisie': reponse_choisie,
            'bonne_reponse':   bonne_reponse,
            'est_correcte':    est_correcte,
            'explication':     question.get('explication', ''),
            'options':         question.get('options', []),
        })

    score  = round((correctes / total) * 100) if total > 0 else 0
    statut = 'TERMINEE' if score >= 80 else 'ECHOUEE'

    session.reponses = reponses
    session.score    = score
    session.statut   = statut
    session.save()

    try:
        from accounts.notifications import notifier
        from django.urls import reverse
        notifier(
            destinataire=session.etudiant,
            type='QCM_CORRIGE',
            titre=f"QCM Corrigé : {session.chapitre.titre}",
            message=f"Tu as complété le QCM du chapitre '{session.chapitre.titre}' avec un score de {score}/100.",
            url=reverse('tuteur_ia:resultats_qcm', args=[session.id])
        )
    except Exception as notif_err:
        logger.error(f"Erreur d'envoi de notification de correction QCM : {notif_err}", exc_info=True)

    if score >= 80:
        feedback = {
            'type':    'success',
            'titre':   f'🎉 Bravo ! Tu as obtenu {score}/100 !',
            'message': 'Excellent travail ! Tu maîtrises bien ce chapitre. Tu peux passer au chapitre suivant.',
            'action':  'next_chapter',
        }
        try:
            from apprentissage.models import Progression, ChapitreComplete
            progression, _ = Progression.objects.get_or_create(
                etudiant=request.user,
                cours=session.chapitre.cours
            )
            progression.chapitres_valides.add(session.chapitre)
            ChapitreComplete.objects.update_or_create(
                etudiant=request.user,
                chapitre=session.chapitre,
            )
        except Exception as e:
            logger.error(f"Erreur lors de la validation automatique du chapitre : {e}", exc_info=True)
    else:
        feedback = {
            'type':    'retry',
            'titre':   f'Score : {score}/100',
            'message': f'Tu as eu {correctes} bonne(s) réponse(s) sur {total}. Relis le chapitre et réessaie !',
            'action':  'retry',
        }

    prochain_chapitre_id = None
    try:
        chapitres    = list(session.chapitre.cours.chapitres.filter(actif=True).order_by('ordre').values('id', 'ordre'))
        ordre_actuel = session.chapitre.ordre
        for c in chapitres:
            if c['ordre'] > ordre_actuel:
                prochain_chapitre_id = str(c['id'])
                break
    except Exception:
        pass

    return JsonResponse({
        'score':                score,
        'correctes':            correctes,
        'total':                total,
        'statut':               statut,
        'feedback':             feedback,
        'details':              details,
        'prochain_chapitre_id': prochain_chapitre_id,
        'session_id':           str(session.id),
    })


@login_required
@ElevePropreDonneeMixin.as_decorator()
def resultats_qcm(request, session_id):
    """Page de résultats détaillés du QCM."""
    session  = get_object_or_404(SessionQCM, id=session_id)
    chapitre = session.chapitre

    details = []
    for i, question in enumerate(session.questions):
        reponse_choisie = session.reponses.get(str(i), '')
        bonne_reponse   = question['reponse_correcte']
        details.append({
            'numero':          i + 1,
            'question':        question['question'],
            'options':         question.get('options', []),
            'reponse_choisie': reponse_choisie,
            'bonne_reponse':   bonne_reponse,
            'est_correcte':    reponse_choisie.strip() == bonne_reponse.strip(),
            'explication':     question.get('explication', ''),
        })

    prochain_chapitre = None
    try:
        prochain_chapitre = (
            chapitre.cours.chapitres
            .filter(actif=True, ordre__gt=chapitre.ordre)
            .order_by('ordre')
            .first()
        )
    except Exception:
        pass

    return render(request, 'tuteur_ia/qcm_resultats.html', {
        'session':           session,
        'chapitre':          chapitre,
        'cours':             chapitre.cours,
        'details':           details,
        'score':             session.score,
        'prochain_chapitre': prochain_chapitre,
        'peut_avancer':      (session.score or 0) >= 80,
    })


@login_required
@require_http_methods(['GET'])
def verifier_statut_qcm(request, task_id):
    """
    Endpoint de polling pour connaître l'état d'une tâche Celery de génération QCM.
    Retourne :
      - {"status": "en_cours"} si la tâche est en attente ou en cours
      - {"status": "pret", "session_id": ..., "questions": ...} si terminée
      - {"status": "erreur", "detail": ...} en cas d'échec
    """
    try:
        from celery.result import AsyncResult
        result = AsyncResult(task_id)

        if result.state == 'PENDING' or result.state == 'STARTED':
            return JsonResponse({'status': 'en_cours'})

        if result.state == 'SUCCESS':
            data = result.get()
            if data and 'error' in data:
                return JsonResponse({'status': 'erreur', 'detail': data['error']}, status=404)
            return JsonResponse({'status': 'pret', **data})

        if result.state == 'FAILURE':
            return JsonResponse({
                'status': 'erreur',
                'detail': str(result.result),
            }, status=500)

        return JsonResponse({'status': 'en_cours'})

    except Exception as e:
        logger.error(f"Erreur vérification statut QCM task {task_id}: {e}", exc_info=True)
        return JsonResponse({'status': 'erreur', 'detail': str(e)}, status=500)

