try:
    import pymysql
    pymysql.install_as_MySQLdb()
except ImportError:
    pass

from pathlib import Path
import os
import sys as _sys

# `manage.py test` : évite d'appliquer le durcissement de prod (redirection SSL,
# garde SECRET_KEY…) à la suite de tests, qui tourne sans variables d'env.
_TESTING = 'test' in _sys.argv


def _load_env_file(env_path: Path) -> None:
    """Load simple KEY=VALUE lines from a local .env file."""
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue

        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
_load_env_file(BASE_DIR / '.env')


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-9h8fzyz98diom8_mc@mb%y*%--n3)$!=#-4*l(&e38@pegwd-b')

# SECURITY WARNING: don't run with debug turned on in production!
# Défaut sûr : False. Le développement local active DJANGO_DEBUG=True via .env
# ou test_local.sh.
DEBUG = os.getenv('DJANGO_DEBUG', 'False').lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    return [item.strip() for item in raw_value.split(',') if item.strip()]


# En prod : liste blanche stricte via DJANGO_ALLOWED_HOSTS (ex. "mon-noeud.lan,10.0.0.5").
# En dev (DEBUG) : wildcard toléré pour l'accès téléphone en LAN sans configuration.
ALLOWED_HOSTS = _env_list(
    'DJANGO_ALLOWED_HOSTS',
    ['*'] if DEBUG else ['127.0.0.1', 'localhost'],
)

CSRF_TRUSTED_ORIGINS = _env_list('DJANGO_CSRF_TRUSTED_ORIGINS', [
    'https://*.up.railway.app', 
    'https://*.railway.app',
    'https://edutech1.up.railway.app'
])

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'accounts',
    'apprentissage',
    'logistics',
    'tuteur_ia',
]

MIDDLEWARE = [
    'core.middleware.HTMXHistoryRestoreMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.notifications',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

db_engine_env = os.getenv('DB_ENGINE', 'mysql')
if db_engine_env.lower() == 'mysql':
    db_engine = 'django.db.backends.mysql'
else:
    db_engine = db_engine_env

DATABASES = {
    'default': {
        'ENGINE': db_engine,
        'NAME': os.getenv('DB_NAME', 'rag_platforme1'),
        'USER': os.getenv('DB_USER', 'root'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', '127.0.0.1'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', 60)),
    }
}

# SQLite (test local, mode hors-ligne sur petit nœud) : laisser plus de temps
# aux écritures pour prendre le verrou plutôt que d'échouer immédiatement, et
# passer en WAL pour que lectures et écritures ne se bloquent pas mutuellement
# (utile pour le tuteur IA : le checkpointer LangGraph écrit pendant la requête).
if db_engine == 'django.db.backends.sqlite3':
    DATABASES['default'].setdefault('OPTIONS', {})['timeout'] = 20
    from django.db.backends.signals import connection_created

    def _sqlite_pragmas(sender, connection, **kwargs):
        if connection.vendor == 'sqlite':
            cur = connection.cursor()
            cur.execute('PRAGMA journal_mode=WAL;')
            cur.execute('PRAGMA synchronous=NORMAL;')
            cur.execute('PRAGMA busy_timeout=20000;')

    connection_created.connect(_sqlite_pragmas)

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# 'fr' (et non 'fr-fr') : doit correspondre à une entrée de LANGUAGES pour que
# reverse()/i18n_patterns génèrent des URLs valides (/fr/…) même hors requête
# (tâches Celery, commandes, tests).
LANGUAGE_CODE = 'fr'
TIME_ZONE = 'Africa/Casablanca'
USE_I18N = True
USE_TZ = True

from django.utils.translation import gettext_lazy as _

LANGUAGES = [
    ('fr', _('Français')),
    ('en', _('English')),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Boîte de réception satellite (carrousel FLUTE) : dossier où le récepteur multicast
# (`carrousel_client.py --output <ce dossier>`) dépose les fichiers reçus. Le tableau
# de bord admin y détecte les ZIP d'export de cours et propose de les importer.
SATELLITE_INBOX_DIR = os.getenv('SATELLITE_INBOX_DIR') or str(MEDIA_ROOT / 'satellite_inbox')

# Vidéos de secours hors-ligne (jusqu'à ~300 Mo, voir validate_video_file_size)
DATA_UPLOAD_MAX_MEMORY_SIZE = 314572800  # 300 Mo
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760   # 10 Mo — au-delà, écrit sur disque au lieu de garder en mémoire

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

AUTH_USER_MODEL = 'accounts.Utilisateur'

# Connexion par e-mail insensible à la casse (claviers mobiles + SQLite
# sensible à la casse). ModelBackend gardé en repli.
AUTHENTICATION_BACKENDS = [
    'accounts.backends.CaseInsensitiveModelBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# URL names (not hard paths) so login/redirect targets keep the active
# language prefix from i18n_patterns instead of falling back to the browser locale.
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'accueil'
LOGOUT_REDIRECT_URL = 'accueil'
# Security settings for deployment
if not DEBUG and not _TESTING:
    SECURE_SSL_REDIRECT = os.getenv('DJANGO_SECURE_SSL_REDIRECT', 'True').lower() in {'1', 'true', 'yes', 'on'}
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000 # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    X_FRAME_OPTIONS = 'DENY'

    # Pas de clé secrète fournie en prod : on en génère une éphémère (les sessions
    # existantes seront invalidées au redémarrage) plutôt que de servir la clé
    # `django-insecure-` du dépôt. Un déploiement sérieux fixe DJANGO_SECRET_KEY.
    if not os.getenv('DJANGO_SECRET_KEY') or 'django-insecure-' in SECRET_KEY:
        import warnings
        from django.core.management.utils import get_random_secret_key
        SECRET_KEY = get_random_secret_key()
        warnings.warn(
            "DJANGO_SECRET_KEY non défini en production : clé aléatoire éphémère "
            "générée. Fixez DJANGO_SECRET_KEY pour des sessions persistantes.",
            RuntimeWarning,
        )
else:
    X_FRAME_OPTIONS = 'SAMEORIGIN'

# Email
if DEBUG:
    EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
else:
    EMAIL_BACKEND = os.getenv('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')

EMAIL_HOST = os.getenv('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 25))
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.getenv('EMAIL_USE_TLS', 'False').lower() in {'1', 'true', 'yes', 'on'}
EMAIL_TIMEOUT = 5
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'webmaster@localhost')

GROQ_API_KEY = os.getenv('GROQ_API_KEY', '')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TASK_DEFAULT_QUEUE = 'pfa_rag_queue_v2'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'False').lower() in {'1', 'true', 'yes', 'on'}
CELERY_TASK_EAGER_PROPAGATES = os.getenv('CELERY_TASK_ALWAYS_EAGER', 'False').lower() in {'1', 'true', 'yes', 'on'}

# Pendant `manage.py test`, exécuter les tâches Celery en synchrone (pas de worker
# ni de Redis requis) et utiliser un backend e-mail en mémoire.
if _TESTING:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']  # tests plus rapides
    # Stockage statique simple : la suite de tests n'exige plus un
    # `collectstatic` préalable (le storage à manifeste est strict et
    # échoue sur `{% static %}` sans staticfiles.json).
    STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'