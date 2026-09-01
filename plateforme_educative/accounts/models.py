import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.translation import gettext_lazy as _


class Niveau(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=50, unique=True)
    nom = models.CharField(max_length=120, unique=True)
    ordre = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = _('Niveau')
        verbose_name_plural = 'Niveaux'

    def __str__(self):
        return self.nom


class Classe(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    niveau = models.ForeignKey(Niveau, on_delete=models.PROTECT, related_name='classes')
    code = models.CharField(max_length=50)
    nom = models.CharField(max_length=120)
    annee_scolaire = models.CharField(max_length=20)
    capacite = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['niveau__ordre', 'nom']
        verbose_name = _('Classe')
        verbose_name_plural = 'Classes'
        constraints = [
            models.UniqueConstraint(
                fields=['niveau', 'code', 'annee_scolaire'],
                name='uniq_classe_par_niveau_code_annee',
            )
        ]

    def __str__(self):
        return f"{self.nom} ({self.niveau})"

class UtilisateurManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('L\'adresse email est obligatoire.')
        email = self.normalize_email(email)
        extra_fields.setdefault('role', 'ELEVE')
        extra_fields.setdefault('statut_compte', 'PENDING')
        extra_fields.setdefault('is_active', False)
        user = self.model(email=email, **extra_fields)
        # Django gère automatiquement le hachage avec bcrypt (via set_password)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('statut_compte', 'ACTIVE')
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_formateur', False)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser doit avoir is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser doit avoir is_superuser=True.')

        return self.create_user(email, password, **extra_fields)
    
class Utilisateur(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('ELEVE', _('Élève')),
        ('FORMATEUR', _('Formateur')),
        ('ADMIN', _('Administrateur')),
    )

    STATUT_COMPTE_CHOICES = (
        ('PENDING', _('En attente')),
        ('ACTIVE', _('Actif')),
    )

    # Correspondance avec le cahier des charges(email unique, rôle, etc.)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) 
    email = models.EmailField(unique=True, max_length=255, verbose_name=_('Adresse e-mail')) 
    first_name = models.CharField(max_length=150, blank=True, null=True, verbose_name=_("Prénom"))
    last_name = models.CharField(max_length=150, blank=True, null=True, verbose_name=_("Nom"))
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='ELEVE') 
    statut_compte = models.CharField(max_length=20, choices=STATUT_COMPTE_CHOICES, default='PENDING')
    classe = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True, related_name='eleves')
    photo = models.ImageField(upload_to='avatars/', null=True, blank=True, verbose_name=_('Photo de profil'))
    date_creation = models.DateTimeField(auto_now_add=True) 

    # Requis par Django pour les modèles utilisateurs personnalisés
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_formateur = models.BooleanField(default=False)
    onboarding_completed = models.BooleanField(default=False)
    
    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]

    @property
    def nom_affichage(self):
        """Nom lisible pour l'affichage personnel (salutations, en-têtes, avatar).

        Ne renvoie JAMAIS l'adresse e-mail complète à l'écran : à défaut de
        prénom/nom, on présente la partie locale de l'e-mail en capitales
        (ex. « jean.dupont@ecole.ma » -> « Jean Dupont »).
        """
        fn = (self.first_name or "").strip()
        ln = (self.last_name or "").strip()
        if fn and ln:
            return f"{fn} {ln}"
        if fn:
            return fn
        local = self.email.split("@")[0]
        return local.replace(".", " ").replace("_", " ").replace("-", " ").strip().title() or self.email

    # Gestion des mots de passe temporaires expirables
    is_temp_password = models.BooleanField(default=False)
    temp_password_created_at = models.DateTimeField(null=True, blank=True)

    objects = UtilisateurManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] # Email est déjà requis par USERNAME_FIELD

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_role = self.role
        self._original_statut = self.statut_compte

    def save(self, *args, **kwargs):
        if self.role == 'FORMATEUR':
            self.is_formateur = True
            self.is_staff = False
            self.is_superuser = False
        elif self.role == 'ADMIN':
            self.is_formateur = False
            self.is_staff = True
            self.is_superuser = True
        else:
            self.is_formateur = False
            self.is_staff = False
            self.is_superuser = False
            
        is_new = getattr(self, '_state', None) and getattr(self._state, 'adding', False)
        super().save(*args, **kwargs)

        # Logique d'envoi d'e-mail pour les nouveaux rôles / activations
        if getattr(self, 'role', '') in ['ADMIN', 'FORMATEUR']:
            role_changed = not is_new and getattr(self, 'role', '') != getattr(self, '_original_role', '')
            statut_changed = not is_new and getattr(self, 'statut_compte', '') == 'ACTIVE' and getattr(self, '_original_statut', '') != 'ACTIVE'
            is_new_active = is_new and getattr(self, 'statut_compte', '') == 'ACTIVE'
            
            if role_changed or statut_changed or is_new_active:
                # Update tracker to avoid multiple emails on subsequent saves in the same instance
                self._original_role = self.role
                self._original_statut = self.statut_compte
                self.send_role_activation_email()

    def send_role_activation_email(self):
        """Envoie l'e-mail premium d'activation/changement de rôle et crée une notification in-app"""
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        from django.conf import settings
        from accounts.tasks import envoyer_email_task
        from accounts.models import Notification
        import logging

        logger = logging.getLogger(__name__)

        # 1. Créer la notification In-App
        try:
            titre = _("Félicitations, vous êtes maintenant Formateur !") if self.role == 'FORMATEUR' else _("Félicitations, vous êtes maintenant Administrateur !")
            Notification.objects.create(
                destinataire=self,
                type='COMPTE_ACTIVE',
                titre=titre,
                message=_("Vos droits d'accès ont été mis à jour. Bienvenue dans l'équipe !"),
                url='/dashboard/formateur/' if self.role == 'FORMATEUR' else '/dashboard/admin/'
            )
        except Exception as e:
            logger.error(f"Erreur création notification in-app pour {self.email} : {e}")
        
        try:
            subject = str(_("[EduTech] Votre compte est activé - Bienvenue dans l'équipe !"))
            base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
            login_url = f"{base_url}/accounts/login/"
            
            context = {
                'destinataire': self,
                'base_url': base_url,
                'login_url': login_url
            }
            
            html_content = render_to_string('accounts/emails/role_activation.html', context)
            text_content = strip_tags(html_content)
            
            envoyer_email_task.delay(
                subject=subject,
                text_content=text_content,
                html_content=html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to_list=[self.email],
            )
            logger.info(f"E-mail premium d'activation planifié pour {self.email} ({self.role})")
        except Exception as e:
            logger.error(f"Erreur lors de la planification de l'e-mail d'activation pour {self.email} : {e}")

    def __str__(self):
        return self.get_full_name()

    @property
    def niveau(self):
        if self.classe and self.classe.niveau:
            return str(self.classe.niveau.id)
        return ''

    @property
    def niveau_label(self):
        if self.classe and self.classe.niveau:
            return self.classe.niveau.nom
        return ''


