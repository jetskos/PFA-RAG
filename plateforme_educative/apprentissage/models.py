import uuid
from django.db import models
from django.core.validators import URLValidator


class Cours(models.Model):
    """Modèle représentant un cours dans la plateforme."""
    
    NIVEAU_CHOICES = (
        ('DEBUTANT', 'Débutant'),
        ('INTERMEDIAIRE', 'Intermédiaire'),
        ('AVANCE', 'Avancé'),
        ('EXPERT', 'Expert'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(
        max_length=255,
        verbose_name='Titre du cours'
    )
    description = models.TextField(
        verbose_name='Description'
    )
    niveau = models.CharField(
        max_length=20,
        choices=NIVEAU_CHOICES,
        default='DEBUTANT',
        verbose_name='Niveau'
    )
    resume = models.TextField(
        verbose_name='Résumé court',
        blank=True,
        help_text='Résumé affiché dans les listes'
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name='Date de modification'
    )
    actif = models.BooleanField(
        default=True,
        verbose_name='Actif'
    )
    createur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cours_crees',
        verbose_name='Créateur'
    )
    
    class Meta:
        verbose_name = 'Cours'
        verbose_name_plural = 'Cours'
        ordering = ['-date_creation']
    
    def __str__(self):
        return f"{self.titre} ({self.niveau})"


class Chapitre(models.Model):
    """Modèle représentant un chapitre dans un cours."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name='chapitres',
        verbose_name='Cours'
    )
    titre = models.CharField(
        max_length=255,
        verbose_name='Titre du chapitre'
    )
    description = models.TextField(
        verbose_name='Description',
        blank=True
    )
    ordre = models.PositiveIntegerField(
        verbose_name='Ordre d\'affichage',
        help_text='Numéro de position dans le cours'
    )
    url_video = models.URLField(
        verbose_name='URL vidéo YouTube',
        blank=True,
        validators=[URLValidator()],
        help_text='Lien vers la vidéo YouTube'
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )
    actif = models.BooleanField(
        default=True,
        verbose_name='Actif'
    )
    
    class Meta:
        verbose_name = 'Chapitre'
        verbose_name_plural = 'Chapitres'
        ordering = ['cours', 'ordre']
        unique_together = ('cours', 'ordre')
    
    def __str__(self):
        return f"{self.cours.titre} - {self.titre} (§{self.ordre})"


class Document(models.Model):
    """Modèle représentant un document pédagogique (PDF)."""
    
    TYPE_DOCUMENT_CHOICES = (
        ('TP', 'TP (Travaux Pratiques)'),
        ('ATELIER', 'Atelier'),
        ('PROJET', 'Projet'),
        ('QCM', 'QCM (Questionnaire)'),
        ('COURS', 'Cours'),
        ('RESSOURCE', 'Ressource'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chapitre = models.ForeignKey(
        Chapitre,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name='Chapitre'
    )
    titre = models.CharField(
        max_length=255,
        verbose_name='Titre du document'
    )
    type_document = models.CharField(
        max_length=20,
        choices=TYPE_DOCUMENT_CHOICES,
        default='RESSOURCE',
        verbose_name='Type de document'
    )
    fichier_pdf = models.FileField(
        upload_to='documents/%Y/%m/',
        verbose_name='Fichier PDF',
        help_text='PDF à télécharger ou analyser'
    )
    description = models.TextField(
        verbose_name='Description',
        blank=True
    )
    contenu_extrait = models.TextField(
        verbose_name='Contenu extrait du PDF',
        blank=True,
        help_text='Rempli automatiquement lors du téléchargement'
    )
    ordre = models.PositiveIntegerField(
        verbose_name='Ordre d\'affichage',
        default=0
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name='Date de modification'
    )
    actif = models.BooleanField(
        default=True,
        verbose_name='Actif'
    )
    
    class Meta:
        verbose_name = 'Document'
        verbose_name_plural = 'Documents'
        ordering = ['chapitre', 'type_document', 'ordre']
    
    def __str__(self):
        return f"{self.titre} ({self.get_type_document_display()})"


class Progression(models.Model):
    """Modèle pour suivre la progression d'un étudiant dans un cours."""
    
    etudiant = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='progressions',
        verbose_name='Étudiant'
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name='progressions',
        verbose_name='Cours'
    )
    chapitres_valides = models.ManyToManyField(
        Chapitre,
        blank=True,
        related_name='progressions',
        verbose_name='Chapitres validés'
    )
    date_derniere_consultation = models.DateTimeField(
        auto_now=True,
        verbose_name='Date de dernière consultation'
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création'
    )
    
    class Meta:
        verbose_name = 'Progression'
        verbose_name_plural = 'Progressions'
        unique_together = ('etudiant', 'cours')
        ordering = ['-date_derniere_consultation']
    
    def __str__(self):
        return f"{self.etudiant.email} → {self.cours.titre}"
    
    @property
    def pourcentage(self):
        """Calcule le pourcentage de progression (0-100)."""
        total_chapitres = self.cours.chapitres.count()
        if total_chapitres == 0:
            return 0
        chapitres_faits = self.chapitres_valides.count()
        return int((chapitres_faits / total_chapitres) * 100)
