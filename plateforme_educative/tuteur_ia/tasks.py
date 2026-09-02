"""
Tâches Celery pour le module tuteur_ia.
- generer_qcm_task           : génération asynchrone du QCM par IA
- warmup_qcm_chapitre_task   : pré-génère le cache QCM d'un chapitre (après import)
- repondre_socratique_task   : un tour du tuteur socratique (graph LangGraph),
                               hors du thread de la requête HTTP
"""
import json
import logging
import random

from celery import shared_task
from django.utils import translation
from django.utils.translation import gettext

logger = logging.getLogger(__name__)

MAX_QUESTIONS_SOCRATIQUE = 15


@shared_task(bind=True, max_retries=0,
             name='tuteur_ia.tasks.warmup_qcm_chapitre_task')
def warmup_qcm_chapitre_task(self, chapitre_id: str, min_questions: int = 8):
    """
    Pré-génère les questions QCM d'UN chapitre et les stocke dans QuestionCache.

    Dispatché (un appel par chapitre) à la fin de `import_courses_task` : le
    formateur voit l'import terminé tout de suite, le cache QCM se remplit
    ensuite. Une tâche par chapitre (plutôt qu'une grosse tâche par cours) pour
    que le worker `--pool=solo` puisse intercaler d'autres tâches entre deux.

    Best-effort : idempotent (saute si le cache a déjà `min_questions`), borné
    par QCM_GEN_MAX_SECONDS dans `_generer_questions_ia`, n'échoue jamais.
    """
    try:
        from apprentissage.models import Chapitre
        from tuteur_ia.models import QuestionCache
        from tuteur_ia.views_qcm import _generer_questions_ia

        chapitre = (Chapitre.objects
                    .filter(pk=chapitre_id, actif=True)
                    .select_related('cours').first())
        if chapitre is None:
            return {'chapitre': chapitre_id, 'skipped': 'introuvable'}

        cache, _ = QuestionCache.objects.get_or_create(chapitre=chapitre)
        pool = cache.questions or []
        if len(pool) >= min_questions:
            return {'chapitre': chapitre_id, 'skipped': 'cache déjà chaud', 'pool': len(pool)}

        questions, reason = _generer_questions_ia(chapitre, n_questions=min_questions)
        if not questions:
            logger.info("[warmup QCM] chapitre %s ignoré : %s", chapitre_id[:8], reason)
            return {'chapitre': chapitre_id, 'skipped': reason}

        existing = {q['question'].strip().lower() for q in pool}
        for q in questions:
            if q['question'].strip().lower() not in existing:
                pool.append(q)
        cache.questions = pool
        cache.save()
        logger.info("[warmup QCM] chapitre %s : %s questions en cache", chapitre_id[:8], len(pool))
        return {'chapitre': chapitre_id, 'ok': True, 'pool': len(pool)}

    except Exception as e:  # best-effort : ne jamais faire échouer la chaîne d'import
        logger.warning("[warmup QCM] chapitre %s : %s", str(chapitre_id)[:8], e)
        return {'chapitre': chapitre_id, 'error': str(e)}


@shared_task(bind=True, max_retries=0,
             name='tuteur_ia.tasks.repondre_socratique_task')
