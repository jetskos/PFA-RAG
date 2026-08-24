"""
Tâches Celery pour le module tuteur_ia.
- generer_qcm_task : génération asynchrone du QCM par IA
"""
import json
import logging
import random

from celery import shared_task

logger = logging.getLogger(__name__)

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
                        'error': 'Aucun document PDF indexé pour ce chapitre.',
                        'detail': "Le formateur doit d'abord uploader un PDF.",
                        'no_pdf': True,
                    }
                else:
                    return {
                        'error': "La génération du QCM par l'IA a échoué. Réessayez dans quelques instants.",
                        'detail': "Le contenu du chapitre est bien indexé, mais l'IA n'a pas réussi à produire les questions cette fois-ci.",
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
