"""
Tests — prompts bilingues du tuteur socratique (prompts.tuteur.tutor_prompts).

La session doit répondre dans la langue du toggle FR/EN : le prompt lui-même
est rédigé dans cette langue (une consigne d'une ligne ne suffit pas sur qwen 1.5B).

Run : python manage.py test tuteur_ia.tests.test_tuteur_bilingue
"""
from django.test import SimpleTestCase

from tuteur_ia.prompts.tuteur import (
    tutor_prompts,
    TUTOR_SYSTEM_PROMPT_FR, TUTOR_SYSTEM_PROMPT_EN,
    TUTOR_USER_PROMPT_TEMPLATE_FR, TUTOR_USER_PROMPT_TEMPLATE_EN,
)


class TutorPromptsSelectorTest(SimpleTestCase):

    def test_francais(self):
        system, template = tutor_prompts("fr")
        self.assertIs(system, TUTOR_SYSTEM_PROMPT_FR)
        self.assertIs(template, TUTOR_USER_PROMPT_TEMPLATE_FR)

    def test_anglais(self):
        system, template = tutor_prompts("en")
        self.assertIs(system, TUTOR_SYSTEM_PROMPT_EN)
        self.assertIs(template, TUTOR_USER_PROMPT_TEMPLATE_EN)

    def test_variantes_de_code_langue(self):
        self.assertIs(tutor_prompts("fr-fr")[0], TUTOR_SYSTEM_PROMPT_FR)
        self.assertIs(tutor_prompts("EN")[0], TUTOR_SYSTEM_PROMPT_EN)

    def test_repli_francais(self):
        for bad in ("", None, "ar", "de"):
            self.assertIs(tutor_prompts(bad)[0], TUTOR_SYSTEM_PROMPT_FR)


class TutorPromptsContentTest(SimpleTestCase):

    def test_fr_est_en_francais(self):
        self.assertIn("Copain d'Étude", TUTOR_SYSTEM_PROMPT_FR)
        self.assertIn("RÈGLES", TUTOR_SYSTEM_PROMPT_FR)
        self.assertIn("Tutoie l'élève", TUTOR_USER_PROMPT_TEMPLATE_FR)

    def test_en_est_en_anglais(self):
        self.assertIn("Study Buddy", TUTOR_SYSTEM_PROMPT_EN)
        self.assertIn("RULES", TUTOR_SYSTEM_PROMPT_EN)

    def test_les_deux_gardent_le_c2pct(self):
        for p in (TUTOR_SYSTEM_PROMPT_FR, TUTOR_SYSTEM_PROMPT_EN):
            self.assertIn("C2PCT", p)
            self.assertIn("Phase 2", p)
            self.assertIn("Phase 5", p)

    def test_templates_formatables(self):
        for template in (TUTOR_USER_PROMPT_TEMPLATE_FR, TUTOR_USER_PROMPT_TEMPLATE_EN):
            filled = template.format(
                etudiant_email="x@y.z",
                current_concept="Les fractions",
                student_niveau="DEBUTANT",
                mastery_background="",
                rag_content="[PDF]",
                recent_messages="[start]",
            )
            self.assertIn("Les fractions", filled)