def repondre_socratique_task(self, session_id: str, message: str, lang: str = 'fr'):
    """
    Exécute un tour du tuteur socratique (diagnostic → question → évaluation)
    pour `message`, met à jour la session et le carnet de notes, et retourne
    un dict JSON-sérialisable :
        {message, mastery_score, iteration, session_terminee}
    ou {error, llm_unavailable?}.

    `lang` = langue de l'UI de l'élève au moment de l'envoi ('fr'|'en') —
    on la réactive ici car la tâche Celery n'a pas le contexte de la requête.
    """
    import time
    from langchain_core.messages import HumanMessage
    from tuteur_ia.models import ProfilEtudiantIA, SessionTuteur
    from tuteur_ia.graph.workflow import get_graph
    from tuteur_ia.views import _get_last_ai_message
    from tuteur_ia.agents.llm_factory import is_llm_unavailable_error

    translation.activate(lang if lang in ('fr', 'en') else 'fr')

    try:
        session = SessionTuteur.objects.select_related('chapitre', 'chapitre__cours').get(pk=session_id)
    except SessionTuteur.DoesNotExist:
        return {'error': gettext("Session introuvable.")}

    if session.statut != 'EN_COURS':
        return {'error': gettext("Session déjà terminée."), 'session_terminee': True}

    try:
        graph = get_graph()
        config = {"configurable": {"thread_id": session.thread_id}}

        def _niveau(user):
            lbl = (getattr(user, 'niveau_label', '') or '').upper()
            if 'DÉBUTANT' in lbl or 'DEBUTANT' in lbl:
                return 'DEBUTANT'
            if 'INTERMÉDIAIRE' in lbl or 'INTERMEDIAIRE' in lbl:
                return 'INTERMEDIAIRE'
            if 'AVANCÉ' in lbl or 'AVANCE' in lbl:
                return 'AVANCE'
            return 'DEBUTANT'

        etu = session.etudiant
        profil_ia, _ = ProfilEtudiantIA.objects.get_or_create(etudiant=etu)
        chapitre = session.chapitre
        cours = chapitre.cours

        state_obj = graph.get_state(config)
        initialized = bool(state_obj.values and "current_concept" in state_obj.values)

        t0 = time.perf_counter()
        final_state = None
        if not initialized:
            initial_state = {
                "messages": [HumanMessage(content=message)],
                "subject": cours.titre,
                "current_concept": chapitre.titre,
                "chapitre_id": str(chapitre.id),
                "cours_id": str(cours.id),
                "etudiant_id": str(etu.id),
                "niveau": _niveau(etu),
                "diagnosis": None,
                "last_evaluation": None,
                "mastery_score": 0.0,
                "iteration": 0,
                "student_profile": profil_ia.to_dict(),
                "next_action": "tutor",
                "rag_context": None,
            }
            for event in graph.stream(initial_state, config, stream_mode="values"):
                final_state = event
        else:
            graph.update_state(config, {"messages": [HumanMessage(content=message)]}, as_node="tutor")
            for event in graph.stream(None, config, stream_mode="values"):
                final_state = event
        logger.info(f"[TIMING] repondre_socratique_task graph.stream(): {time.perf_counter() - t0:.2f}s")

        tutor_response, mastery_score, iteration, next_action = "", 0.0, 0, "tutor"
        if final_state:
            tutor_response = _get_last_ai_message(final_state.get("messages", []))
            mastery_score = final_state.get("mastery_score", 0.0)
            iteration = final_state.get("iteration", 0)
            next_action = final_state.get("next_action", "tutor")

        session_terminee = (
            mastery_score >= 0.75
            or iteration >= MAX_QUESTIONS_SOCRATIQUE
            or next_action == "end"
        )
        session.mastery_score_final = mastery_score
        if session_terminee:
            session.statut = 'TERMINEE'
            try:
                from apprentissage.models import Devoir, Soumission
                devoir_ia, _ = Devoir.objects.get_or_create(
                    chapitre=chapitre,
                    titre=f"QCM Intelligence Artificielle - {chapitre.titre}",
                    defaults={
                        'consigne': "Évaluation générée automatiquement par le Tuteur IA.",
                        'note_max': 100,
                        'createur': cours.createur,
                    },
                )
                soumission, s_created = Soumission.objects.get_or_create(
                    devoir=devoir_ia, etudiant=etu,
                    defaults={'note': min(mastery_score * 100, 100),
                              'feedback': "Score automatique par le Tuteur IA."},
                )
                if not s_created:
                    nn = min(mastery_score * 100, 100)
                    if soumission.note is None or nn > soumission.note:
                        soumission.note = nn
                        soumission.save(update_fields=['note'])
            except Exception as e:
                logger.error(f"[Socratique] Erreur carnet de notes : {e}")
        session.save()

        return {
            "message": tutor_response or gettext("Continue, tu es sur la bonne voie !"),
            "mastery_score": mastery_score,
            "iteration": iteration,
            "session_terminee": session_terminee,
        }

    except Exception as e:
        logger.error(f"[Socratique] Erreur dans repondre_socratique_task : {e}", exc_info=True)
        if is_llm_unavailable_error(e):
            return {
                "error": gettext("Le tuteur IA n'est pas disponible pour le moment. Réessaie dans un instant ou préviens ton formateur."),
                "llm_unavailable": True,
            }
        return {"error": gettext("Le tuteur IA a rencontré un problème. Réessaie dans un instant.")}

