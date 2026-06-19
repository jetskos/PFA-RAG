# TODO List - Plateforme Éducative

## Optimisation de la soumission des Documents (PDF)
**Problème actuel :** L'upload et la sauvegarde d'un PDF prend énormément de temps car l'extraction de texte (parsing) et l'indexation IA (embeddings ChromaDB) se font de manière **synchrone** pendant le chargement de la page. Cela est dû au mode Eager de Celery qui est activé en mode DEBUG.

### Étapes pour corriger ce problème (Activer l'asynchronisme) :

**1. Installer et lancer Redis (Le Broker pour Celery)**
Puisque Redis n'a pas de version officielle Windows, la méthode recommandée est d'utiliser WSL (Windows Subsystem for Linux) :
* Ouvrez un terminal WSL (Ubuntu).
* Installez Redis : `sudo apt update && sudo apt install redis-server`
* Lancez Redis : `sudo service redis-server start`
*(Note : Redis sera accessible sur `localhost:6379` depuis Windows).*

**2. Lancer le Worker Celery sur Windows**
Ouvrez un *nouveau terminal* PowerShell ou CMD à la racine du projet Django (`plateforme_educative`).
Exécutez la commande suivante avec le flag `--pool=solo` (obligatoire sur Windows pour éviter les bugs liés aux processus) :
```bash
celery -A core worker -l info --pool=solo
```

**3. Mettre à jour la configuration Django**
Ouvrez le fichier `core/settings.py` (vers la ligne 188) et modifiez la configuration de Celery pour désactiver le mode synchrone ("Eager") :
```python
# Remplacer DEBUG par False pour forcer le traitement en arrière-plan
CELERY_TASK_ALWAYS_EAGER = False
CELERY_TASK_EAGER_PROPAGATES = False
```

Une fois ces trois étapes complétées, lorsque vous cliquerez sur "Soumettre", la page se rechargera instantanément et l'indexation du PDF (qui prend beaucoup de temps) se fera silencieusement en arrière-plan via le terminal du worker Celery !
