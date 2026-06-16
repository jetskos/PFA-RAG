import uuid
from django.db import models


class ProfilEtudiantIA(models.Model):
    etudiant = models.OneToOneField(
        'accounts.Utilisateur', on_delete=models.CASCADE, related_name='profil_ia'
    )
    concepts_maitrises = models.JSONField(default=list)
    concepts_fragiles  = models.JSONField(default=list)
    erreurs_communes   = models.JSONField(default=list)
    style_prefere      = models.CharField(max_length=50, default='textuel')
    date_modification  = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Profil Étudiant IA'
        verbose_name_plural = 'Profils Étudiants IA'

    def __str__(self):
        return f"Profil IA - {self.etudiant.email}"

    def to_dict(self):
        return {
            "mastered_concepts": self.concepts_maitrises,
            "fragile_concepts":  self.concepts_fragiles,
            "common_errors":     self.erreurs_communes,
            "preferred_style":   self.style_prefere,
        }

    def update_from_dict(self, data: dict):
        self.concepts_maitrises = data.get("mastered_concepts", self.concepts_maitrises)
        self.concepts_fragiles  = data.get("fragile_concepts",  self.concepts_fragiles)
        self.erreurs_communes   = data.get("common_errors",     self.erreurs_communes)
        self.style_prefere      = data.get("preferred_style",   self.style_prefere)
        self.save()


class SessionTuteur(models.Model):
    STATUS_CHOICES = [
        ('EN_COURS',   'En cours'),
        ('TERMINEE',   'Terminée'),
        ('ABANDONNEE', 'Abandonnée'),
    ]
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    etudiant   = models.ForeignKey('accounts.Utilisateur', on_delete=models.CASCADE, related_name='sessions_tuteur')
    chapitre   = models.ForeignKey('apprentissage.Chapitre', on_delete=models.CASCADE, related_name='sessions_tuteur')
    thread_id  = models.CharField(max_length=100, unique=True)
    statut     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='EN_COURS')
    mastery_score_final = models.FloatField(null=True, blank=True)
    date_creation      = models.DateTimeField(auto_now_add=True)
    date_modification  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Session Tuteur'
        verbose_name_plural = 'Sessions Tuteur'

    def __str__(self):
        return f"Session {self.etudiant.email} - {self.chapitre.titre}"


class SessionQCM(models.Model):
    """Session QCM générée par IA à la fin d'un chapitre."""
    STATUS_CHOICES = [
        ('EN_COURS',  'En cours'),
        ('TERMINEE',  'Terminée'),
        ('ECHOUEE',   'Échouée'),
    ]
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    etudiant   = models.ForeignKey('accounts.Utilisateur', on_delete=models.CASCADE, related_name='sessions_qcm')
    chapitre   = models.ForeignKey('apprentissage.Chapitre', on_delete=models.CASCADE, related_name='sessions_qcm')
    questions  = models.JSONField(default=list)   # [{question, options:[A,B,C,D], reponse_correcte, explication}]
    reponses   = models.JSONField(default=dict)   # {index_question: reponse_choisie}
    score      = models.IntegerField(null=True, blank=True)   # 0-100
    statut     = models.CharField(max_length=20, choices=STATUS_CHOICES, default='EN_COURS')
    tentative  = models.IntegerField(default=1)
    date_creation     = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date_creation']
        verbose_name = 'Session QCM'
        verbose_name_plural = 'Sessions QCM'

    def __str__(self):
        return f"QCM {self.etudiant.email} - {self.chapitre.titre} (score={self.score})"
