import uuid
from django.db import models
from django.core.validators import URLValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from accounts.models import Niveau


def validate_file_size(value):
    """Valide que le fichier ne dépasse pas 10 Mo."""
    limit_mb = 10
    if value.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"Le fichier ne doit pas dépasser {limit_mb} Mo.")


def validate_video_file_size(value):
    """Valide que la vidéo ne dépasse pas 300 Mo."""
    limit_mb = 300
    if value.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"La vidéo ne doit pas dépasser {limit_mb} Mo.")



class Cours(models.Model):
    """Modèle représentant un cours dans la plateforme."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(
        max_length=255,
        verbose_name='Titre du cours'
    )
    description = models.TextField(
        verbose_name='Description'
    )
    niveau = models.ForeignKey(
        Niveau,
        on_delete=models.CASCADE,
        related_name='cours',
        verbose_name='Niveau'
    )
    resume = models.TextField(
        verbose_name='Résumé court',
        blank=True,
        help_text='Résumé affiché dans les listes'
    )
    image_couverture = models.ImageField(
        upload_to='cours_covers/', 
        null=True, 
        blank=True, 
        verbose_name='Image de couverture'
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
    video_fichier = models.FileField(
        upload_to='videos/%Y/%m/',
        verbose_name='Vidéo hors-ligne (MP4)',
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['mp4']),
            validate_video_file_size,
        ],
        help_text="Utilisée automatiquement à la place du lien YouTube quand l'élève n'a pas de connexion internet."
    )
    video_hls_url = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        verbose_name="Chemin Playlist HLS"
    )
    is_hls_ready = models.BooleanField(
        default=False,
        verbose_name="HLS Prêt"
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
        help_text='PDF à télécharger ou analyser',
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
            validate_file_size,
        ]
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
        return f"{self.etudiant.get_full_name()} → {self.cours.titre}"
    
    @property
    def pourcentage(self):
        """Calcule le pourcentage de progression (0-100)."""
        total_chapitres = self.cours.chapitres.count()
        if total_chapitres == 0:
            return 0
        chapitres_faits = self.chapitres_valides.count()
        return int((chapitres_faits / total_chapitres) * 100)


class ChapitreVisite(models.Model):
    """Historique de consultation d'un chapitre par un utilisateur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    etudiant = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='chapitres_visites',
        verbose_name='Utilisateur'
    )
    chapitre = models.ForeignKey(
        Chapitre,
        on_delete=models.CASCADE,
        related_name='visites',
        verbose_name='Chapitre'
    )
    date_visite = models.DateTimeField(auto_now=True, verbose_name='Date de visite')

    class Meta:
        verbose_name = 'Visite de chapitre'
        verbose_name_plural = 'Visites de chapitres'
        unique_together = ('etudiant', 'chapitre')
        ordering = ['-date_visite']

    def __str__(self):
        return f"{self.etudiant.get_full_name()} → {self.chapitre.titre}"


class ChapitreComplete(models.Model):
    """Historique des chapitres validés par un utilisateur."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    etudiant = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='chapitres_completes',
        verbose_name='Utilisateur'
    )
    chapitre = models.ForeignKey(
        Chapitre,
        on_delete=models.CASCADE,
        related_name='validations',
        verbose_name='Chapitre'
    )
    date_completion = models.DateTimeField(auto_now=True, verbose_name='Date de completion')

    class Meta:
        verbose_name = 'Chapitre terminé'
        verbose_name_plural = 'Chapitres terminés'
        unique_together = ('etudiant', 'chapitre')
        ordering = ['-date_completion']

    def __str__(self):
        return f"{self.etudiant.get_full_name()} → {self.chapitre.titre}"


# ── Extensions autorisées pour les pièces jointes ──────────────────────────────
EXTENSIONS_AUTORISEES = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png']


class Devoir(models.Model):
    """Devoir assigné par un formateur à un chapitre."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chapitre = models.ForeignKey(
        Chapitre,
        on_delete=models.CASCADE,
        related_name='devoirs',
        verbose_name='Chapitre'
    )
    titre = models.CharField(max_length=255, verbose_name='Titre')
    consigne = models.TextField(verbose_name='Consigne')
    fichier_consigne = models.FileField(
        upload_to='devoirs/consignes/%Y/%m/',
        blank=True,
        null=True,
        verbose_name='Fichier consigne (facultatif)',
        validators=[
            FileExtensionValidator(allowed_extensions=EXTENSIONS_AUTORISEES),
            validate_file_size,
        ]
    )
    date_limite = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Date limite de rendu'
    )
    note_max = models.PositiveSmallIntegerField(default=20, verbose_name='Note maximale')
    createur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        related_name='devoirs_crees',
        verbose_name='Créateur'
    )
    actif = models.BooleanField(default=True, verbose_name='Actif')
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')

    class Meta:
        verbose_name = 'Devoir'
        verbose_name_plural = 'Devoirs'
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.titre} — {self.chapitre.titre}"


