# config/settings.py
import os
from pathlib import Path
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'your-secret-key-here'

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    #'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'dashboard',
]

# Sessions stockées en base (djongo gère la table django_session via MongoDB)
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_AGE = 3600 * 24 * 7   # 7 jours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    # ↓ Notre middleware injecte request.user depuis la session MongoDB
    #   Il REMPLACE django.contrib.auth.middleware.AuthenticationMiddleware
    'dashboard.middleware.MongoAuthMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'dashboard.middleware.UserSessionMiddleware',
]

if DEBUG:
    MIDDLEWARE.append('dashboard.middleware.NoBrowserCacheMiddleware')

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
                # NE PAS utiliser django.contrib.auth.context_processors.auth
                # car il appelle request.user.get_all_permissions() via Django ORM
                # 'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'dashboard.context_processors.employe_photo',
                # Notre context processor qui expose user dans les templates
                'dashboard.context_processors.mongo_user_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# djongo reste pour les sessions et les modèles Django (AccessRule, etc.)
DATABASES = {
    'default': {
        'ENGINE': 'djongo',
        'NAME': 'general_emballage',
        'CLIENT': {
            'host': 'mongodb://localhost:27017',
        }
    }
}

# On n'utilise plus Django Auth pour les utilisateurs
# AUTH_USER_MODEL = 'dashboard.Utilisateur'  # ← retiré

AUTH_PASSWORD_VALIDATORS = []  # inutile, on utilise bcrypt

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

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False
EMAIL_HOST_USER = os.getenv("EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
DEFAULT_FROM_EMAIL = 'SIGR-CA <souhla.ghanem@gmail.com>'

# MongoDB direct (pour toute la logique métier)
MONGO_CLIENT = MongoClient('localhost', 27017)
MONGO_DB = MONGO_CLIENT['general_emballage']

CSRF_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000']

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}

ESP32_API_KEY = "123456789ZAHRA"

CRONJOBS = [
    ('0 9 * * *', 'django.core.management.call_command', ['rappel_retour_ressource']),
]