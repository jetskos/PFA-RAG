#!/bin/bash
# Script de démarrage pour un déploiement mono-conteneur (ex. Railway).
# Avec docker-compose, le worker Celery tourne dans son propre service :
# ce script ne sert alors qu'au service web via le CMD du Dockerfile.

# Worker Celery en arrière-plan — pool solo obligatoire avec ChromaDB
celery -A core worker -l info --pool=solo &

# Serveur web WSGI (gunicorn) au premier plan
# (le projet n'utilise ni websockets ni vues async : WSGI suffit)
gunicorn core.wsgi:application -b 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 120
