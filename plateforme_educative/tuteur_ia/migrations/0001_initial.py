# Generated migration for tuteur_ia initial models

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('accounts', '0001_initial'),
        ('apprentissage', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ProfilEtudiantIA',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('concepts_maitrises', models.JSONField(default=list)),
                ('concepts_fragiles', models.JSONField(default=list)),
                ('erreurs_communes', models.JSONField(default=list)),
                ('style_prefere', models.CharField(default='textuel', max_length=50)),
                ('date_modification', models.DateTimeField(auto_now=True)),
                ('etudiant', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profil_ia', to='accounts.utilisateur')),
            ],
            options={
                'verbose_name': 'Profil Étudiant IA',
                'verbose_name_plural': 'Profils Étudiants IA',
            },
        ),
        migrations.CreateModel(
            name='SessionTuteur',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('thread_id', models.CharField(max_length=100, unique=True)),
                ('statut', models.CharField(choices=[('EN_COURS', 'En cours'), ('TERMINEE', 'Terminée'), ('ABANDONNEE', 'Abandonnée')], default='EN_COURS', max_length=20)),
                ('mastery_score_final', models.FloatField(blank=True, null=True)),
                ('date_creation', models.DateTimeField(auto_now_add=True)),
                ('date_modification', models.DateTimeField(auto_now=True)),
                ('chapitre', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions_tuteur', to='apprentissage.chapitre')),
                ('etudiant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions_tuteur', to='accounts.utilisateur')),
            ],
            options={
                'verbose_name': 'Session Tuteur',
                'verbose_name_plural': 'Sessions Tuteur',
                'ordering': ['-date_creation'],
            },
        ),
    ]
