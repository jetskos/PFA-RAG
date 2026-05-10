import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin

class UtilisateurManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('L\'adresse email est obligatoire.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        # Django gère automatiquement le hachage avec bcrypt (via set_password)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')

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

    NIVEAU_CHOICES = (
        ('DEBUTANT', 'Débutant'),
        ('INTERMEDIAIRE', 'Intermédiaire'),
        ('AVANCE', 'Avancé'),
    )

    # Correspondance avec le cahier des charges(email unique, rôle, etc.)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False) 
    email = models.EmailField(unique=True, max_length=255) 
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='ELEVE') 
    niveau = models.CharField(max_length=20, choices=NIVEAU_CHOICES, default='DEBUTANT')
    date_creation = models.DateTimeField(auto_now_add=True) 

    # Requis par Django pour les modèles utilisateurs personnalisés
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_formateur = models.BooleanField(default=False)

    objects = UtilisateurManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = [] # Email est déjà requis par USERNAME_FIELD

    def __str__(self):
        return f"{self.email} - {self.role}"    