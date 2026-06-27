"""
Tests — Intégration C2PCT dans les prompts agents

Vérifie que chaque prompt contient les phases C2PCT pertinentes
et que le format JSON attendu est respecté.

Run : python manage.py test tuteur_ia.tests.test_c2pct_prompts
"""
from django.test import SimpleTestCase

from tuteur_ia.prompts.tuteur        import TUTOR_SYSTEM_PROMPT, TUTOR_USER_PROMPT_TEMPLATE
from tuteur_ia.prompts.diagnostiqueur import DIAGNOSTIC_SYSTEM_PROMPT, DIAGNOSTIC_USER_PROMPT_TEMPLATE
from tuteur_ia.prompts.evaluateur    import EVALUATOR_SYSTEM_PROMPT, EVALUATOR_USER_PROMPT_TEMPLATE
from tuteur_ia.prompts.memoire       import MEMORY_SYSTEM_PROMPT, MEMORY_USER_PROMPT_TEMPLATE


class TuteurPromptC2PCTTest(SimpleTestCase):

    def test_contains_c2pct_marker(self):
        self.assertIn("C2PCT", TUTOR_SYSTEM_PROMPT)

    def test_contains_decomposition_phase(self):
        self.assertIn("Décomposition", TUTOR_SYSTEM_PROMPT)

    def test_contains_structuration_phase(self):
        self.assertIn("Structuration", TUTOR_SYSTEM_PROMPT)

    def test_contains_generalisation_phase(self):
        self.assertIn("Généralisation", TUTOR_SYSTEM_PROMPT)

    def test_contains_communication_phase(self):
        self.assertIn("Communication", TUTOR_SYSTEM_PROMPT)

    def test_still_has_core_rules(self):
        self.assertIn("RÈGLES", TUTOR_SYSTEM_PROMPT)
        self.assertIn("vocabulaire", TUTOR_SYSTEM_PROMPT.lower())

    def test_user_template_has_required_placeholders(self):
        # Doit pouvoir être formaté sans KeyError
        filled = TUTOR_USER_PROMPT_TEMPLATE.format(
            etudiant_email="test@test.com",
            current_concept="Les fractions",
            student_niveau="DEBUTANT",
            mastery_background="",
            rag_content="[PDF content]",
            recent_messages="[Début]",
        )
        self.assertIn("Les fractions", filled)


class DiagnostiqueurPromptC2PCTTest(SimpleTestCase):

    def test_contains_c2pct_marker(self):
        self.assertIn("C2PCT", DIAGNOSTIC_SYSTEM_PROMPT)

    def test_contains_phase_1_donnees_planification(self):
        self.assertIn("Phase 1", DIAGNOSTIC_SYSTEM_PROMPT)
        self.assertIn("planification", DIAGNOSTIC_SYSTEM_PROMPT.lower())

    def test_contains_phase_7_metacognition(self):
        self.assertIn("Phase 7", DIAGNOSTIC_SYSTEM_PROMPT)
        self.assertIn("métacognition", DIAGNOSTIC_SYSTEM_PROMPT.lower())

    def test_still_requires_json_output(self):
        self.assertIn("JSON", DIAGNOSTIC_SYSTEM_PROMPT)
        self.assertIn("assessment", DIAGNOSTIC_SYSTEM_PROMPT)
        self.assertIn("questions", DIAGNOSTIC_SYSTEM_PROMPT)
        self.assertIn("confidence", DIAGNOSTIC_SYSTEM_PROMPT)

    def test_user_template_has_required_placeholders(self):
        filled = DIAGNOSTIC_USER_PROMPT_TEMPLATE.format(
            etudiant_email="test@test.com",
            niveau="DEBUTANT",
            concept="Les fractions",
            concepts_maitrises="aucun",
            concepts_fragiles="aucun",
            rag_content="[PDF]",
        )
        self.assertIn("Les fractions", filled)


class EvaluateurPromptC2PCTTest(SimpleTestCase):

    def test_contains_c2pct_marker(self):
        self.assertIn("C2PCT", EVALUATOR_SYSTEM_PROMPT)

    def test_contains_phase_6_autoevaluation(self):
        self.assertIn("Phase 6", EVALUATOR_SYSTEM_PROMPT)
        self.assertIn("Auto-évaluation", EVALUATOR_SYSTEM_PROMPT)

    def test_contains_phase_7_metacognition(self):
        self.assertIn("Phase 7", EVALUATOR_SYSTEM_PROMPT)
        self.assertIn("métacognition", EVALUATOR_SYSTEM_PROMPT.lower())

    def test_still_has_scoring_rules(self):
        self.assertIn("mastery_score", EVALUATOR_SYSTEM_PROMPT)
        self.assertIn("0.12", EVALUATOR_SYSTEM_PROMPT)
        self.assertIn("0.08", EVALUATOR_SYSTEM_PROMPT)

    def test_creativity_valorised(self):
        self.assertIn("créativité", EVALUATOR_SYSTEM_PROMPT.lower())

    def test_user_template_has_required_placeholders(self):
        filled = EVALUATOR_USER_PROMPT_TEMPLATE.format(
            current_concept="Les fractions",
            student_niveau="DEBUTANT",
            previous_score=0.3,
            last_question="Qu'est-ce qu'une fraction ?",
            student_response="c'est une partie",
            rag_content="[PDF]",
        )
        self.assertIn("0.3", filled)


class MemoirePromptC2PCTTest(SimpleTestCase):

    def test_contains_c2pct_marker(self):
        self.assertIn("C2PCT", MEMORY_SYSTEM_PROMPT)

    def test_contains_phase_1_planification(self):
        self.assertIn("Phase 1", MEMORY_SYSTEM_PROMPT)
        self.assertIn("planification", MEMORY_SYSTEM_PROMPT.lower())

    def test_contains_phase_7_synthese(self):
        self.assertIn("Phase 7", MEMORY_SYSTEM_PROMPT)

    def test_still_has_mastered_fragile_structure(self):
        self.assertIn("mastered_concepts", MEMORY_SYSTEM_PROMPT)
        self.assertIn("fragile_concepts", MEMORY_SYSTEM_PROMPT)
        self.assertIn("common_errors", MEMORY_SYSTEM_PROMPT)

    def test_summary_references_c2pct_dimensions(self):
        # Le summary doit mentionner les dimensions C2PCT importantes
        for keyword in ("communiquer", "généralis", "métacognition", "summary"):
            self.assertIn(keyword.lower(), MEMORY_SYSTEM_PROMPT.lower(),
                          msg=f"Mot-clé manquant : {keyword}")

    def test_user_template_has_required_placeholders(self):
        filled = MEMORY_USER_PROMPT_TEMPLATE.format(
            etudiant_email="test@test.com",
            mastered_concepts=["fractions"],
            fragile_concepts=[],
            common_errors=[],
            preferred_style="textuel",
            current_concept="Les fractions",
            mastery_score=0.8,
            feedback_type="encouragement",
            specific_confusion=None,
        )
        self.assertIn("Les fractions", filled)
        self.assertIn("0.8", filled)
