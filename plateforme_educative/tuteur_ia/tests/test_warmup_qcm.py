"""
Tests — warmup_qcm_chapitre_task (pré-génération QCM après import).

Run : python manage.py test tuteur_ia.tests.test_warmup_qcm
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from accounts.models import Niveau
from apprentissage.models import Cours, Chapitre
from tuteur_ia.models import QuestionCache
from tuteur_ia.tasks import warmup_qcm_chapitre_task

Utilisateur = get_user_model()


class WarmupQcmChapitreTaskTest(TestCase):

    def setUp(self):
        self.niveau = Niveau.objects.create(code="NV_W", nom="Niveau W", ordre=1)
        self.formateur = Utilisateur.objects.create_user(
            email="f@example.com", password="Password123!", role="FORMATEUR",
        )
        self.cours = Cours.objects.create(
            titre="Cours warmup", description="", niveau=self.niveau,
            createur=self.formateur, actif=True,
        )
        self.chapitre = Chapitre.objects.create(
            cours=self.cours, titre="Chapitre 1", ordre=1,
        )

    def _q(self, n):
        return [{
            "question": f"Q{i} ?", "options": ["a", "b", "c", "d"],
            "reponse_correcte": "a", "explication": "…",
        } for i in range(n)]

    def test_chapitre_introuvable(self):
        res = warmup_qcm_chapitre_task("00000000-0000-0000-0000-000000000000")
        self.assertEqual(res["skipped"], "introuvable")

    def test_cache_deja_chaud_est_saute(self):
        QuestionCache.objects.create(chapitre=self.chapitre, questions=self._q(8))
        with patch("tuteur_ia.views_qcm._generer_questions_ia") as gen:
            res = warmup_qcm_chapitre_task(str(self.chapitre.id))
        gen.assert_not_called()
        self.assertEqual(res["skipped"], "cache déjà chaud")

    def test_genere_et_met_en_cache(self):
        with patch("tuteur_ia.views_qcm._generer_questions_ia",
                   return_value=(self._q(8), "")) as gen:
            res = warmup_qcm_chapitre_task(str(self.chapitre.id))
        gen.assert_called_once()
        self.assertTrue(res["ok"])
        self.assertEqual(res["pool"], 8)
        self.assertEqual(len(QuestionCache.objects.get(chapitre=self.chapitre).questions), 8)

    def test_echec_generation_ne_leve_pas(self):
        with patch("tuteur_ia.views_qcm._generer_questions_ia",
                   return_value=([], "llm_unavailable")):
            res = warmup_qcm_chapitre_task(str(self.chapitre.id))
        self.assertEqual(res["skipped"], "llm_unavailable")

    def test_exception_est_avalee(self):
        with patch("tuteur_ia.views_qcm._generer_questions_ia",
                   side_effect=RuntimeError("boom")):
            res = warmup_qcm_chapitre_task(str(self.chapitre.id))
        self.assertIn("boom", res["error"])
