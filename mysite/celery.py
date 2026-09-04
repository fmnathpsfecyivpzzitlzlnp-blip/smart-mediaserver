# mysite/celery.py
import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'mysite.settings')

app = Celery('mysite')

app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Настройка периодических задач
app.conf.beat_schedule = {
    'backup-database-every-night': {
        'task': 'blog.tasks.backup_database_to_telegram',
        # Выполнять каждый день в 03:00 ночи
        'schedule': crontab(hour=3, minute=0),
    },
}