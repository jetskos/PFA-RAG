from django.db import models
from django.conf import settings

class JournalAudit(models.Model):
    ACTIONS = [
        ('SUPPRESSION_COURS', 'Suppression de cours'),
        ('SUPPRESSION_CHAPITRE', 'Suppression de chapitre'),
        ('SUPPRESSION_DEVOIR', 'Suppression de devoir'),
        ('NOTATION_SOUMISSION', 'Notation de soumission'),
        ('CREATION_COURS', 'Création de cours'),
        ('MODIFICATION_COURS', 'Modification de cours'),
        ('MODIFICATION_ROLE', 'Modification de rôle'),
        ('MODIFICATION_STATUT', 'Modification de statut de compte'),
        ('ACTIVATION_ELEVE', 'Activation d\'élève'),
    ]

    date_action = models.DateTimeField(auto_now_add=True, db_index=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=50, choices=ACTIONS)
    type_objet = models.CharField(max_length=100)
    id_objet = models.CharField(max_length=255, null=True, blank=True)
    representation = models.TextField(null=True, blank=True)
    details = models.JSONField(null=True, blank=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-date_action']

    def save(self, *args, **kwargs):
        if self.pk:
            raise Exception("Le journal d'audit est immuable. Les modifications sont interdites.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise Exception("Le journal d'audit est immuable. Les suppressions sont interdites.")
