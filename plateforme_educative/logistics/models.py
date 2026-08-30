from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


import uuid

class Equipment(models.Model):
    nom = models.CharField(max_length=255, verbose_name=_('Nom'))
    reference = models.CharField(max_length=255, unique=True, default=uuid.uuid4, verbose_name=_('Référence'))
    stock_total = models.PositiveIntegerField(default=0, verbose_name=_('Stock total'))
    stock_disponible = models.PositiveIntegerField(default=0, verbose_name=_('Stock disponible'))
    seuil_alerte = models.PositiveIntegerField(default=5, verbose_name=_("Seuil d'alerte"))
    est_actif = models.BooleanField(default=True, verbose_name=_('Est actif'))
    note = models.TextField(blank=True, verbose_name=_('Note'))

    class Meta:
        verbose_name = _('Équipement')
        verbose_name_plural = 'Équipements'
        ordering = ['nom']

    def __str__(self):
        return f"{self.nom} ({self.reference})"

    @property
    def en_alerte(self):
        return self.stock_disponible <= self.seuil_alerte


class Workshop(models.Model):
    titre = models.CharField(max_length=255, verbose_name=_('Titre'))
    date_debut = models.DateTimeField(verbose_name=_('Date de début'))
    date_fin = models.DateTimeField(verbose_name=_('Date de fin'))
    salle = models.CharField(max_length=120, verbose_name=_('Salle'))
    tuteur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.PROTECT,
        related_name='ateliers_tutores',
        verbose_name=_('Tuteur'),
    )
    niveau_cible = models.CharField(max_length=100, verbose_name=_('Niveau cible'))
    createur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='ateliers_crees',
        verbose_name=_('Créateur'),
    )
    est_annule = models.BooleanField(default=False, verbose_name=_('Est annulé'))

    class Meta:
        verbose_name = _('Atelier')
        verbose_name_plural = 'Ateliers'
        ordering = ['-date_debut']

    def __str__(self):
        return self.titre
        
    @property
    def statut_dynamique(self):
        from django.utils import timezone
        if self.est_annule:
            return _("Annulé")
        now = timezone.now()
        if self.date_debut > now:
            return _("À venir")
        elif self.date_debut <= now <= self.date_fin:
            return _("En cours")
        else:
            return _("Terminé")
    
    def clean(self):
        # Ensure end is after start
        if self.date_fin <= self.date_debut:
            raise ValidationError({'date_fin': _('La date de fin doit être postérieure à la date de début.')})

    def save(self, *args, **kwargs):
        # Run model validation before saving to enforce invariants
        self.full_clean()
        return super().save(*args, **kwargs)


class Ticket(models.Model):
    STATUT_CHOICES = (
        ('OUVERT', _('Ouvert')),
        ('EN_COURS', _('En cours')),
        ('RESOLU', _('Résolu')),
    )

    titre = models.CharField(max_length=255, verbose_name=_('Titre'))
    description = models.TextField(verbose_name=_('Description'))
    equipement = models.ForeignKey(
        Equipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name=_('Équipement'),
    )
    atelier = models.ForeignKey(
        Workshop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tickets',
        verbose_name=_('Atelier'),
    )
    ouvert_par = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.PROTECT,
        related_name='tickets_ouverts',
        verbose_name=_('Ouvert par'),
    )
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='OUVERT',
        verbose_name=_('Statut'),
    )
    date_creation = models.DateTimeField(
        auto_now_add=True,
        null=True,
        verbose_name=_('Date de création'),
    )

    class Meta:
        verbose_name = _('Ticket')
        verbose_name_plural = 'Tickets'
        ordering = ['-date_creation', '-id']

    def __str__(self):
        return self.titre


class DemandeMateriel(models.Model):
    STATUT_CHOICES = (
        ('PENDING', _('En attente')),
        ('APPROVED', _('Approuvée')),
        ('REJECTED', _('Rejetée')),
        ('RETURNED', _('Retournée')),
    )

    formateur = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='demandes_materiel',
        verbose_name=_('Formateur'),
    )
    equipement = models.ForeignKey(
        Equipment,
        on_delete=models.PROTECT,
        related_name='demandes_materiel',
        verbose_name=_('Équipement'),
    )
    atelier_cible = models.ForeignKey(
        Workshop,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='demandes_materiel',
        verbose_name=_('Atelier cible'),
    )
    quantite = models.PositiveIntegerField(verbose_name=_('Quantité'))
    statut = models.CharField(
        max_length=20,
        choices=STATUT_CHOICES,
        default='PENDING',
        verbose_name=_('Statut'),
    )
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name=_('Date de création'))
    date_mise_a_jour = models.DateTimeField(auto_now=True, verbose_name=_('Date de mise à jour'))

    class Meta:
        verbose_name = _('Demande de matériel')
        verbose_name_plural = 'Demandes de matériel'
        ordering = ['-date_creation']

    def __str__(self):
        return f"{self.formateur.get_full_name()} - {self.equipement.nom} x{self.quantite}"
