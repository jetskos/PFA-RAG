import uuid
from django.db import models


class GraphCheckpoint(models.Model):
    """Persistance LangGraph : snapshots du workflow (remplace MemorySaver)."""
    thread_id            = models.CharField(max_length=255, db_index=True)
    checkpoint_ns        = models.CharField(max_length=255, default="")
    checkpoint_id        = models.CharField(max_length=255)
    parent_checkpoint_id = models.CharField(max_length=255, blank=True, null=True)
    type                 = models.CharField(max_length=50, default="json")
    checkpoint           = models.BinaryField()
    metadata             = models.BinaryField()
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("thread_id", "checkpoint_ns", "checkpoint_id")]
        ordering = ["-created_at"]
        verbose_name = "Checkpoint LangGraph"
        verbose_name_plural = "Checkpoints LangGraph"

    def __str__(self):
        return f"[{self.thread_id}] {self.checkpoint_id[:8]}…"


class GraphWrite(models.Model):
    """Persistance LangGraph : pending writes entre nœuds."""
    thread_id     = models.CharField(max_length=255, db_index=True)
    checkpoint_ns = models.CharField(max_length=255, default="")
    checkpoint_id = models.CharField(max_length=255, db_index=True)
    task_id       = models.CharField(max_length=255)
    idx           = models.IntegerField()
    channel       = models.CharField(max_length=255)
    type          = models.CharField(max_length=50)
    value         = models.BinaryField()

    class Meta:
        unique_together = [("thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx")]
        verbose_name = "Write LangGraph"
        verbose_name_plural = "Writes LangGraph"

    def __str__(self):
        return f"[{self.thread_id}] {self.channel}[{self.idx}]"


class DocumentChunk(models.Model):
    """
    Stockage persistant des chunks de documents pour la recherche BM25.
    Synchronisé avec ChromaDB lors de l'indexation.
    """
    chunk_id        = models.CharField(max_length=255, unique=True, db_index=True)
    document_id     = models.CharField(max_length=36, db_index=True)
    document_titre  = models.CharField(max_length=500)
    chapitre_id     = models.CharField(max_length=36, db_index=True)
    cours_id        = models.CharField(max_length=36, db_index=True)
    page_hint       = models.CharField(max_length=20, blank=True)
    chunk_index     = models.IntegerField(default=0)
    texte           = models.TextField()
    date_creation   = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chunk de document'
        verbose_name_plural = 'Chunks de documents'
        indexes = [
            models.Index(fields=['chapitre_id']),
            models.Index(fields=['cours_id']),
            models.Index(fields=['document_id']),
        ]

    def __str__(self):
        return f"{self.document_titre} — chunk {self.chunk_index}"


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
        return f"Profil IA - {self.etudiant.get_full_name()}"

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
        return f"Session {self.etudiant.get_full_name()} - {self.chapitre.titre}"


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
        return f"QCM {self.etudiant.get_full_name()} - {self.chapitre.titre} (score={self.score})"


class QuestionCache(models.Model):
    """Banque de questions QCM générées par IA pour un chapitre."""
    chapitre = models.OneToOneField('apprentissage.Chapitre', on_delete=models.CASCADE, related_name='qcm_cache')
    questions = models.JSONField(default=list)  # Stocke la liste de toutes les questions générées [{question, options, reponse_correcte, explication}]
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cache de questions QCM'
        verbose_name_plural = 'Caches de questions QCM'

    def __str__(self):
        return f"Cache {self.chapitre.titre} ({len(self.questions)} questions)"


class SessionAssistant(models.Model):
    """Session de discussion avec l'Assistant RAG explicatif (Tuteur Pédagogique)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    etudiant = models.ForeignKey(
        'accounts.Utilisateur',
        on_delete=models.CASCADE,
        related_name='sessions_assistant'
    )
    chapitre = models.ForeignKey(
        'apprentissage.Chapitre',
        on_delete=models.CASCADE,
        related_name='sessions_assistant'
    )
    messages = models.JSONField(default=list)  # [{'role': 'user'|'assistant', 'content': str, 'sources': str, 'timestamp': str}]
    date_creation = models.DateTimeField(auto_now_add=True)
    date_modification = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Session Assistant'
        verbose_name_plural = 'Sessions Assistant'
        ordering = ['-date_modification']

    def __str__(self):
        return f"Assistant {self.etudiant.get_full_name()} - {self.chapitre.titre}"

