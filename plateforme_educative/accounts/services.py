from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import logging

from .models import Utilisateur, Classe, Niveau
from .tasks import envoyer_email_task

logger = logging.getLogger(__name__)


class UserService:
    """
    Service class to handle business logic for user management.
    """

    @staticmethod
    def update_user(user: Utilisateur, data: dict, request_user: Utilisateur) -> tuple[bool, str]:
        """
        Met à jour les informations d'un utilisateur, en appliquant les règles métiers
        (changement de statut, affectation de rôle, envoi d'emails).
        
        Args:
            user (Utilisateur): L'utilisateur à modifier
            data (dict): Les données de la requête POST (role, classe_id, niveau)
            request_user (Utilisateur): L'utilisateur qui fait la requête (pour permissions)
            
        Returns:
            tuple[bool, str]: (Success, Error Message if any)
        """
        role = data.get('role')
        classe_id = data.get('classe_id')
        niveau_id = data.get('niveau')

        # Mise à jour du rôle
        if role in dict(Utilisateur.ROLE_CHOICES):
            user.role = role
            user.is_formateur = (role == 'FORMATEUR')
            if role == 'ADMIN':
                user.is_staff = True
                user.is_superuser = True
            else:
                user.is_staff = False
                user.is_superuser = False

        # Affectation de la classe ou du niveau
        if classe_id:
            try:
                user.classe = Classe.objects.get(pk=classe_id)
            except Classe.DoesNotExist:
                return False, 'Classe introuvable'
        elif niveau_id:
            try:
                niveau = Niveau.objects.get(pk=niveau_id)
            except Niveau.DoesNotExist:
                return False, 'Niveau introuvable'
            
            user.classe = (
                Classe.objects.filter(niveau=niveau, actif=True)
                .order_by('annee_scolaire', 'nom')
                .first()
            )
        
        # Logique des statuts selon le rôle et la classe
        if role == 'ELEVE' and not user.classe:
            user.statut_compte = 'PENDING'
            user.is_active = False
        elif role != 'ELEVE':
            user.statut_compte = 'ACTIVE'
            user.is_active = True

        # Gestion de l'email de bienvenue pour les élèves
        if user.is_active and user.statut_compte == 'ACTIVE' and user.role == 'ELEVE':
            try:
                ctx = {
                    'user': user,
                    'base_url': getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
                }
                html_content = render_to_string('accounts/emails/activation_email.html', ctx)
                text_content = strip_tags(html_content)
                envoyer_email_task.delay(
                    subject=str(_("Votre compte EduTech est activé !")),
                    text_content=text_content,
                    html_content=html_content,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to_list=[user.email],
                )
            except Exception as e:
                logger.error(f"Erreur d'envoi d'e-mail d'activation à {user.email}: {e}")

        user.save()
        return True, ''

    @staticmethod
    def delete_user(user: Utilisateur, request_user: Utilisateur) -> tuple[bool, str]:
        """
        Supprime un utilisateur avec vérifications.
        """
        if str(user.pk) == str(request_user.pk):
            return False, _('Vous ne pouvez pas supprimer votre propre compte.')
        if user.is_superuser:
            return False, _('Impossible de supprimer un superuser.')
        
        user.delete()
        return True, ''
