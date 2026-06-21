import json
import uuid
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.authtoken.models import Token

from accounts.models import Niveau, Classe, Notification
from apprentissage.models import Cours, Chapitre, Document, Progression, Devoir, Soumission, Evenement
from tuteur_ia.models import SessionQCM
from apprentissage.analytics import (
    stats_cours,
    stats_formateur,
    stats_eleves_en_difficulte,
    stats_plateforme
)

Utilisateur = get_user_model()

class AccountsTests(TestCase):
    def setUp(self):
        self.niveau = Niveau.objects.create(code="NV_A", nom="Niveau A", ordre=1)
        self.classe = Classe.objects.create(
            niveau=self.niveau,
            code="CLS_A",
            nom="Classe A",
            annee_scolaire="2026",
            capacite=25
        )
        self.admin = Utilisateur.objects.create_superuser(
            email="admin@example.com",
            password="Password123!"
        )
        self.student_pending = Utilisateur.objects.create_user(
            email="pending@example.com",
            password="Password123!",
            role="ELEVE"
        )

    def test_registration_pending(self):
        """L'inscription crée par défaut un compte PENDING inactif."""
        user = Utilisateur.objects.get(email="pending@example.com")
        self.assertEqual(user.statut_compte, "PENDING")
        self.assertFalse(user.is_active)

    def test_admin_activation(self):
        """L'administrateur peut activer un étudiant et l'affecter à une classe."""
        self.client.login(email="admin@example.com", password="Password123!")
        
        # Envoi de la requête d'activation
        response = self.client.post(
            reverse("dashboard_admin_activate_pending_student"),
            {"student_id": str(self.student_pending.id), "classe": str(self.classe.id)}
        )
        self.assertEqual(response.status_code, 200) # Re-rend le dashboard (Partial admin_structure)
        
        # Vérification des changements sur l'élève
        self.student_pending.refresh_from_db()
        self.assertEqual(self.student_pending.statut_compte, "ACTIVE")
        self.assertTrue(self.student_pending.is_active)
        self.assertEqual(self.student_pending.classe, self.classe)

    def test_login_flow(self):
        """Seuls les utilisateurs actifs peuvent se connecter."""
        # Tentative avec un compte PENDING
        login_success = self.client.login(email="pending@example.com", password="Password123!")
        self.assertFalse(login_success)

        # Activation du compte
        self.student_pending.is_active = True
        self.student_pending.statut_compte = "ACTIVE"
        self.student_pending.save()

        # Re-tentative
        login_success = self.client.login(email="pending@example.com", password="Password123!")
        self.assertTrue(login_success)

    def test_admin_dashboard_permissions(self):
        """Seul l'admin a accès au tableau de bord administration."""
        # Non connecté
        response = self.client.get(reverse("dashboard_admin"))
        self.assertEqual(response.status_code, 302) # Redirection login

        # Connecté en tant qu'élève actif
        self.student_pending.is_active = True
        self.student_pending.statut_compte = "ACTIVE"
        self.student_pending.save()
        self.client.login(email="pending@example.com", password="Password123!")
        response = self.client.get(reverse("dashboard_admin"))
        self.assertEqual(response.status_code, 403)

        # Connecté en tant qu'admin
        self.client.login(email="admin@example.com", password="Password123!")
        response = self.client.get(reverse("dashboard_admin"))
        self.assertEqual(response.status_code, 200)


