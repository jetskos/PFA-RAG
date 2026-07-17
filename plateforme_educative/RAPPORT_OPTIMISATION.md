# Rapport d'analyse — Plateforme Éducative (PFA-RAG)

**Date :** 16/07/2026
**Projet :** Django 5 + HTMX + Celery/Redis + MySQL + Tuteur IA (LangGraph, ChromaDB, RAG hybride BM25/vecteurs)
**Apps :** `accounts`, `apprentissage`, `core`, `logistics`, `tuteur_ia`

---

## PARTIE 1 — Éléments inutiles à éliminer (~13,6 Mo + dépendances)

### 1.1 Fichiers CSS morts (~90 Ko)

| Fichier | Taille | Raison |
|---|---|---|
| `static/core/css/app_old.css` | 28 Ko | Ancien fichier « _old », référencé nulle part |
| `static/core/css/ia_premium_old.css` | 60 Ko | Ancien fichier « _old », référencé nulle part |
| `static/core/css/backgrounds.css` | 2,3 Ko | Jamais chargé dans aucun template (absent de `base.html`) |

### 1.2 Images non référencées dans `static/images/` (~11 Mo)

Aucune référence trouvée dans les templates, CSS ou Python :

- `57d2c4e710b0e494fc69761999191245.jpg`
- `admin_bg.jpg`
- `arduino-for-beginners-cbag_s.PNG`
- `aryan-nikhil-jSyzETbKch4-unsplash.jpg`
- `blue-background-with-white-line-middle_483537-4472.avif`
- `conceptartist-leeb-cover-web-02.png`
- `icon_ai_tutor_generated.png`, `icon_courses_generated.png`, `icon_iot_generated.png`, `icon_workshop_generated.png`
- `michael-fortsch-F6jTkr9T_zI-unsplash.jpg`
- `photo-1461360228754-6e81c478b882.avif`, `photo-1544396821-4dd40b938ad3.avif`, `photo-1590098563837-5e7669b27e55.avif`, `photo-1683178861337-ca70ef8c0db3.avif`, `photo-1742782328790-122e5deb2f51.avif`
- `pngtree-teacher-s-college-classroom-coaching-course-poster-background-image_188494.jpg`
- `premium_photo-1683147638125-fd31a506a429.avif`
- `shutterstock_2682150417.JPG`

### 1.3 Dossier `core/static/core/images/` entièrement inutilisé (~2,5 Mo)

Aucun fichier n'y est référencé (aucune occurrence de `core/images/` dans le code). Il contient en plus des **doublons exacts** de `static/images/` (mêmes noms de fichiers : `57d2c4e…`, `aryan-nikhil…`, `photo-*.avif`, etc.). **Tout le dossier peut être supprimé.**

### 1.4 Dépendances Python inutilisées (`requirements.txt`)

| Paquet | Constat |
|---|---|
| `djangorestframework` + `djangorestframework-simplejwt` + config DRF/JWT dans `settings.py` | **Aucune API REST n'existe** (aucune route `api/`, aucun serializer, aucune vue DRF). Seul un fichier de test l'importe. À retirer avec `rest_framework`, `rest_framework.authtoken`, `rest_framework_simplejwt` de `INSTALLED_APPS` + blocs `REST_FRAMEWORK` et `SIMPLE_JWT` |
| `django-cors-headers` | Installé mais **jamais activé** (absent de `INSTALLED_APPS` et `MIDDLEWARE`) |
| `PyPDF2` | Jamais importé — le projet utilise `pdfplumber` partout |
| `beautifulsoup4` | Jamais importé |
| `requests` | Jamais importé directement (dépendance transitive de toute façon) |
| `bcrypt` + `argon2-cffi` | `PASSWORD_HASHERS` n'est pas configuré → Django utilise PBKDF2 par défaut ; les deux paquets sont inutilisés (le commentaire dans `accounts/models.py` disant « Django gère le hachage avec bcrypt » est faux) |
| `PyJWT` | Utilisé uniquement comme dépendance transitive de simplejwt (inutile si DRF part) |
| `python-dotenv` | Jamais importé — `settings.py` a son propre chargeur `.env` maison |
| `langchain` (méta-paquet) | Seuls `langchain-core`, `langchain-groq`, `langchain-openai`, `langgraph` sont importés ; le méta-paquet `langchain` est superflu |
| `asgiref` | Dépendance automatique de Django, inutile de la lister |

