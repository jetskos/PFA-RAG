from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tuteur_ia", "0005_documentchunk"),
    ]

    operations = [
        migrations.CreateModel(
            name="GraphCheckpoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("thread_id", models.CharField(db_index=True, max_length=128)),
                ("checkpoint_ns", models.CharField(default="", max_length=128)),
                ("checkpoint_id", models.CharField(max_length=128)),
                ("parent_checkpoint_id", models.CharField(blank=True, max_length=128, null=True)),
                ("type", models.CharField(default="json", max_length=50)),
                ("checkpoint", models.BinaryField()),
                ("metadata", models.BinaryField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Checkpoint LangGraph",
                "verbose_name_plural": "Checkpoints LangGraph",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="graphcheckpoint",
            constraint=models.UniqueConstraint(
                fields=["thread_id", "checkpoint_ns", "checkpoint_id"],
                name="unique_graph_checkpoint",
            ),
        ),
        migrations.CreateModel(
            name="GraphWrite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("thread_id", models.CharField(db_index=True, max_length=128)),
                ("checkpoint_ns", models.CharField(default="", max_length=128)),
                ("checkpoint_id", models.CharField(db_index=True, max_length=128)),
                ("task_id", models.CharField(max_length=128)),
                ("idx", models.IntegerField()),
                ("channel", models.CharField(max_length=128)),
                ("type", models.CharField(max_length=50)),
                ("value", models.BinaryField()),
            ],
            options={
                "verbose_name": "Write LangGraph",
                "verbose_name_plural": "Writes LangGraph",
            },
        ),
        migrations.AddConstraint(
            model_name="graphwrite",
            constraint=models.UniqueConstraint(
                fields=["thread_id", "checkpoint_ns", "checkpoint_id", "task_id", "idx"],
                name="unique_graph_write",
            ),
        ),
    ]
