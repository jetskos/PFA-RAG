"""
Migration : ajout du model SessionQCM.
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("tuteur_ia", "0001_initial"),
        ("accounts", "0001_initial"),
        ("apprentissage", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessionQCM",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("etudiant", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sessions_qcm",
                    to="accounts.utilisateur",
                )),
                ("chapitre", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="sessions_qcm",
                    to="apprentissage.chapitre",
                )),
                ("questions",  models.JSONField(default=list)),
                ("reponses",   models.JSONField(default=dict)),
                ("score",      models.IntegerField(null=True, blank=True)),
                ("statut",     models.CharField(
                    max_length=20,
                    choices=[("EN_COURS","En cours"),("TERMINEE","Terminée"),("ECHOUEE","Échouée")],
                    default="EN_COURS",
                )),
                ("tentative",          models.IntegerField(default=1)),
                ("date_creation",      models.DateTimeField(auto_now_add=True)),
                ("date_modification",  models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Session QCM",
                "verbose_name_plural": "Sessions QCM",
                "ordering": ["-date_creation"],
            },
        ),
    ]
