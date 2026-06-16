from django.apps import AppConfig


class ApprentissageConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apprentissage'
    verbose_name = 'Module d\'Apprentissage'

    def ready(self):
        """Wire in signal handlers for auto-embedding documents to Chroma."""
        import apprentissage.signals  # noqa

