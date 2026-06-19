# Ce fichier assure que l'application Celery est chargée lorsque Django démarre.
from .celery import app as celery_app

__all__ = ('celery_app',)
