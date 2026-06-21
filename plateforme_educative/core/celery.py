"""
Configuration de l'application Celery pour la plateforme éducative.
"""
import os

from celery import Celery

# Définir les paramètres Django par défaut pour le programme 'celery'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('plateforme_educative')

# Charger la configuration Celery depuis les paramètres Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Découverte automatique des tâches dans tous les modules tasks.py
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    pass
