from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-pwb^w4t%9fplrljnh7h*4v%p+yfg^po)mf@2vtf_j7f@)(!lmm'

DEBUG = False

ALLOWED_HOSTS = [
    "synchro.ambipar.vps-kinghost.net",
    "177.153.69.133",
    "industrial-cleaning.vps-kinghost.net",
    "ambipar.vps-kinghost.net",
    "synchro.industrial-cleaning.vps-kinghost.net",
    "localhost",
    "127.0.0.1",
]

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'GO.apps.GoConfig',
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

ROOT_URLCONF = 'setup.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'setup.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

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

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / "GO/static"]
STATIC_ROOT = "/var/www/html/GESTAO_OPERACIONAL/static/"
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

try:
    if isinstance(MIDDLEWARE, (list, tuple)):
        mw_list = list(MIDDLEWARE)
        wn = 'whitenoise.middleware.WhiteNoiseMiddleware'
        if wn not in mw_list:
            try:
                idx = mw_list.index('django.middleware.security.SecurityMiddleware')
                mw_list.insert(idx + 1, wn)
            except ValueError:
                mw_list.insert(0, wn)
        MIDDLEWARE = mw_list
except Exception:
    pass

MEDIA_URL = '/media/'
MEDIA_ROOT = '/var/www/html/GESTAO_OPERACIONAL/fotos_rdo/'

EMAIL_BACKEND = os.environ.get('DJANGO_EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')

try:
    MIDDLEWARE = list(MIDDLEWARE)
    mw = 'GO.middleware.supervisor_middleware.SupervisorForceRdoMiddleware'
    if mw not in MIDDLEWARE:
        try:
            idx = MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware')
            MIDDLEWARE.insert(idx + 1, mw)
        except ValueError:
            MIDDLEWARE.append(mw)
except Exception:
    pass

try:
    cp = 'GO.context_processors.mobile_detector'
    if 'TEMPLATES' in globals() and isinstance(TEMPLATES, (list, tuple)) and len(TEMPLATES) > 0:
        try:
            opts = TEMPLATES[0].setdefault('OPTIONS', {})
            cps = opts.setdefault('context_processors', [])
            if cp not in cps:
                cps.append(cp)
        except Exception:
            pass
except Exception:
    pass

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTHENTICATION_BACKENDS = [
    'GO.email_backend.EmailBackend',
]

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(name)s %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'level': 'ERROR',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': '/var/log/django_errors.log',
            'formatter': 'verbose',
            'level': 'ERROR',
            'mode': 'a',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': True,
        },
        'django.request': {
            'handlers': ['console', 'file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}