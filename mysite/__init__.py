# mysite/__init__.py
# чтобы Celery запускался вместе с Django:
from .celery import app as celery_app

__all__ = ('celery_app',)