class Notification(models.Model):
    TYPE_CHOICES = (
        ('COMPTE_ACTIVE', _('Compte Activé')),
        ('QCM_CORRIGE', _('QCM Corrigé')),
        ('NOUVEAU_COURS', _('Nouveau Cours')),
        ('DEMANDE_TRAITEE', _('Demande Traitée')),
        ('NOUVELLE_INSCRIPTION', _('Nouvelle Inscription')),
        ('NOUVELLE_DEMANDE', _('Nouvelle Demande')),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    destinataire = models.ForeignKey(
        Utilisateur,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('Destinataire')
    )
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        verbose_name=_('Type de notification')
    )
    titre = models.CharField(max_length=255, verbose_name=_('Titre'))
    message = models.TextField(verbose_name=_('Message'))
    url = models.CharField(max_length=512, blank=True, null=True, verbose_name=_('URL associée'))
    lu = models.BooleanField(default=False, verbose_name=_('Lu'))
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_('Date de création'))

    class Meta:
        ordering = ['-date_creation']
        verbose_name = _('Notification')
        verbose_name_plural = 'Notifications'

    @property
    def age_humanise(self):
        from django.utils import timezone
        from django.utils.translation import gettext, ngettext
        delta = timezone.now() - self.date_creation
        if delta.days == 0:
            seconds = delta.seconds
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            if hours > 0:
                return gettext("Il y a %(n)s h") % {"n": hours}
            elif minutes > 0:
                return gettext("Il y a %(n)s min") % {"n": minutes}
            else:
                return gettext("À l'instant")
        elif delta.days == 1:
            return gettext("Hier")
        else:
            return ngettext("Il y a %(n)s jour", "Il y a %(n)s jours", delta.days) % {"n": delta.days}

    def __str__(self):
        return f"{self.titre} -> {self.destinataire.email} ({'Lu' if self.lu else 'Non lu'})"

class ConfigurationSysteme(models.Model):
    id = models.IntegerField(primary_key=True, default=1)
    
    mode_hors_ligne = models.BooleanField(
        default=False, 
        verbose_name=_("Mode Hors-Ligne"),
        help_text=_("Active le mode déconnecté. Coupe l'envoi d'e-mails et force l'IA locale.")
    )
    
    PROVIDER_CHOICES = (
        ('AUTO', _('Automatique (Groq -> Ollama)')),
        ('GROQ', _('Forcer Groq (API)')),
        ('OPENAI', _('Forcer OpenAI (API)')),
        ('OLLAMA', _('Forcer Ollama (Local)')),
    )
    llm_provider = models.CharField(
        max_length=20, 
        choices=PROVIDER_CHOICES, 
        default='AUTO',
        verbose_name=_("Fournisseur IA (LLM)")
    )
    
    activer_hls = models.BooleanField(
        default=True, 
        verbose_name=_("Activer HLS (Projet FLUTE)"),
        help_text=_("Active la génération de vidéos par morceaux avec FFmpeg.")
    )

    class Meta:
        verbose_name = _("Configuration Système")
        verbose_name_plural = "Configurations Système"

    def save(self, *args, **kwargs):
        self.id = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls):
        config, created = cls.objects.get_or_create(id=1)
        return config