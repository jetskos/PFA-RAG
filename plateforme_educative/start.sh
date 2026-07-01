#!/bin/bash
# Démarrer le worker Celery en arrière-plan avec 1 seul thread pour économiser la RAM
celery -A core worker -l info --concurrency=1 &

# Démarrer le serveur web Daphne au premier plan
daphne -b 0.0.0.0 -p ${PORT:-8000} core.asgi:application
