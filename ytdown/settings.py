"""
Django settings for ytdown project.

Generated by 'django-admin startproject' using Django 5.2.3.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.2/ref/settings/
"""

from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url # Import dj_database_url

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Get ALLOWED_HOSTS from environment, splitting by comma
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')
if ALLOWED_HOSTS == ['']:
    ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'downloader',
    'crispy_forms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'ytdown.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates' ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'ytdown.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

# --- DEBUGGING START ---
# Get DATABASE_URL from environment for explicit inspection
_db_url_from_env = os.getenv('DATABASE_URL')

print(f"DEBUG: Value of DATABASE_URL from os.getenv: '{_db_url_from_env}'")

if not _db_url_from_env:
    print("DEBUG: DATABASE_URL is empty or None! This will cause an error.")
    # You could raise an exception here to stop execution immediately:
    # raise Exception("DATABASE_URL environment variable is not set or empty!")

# Use dj_database_url to parse the DATABASE_URL environment variable
DATABASES = {
    'default': dj_database_url.config(
        default=_db_url_from_env, # Pass the variable directly
        conn_max_age=600 # Optional: Reconnect after 10 minutes
    )
}
print(f"DEBUG: DATABASES['default'] after dj_database_url.config: {DATABASES['default']}")

# --- DEBUGGING END ---


# Ensure the MySQL engine is set correctly by dj_database_url,
# and add common options if needed (dj_database_url handles many defaults)
# You might want to explicitly set charset for full emoji support if not handled by default
# This part is generally covered by dj_database_url, but for explicit control:
if 'ENGINE' in DATABASES['default'] and DATABASES['default']['ENGINE'] == 'django.db.backends.mysql':
    if 'OPTIONS' not in DATABASES['default']:
        DATABASES['default']['OPTIONS'] = {}
    DATABASES['default']['OPTIONS']['charset'] = 'utf8mb4'
    print("DEBUG: MySQL charset utf8mb4 option applied.")
else:
    # This might happen if DATABASE_URL was invalid and django didn't set an engine
    print(f"DEBUG: MySQL backend not detected or 'ENGINE' key missing. Current engine: {DATABASES['default'].get('ENGINE', 'N/A')}")


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

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


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles') 
# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

CRISPY_TEMPLATE_PACK = 'bootstrap4'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')