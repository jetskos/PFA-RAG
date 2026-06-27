# 🚀 Documentation de Déploiement : Plateforme Éducative RAG

Ce document retrace l'architecture complète et les étapes de déploiement réalisées pour mettre en production la Plateforme Éducative intelligente (RAG).

## 🏗️ 1. Architecture Réseau et Serveurs (Proxmox)

L'infrastructure est hébergée sur **Proxmox** et isolée derrière un routeur/pare-feu **pfSense**, créant ainsi une DMZ (Zone Démilitarisée) hautement sécurisée.

*   **pfSense (Routeur/Firewall)** : Protège le réseau et gère le port forwarding.
    *   IP WAN (Réseau Host) : `10.22.88.128`
    *   IP LAN (Réseau Interne Proxmox) : `192.168.50.1`
*   **VM 101 (Serveur Web & IA)** : Fait tourner l'application Django et le moteur Celery.
    *   IP : `192.168.50.10`
    *   OS : Ubuntu 24.04
    *   Ressources recommandées : 4 à 6 cœurs (Type `max`), 8 Go RAM.
*   **VM 102 (Serveur de Données)** : Héberge la base de données SQL et le courtier de messages.
    *   IP : `192.168.50.20`
    *   OS : Ubuntu 24.04
    *   Ressources : 2 cœurs, 2 à 4 Go RAM.

> [!IMPORTANT]
> **Compatibilité CPU / IA :** Pour que les librairies d'Intelligence Artificielle (HuggingFace, PyTorch) puissent fonctionner sans générer l'erreur `Illegal instruction (core dumped)`, le processeur de la VM 101 dans Proxmox a été configuré avec le **Type : `max`** (permettant d'émuler les instructions AVX nécessaires).

---

## 🗄️ 2. Configuration du Serveur de Données (VM 102)

Ce serveur est dédié au stockage et ne communique qu'avec la VM 101 sur le réseau privé.

### MariaDB (Base de données)
*   **Utilisateur** : `jatski2`
*   **Mot de passe** : `12345678`
*   **Configuration réseau** : Le fichier `/etc/mysql/mariadb.conf.d/50-server.cnf` a été modifié pour écouter sur `bind-address = 192.168.50.20` au lieu de `127.0.0.1`.

### Redis (Broker pour Celery)
*   **Configuration réseau** : Modifié dans `/etc/redis/redis.conf` pour écouter sur `bind 192.168.50.20`.
*   **Mode protégé et Authentification** :
    *   Le mot de passe a été découvert (ou configuré) via la ligne `requirepass`.
    *   Le mode protégé est géré pour accepter les connexions authentifiées de la VM 101.

---

## 🌐 3. Configuration du Serveur Web (VM 101)

C'est le cœur de l'application, hébergeant l'interface utilisateur et le moteur IA de traitement de documents (RAG).

### Variables d'Environnement (`.env`)
Le fichier `/var/www/plateforme_educative/plateforme_educative/.env` connecte la VM 101 à la VM 102 et au monde extérieur :
```env
DB_ENGINE=django.db.backends.mysql
DB_NAME=plateforme_db
DB_USER=jatski2
DB_PASSWORD=12345678
DB_HOST=192.168.50.20
DB_PORT=3306

REDIS_URL=redis://:VOTRE_MOT_DE_PASSE@192.168.50.20:6379/0
CELERY_BROKER_URL=redis://:VOTRE_MOT_DE_PASSE@192.168.50.20:6379/0
CELERY_RESULT_BACKEND=redis://:VOTRE_MOT_DE_PASSE@192.168.50.20:6379/0

GROQ_API_KEY=votre_cle_api_groq
```

### Le Script de Démarrage (`start.sh`)
Un script a été créé pour automatiser le lancement du serveur Django et du travailleur IA (Celery) en arrière-plan.

**Contenu de `/home/jatski1/start.sh` :**
```bash
#!/bin/bash
echo "🚀 Lancement de la Plateforme Éducative RAG..."
cd /var/www/plateforme_educative/plateforme_educative
source .venv/bin/activate

echo "🧠 Démarrage du moteur IA (Celery)..."
nohup celery -A core worker -l info > /home/jatski1/celery.log 2>&1 &

echo "🌐 Démarrage du Serveur Web..."
nohup python manage.py runserver 0.0.0.0:8000 > /home/jatski1/django.log 2>&1 &

echo "✅ Tout est lancé en arrière-plan !"
```

> [!TIP]
> Le script a été configuré pour se lancer automatiquement au démarrage de la machine via la crontab (`@reboot /home/jatski1/start.sh`).

---

## 🛡️ 4. Configuration du Pare-feu (pfSense)

Pour rendre le site accessible depuis la machine Windows hôte tout en protégeant les VM, une règle de redirection de port (NAT / Port Forwarding) a été créée sur pfSense :

*   **Interface** : WAN
*   **Protocol** : TCP
*   **Destination port** : 8000
*   **Redirect target IP** : `192.168.50.10` (Serveur Web)
*   **Redirect target port** : 8000

*Résultat : En tapant `http://10.22.88.128:8000` sur le PC Windows, pfSense transfère silencieusement le trafic vers le serveur Django interne.*

---

## 🔧 5. Dépannages fréquents rencontrés

1.  **`DisallowedHost` dans Django** : Django bloquait l'accès via l'IP WAN de pfSense. Corrigé en mettant `ALLOWED_HOSTS = ['*']` dans `core/settings.py`.
2.  **`Unknown column 'reference'`** : Décalage entre le code et la BDD. Corrigé en appliquant les migrations (`python manage.py makemigrations` et `migrate`).
3.  **Crash Celery (Module non trouvé)** : L'argument `-A` de Celery devait pointer vers le nom du module de configuration (`core`), et non le nom du dossier racine.
4.  **Celery n'arrive pas à se connecter à Redis** : 
    *   Correction de l'IP (pointée par erreur sur `localhost`).
    *   Correction du mot de passe en utilisant l'URL formatée `redis://:password@ip:port/db`.
5.  **`Aucun LLM configuré`** : Corrigé en ajoutant la `GROQ_API_KEY` dans le `.env`.

---
*Document généré le 23 Juin 2026 suite au succès du déploiement.*
