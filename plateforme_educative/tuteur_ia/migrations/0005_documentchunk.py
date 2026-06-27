from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tuteur_ia', '0004_sessionassistant'),
    ]

    operations = [
        migrations.CreateModel(
            name='DocumentChunk',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chunk_id',       models.CharField(db_index=True, max_length=255, unique=True)),
                ('document_id',    models.CharField(db_index=True, max_length=36)),
                ('document_titre', models.CharField(max_length=500)),
                ('chapitre_id',    models.CharField(db_index=True, max_length=36)),
                ('cours_id',       models.CharField(db_index=True, max_length=36)),
                ('page_hint',      models.CharField(blank=True, max_length=20)),
                ('chunk_index',    models.IntegerField(default=0)),
                ('texte',          models.TextField()),
                ('date_creation',  models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Chunk de document',
                'verbose_name_plural': 'Chunks de documents',
            },
        ),
        migrations.AddIndex(
            model_name='documentchunk',
            index=models.Index(fields=['chapitre_id'], name='tuteur_ia_d_chapitr_idx'),
        ),
        migrations.AddIndex(
            model_name='documentchunk',
            index=models.Index(fields=['cours_id'], name='tuteur_ia_d_cours_id_idx'),
        ),
        migrations.AddIndex(
            model_name='documentchunk',
            index=models.Index(fields=['document_id'], name='tuteur_ia_d_documen_idx'),
        ),
    ]