**Gain :** installation Docker plus rapide, image plus légère, surface d'attaque réduite.

### 1.5 Fichiers divers

| Élément | Raison |
|---|---|
| `.vscode/settings.json` | Config personnelle d'éditeur, ne devrait pas être versionnée |
| `docs/schema.sql` | Schéma SQL figé et **désynchronisé** des modèles (les migrations sont la source de vérité) — à supprimer ou régénérer automatiquement |
| `TODO.md` | Instructions déjà obsolètes en partie (Docker gère Redis/Celery) — à intégrer au README puis supprimer |
| Migration `tuteur_ia/0006_graphcheckpoint_graphwrite.py` (doublon) | Voir problème critique n°1 ci-dessous — à éliminer via squash |

### 1.6 Code dupliqué (à factoriser, pas à supprimer aveuglément)

- **Export Excel dupliqué** : `core/views.py` (~150 lignes inline dans `export_classe_students_excel_view`) refait ce que `logistics/excel_export.py` fait déjà proprement. → Mutualiser un module `utils/excel.py`.
- **Templates quasi-doublons** : `detail_chapitre.html` / `partials/detail_chapitre.html`, `detail_cours.html` / `partials/detail_cours.html`, `chapitre_detail.html` vs `detail_chapitre.html` (noms inversés qui prêtent à confusion).
- **CSS/JS inline massif dans les templates** : `partials/detail_chapitre.html` (1 366 lignes), `admin_dashboard.html` (1 020), `dashboard_student.html` (1 017)… Les blocs `<style>`/`<script>` répétés empêchent le cache navigateur — à extraire dans des fichiers statiques.

---

## PARTIE 2 — Erreurs et problèmes identifiés

### 🔴 Critiques

**P1. Graphe de migrations `tuteur_ia` cassé (doublon 0006).**
Deux migrations `0006` (`0006_graphcheckpoint_graphwrite.py` et `0006_graphcheckpoint_graphwrite_and_more.py`) **créent les mêmes tables** (`GraphCheckpoint`, `GraphWrite`) et **renomment les mêmes index** de `documentchunk`. La migration de fusion `0008_merge` force l'application des deux branches → sur une **base de données neuve**, `migrate` plantera (« table already exists » / « index doesn't exist »). À corriger par un squash des migrations 0006→0009.

**P2. Secrets et mots de passe en dur.**
- `SECRET_KEY` avec valeur par défaut committée dans `settings.py:32`.
- Mot de passe MySQL `jatski` en dur comme défaut dans `settings.py:116`, dans `.env.docker` (committé) et dans `docker-compose.yml`.
- `DEBUG=True` par défaut (`settings.py:35`) : un oubli de variable d'env en production expose les pages de debug.

**P3. `ALLOWED_HOSTS` contient `'*'` par défaut** (`settings.py:45`) — combiné à `SECURE_PROXY_SSL_HEADER` toujours actif (`settings.py:53`), cela permet le spoofing d'en-tête `X-Forwarded-Proto` quand l'app n'est pas derrière un proxy de confiance.

**P4. Tests `accounts` incompatibles Django 5.**
`accounts/tests.py` utilise l'ancienne signature `assertFormError(response, 'form', …)` **supprimée dans Django 5.0**, alors que `requirements.txt` impose `Django>=5.0`. Ces tests lèvent une `TypeError` — la suite de tests ne peut pas passer.

### 🟠 Importants

