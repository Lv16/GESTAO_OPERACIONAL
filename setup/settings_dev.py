from .settings import *

DEBUG = True

ALLOWED_HOSTS = [
    "*",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "192.168.0.10",
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "http://0.0.0.0:8001",
    "http://192.168.0.10:8001",
    "http://localhost:8002",
    "http://127.0.0.1:8002",
    "http://0.0.0.0:8002",
    "http://192.168.0.10:8002",
]

# Em ambiente de desenvolvimento, evitar forçar HTTPS
SECURE_SSL_REDIRECT = False
# Não confiar automaticamente no header X-Forwarded-Proto no dev
SECURE_PROXY_SSL_HEADER = None

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

import os
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_dev.sqlite3',
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

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

# Garantir que `django_extensions` esteja disponível no dev para runserver_plus
try:
    INSTALLED_APPS = list(INSTALLED_APPS)
    if 'django_extensions' not in INSTALLED_APPS:
        INSTALLED_APPS.append('django_extensions')
except Exception:
    pass

# Permitir adicionar a origem pública via variável de ambiente PUBLIC_IP
try:
    pub = os.environ.get('PUBLIC_IP')
    if pub:
        http_origin = f"http://{pub}:8001"
        https_origin = f"https://{pub}:8001"
        # Adiciona em CSRF_TRUSTED_ORIGINS se não existir
        try:
            if 'CSRF_TRUSTED_ORIGINS' in globals() and isinstance(CSRF_TRUSTED_ORIGINS, (list, tuple)):
                if http_origin not in CSRF_TRUSTED_ORIGINS:
                    CSRF_TRUSTED_ORIGINS.append(http_origin)
                if https_origin not in CSRF_TRUSTED_ORIGINS:
                    CSRF_TRUSTED_ORIGINS.append(https_origin)
        except Exception:
            pass
        # Adiciona HOST público em ALLOWED_HOSTS se necessário
        try:
            if 'ALLOWED_HOSTS' in globals() and isinstance(ALLOWED_HOSTS, (list, tuple)):
                if pub not in ALLOWED_HOSTS:
                    ALLOWED_HOSTS.append(pub)
        except Exception:
            pass
except Exception:
    pass