class Soumission(models.Model):
    """Soumission d'un élève pour un devoir donné."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    devoir = models.ForeignKey(
        Devoir,
        on_delete=models.CASCADE,
        related_name='soumissions',
        verbose_name='Devoir'
    )
    etudiant = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='soumissions',
        verbose_name='Étudiant'
    )
    fichier = models.FileField(
        upload_to='devoirs/soumissions/%Y/%m/',
        verbose_name='Fichier soumis',
        validators=[
            FileExtensionValidator(allowed_extensions=EXTENSIONS_AUTORISEES),
            validate_file_size,
        ]
    )
    commentaire_eleve = models.TextField(blank=True, verbose_name='Commentaire de l\'élève')
    date_soumission = models.DateTimeField(auto_now=True, verbose_name='Date de soumission')

    # Correction
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Note obtenue'
    )
    feedback = models.TextField(blank=True, verbose_name='Feedback du formateur')
    corrige_par = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='soumissions_corrigees',
        verbose_name='Corrigé par'
    )
    date_correction = models.DateTimeField(null=True, blank=True, verbose_name='Date de correction')

    class Meta:
        verbose_name = 'Soumission'
        verbose_name_plural = 'Soumissions'
        unique_together = ('devoir', 'etudiant')
        ordering = ['-date_soumission']

    def __str__(self):
        return f"Soumission de {self.etudiant.get_full_name()} — {self.devoir.titre}"

    @property
    def est_corrigee(self):
        return self.note is not None

    @property
    def appreciation_details(self):
        """Retourne l'appréciation et la couleur associée à la note."""
        if self.note is None:
            return None

        note = float(self.note)
        if note < 10:
            return {
                'text': "Passable",
                'color': "#ef4444",
                'bg_color': "rgba(239, 68, 68, 0.15)",
                'border_color': "#ef4444"
            }
        elif note < 14:
            return {
                'text': "Bien, tu peux faire mieux",
                'color': "#f59e0b",
                'bg_color': "rgba(245, 158, 11, 0.15)",
                'border_color': "#f59e0b"
            }
        elif note < 17:
            return {
                'text': "Bravo, bonne note",
                'color': "#3b82f6",
                'bg_color': "rgba(59, 130, 246, 0.15)",
                'border_color': "#3b82f6"
            }
        else:
            return {
                'text': "Excellent ! Bravo",
                'color': "#10b981",
                'bg_color': "rgba(16, 185, 129, 0.15)",
                'border_color': "#10b981"
            }


class Evenement(models.Model):
    TYPE_EVENEMENT_CHOICES = (
        ('ECHEANCE_DEVOIR', 'Échéance Devoir'),
        ('SESSION', 'Session'),
        ('EXAMEN', 'Examen'),
        ('AUTRE', 'Autre'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(max_length=255, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    type = models.CharField(
        max_length=20,
        choices=TYPE_EVENEMENT_CHOICES,
        default='AUTRE',
        verbose_name="Type d'événement"
    )
    date_debut = models.DateTimeField(verbose_name="Date de début")
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin")
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='evenements',
        verbose_name="Cours"
    )
    createur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        related_name='evenements_crees',
        verbose_name="Créateur"
    )
    classe = models.ForeignKey(
        'accounts.Classe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evenements',
        verbose_name="Classe cible"
    )
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")

    class Meta:
        ordering = ['date_debut']
        verbose_name = "Événement"
        verbose_name_plural = "Événements"

    def __str__(self):
        return f"{self.titre} ({self.get_type_display()})"

    @property
    def titre_affiche(self):
        """Retire le préfixe 'Échéance : ' pour un affichage plus propre."""
        if self.type == 'ECHEANCE_DEVOIR' and self.titre.startswith("Échéance : "):
            return self.titre[len("Échéance : "):]
        return self.titre

    @property
    def description_affichee(self):
        """Nettoie le marqueur interne [Devoir ID: ...] de la description."""
        import re
        return re.sub(r'\[Devoir\s+ID:\s*[a-f0-9\-]+\]', '', self.description).strip()


from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=Devoir)
def synchroniser_devoir_evenement(sender, instance, created, **kwargs):
    search_str = f"[Devoir ID: {instance.id}]"
    if not instance.date_limite or not instance.actif:
        Evenement.objects.filter(description__contains=search_str).delete()
        return

    evt = Evenement.objects.filter(description__contains=search_str).first()
    titre = f"Échéance : {instance.titre}"
    description = f"Date limite pour rendre le devoir '{instance.titre}'. {search_str}"
    
    if evt:
        evt.titre = titre
        evt.description = description
        evt.date_debut = instance.date_limite
        evt.createur = instance.createur
        evt.cours = instance.chapitre.cours
        evt.save()
    else:
        Evenement.objects.create(
            titre=titre,
            description=description,
            type='ECHEANCE_DEVOIR',
            date_debut=instance.date_limite,
            createur=instance.createur,
            cours=instance.chapitre.cours
        )

@receiver(post_delete, sender=Devoir)
def supprimer_devoir_evenement(sender, instance, **kwargs):
    search_str = f"[Devoir ID: {instance.id}]"
    Evenement.objects.filter(description__contains=search_str).delete()


class ExportJob(models.Model):
    """Suivi asynchrone des exportations de cours en ZIP."""
    STATUS_CHOICES = (
        ('PENDING', 'En cours'),
        ('SUCCESS', 'Terminé'),
        ('FAILED', 'Échoué'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    formateur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='export_jobs',
        verbose_name='Formateur'
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name='export_jobs',
        verbose_name='Cours'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    fichier_zip = models.FileField(upload_to='exports/cours/%Y/%m/', null=True, blank=True, verbose_name='Fichier ZIP')
    erreur = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Tâche d\'export'
        verbose_name_plural = 'Tâches d\'export'
        ordering = ['-date_creation']

    def __str__(self):
        return f"Export {self.cours.titre} par {self.formateur.get_full_name()} ({self.get_status_display()})"


