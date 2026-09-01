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

## 📴 6. Déploiement 100 % hors-ligne (serveur coupé d'internet)

La plateforme fonctionne sans aucune connexion, mais **trois composants locaux**
doivent être préparés **une fois, avec internet**, avant de couper le réseau :

| Composant | Pourquoi | Préparation |
|---|---|---|
| **Ollama** + modèle | Tuteur IA & génération de QCM quand il n'y a pas de clé Groq/OpenAI | `curl -fsSL https://ollama.com/install.sh \| sh` puis `ollama pull qwen2.5:1.5b-instruct` ; lancer `ollama serve` (ou service systemd) |
| **Modèle d'embeddings** (RAG) | Indexation des PDF pour le tuteur/QCM | il se télécharge tout seul au 1ᵉʳ import de PDF **tant qu'internet est là** — sinon `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"` |
| **FFmpeg** | Conversion vidéo HLS à l'import de cours | `apt install ffmpeg` (sinon les vidéos importées restent en MP4 brut, sans streaming) |

Puis, à chaque mise en service :

```bash
source .venv/bin/activate
python manage.py migrate
python manage.py compilemessages          # traductions fr / en
python manage.py collectstatic --noinput  # sert les librairies front en local (aucun CDN)
python manage.py check_offline             # <-- vérifie que tout est prêt (voir ci-dessous)
```

### `python manage.py check_offline`

Une seule commande qui affiche l'état de préparation :

```
[OK] Base de données joignable
[OK] Migrations à jour
[OK] Fichiers statiques collectés
[OK] Librairies front vendored (aucun CDN)
[OK] Traductions compilées (.mo présents)
[OK] Ollama joignable + modèle présent
[OK] Modèle d'embeddings RAG en cache
[OK] FFmpeg installé
[OK] Boîte de réception satellite prête
```

Un `[! ]` = fonctionnalité dégradée mais plateforme utilisable ; un `[KO]` = bloquant.
Ajouter `--strict` pour traiter les avertissements comme des erreurs (utile en CI).

### Réglage dans l'interface

Admin → **Paramètres système** → activer **« Mode Hors-Ligne »** : coupe les tentatives
d'envoi d'e-mail et force l'IA locale (Ollama) sans même tester le réseau.

### Réception par satellite

Voir `plateforme_educative/DOCUMENTATION_HLS_FLUTE.md` §5 : lancer le récepteur du
carrousel FLUTE en tâche de fond, sortie pointée sur `SATELLITE_INBOX_DIR`.

### Import en ligne de commande (sans interface web)

Pour un déploiement scripté, reproductible, sans souris — et pour un
**orchestrateur externe** (page « Updates » / script satellite) qui coche
« simulation » par défaut avant d'exécuter réellement.

**Toutes les commandes acceptent `--dry-run`** : elles affichent ce qu'elles
feraient (suppressions, cours créés, objets rechargés, fichiers médias) **sans
rien écrire**, et sortent avec le code retour `0`. Retirer `--dry-run` exécute
pour de vrai. Une commande qui échoue sort avec un **code retour ≠ 0** (scriptable).

#### a) Un cours déposé — équivalent du bouton « Importer (ZIP) »

```bash
cd plateforme_educative

# simulation (n'écrit rien) — scénario « on efface et on injecte »
python manage.py import_course /chemin/cours.zip --replace-all --dry-run

# exécution réelle
python manage.py import_course /chemin/cours.zip --replace-all -y

# variantes
python manage.py import_course /chemin/cours.zip                       # ajoute sans rien effacer
python manage.py import_course /chemin/cours.zip --replace "IoT" -y     # remplace le cours ciblé
python manage.py import_course /chemin/cours.zip --as prof@ecole.ma     # propriétaire (défaut : 1er superuser/ADMIN)
```

Wrappers (migrent d'abord, puis importent) :

```bash
bash plateforme_educative/deploy_course.sh cours.zip --replace-all      # Linux / Git Bash
plateforme_educative\deploy_course.bat cours.zip --replace-all          # Windows
```

#### b) Snapshot complet de la plateforme (base + médias)

```bash
python manage.py backup_satellite                              # produit media/satellite_backups/*.zip
python manage.py restore_satellite snapshot.zip --dry-run      # simulation
python manage.py restore_satellite snapshot.zip                # flush → médias → loaddata → réindexation RAG
```

#### Notes

- **100 % hors-ligne** : exécution Celery forcée en synchrone, aucun worker requis.
- Le **ZIP source n'est pas modifié** (l'import travaille sur une copie).
- `import_course --replace*` supprime aussi les fichiers média associés (MP4, PDF,
  couvertures, dossiers HLS) — pas d'orphelins entre deux imports.
- L'indexation IA des PDF (ChromaDB) est faite au passage si disponible ; sinon
  la relancer avec `python manage.py indexer_pdfs`.

---

## 📱 7. Application mobile (PWA)

La plateforme est une **Progressive Web App** : elle s'installe sur l'écran
d'accueil d'un téléphone, s'ouvre en plein écran (sans barre de navigateur) et
reste consultable sans réseau.

- **Manifeste** : `/manifest.webmanifest` — nom, icônes (`static/images/pwa/`),
  thème `#0d9488`, mode `standalone`, raccourcis « Mes cours » / « Calendrier ».
- **Service worker** : `/sw.js` — réseau d'abord pour les pages (repli cache puis
  page `/offline/`), cache d'abord pour `/static/`, jamais de mise en cache des
  POST / de l'API tuteur IA / de la vidéo HLS. Purge automatique au changement de
  version (`SW_CACHE_VERSION` dans `core/pwa.py`).
- **Installation** : Android/Chrome/Edge affichent une bannière « Installer
  EduTech » ; iOS/Safari → *Partager → Sur l'écran d'accueil*.

> ⚠️ Le service worker et l'installation exigent un **contexte sécurisé** :
> `https://…` **ou** `localhost`. En production (VM 101 derrière le reverse proxy
> HTTPS) c'est automatique. En **HTTP nu sur IP LAN** (`http://192.168.x.x`) la
> PWA est silencieusement désactivée.

### Tester la PWA sur un vrai téléphone en local

```bash
# Terminal 1 — Django
bash plateforme_educative/test_local.sh            # http://127.0.0.1:8000

# Terminal 2 — proxy HTTPS auto-signé (aucune dépendance en plus)
python plateforme_educative/serve_https.py         # https://<IP-PC>:8443
```

Sur le téléphone (même Wi-Fi) : `https://<IP-du-PC>:8443/` → accepter
l'avertissement de certificat une fois → la bannière d'installation apparaît.
Variante sans proxy (Android) : `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
→ ajouter `http://<IP-PC>:8000` → relancer Chrome.

---
*Document généré le 23 Juin 2026 — sections hors-ligne (29 Août 2026) et PWA (29 Août 2026) ajoutées.*
