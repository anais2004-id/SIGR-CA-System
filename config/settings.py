# config/settings.py
import os
from pathlib import Path
from pymongo import MongoClient

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'your-secret-key-here'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'dashboard',
]
# Configuration des sessions pour qu'elles soient partagées
SESSION_ENGINE = 'django.contrib.sessions.backends.db'  # Utilise la base de données
SESSION_COOKIE_AGE = 3600 * 24 * 7  # 7 jours
SESSION_SAVE_EVERY_REQUEST = True  # Sauvegarde à chaque requête
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
# config/settings.py - Ajoutez dans MIDDLEWARE
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dashboard.middleware.UserSessionMiddleware', 
     'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',  # ← CRUCIAL
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dashboard.middleware.UserSessionMiddleware',  # Votre middleware # Ajouter cette ligne
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_USER_MODEL = 'dashboard.Utilisateur'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Algiers'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

# ── Configuration email (SMTP Gmail) ────────────────────────────────────────
# Remplacez par vos vraies informations avant le déploiement.
# Pour Gmail : activez "Mots de passe d'application" dans votre compte Google
# (Sécurité > Validation en 2 étapes > Mots de passe d'application).
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'votre.email@gmail.com'        # <-- à remplacer
EMAIL_HOST_PASSWORD = 'xxxx xxxx xxxx xxxx'       # <-- mot de passe d'application Gmail
DEFAULT_FROM_EMAIL = 'SIGR-CA <votre.email@gmail.com>'  # <-- à remplacer

# En développement, pour tester sans vrai serveur SMTP,
# commentez les lignes ci-dessus et décommentez la ligne suivante :
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# MongoDB Configuration
MONGO_CLIENT = MongoClient('localhost', 27017)
MONGO_DB = MONGO_CLIENT['general_emballage']
# config/settings.py
CSRF_COOKIE_SECURE = False  # Pour le développement
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000']
# Ajoutez cette configuration pour le cache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,  # 5 minutes
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}
# ── Configuration Email (SMTP Gmail) ────────────────────────────────────────
# Pour utiliser Gmail : activez "Mots de passe d'application" dans votre compte Google
# puis remplacez les valeurs ci-dessous.
# Tutoriel : https://support.google.com/accounts/answer/185833
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_SSL = True
EMAIL_USE_TLS = False
EMAIL_HOST_USER = 'souhla.ghanem@gmail.com'
EMAIL_HOST_PASSWORD = 'vkql vguf wvqc ykph'   # mot de passe d'application
DEFAULT_FROM_EMAIL = 'SIGR-CA <souhla.ghanem@gmail.com>'

 
# ── Pour tester en développement (écrit les emails dans la console) ──────────
# Commentez les lignes EMAIL_BACKEND..DEFAULT_FROM_EMAIL ci-dessus
# et décommentez la ligne suivante :
#EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'