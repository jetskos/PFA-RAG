#!/bin/bash
# Démarrer le worker Celery en arrière-plan avec le pool solo pour éviter les deadlocks de fork ChromaDB
celery -A core worker -l info --pool=solo &

# Démarrer le serveur web Daphne au premier plan
daphne -b 0.0.0.0 -p ${PORT:-8000} core.asgi:application
