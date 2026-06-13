import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class Niveau(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.SlugField(max_length=50, unique=True)
    nom = models.CharField(max_length=120, unique=True)
    ordre = models.PositiveIntegerField(default=0)
    actif = models.BooleanField(default=True)

    class Meta:
        ordering = ['ordre', 'nom']
        verbose_name = 'Niveau'
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
        verbose_name = 'Classe'
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
        ('ELEVE', 'Élève'),
        ('FORMATEUR', 'Formateur'),
        ('ADMIN', 'Administrateur'),
    )

    STATUT_COMPTE_CHOICES = (
        ('PENDING', 'En attente'),
        ('ACTIVE', 'Actif'),
    )

    # Correspondance avec le cahier des charges(email unique, rôle, etc.)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) 
    email = models.EmailField(unique=True, max_length=255) 
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='ELEVE') 
    statut_compte = models.CharField(max_length=20, choices=STATUT_COMPTE_CHOICES, default='PENDING')
    classe = models.ForeignKey(Classe, on_delete=models.SET_NULL, null=True, blank=True, related_name='eleves')
    date_creation = models.DateTimeField(auto_now_add=True) 

    # Requis par Django pour les modèles utilisateurs personnalisés
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    is_formateur = models.BooleanField(default=False)

    objects = UtilisateurManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] # Email est déjà requis par USERNAME_FIELD

    def __str__(self):
        return f"{self.email} - {self.role}"

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