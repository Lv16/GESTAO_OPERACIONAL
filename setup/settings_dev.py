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
]

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