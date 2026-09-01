import uuid
from django.db import models
from django.core.validators import URLValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from accounts.models import Niveau


def validate_file_size(value):
    """Valide que le fichier ne dépasse pas 10 Mo."""
    limit_mb = 10
    if value.size > limit_mb * 1024 * 1024:
        raise ValidationError(_("Le fichier ne doit pas dépasser %(n)s Mo.") % {'n': limit_mb})


def validate_video_file_size(value):
    """Valide que la vidéo ne dépasse pas 300 Mo."""
    limit_mb = 300
    if value.size > limit_mb * 1024 * 1024:
        raise ValidationError(_("La vidéo ne doit pas dépasser %(n)s Mo.") % {'n': limit_mb})



class Cours(models.Model):
    """Modèle représentant un cours dans la plateforme."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(
        max_length=255,
        verbose_name=_('Titre du cours')
    )
    description = models.TextField(
        verbose_name=_('Description')
    )
    niveau = models.ForeignKey(
        Niveau,
        on_delete=models.CASCADE,
        related_name='cours',
        verbose_name=_('Niveau')
    )
    resume = models.TextField(
        verbose_name=_('Résumé court'),
        blank=True,
        help_text=_('Résumé affiché dans les listes')
    )
    image_couverture = models.ImageField(
        upload_to='cours_covers/', 
        null=True, 
        blank=True, 
        verbose_name=_('Image de couverture')
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Date de création')
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Date de modification')
    )
    actif = models.BooleanField(
        default=True,
        verbose_name=_('Actif')
    )
    createur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='cours_crees',
        verbose_name=_('Créateur')
    )
    SOURCE_CHOICES = (
        ('MANUEL', _('Créé sur la plateforme')),
        ('IMPORT', _('Importé (ZIP)')),
        ('SATELLITE', _('Reçu par satellite')),
    )
    source = models.CharField(
        max_length=12,
        choices=SOURCE_CHOICES,
        default='MANUEL',
        verbose_name=_('Origine'),
        help_text=_("Les cours « satellite » sont remplacés à chaque mise à jour ; "
                    "les autres (préchargés / créés à la main) sont persistants."),
    )

    class Meta:
        verbose_name = _('Cours')
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
        verbose_name=_('Cours')
    )
    titre = models.CharField(
        max_length=255,
        verbose_name=_('Titre du chapitre')
    )
    description = models.TextField(
        verbose_name=_('Description'),
        blank=True
    )
    ordre = models.PositiveIntegerField(
        verbose_name=_('Ordre d\'affichage'),
        help_text=_('Numéro de position dans le cours')
    )
    url_video = models.URLField(
        verbose_name=_('URL vidéo YouTube'),
        blank=True,
        validators=[URLValidator()],
        help_text=_('Lien vers la vidéo YouTube')
    )
    video_fichier = models.FileField(
        upload_to='videos/%Y/%m/',
        verbose_name=_('Vidéo hors-ligne (MP4)'),
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['mp4']),
            validate_video_file_size,
        ],
        help_text=_("Utilisée automatiquement à la place du lien YouTube quand l'élève n'a pas de connexion internet.")
    )
    video_hls_url = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        verbose_name=_("Chemin Playlist HLS")
    )
    is_hls_ready = models.BooleanField(
        default=False,
        verbose_name=_("HLS Prêt")
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Date de création')
    )
    actif = models.BooleanField(
        default=True,
        verbose_name=_('Actif')
    )
    
    class Meta:
        verbose_name = _('Chapitre')
        verbose_name_plural = 'Chapitres'
        ordering = ['cours', 'ordre']
        unique_together = ('cours', 'ordre')
    
    def __str__(self):
        return f"{self.cours.titre} - {self.titre} (§{self.ordre})"


class Document(models.Model):
    """Modèle représentant un document pédagogique (PDF)."""
    
    TYPE_DOCUMENT_CHOICES = (
        ('TP', pgettext_lazy('document type', 'TP (Travaux Pratiques)')),
        ('ATELIER', pgettext_lazy('document type', 'Atelier')),
        ('PROJET', pgettext_lazy('document type', 'Projet')),
        ('QCM', pgettext_lazy('document type', 'QCM (Questionnaire)')),
        ('COURS', pgettext_lazy('document type', 'Cours')),
        ('RESSOURCE', pgettext_lazy('document type', 'Ressource')),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    chapitre = models.ForeignKey(
        Chapitre,
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name=_('Chapitre')
    )
    titre = models.CharField(
        max_length=255,
        verbose_name=_('Titre du document')
    )
    type_document = models.CharField(
        max_length=20,
        choices=TYPE_DOCUMENT_CHOICES,
        default='RESSOURCE',
        verbose_name=_('Type de document')
    )
    fichier_pdf = models.FileField(
        upload_to='documents/%Y/%m/',
        verbose_name=_('Fichier PDF'),
        help_text=_('PDF à télécharger ou analyser'),
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf']),
            validate_file_size,
        ]
    )
    description = models.TextField(
        verbose_name=_('Description'),
        blank=True
    )
    contenu_extrait = models.TextField(
        verbose_name=_('Contenu extrait du PDF'),
        blank=True,
        help_text=_('Rempli automatiquement lors du téléchargement')
    )
    ordre = models.PositiveIntegerField(
        verbose_name=_('Ordre d\'affichage'),
        default=0
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Date de création')
    )
    date_modification = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Date de modification')
    )
    actif = models.BooleanField(
        default=True,
        verbose_name=_('Actif')
    )
    
    class Meta:
        verbose_name = _('Document')
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
        verbose_name=_('Étudiant')
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name='progressions',
        verbose_name=_('Cours')
    )
    chapitres_valides = models.ManyToManyField(
        Chapitre,
        blank=True,
        related_name='progressions',
        verbose_name=_('Chapitres validés')
    )
    date_derniere_consultation = models.DateTimeField(
        auto_now=True,
        verbose_name=_('Date de dernière consultation')
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_('Date de création')
    )
    
    class Meta:
        verbose_name = _('Progression')
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
        verbose_name=_('Utilisateur')
    )
    chapitre = models.ForeignKey(
        Chapitre,
        on_delete=models.CASCADE,
        related_name='visites',
        verbose_name=_('Chapitre')
    )
    date_visite = models.DateTimeField(auto_now=True, verbose_name=_('Date de visite'))

    class Meta:
        verbose_name = _('Visite de chapitre')
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
        verbose_name=_('Utilisateur')
    )
    chapitre = models.ForeignKey(
        Chapitre,
        on_delete=models.CASCADE,
        related_name='validations',
        verbose_name=_('Chapitre')
    )
    date_completion = models.DateTimeField(auto_now=True, verbose_name=_('Date de completion'))

    class Meta:
        verbose_name = _('Chapitre terminé')
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
        verbose_name=_('Chapitre')
    )
    titre = models.CharField(max_length=255, verbose_name=_('Titre'))
    consigne = models.TextField(verbose_name=_('Consigne'))
    fichier_consigne = models.FileField(
        upload_to='devoirs/consignes/%Y/%m/',
        blank=True,
        null=True,
        verbose_name=_('Fichier consigne (facultatif)'),
        validators=[
            FileExtensionValidator(allowed_extensions=EXTENSIONS_AUTORISEES),
            validate_file_size,
        ]
    )
    date_limite = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_('Date limite de rendu')
    )
    note_max = models.PositiveSmallIntegerField(default=20, verbose_name=_('Note maximale'))
    createur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        related_name='devoirs_crees',
        verbose_name=_('Créateur')
    )
    actif = models.BooleanField(default=True, verbose_name=_('Actif'))
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_('Date de création'))

    class Meta:
        verbose_name = _('Devoir')
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
        verbose_name=_('Devoir')
    )
    etudiant = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='soumissions',
        verbose_name=_('Étudiant')
    )
    fichier = models.FileField(
        upload_to='devoirs/soumissions/%Y/%m/',
        verbose_name=_('Fichier soumis'),
        validators=[
            FileExtensionValidator(allowed_extensions=EXTENSIONS_AUTORISEES),
            validate_file_size,
        ]
    )
    commentaire_eleve = models.TextField(blank=True, verbose_name=_('Commentaire de l\'élève'))
    date_soumission = models.DateTimeField(auto_now=True, verbose_name=_('Date de soumission'))

    # Correction
    note = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name=_('Note obtenue')
    )
    feedback = models.TextField(blank=True, verbose_name=_('Feedback du formateur'))
    corrige_par = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='soumissions_corrigees',
        verbose_name=_('Corrigé par')
    )
    date_correction = models.DateTimeField(null=True, blank=True, verbose_name=_('Date de correction'))

    class Meta:
        verbose_name = _('Soumission')
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
        ('ECHEANCE_DEVOIR', pgettext_lazy('event type', 'Échéance Devoir')),
        ('SESSION', pgettext_lazy('event type', 'Session')),
        ('EXAMEN', pgettext_lazy('event type', 'Examen')),
        ('AUTRE', pgettext_lazy('event type', 'Autre')),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    titre = models.CharField(max_length=255, verbose_name=_("Titre"))
    description = models.TextField(blank=True, verbose_name=_("Description"))
    type = models.CharField(
        max_length=20,
        choices=TYPE_EVENEMENT_CHOICES,
        default='AUTRE',
        verbose_name=_("Type d'événement")
    )
    date_debut = models.DateTimeField(verbose_name=_("Date de début"))
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name=_("Date de fin"))
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='evenements',
        verbose_name=_("Cours")
    )
    createur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        related_name='evenements_crees',
        verbose_name=_("Créateur")
    )
    classe = models.ForeignKey(
        'accounts.Classe',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='evenements',
        verbose_name=_("Classe cible")
    )
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_("Date de création"))

    class Meta:
        ordering = ['date_debut']
        verbose_name = _("Événement")
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
    titre = _("Échéance : %(devoir)s") % {'devoir': instance.titre}
    description = _("Date limite pour rendre le devoir '%(devoir)s'.") % {'devoir': instance.titre} + f" {search_str}"
    
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
        ('PENDING', _('En cours')),
        ('SUCCESS', _('Terminé')),
        ('FAILED', _('Échoué')),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    formateur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='export_jobs',
        verbose_name=_('Formateur')
    )
    cours = models.ForeignKey(
        Cours,
        on_delete=models.CASCADE,
        related_name='export_jobs',
        verbose_name=_('Cours')
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    fichier_zip = models.FileField(upload_to='exports/cours/%Y/%m/', null=True, blank=True, verbose_name=_('Fichier ZIP'))
    erreur = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('Tâche d\'export')
        verbose_name_plural = 'Tâches d\'export'
        ordering = ['-date_creation']

    def __str__(self):
        return f"Export {self.cours.titre} par {self.formateur.get_full_name()} ({self.get_status_display()})"


class ImportJob(models.Model):
    """Suivi asynchrone des importations de cours en ZIP."""
    STATUS_CHOICES = (
        ('EN_ATTENTE', _('En attente')),
        ('EXTRACTION', _('Extraction du ZIP')),
        ('SAUVEGARDE_BDD', _('Sauvegarde en base de données')),
        ('INDEXATION_IA', _("Indexation pour l'IA")),
        ('TERMINE', _('Terminé')),
        ('FAILED', _('Échoué')),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    formateur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='import_jobs',
        verbose_name=_('Formateur')
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='EN_ATTENTE')
    titre_cours = models.CharField(max_length=255, blank=True, null=True)
    source = models.CharField(max_length=12, default='IMPORT',
                              help_text="Origine posée sur les cours créés : IMPORT / SATELLITE")
    erreur = models.TextField(blank=True, null=True)
    date_creation = models.DateTimeField(auto_now_add=True)
    date_fin = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Tâche d'import")
        verbose_name_plural = "Tâches d'import"
        ordering = ['-date_creation']

    def __str__(self):
        return f"Import par {self.formateur.get_full_name()} ({self.get_status_display()})"


class SatelliteUpdate(models.Model):
    """Fichier de mise à jour de cours reçu par satellite (carrousel FLUTE), détecté
    automatiquement dans SATELLITE_INBOX_DIR et en attente d'application manuelle
    par un administrateur depuis le tableau de bord."""
    STATUS_CHOICES = (
        ('DETECTED', _('Détectée')),
        ('IMPORTING', _('Import en cours')),
        ('APPLIED', _('Appliquée')),
        ('FAILED', _('Échouée')),
        ('IGNORED', _('Ignorée')),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    logical_name = models.CharField(max_length=255, verbose_name=_('Nom du fichier'))
    file_hash = models.CharField(max_length=64, unique=True, db_index=True, verbose_name=_('Empreinte SHA-256'))
    size = models.BigIntegerField(default=0, verbose_name=_('Taille (octets)'))
    cycle_id = models.IntegerField(null=True, blank=True, verbose_name=_('Cycle satellite'))
    titre_cours = models.CharField(max_length=255, blank=True, default='', verbose_name=_('Cours'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DETECTED', db_index=True)
    erreur = models.TextField(blank=True, default='')
    import_job = models.ForeignKey(
        'ImportJob', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='satellite_updates'
    )
    applied_by = models.ForeignKey(
        'accounts.Utilisateur', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='satellite_updates_applied'
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("Mise à jour satellite")
        verbose_name_plural = _("Mises à jour satellite")
        ordering = ['-detected_at']

    def __str__(self):
        return f"{self.logical_name} ({self.get_status_display()})"



