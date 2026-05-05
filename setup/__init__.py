try:
    from .celery import app as celery_app
except ModuleNotFoundError as exc:
    if getattr(exc, 'name', '') != 'celery':
        raise
    celery_app = None

__all__ = ('celery_app',)
