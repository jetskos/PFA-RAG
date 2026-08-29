from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from django.contrib.auth import get_user_model
from datetime import timedelta
from django.core import mail

Utilisateur = get_user_model()
from accounts.models import Notification

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TemporaryPasswordTests(TestCase):
    def setUp(self):
        self.email = "test_user@example.com"
        self.password = "OriginalPassword123!"
        self.user = Utilisateur.objects.create_user(
            email=self.email,
            password=self.password,
            role="ELEVE",
            statut_compte="ACTIVE",
            is_active=True
        )

    def test_user_model_fields(self):
        """Test that default values for temporary password fields are set correctly."""
        self.assertFalse(self.user.is_temp_password)
        self.assertIsNone(self.user.temp_password_created_at)

    def test_custom_password_reset_view(self):
        """Test requesting a password reset generates a temp password and sends an email."""
        response = self.client.post(reverse('accounts:password_reset'), {'email': self.email})
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:password_reset_done'))

        # Check mail was sent
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Votre mot de passe temporaire", mail.outbox[0].subject)
        self.assertIn(self.email, mail.outbox[0].to)

        # Check user fields updated
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_temp_password)
        self.assertIsNotNone(self.user.temp_password_created_at)

    def test_login_with_valid_temp_password(self):
        """Test logging in with a temporary password within the 10-minute window."""
        # Setup temporary password
        temp_pass = "TEMP1234"
        self.user.set_password(temp_pass)
        self.user.is_temp_password = True
        self.user.temp_password_created_at = timezone.now() - timedelta(minutes=5)
        self.user.save()

        # Try to log in
        response = self.client.post(reverse('accounts:login'), {
            'username': self.email,
            'password': temp_pass
        })
        
        # Should redirect to change password view
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:change_password'))

        # Verify user is logged in
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_with_expired_temp_password(self):
        """Test logging in with a temporary password after the 10-minute window."""
        temp_pass = "TEMP5678"
        self.user.set_password(temp_pass)
        self.user.is_temp_password = True
        self.user.temp_password_created_at = timezone.now() - timedelta(minutes=11)
        self.user.save()

        # Try to log in
        response = self.client.post(reverse('accounts:login'), {
            'username': self.email,
            'password': temp_pass
        })

        # Should render the login page with errors
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertFormError(response, 'form', None, "Ce mot de passe temporaire a expiré (validité de 10 minutes). Veuillez effectuer une nouvelle demande.")

    def test_change_password_clears_flags(self):
        """Test that changing password clears the temporary password flags."""
        # Log the user in
        self.client.login(email=self.email, password=self.password)

        # Simulate the user changing their password
        response = self.client.post(reverse('accounts:change_password'), {
            'old_password': self.password,
            'new_password1': 'NewSecurePassword123!',
            'new_password2': 'NewSecurePassword123!'
        })

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('accounts:profile'))

        # Check DB updates
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_temp_password)
        self.assertIsNone(self.user.temp_password_created_at)
        self.assertTrue(self.user.check_password('NewSecurePassword123!'))


class HTMXHistoryRestoreMiddlewareTests(TestCase):
    def test_middleware_removes_hx_request_on_restore_request(self):
        """Test that HTMXHistoryRestoreMiddleware removes the HTTP_HX_REQUEST header when HTTP_HX_HISTORY_RESTORE_REQUEST is true."""
        headers = {
            'HTTP_HX_REQUEST': 'true',
            'HTTP_HX_HISTORY_RESTORE_REQUEST': 'true'
        }
        # Requesting registration page with both headers should bypass partial rendering and return full page.
        response = self.client.get(reverse('accounts:register'), **headers)
        
        # Ensure it contains the main DOCTYPE showing it's a full page rendering
        self.assertContains(response, "<!DOCTYPE html>")

    def test_middleware_adds_vary_hx_request_header(self):
        """Test that HTMXHistoryRestoreMiddleware adds 'HX-Request' to the 'Vary' header of the response."""
        response = self.client.get(reverse('accounts:login'))
        self.assertIn('Vary', response)
        self.assertIn('HX-Request', response['Vary'])

    def test_middleware_disables_cache_on_htmx_requests(self):
        """Test that HTMXHistoryRestoreMiddleware disables caching on HTMX requests."""
        headers = {
            'HTTP_HX_REQUEST': 'true'
        }
        response = self.client.get(reverse('accounts:register'), **headers)
        self.assertEqual(response['Cache-Control'], 'no-cache, no-store, must-revalidate')
        self.assertEqual(response['Pragma'], 'no-cache')
        self.assertEqual(response['Expires'], '0')


class RegistrationNotificationTests(TestCase):
    def setUp(self):
        self.admin = Utilisateur.objects.create_user(
            email="admin_test_notif@example.com",
            password="AdminPassword123!",
            role="ADMIN",
            statut_compte="ACTIVE",
            is_active=True
        )
        self.superuser = Utilisateur.objects.create_superuser(
            email="superuser_test_notif@example.com",
            password="SuperuserPassword123!",
            is_active=True
        )

    def test_student_registration_creates_notifications_for_admins(self):
        """Test that registering a new student generates notification alerts for all admins and superusers."""
        response = self.client.post(reverse('accounts:register'), {
            'email': 'new_student_test@example.com',
            'password1': 'NewStudentPass123!',
            'password2': 'NewStudentPass123!',
            'role': 'ELEVE'
        })
        self.assertEqual(response.status_code, 302)

        # Check notifications generated for admin
        admin_notifs = Notification.objects.filter(destinataire=self.admin, type='NOUVELLE_INSCRIPTION')
        self.assertEqual(admin_notifs.count(), 1)
        self.assertIn('new_student_test@example.com', admin_notifs.first().message)
        self.assertEqual(admin_notifs.first().url, reverse('dashboard_admin_structure') + '?tab=students')

        # Check notifications generated for superuser
        super_notifs = Notification.objects.filter(destinataire=self.superuser, type='NOUVELLE_INSCRIPTION')
        self.assertEqual(super_notifs.count(), 1)

    def test_student_activation_deletes_registration_notification(self):
        """Test that activating a pending student deletes their registration notifications."""
        from accounts.models import Niveau, Classe

        # 1. Register student
        self.client.post(reverse('accounts:register'), {
            'email': 'new_student_test@example.com',
            'password1': 'NewStudentPass123!',
            'password2': 'NewStudentPass123!',
            'role': 'ELEVE'
        })

        # Check notification exists initially
        admin_notifs = Notification.objects.filter(destinataire=self.admin, type='NOUVELLE_INSCRIPTION')
        self.assertEqual(admin_notifs.count(), 1)
        self.assertFalse(admin_notifs.first().lu)

        # 2. Setup Niveau and Classe
        niveau = Niveau.objects.create(code="nv1", nom="Niveau 1", ordre=1)
        classe = Classe.objects.create(niveau=niveau, code="cls1", nom="Classe 1", annee_scolaire="2026", capacite=30)

        # 3. Log in as admin
        self.client.login(email="admin_test_notif@example.com", password="AdminPassword123!")

        # 4. Get the student object
        student = Utilisateur.objects.get(email='new_student_test@example.com')

        # 5. Activate the student via the POST view
        response = self.client.post(reverse('dashboard_admin_activate_pending_student'), {
            'student_id': str(student.id),
            'classe': str(classe.id)
        })
        self.assertEqual(response.status_code, 200)

        # 6. Verify notification is deleted
        admin_notifs = Notification.objects.filter(destinataire=self.admin, type='NOUVELLE_INSCRIPTION')
        self.assertEqual(admin_notifs.count(), 0)





