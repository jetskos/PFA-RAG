#!/bin/bash
# Démarrer le serveur web Daphne au premier plan (serveur de production)
daphne -b 0.0.0.0 -p ${PORT:-8000} core.asgi:application