class ApprentissageTests(TestCase):
    def setUp(self):
        self.niveau = Niveau.objects.create(code="NV_B", nom="Niveau B", ordre=2)
        self.classe = Classe.objects.create(
            niveau=self.niveau,
            code="CLS_B",
            nom="Classe B",
            annee_scolaire="2026",
            capacite=20
        )
        self.formateur1 = Utilisateur.objects.create_user(
            email="f1@example.com", password="Password123!", role="FORMATEUR", is_formateur=True, is_active=True, statut_compte="ACTIVE"
        )
        self.formateur2 = Utilisateur.objects.create_user(
            email="f2@example.com", password="Password123!", role="FORMATEUR", is_formateur=True, is_active=True, statut_compte="ACTIVE"
        )
        self.student = Utilisateur.objects.create_user(
            email="student@example.com", password="Password123!", role="ELEVE", classe=self.classe, is_active=True, statut_compte="ACTIVE"
        )
        self.cours1 = Cours.objects.create(
            titre="Cours 1", description="Desc 1", niveau=self.niveau, createur=self.formateur1, actif=True
        )
        self.cours2 = Cours.objects.create(
            titre="Cours 2", description="Desc 2", niveau=self.niveau, createur=self.formateur1, actif=False
        )
        self.chapitre1 = Chapitre.objects.create(
            titre="Chapitre 1", description="Desc Chap 1", cours=self.cours1, ordre=1, actif=True
        )
        self.chapitre2 = Chapitre.objects.create(
            titre="Chapitre 2", description="Desc Chap 2", cours=self.cours1, ordre=2, actif=True
        )

    def test_formateur_edit_permissions(self):
        """Un formateur ne peut pas modifier ou supprimer le cours d'un autre."""
        self.client.login(email="f2@example.com", password="Password123!")
        
        # Tentative d'édition du cours de f1
        response = self.client.get(reverse("apprentissage:gerer_cours", args=[self.cours1.id]))
        self.assertEqual(response.status_code, 403)

    def test_student_sees_only_published_cours(self):
        """Un élève ne voit que les cours actifs/publiés de son niveau."""
        self.client.login(email="student@example.com", password="Password123!")
        response = self.client.get(reverse("apprentissage:liste_cours"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.cours1.titre)
        self.assertNotContains(response, self.cours2.titre)

    def test_upload_validation(self):
        """Rejet des fichiers de taille excessive ou d'extension non autorisée."""
        # Fichier non PDF
        invalid_ext_file = SimpleUploadedFile("test.txt", b"Contenu texte factice", content_type="text/plain")
        doc_invalid = Document(
            titre="Doc Invalide",
            chapitre=self.chapitre1,
            type_document="TP",
            fichier_pdf=invalid_ext_file
        )
        with self.assertRaises(ValidationError):
            doc_invalid.full_clean()

        # Fichier PDF trop volumineux (> 10 Mo)
        large_pdf = SimpleUploadedFile("large.pdf", b"0" * (11 * 1024 * 1024), content_type="application/pdf")
        doc_large = Document(
            titre="Doc Volumineux",
            chapitre=self.chapitre1,
            type_document="TP",
            fichier_pdf=large_pdf
        )
        with self.assertRaises(ValidationError):
            doc_large.full_clean()

    def test_progression_calculation(self):
        """Vérifie le calcul correct du pourcentage de progression."""
        prog = Progression.objects.create(etudiant=self.student, cours=self.cours1)
        
        # 0 chapitre validé
        self.assertEqual(prog.pourcentage, 0)
        
        # 1/2 chapitres validés
        prog.chapitres_valides.add(self.chapitre1)
        self.assertEqual(prog.pourcentage, 50)
        
        # 2/2 chapitres validés
        prog.chapitres_valides.add(self.chapitre2)
        self.assertEqual(prog.pourcentage, 100)

    def test_analytics_pure_functions(self):
        """Teste les fonctions pures du module analytics."""
        prog = Progression.objects.create(etudiant=self.student, cours=self.cours1)
        prog.chapitres_valides.add(self.chapitre1)

        # Session QCM pour le chapitre 1
        SessionQCM.objects.create(
            etudiant=self.student,
            chapitre=self.chapitre1,
            score=90,
            statut="TERMINEE"
        )

        # Appel aux fonctions analytics
        c_stats = stats_cours(self.cours1)
        self.assertEqual(c_stats["nb_inscrits"], 1)
        self.assertEqual(c_stats["taux_completion_moyen"], 50.0)
        self.assertEqual(c_stats["score_qcm_moyen"], 90.0)

        f_stats = stats_formateur(self.formateur1)
        self.assertEqual(f_stats["total_cours"], 2)
        self.assertEqual(f_stats["total_inscrits"], 1)

        diff = stats_eleves_en_difficulte(self.cours1, seuil=60)
        # student a 50% de progression (< 60%), donc en difficulté
        self.assertEqual(len(diff), 1)
        self.assertEqual(diff[0]["email"], self.student.email)

        platform = stats_plateforme()
        self.assertEqual(platform["nb_cours_publies"], 1)


class TuteurIATests(TestCase):
    def setUp(self):
        self.niveau = Niveau.objects.create(code="NV_C", nom="Niveau C", ordre=3)
        self.classe = Classe.objects.create(
            niveau=self.niveau,
            code="CLS_C",
            nom="Classe C",
            annee_scolaire="2026",
            capacite=20
        )
        self.student1 = Utilisateur.objects.create_user(
            email="st1@example.com", password="Password123!", role="ELEVE", classe=self.classe, is_active=True, statut_compte="ACTIVE"
        )
        self.student2 = Utilisateur.objects.create_user(
            email="st2@example.com", password="Password123!", role="ELEVE", classe=self.classe, is_active=True, statut_compte="ACTIVE"
        )
        self.cours = Cours.objects.create(
            titre="Cours C", description="Desc C", niveau=self.niveau, actif=True
        )
        self.chapitre = Chapitre.objects.create(
            titre="Chapitre C", description="Desc Chap C", cours=self.cours, ordre=1, actif=True
        )
        
        # Session QCM
        self.questions = [
            {"question": "Q1", "options": ["A", "B"], "reponse_correcte": "A", "explication": "Ex1"},
            {"question": "Q2", "options": ["A", "B"], "reponse_correcte": "B", "explication": "Ex2"}
        ]
        self.session_qcm = SessionQCM.objects.create(
            etudiant=self.student1,
            chapitre=self.chapitre,
            questions=self.questions,
            statut="EN_COURS"
        )

    def test_qcm_correction(self):
        """Vérifie que corriger_qcm calcule correctement le score et met à jour le statut."""
        self.client.login(email="st1@example.com", password="Password123!")
        
        # Envoi des réponses : 1 correcte, 1 incorrecte (Score = 50%)
        reponses = {"0": "A", "1": "A"}
        response = self.client.post(
            reverse("tuteur_ia:corriger_qcm", args=[self.session_qcm.id]),
            data=json.dumps({"reponses": reponses}),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        
        # Vérification en base de données
        self.session_qcm.refresh_from_db()
        self.assertEqual(self.session_qcm.score, 50)
        self.assertEqual(self.session_qcm.statut, "ECHOUEE")

    def test_qcm_isolation(self):
        """Un élève ne peut pas accéder ou modifier la session QCM d'un autre élève."""
        self.client.login(email="st2@example.com", password="Password123!")
        
        # Tentative d'accès à la session QCM de st1
        response = self.client.get(reverse("tuteur_ia:resultats_qcm", args=[self.session_qcm.id]))
        self.assertEqual(response.status_code, 403)


class APIRestTests(APITestCase):
    def setUp(self):
        self.niveau = Niveau.objects.create(code="NV_D", nom="Niveau D", ordre=4)
        self.classe = Classe.objects.create(
            niveau=self.niveau,
            code="CLS_D",
            nom="Classe D",
            annee_scolaire="2026",
            capacite=20
        )
        self.formateur = Utilisateur.objects.create_user(
            email="f_api@example.com", password="Password123!", role="FORMATEUR", is_formateur=True, is_active=True, statut_compte="ACTIVE"
        )
        self.student = Utilisateur.objects.create_user(
            email="s_api@example.com", password="Password123!", role="ELEVE", classe=self.classe, is_active=True, statut_compte="ACTIVE"
        )
        self.cours = Cours.objects.create(
            titre="Cours API", description="Desc API", niveau=self.niveau, createur=self.formateur, actif=True
        )

        # Jetons d'authentification
        self.token_formateur = Token.objects.create(user=self.formateur)
        self.token_student = Token.objects.create(user=self.student)

    def test_api_requires_auth(self):
        """L'accès à l'API requiert d'être authentifié."""
        response = self.client.get("/api/cours/")
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_api_me(self):
        """L'endpoint /api/me/ renvoie les informations du profil connecté."""
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token_student.key)
        response = self.client.get("/api/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], self.student.email)
        self.assertEqual(response.data["role"], "ELEVE")

    def test_api_permissions(self):
        """Vérifie la permission IsCreateurOrReadOnly sur les cours."""
        # 1. Un élève ne peut pas créer de cours
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token_student.key)
        data = {"titre": "Cours interdit", "description": "Interdit", "niveau": str(self.niveau.id)}
        response = self.client.post("/api/cours/", data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Un formateur peut créer un cours
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token_formateur.key)
        response = self.client.post("/api/cours/", data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 3. Un élève peut lire les cours
        self.client.credentials(HTTP_AUTHORIZATION="Token " + self.token_student.key)
        response = self.client.get(f"/api/cours/{self.cours.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class RagAssistantTests(TestCase):
    def setUp(self):
        self.niveau = Niveau.objects.create(code="NV_T", nom="Niveau Test", ordre=1)
        self.student = Utilisateur.objects.create_user(
            email="student_rag@example.com",
            password="Password123!",
            role="ELEVE",
            is_active=True,
            statut_compte="ACTIVE"
        )
        self.formateur = Utilisateur.objects.create_user(
            email="formateur_rag@example.com",
            password="Password123!",
            role="FORMATEUR",
            is_active=True,
            statut_compte="ACTIVE"
        )
        self.cours = Cours.objects.create(
            titre="Cours IoT",
            description="IoT Course description",
            niveau=self.niveau,
            createur=self.formateur,
            actif=True
        )
        self.chapitre = Chapitre.objects.create(
            cours=self.cours,
            titre="Introduction IoT",
            description="Chapitre intro",
            ordre=1,
            actif=True
        )

    def test_demarrer_assistant(self):
        """Démarrer l'assistant crée/récupère la session et renvoie les détails en JSON."""
        self.client.login(email="student_rag@example.com", password="Password123!")
        url = reverse("tuteur_ia:demarrer_assistant", args=[self.chapitre.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("session_id", data)
        self.assertEqual(data["messages"], [])

        # Tester qu'une session a bien été créée en BDD
        from tuteur_ia.models import SessionAssistant
        self.assertTrue(SessionAssistant.objects.filter(etudiant=self.student, chapitre=self.chapitre).exists())

    def test_poser_question_empty(self):
        """Poser une question vide renvoie une erreur 400."""
        self.client.login(email="student_rag@example.com", password="Password123!")
        from tuteur_ia.models import SessionAssistant
        session = SessionAssistant.objects.create(
            etudiant=self.student,
            chapitre=self.chapitre
        )
        url = reverse("tuteur_ia:poser_question", args=[session.id])
        response = self.client.post(url, json.dumps({"question": ""}), content_type="application/json")
        self.assertEqual(response.status_code, 400)


class ChapterValidationTests(TestCase):
    def setUp(self):
        self.niveau = Niveau.objects.create(code="NV_VAL", nom="Niveau Val", ordre=10)
        self.classe = Classe.objects.create(
            niveau=self.niveau,
            code="CLS_VAL",
            nom="Classe Val",
            annee_scolaire="2026",
            capacite=20
        )
        self.student = Utilisateur.objects.create_user(
            email="student_val@example.com",
            password="Password123!",
            role="ELEVE",
            classe=self.classe,
            is_active=True,
            statut_compte="ACTIVE"
        )
        self.formateur = Utilisateur.objects.create_user(
            email="formateur_val@example.com",
            password="Password123!",
            role="FORMATEUR",
            is_active=True,
            statut_compte="ACTIVE"
        )
        self.cours = Cours.objects.create(
            titre="Cours Val",
            description="Desc Val",
            niveau=self.niveau,
            createur=self.formateur,
            actif=True
        )
        self.chapitre1 = Chapitre.objects.create(
            cours=self.cours,
            titre="Chapitre 1",
            description="Description 1",
            ordre=1,
            actif=True
        )
        self.chapitre2 = Chapitre.objects.create(
            cours=self.cours,
            titre="Chapitre 2",
            description="Description 2",
            ordre=2,
            actif=True
        )

    def test_validation_fails_without_passing_qcm(self):
        """La validation doit échouer si aucun QCM n'a été réussi (score >= 80%)."""
        self.client.login(email="student_val@example.com", password="Password123!")
        url = reverse("apprentissage:valider_chapitre", args=[self.chapitre1.id])
        
        # Cas 1: Aucun QCM passé
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Validation requise")
        self.assertContains(response, "Passer le QCM")
        
        # Cas 2: QCM échoué (score < 80)
        SessionQCM.objects.create(
            etudiant=self.student,
            chapitre=self.chapitre1,
            score=70,
            statut="ECHOUEE"
        )
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Validation requise")
        self.assertContains(response, "Passer le QCM")

    def test_validation_succeeds_with_passing_qcm(self):
        """La validation réussit s'il y a un QCM réussi (score >= 80%)."""
        self.client.login(email="student_val@example.com", password="Password123!")
        url = reverse("apprentissage:valider_chapitre", args=[self.chapitre1.id])
        
        # Création d'une session QCM réussie
        SessionQCM.objects.create(
            etudiant=self.student,
            chapitre=self.chapitre1,
            score=90,
            statut="TERMINEE"
        )
        
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        # Vérification qu'il propose de passer au chapitre suivant
        self.assertContains(response, "Passer au chapitre suivant")
        
        # Vérifier en BDD
        from apprentissage.models import ChapitreComplete, Progression
        self.assertTrue(ChapitreComplete.objects.filter(etudiant=self.student, chapitre=self.chapitre1).exists())
        
        progression = Progression.objects.get(etudiant=self.student, cours=self.cours)
        self.assertIn(self.chapitre1, progression.chapitres_valides.all())


from logistics.models import Equipment, DemandeMateriel

class EquipmentRequestTests(TestCase):
    def setUp(self):
        self.student = Utilisateur.objects.create_user(
            email="st_req@example.com", password="Password123!", role="ELEVE", is_active=True, statut_compte="ACTIVE"
        )
        self.formateur1 = Utilisateur.objects.create_user(
            email="f_req1@example.com", password="Password123!", role="FORMATEUR", is_active=True, statut_compte="ACTIVE"
        )
        self.formateur2 = Utilisateur.objects.create_user(
            email="f_req2@example.com", password="Password123!", role="FORMATEUR", is_active=True, statut_compte="ACTIVE"
        )
        self.equipement = Equipment.objects.create(
            nom="Oscilloscope",
            numero_serie="OSC-12345",
            etat="DISPONIBLE"
        )

    def test_student_can_create_request(self):
        """Un élève peut formuler une demande de matériel et le destinataire est notifié."""
        self.client.login(email="st_req@example.com", password="Password123!")
        
        # Soumettre une demande adressée à formateur1
        response = self.client.post(
            reverse("dashboard_student_create_demande"),
            {
                "equipement": str(self.equipement.id),
                "destinataire": str(self.formateur1.id),
                "quantite": 2,
                "atelier_cible": ""
            }
        )
        self.assertEqual(response.status_code, 200)
        from django.contrib.messages import get_messages
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Demande envoyée avec succès !")
        
        # Vérifier en BDD
        demande = DemandeMateriel.objects.filter(demandeur=self.student, equipement=self.equipement).first()
        self.assertIsNotNone(demande)
        self.assertEqual(demande.quantite, 2)
        self.assertEqual(demande.destinataire, self.formateur1)
        self.assertEqual(demande.statut, "PENDING")
        
        # Vérifier la notification reçue par le formateur1
        notif = Notification.objects.filter(destinataire=self.formateur1, type="NOUVELLE_DEMANDE").first()
        self.assertIsNotNone(notif)
        self.assertIn("Oscilloscope", notif.message)

    def test_processing_permissions(self):
        """Seul l'admin ou le formateur destinataire peut traiter la demande."""
        demande = DemandeMateriel.objects.create(
            demandeur=self.student,
            destinataire=self.formateur1,
            equipement=self.equipement,
            quantite=1
        )
        
        # Cas 1: Le mauvais formateur (formateur2) essaie de traiter -> 403
        self.client.login(email="f_req2@example.com", password="Password123!")
        url = reverse("dashboard_admin_process_demande", args=[demande.id])
        response = self.client.post(url, {"action": "approve"})
        self.assertEqual(response.status_code, 403)
        
        # Cas 2: Le bon formateur (formateur1) traite -> 200 (re-rend le partiel)
        self.client.login(email="f_req1@example.com", password="Password123!")
        response = self.client.post(url, {"action": "approve"})
        self.assertEqual(response.status_code, 200)
        
        demande.refresh_from_db()
        self.assertEqual(demande.statut, "APPROVED")
        
        # L'élève reçoit une notification
        notif = Notification.objects.filter(destinataire=self.student, type="DEMANDE_TRAITEE").first()
        self.assertIsNotNone(notif)
        self.assertIn("approuvée", notif.message)

    def test_student_cannot_request_quantity_outside_limits(self):
        """Un élève ne peut pas demander une quantité inférieure à 1 ou supérieure à 2."""
        self.client.login(email="st_req@example.com", password="Password123!")
        
        # Cas 1: Quantité = 0 -> Devrait échouer
        response = self.client.post(
            reverse("dashboard_student_create_demande"),
            {
                "equipement": str(self.equipement.id),
                "destinataire": str(self.formateur1.id),
                "quantite": 0,
                "atelier_cible": ""
            }
        )
        # S'il y a des erreurs, la vue réaffiche le formulaire avec les erreurs (ou renvoie les erreurs dans le modal)
        # Vérifions que la demande n'a pas été créée en BDD
        self.assertFalse(DemandeMateriel.objects.filter(demandeur=self.student, quantite=0).exists())

        # Cas 2: Quantité = 3 -> Devrait échouer
        response = self.client.post(
            reverse("dashboard_student_create_demande"),
            {
                "equipement": str(self.equipement.id),
                "destinataire": str(self.formateur1.id),
                "quantite": 3,
                "atelier_cible": ""
            }
        )
        self.assertFalse(DemandeMateriel.objects.filter(demandeur=self.student, quantite=3).exists())




