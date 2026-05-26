from django.db import models
from django.core.exceptions import ValidationError


class Equipment(models.Model):
    ETAT_CHOICES = (
        ('DISPONIBLE', 'Disponible'),
        ('EN_PANNE', 'En panne'),
        ('EN_MAINTENANCE', 'En maintenance'),
    )

    nom = models.CharField(max_length=255, verbose_name='Nom')
    numero_serie = models.CharField(max_length=255, unique=True, verbose_name='Numéro de série')
    etat = models.CharField(
        max_length=20,
        choices=ETAT_CHOICES,
        default='DISPONIBLE',
        verbose_name='État',
    )
    note = models.TextField(blank=True, verbose_name='Note')

    class Meta:
        verbose_name = 'Équipement'
        verbose_name_plural = 'Équipements'
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.numero_serie})"


class Workshop(models.Model):
    titre = models.CharField(max_length=255, verbose_name='Titre')
    date_debut = models.DateTimeField(verbose_name='Date de début')
    date_fin = models.DateTimeField(verbose_name='Date de fin')
    salle = models.CharField(max_length=120, verbose_name='Salle')
    tuteur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.PROTECT,
        related_name='ateliers_tutores',
        verbose_name='Tuteur',
    )
    niveau_cible = models.CharField(max_length=100, verbose_name='Niveau cible')

    class Meta:
        verbose_name = 'Atelier'
        verbose_name_plural = 'Ateliers'
        ordering = ['-date_debut']

    def __str__(self):
        return self.titre
    
    def clean(self):
        # Ensure end is after start
        if self.date_fin <= self.date_debut:
            raise ValidationError({'date_fin': 'La date de fin doit être postérieure à la date de début.'})

    def save(self, *args, **kwargs):
        # Run model validation before saving to enforce invariants
        self.full_clean()
        return super().save(*args, **kwargs)


class Ticket(models.Model):
    STATUT_CHOICES = (
        ('OUVERT', 'Ouvert'),
        ('EN_COURS', 'En cours'),
        ('RESOLU', 'Résolu'),
    )

    titre = models.CharField(max_length=255, verbose_name='Titre')
    description = models.TextField(verbose_name='Description')
    equipement = models.ForeignKey(
        Equipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name='Équipement',
    )
    atelier = models.ForeignKey(
        Workshop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name='Atelier',
    )
    ouvert_par = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.PROTECT,
        related_name='tickets_ouverts',
        verbose_name='Ouvert par',
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='OUVERT',
        verbose_name='Statut',
    )

    class Meta:
        verbose_name = 'Ticket'
        verbose_name_plural = 'Tickets'
        ordering = ['-id']

    def __str__(self):
        return self.titre
