"""
Vues QCM IA — génération automatique depuis le contenu du PDF.

Flux :
  1. GET  /tuteur/qcm/<chapitre_id>/         → génère le QCM (IA) et affiche
  2. POST /tuteur/qcm/<session_id>/corriger/ → corrige les réponses, calcule le score
  3. GET  /tuteur/qcm/<session_id>/resultats/→ page résultats avec feedback
"""
import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from tuteur_ia.models import SessionQCM

logger = logging.getLogger(__name__)

LETTRES = ['A', 'B', 'C', 'D']


# ── Génération du QCM par IA ──────────────────────────────────────────────────

def _generer_questions_ia(chapitre, n_questions: int = 10) -> list[dict]:
    """
    Génère n questions QCM depuis le contenu ChromaDB du chapitre.
    Adapté au niveau primaire : questions simples, claires, 4 options.
    """
    from tuteur_ia.tools.rag_tool import rag_search
    from tuteur_ia.agents.llm_factory import get_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    contenu = rag_search(
        query=chapitre.titre,
        chapitre_id=str(chapitre.id),
        n_results=6,
    )

    llm = get_llm(temperature=0.4)

    system_prompt = f"""Tu es un créateur de QCM pédagogique pour des élèves de primaire.
Tu crées des questions SIMPLES, CLAIRES et DIRECTEMENT tirées du contenu du cours fourni.

RÈGLES STRICTES :
- Exactement {n_questions} questions
- Chaque question a exactement 4 options (A, B, C, D)
- Une seule bonne réponse par question
- Questions simples et compréhensibles pour des enfants
- Toutes les questions doivent venir du contenu du cours
- Explication courte de la bonne réponse (1 phrase)

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après :
{{
  "questions": [
    {{
      "question": "Texte de la question ?",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "reponse_correcte": "Option A",
      "explication": "Explication courte pourquoi c'est A."
    }}
  ]
}}"""

    user_prompt = f"""CONTENU DU COURS :
{contenu}

Chapitre : {chapitre.titre}
Cours : {chapitre.cours.titre}

Génère exactement {n_questions} questions QCM basées sur ce contenu."""

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
    Évite d'utiliser le filtre |chr inexistant en Django.
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
@require_http_methods(['GET', 'POST'])
def demarrer_qcm(request, chapitre_id):
    """
    GET → génère un nouveau QCM IA et affiche la page.
    """
    from apprentissage.models import Chapitre
    chapitre = get_object_or_404(Chapitre, id=chapitre_id, actif=True)

    tentative  = SessionQCM.objects.filter(etudiant=request.user, chapitre=chapitre).count() + 1
    n_questions = min(12 + (tentative - 1), 15)

    questions = _generer_questions_ia(chapitre, n_questions=n_questions)

    if not questions:
        return render(request, 'tuteur_ia/qcm_erreur.html', {
            'chapitre': chapitre,
            'message': "Impossible de générer le QCM. Vérifiez que le PDF du chapitre est bien indexé.",
        })

    session = SessionQCM.objects.create(
        etudiant=request.user,
        chapitre=chapitre,
        questions=questions,
        tentative=tentative,
    )

    # Ajouter les lettres A/B/C/D pour le template (pas de filtre |chr)
    questions_template = _ajouter_lettres(questions)

    return render(request, 'tuteur_ia/qcm.html', {
        'session':     session,
        'chapitre':    chapitre,
        'cours':       chapitre.cours,
        'questions':   questions_template,
        'n_questions': len(questions),
        'tentative':   tentative,
    })


@login_required
@require_http_methods(['POST'])
def corriger_qcm(request, session_id):
    """
    Reçoit les réponses, calcule le score, retourne JSON.
    """
    session = get_object_or_404(SessionQCM, id=session_id, etudiant=request.user)

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

    if score >= 80:
        feedback = {
            'type':    'success',
            'titre':   f'🎉 Bravo ! Tu as obtenu {score}/100 !',
            'message': 'Excellent travail ! Tu maîtrises bien ce chapitre. Tu peux passer au chapitre suivant.',
            'action':  'next_chapter',
        }
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
def resultats_qcm(request, session_id):
    """Page de résultats détaillés du QCM."""
    session  = get_object_or_404(SessionQCM, id=session_id, etudiant=request.user)
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