LETTRES = ['A', 'B', 'C', 'D']


def _ajouter_lettres(questions: list) -> list:
    result = []
    for q in questions:
        q_copy = dict(q)
        q_copy['options_avec_lettres'] = [
            {'lettre': LETTRES[i], 'texte': opt}
            for i, opt in enumerate(q.get('options', []))
        ]
        result.append(q_copy)
    return result


@shared_task(bind=True, max_retries=1, default_retry_delay=10,
             name='tuteur_ia.tasks.generer_qcm_task')
def generer_qcm_task(self, chapitre_id: str, etudiant_id: str, n_questions: int = 8):
    """
    Génère un QCM pour un chapitre donné via l'IA, peuple le cache QuestionCache
    et crée la SessionQCM. Retourne un dict JSON-sérialisable avec le résultat.

    Args:
        chapitre_id  : UUID du chapitre.
        etudiant_id  : UUID de l'étudiant.
        n_questions  : Nombre de questions à générer.

    Returns:
        dict avec les clés 'session_id', 'questions', 'n_questions', 'tentative'
        ou 'error' en cas d'échec.
    """
    try:
        from apprentissage.models import Chapitre
        from accounts.models import Utilisateur
        from tuteur_ia.models import SessionQCM, QuestionCache
        from tuteur_ia.views_qcm import _generer_questions_ia

        chapitre = Chapitre.objects.get(pk=chapitre_id, actif=True)
        etudiant = Utilisateur.objects.get(pk=etudiant_id)

        tentative = SessionQCM.objects.filter(
            etudiant=etudiant, chapitre=chapitre
        ).count() + 1

        # Récupération / création du cache
        cache, _ = QuestionCache.objects.get_or_create(chapitre=chapitre)
        questions_pool = cache.questions or []

        if len(questions_pool) >= n_questions:
            questions = random.sample(questions_pool, n_questions)
            logger.info(
                f"[QCM] Chargé depuis le cache pour chapitre {chapitre_id} "
                f"(pool: {len(questions_pool)})"
            )
        else:
            questions, reason = _generer_questions_ia(chapitre, n_questions=n_questions)
            if not questions:
                if reason == 'no_content':
                    return {
                        'error': gettext('Aucun document PDF indexé pour ce chapitre.'),
                        'detail': gettext("Le formateur doit d'abord uploader un PDF."),
                        'no_pdf': True,
                    }
                elif reason == 'llm_unavailable':
                    return {
                        'error': gettext("Le service IA n'est pas disponible pour le moment."),
                        'detail': gettext("La génération de QCM nécessite le moteur IA (local ou en ligne). Réessayez plus tard ou prévenez votre formateur."),
                        'llm_unavailable': True,
                    }
                else:
                    return {
                        'error': gettext("La génération du QCM par l'IA a échoué. Réessayez dans quelques instants."),
                        'detail': gettext("Le contenu du chapitre est bien indexé, mais l'IA n'a pas réussi à produire les questions cette fois-ci."),
                        'no_pdf': False,
                    }

            # Enrichir le cache sans doublons
            existing_texts = {q['question'].strip().lower() for q in questions_pool}
            added = 0
            for q in questions:
                if q['question'].strip().lower() not in existing_texts:
                    questions_pool.append(q)
                    added += 1

            if added > 0:
                cache.questions = questions_pool
                cache.save()
                logger.info(
                    f"[QCM] Cache enrichi de {added} nouvelles questions "
                    f"pour le chapitre {chapitre_id}"
                )

        # Création de la SessionQCM
        session = SessionQCM.objects.create(
            etudiant=etudiant,
            chapitre=chapitre,
            questions=questions,
            tentative=tentative,
        )

        questions_template = _ajouter_lettres(questions)

        return {
            'session_id': str(session.id),
            'questions': questions_template,
            'n_questions': len(questions),
            'tentative': tentative,
        }

    except Exception as exc:
        logger.error(f"[QCM] Erreur dans generer_qcm_task : {exc}", exc_info=True)
        raise self.retry(exc=exc)
