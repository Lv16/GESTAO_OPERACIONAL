from .settings import *

# Desenvolvimento: depure localmente sem afetar o deploy
DEBUG = True

# Permitir acesso local e via container/túnel
ALLOWED_HOSTS = [
    "*",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
]

# Evitar problemas de CSRF ao usar porta alternativa
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "http://0.0.0.0:8001",
]

# E-mails vão para o console no dev
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# Banco de dados separado para desenvolvimento
import os
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db_dev.sqlite3',
        # Aumentar timeout ajuda a reduzir erros 'database is locked' em
        # ambientes com alguma concorrência durante desenvolvimento.
        # Ajuste conforme necessário; em produção prefira PostgreSQL/MySQL.
        'OPTIONS': {
            'timeout': 20,
        },
    }
}

# Static: no dev o Django serve direto de STATICFILES_DIRS
# (STATIC_ROOT é ignorado no runserver)

# Injetar middleware restritivo para contas do grupo 'Supervisor' em dev
try:
    MIDDLEWARE = list(MIDDLEWARE)
    mw = 'GO.middleware.supervisor_middleware.SupervisorForceRdoMiddleware'
    if mw not in MIDDLEWARE:
        # inserir após AuthenticationMiddleware para que user esteja disponível
        try:
            idx = MIDDLEWARE.index('django.contrib.auth.middleware.AuthenticationMiddleware')
            MIDDLEWARE.insert(idx + 1, mw)
        except ValueError:
            MIDDLEWARE.append(mw)
except Exception:
    # se algo falhar, não impedir o startup
    pass

# Injetar context processor para detectar mobile em desenvolvimento (opcional)
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
