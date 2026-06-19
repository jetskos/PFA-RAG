from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from accounts.models import Niveau, Classe
from apprentissage.models import Cours, Chapitre, Devoir, Soumission, Document
from tuteur_ia.models import SessionQCM

Utilisateur = get_user_model()

class PermissionTestCases(TestCase):
    def setUp(self):
        # 1. Création du niveau et de la classe
        self.niveau = Niveau.objects.create(code="NV_TEST", nom="Niveau Test", ordre=1)
        self.classe = Classe.objects.create(
            niveau=self.niveau,
            code="CLS_TEST",
            nom="Classe Test",
            annee_scolaire="2026",
            capacite=30
        )

        # 2. Création des utilisateurs
        self.formateur1 = Utilisateur.objects.create_user(
            email="formateur1@example.com",
            password="Password123!",
            role="FORMATEUR",
            is_formateur=True,
            statut_compte="ACTIVE",
            is_active=True
        )
        self.formateur2 = Utilisateur.objects.create_user(
            email="formateur2@example.com",
            password="Password123!",
            role="FORMATEUR",
            is_formateur=True,
            statut_compte="ACTIVE",
            is_active=True
        )
        self.student1 = Utilisateur.objects.create_user(
            email="student1@example.com",
            password="Password123!",
            role="ELEVE",
            classe=self.classe,
            statut_compte="ACTIVE",
            is_active=True
        )
        self.student2 = Utilisateur.objects.create_user(
            email="student2@example.com",
            password="Password123!",
            role="ELEVE",
            classe=self.classe,
            statut_compte="ACTIVE",
            is_active=True
        )
        self.admin = Utilisateur.objects.create_user(
            email="admin@example.com",
            password="Password123!",
            role="ADMIN",
            statut_compte="ACTIVE",
            is_active=True
        )

        # 3. Création des objets liés à formateur1
        self.cours = Cours.objects.create(
            titre="Cours Test",
            description="Description",
            niveau=self.niveau,
            createur=self.formateur1,
            actif=True
        )
        self.chapitre = Chapitre.objects.create(
            titre="Chapitre Test",
            description="Description chapitre",
            cours=self.cours,
            ordre=1,
            actif=True
        )
        self.document = Document.objects.create(
            titre="Doc Test",
            chapitre=self.chapitre,
            type_document="PDF",
            ordre=1,
            actif=True
        )
        self.devoir = Devoir.objects.create(
            titre="Devoir Test",
            consigne="Description devoir",
            chapitre=self.chapitre,
            createur=self.formateur1,
            note_max=20,
            actif=True
        )
        self.soumission = Soumission.objects.create(
            devoir=self.devoir,
            etudiant=self.student1,
            commentaire_eleve="Mon devoir"
        )
        self.session_qcm = SessionQCM.objects.create(
            etudiant=self.student1,
            chapitre=self.chapitre,
            questions=[],
            score=0,
            statut="EN_COURS"
        )

    # --- TESTS FormateurCoursRequiredMixin ---

    def test_gerer_cours_owner(self):
        """Le formateur créateur peut accéder à gerer_cours."""
        self.client.login(email="formateur1@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:gerer_cours', args=[self.cours.id]))
        self.assertEqual(response.status_code, 200)

    def test_gerer_cours_non_owner(self):
        """Un autre formateur ne peut pas accéder à gerer_cours (403)."""
        self.client.login(email="formateur2@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:gerer_cours', args=[self.cours.id]))
        self.assertEqual(response.status_code, 403)

    def test_gerer_cours_student(self):
        """Un étudiant ne peut pas accéder à gerer_cours (403)."""
        self.client.login(email="student1@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:gerer_cours', args=[self.cours.id]))
        self.assertEqual(response.status_code, 403)

    def test_gerer_cours_admin(self):
        """Un administrateur peut accéder à gerer_cours (bypass)."""
        self.client.login(email="admin@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:gerer_cours', args=[self.cours.id]))
        self.assertEqual(response.status_code, 200)

    # --- TESTS FormateurChapitreRequiredMixin ---

    def test_gerer_chapitre_owner(self):
        """Le formateur créateur du cours peut accéder à gerer_chapitre."""
        self.client.login(email="formateur1@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:gerer_chapitre', args=[self.chapitre.id]))
        self.assertEqual(response.status_code, 200)

    def test_gerer_chapitre_non_owner(self):
        """Un autre formateur ne peut pas accéder à gerer_chapitre (403)."""
        self.client.login(email="formateur2@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:gerer_chapitre', args=[self.chapitre.id]))
        self.assertEqual(response.status_code, 403)

    def test_gerer_chapitre_admin(self):
        """Un administrateur peut accéder à gerer_chapitre."""
        self.client.login(email="admin@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:gerer_chapitre', args=[self.chapitre.id]))
        self.assertEqual(response.status_code, 200)

    # --- TESTS FormateurDevoirRequiredMixin ---

    def test_devoir_editer_owner(self):
        """Le formateur créateur peut accéder au formulaire d'édition de devoir."""
        self.client.login(email="formateur1@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:devoir_editer', args=[self.devoir.id]))
        self.assertEqual(response.status_code, 200)

    def test_devoir_editer_non_owner(self):
        """Un autre formateur ne peut pas accéder à l'édition de devoir (403)."""
        self.client.login(email="formateur2@example.com", password="Password123!")
        response = self.client.get(reverse('apprentissage:devoir_editer', args=[self.devoir.id]))
        self.assertEqual(response.status_code, 403)

    # --- TESTS ElevePropreDonneeMixin ---

    def test_resultats_qcm_student_owner(self):
        """L'étudiant propriétaire de la session QCM peut voir ses résultats."""
        self.client.login(email="student1@example.com", password="Password123!")
        response = self.client.get(reverse('tuteur_ia:resultats_qcm', args=[self.session_qcm.id]))
        self.assertEqual(response.status_code, 200)

    def test_resultats_qcm_non_owner(self):
        """Un autre étudiant ne peut pas voir les résultats QCM (403)."""
        self.client.login(email="student2@example.com", password="Password123!")
        response = self.client.get(reverse('tuteur_ia:resultats_qcm', args=[self.session_qcm.id]))
        self.assertEqual(response.status_code, 403)

    def test_resultats_qcm_admin(self):
        """Un administrateur peut voir les résultats QCM de n'importe quel élève."""
        self.client.login(email="admin@example.com", password="Password123!")
        response = self.client.get(reverse('tuteur_ia:resultats_qcm', args=[self.session_qcm.id]))
        self.assertEqual(response.status_code, 200)