**P5. Docker incohérent avec la production.**
- `docker-compose.yml` lance `python manage.py runserver` (serveur de dev) avec `DJANGO_DEBUG=True`, alors que le `Dockerfile` prévoit `start.sh` (Daphne + Celery).
- Le volume `.:/app` écrase le `collectstatic` fait dans l'image.
- `start.sh` lance Celery et Daphne dans le **même conteneur** avec `&` : si Celery meurt, rien ne le relance et Docker ne le voit pas.
- Ports MySQL incohérents entre les configs : défaut `3307` (settings), `3308→3306` (compose), `3306` (.env.docker) — source classique d'erreurs de connexion.

**P6. Driver MySQL ambigu.** `settings.py` tente `pymysql` (non listé dans `requirements.txt`) avec un `except ImportError: pass` silencieux, tandis que `requirements.txt` installe `mysqlclient`. Si les deux manquent, l'erreur apparaît tard et de façon cryptique. Choisir un seul driver.

**P7. 63 blocs `except Exception` génériques** dans les vues/tâches, dont plusieurs qui avalent l'erreur avec un simple `print()` (`logistics/views.py:614,663`, `apprentissage/views_wizard.py:110`). Aucune configuration `LOGGING` dans le projet : les erreurs en production sont invisibles. Remplacer par le module `logging` + capturer des exceptions précises.

**P8. Performance upload PDF (documenté dans TODO.md).** `CELERY_TASK_ALWAYS_EAGER` par défaut rend l'indexation RAG (extraction + embeddings ChromaDB) **synchrone** pendant la requête HTTP → uploads très lents et risque de timeout. Le mode asynchrone existe mais n'est pas activé par défaut en dev.

**P9. Emails synchrones dans les vues.** Plusieurs envois d'emails sont faits dans le cycle requête/réponse (avec `EMAIL_TIMEOUT=5`) au lieu de passer par les tâches Celery existantes — chaque action admin peut bloquer jusqu'à 5 s.

### 🟡 Mineurs

- **P10.** `print()` de debug résiduels (4 occurrences hors tests/migrations) au lieu de `logging`.
- **P11.** Numérotation des migrations `apprentissage` trouée (`0002` → `0005`) : fonctionne, mais révèle des suppressions manuelles ; risque si d'autres branches existent.
- **P12.** `X_FRAME_OPTIONS = 'SAMEORIGIN'` global au lieu de `DENY` + exceptions ciblées.
- **P13.** Pas de `.gitignore` visible à la racine du projet (les caches `__pycache__`, `chroma_db/`, `media/` risquent d'être versionnés).
- **P14.** `EMAIL_HOST_PASSWORD` attendu en clair dans `.env.docker` committé — modèle à déplacer vers `.env.example` uniquement.
- **P15.** `whitenoise CompressedManifestStaticFilesStorage` + images non optimisées (17 Mo dans `static/images`, certaines >1 Mo) : temps de `collectstatic` et de premier chargement inutilement longs. Compresser/convertir en WebP/AVIF les JPG/PNG lourds restants.

---

## PARTIE 3 — Plan d'action recommandé (ordre de priorité)

1. **Corriger le graphe de migrations `tuteur_ia`** (P1) — bloquant pour toute nouvelle installation.
2. **Sécuriser la config** (P2, P3) : exiger `DJANGO_SECRET_KEY` sans défaut, `DEBUG=False` par défaut, retirer `'*'` d'`ALLOWED_HOSTS`, conditionner `SECURE_PROXY_SSL_HEADER`, retirer `jatski` du dépôt.
3. **Réparer les tests** (P4) : nouvelle signature `assertFormError(response.context['form'], None, "…")`.
4. **Purger les fichiers morts** (§1.1–1.3) : ~13,6 Mo.
5. **Alléger `requirements.txt`** (§1.4) : retirer DRF/JWT/CORS/PyPDF2/bs4/bcrypt/argon2/python-dotenv/langchain méta.
6. **Unifier Docker** (P5) et activer le vrai mode asynchrone Celery (P8).
7. **Ajouter `LOGGING`** et remplacer les `print()`/`except Exception` muets (P7, P10).
8. **Factoriser** l'export Excel et extraire le CSS/JS inline des gros templates (§1.6).
