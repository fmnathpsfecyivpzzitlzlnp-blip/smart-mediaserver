# mysite/settings.py

from pathlib import Path
import os

# Строим пути внутри проекта: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================================================================
# БЕЗОПАСНОСТЬ И КОНФИГУРАЦИЯ СРЕДЫ
# ==============================================================================

# Секретный ключ берем из .env. Если его нет — используем временный (только для локальной разработки!)
SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-default-dev-key-change-me')

# Режим отладки. Читаем из .env, по умолчанию False для безопасности.
# В вашем .env стоит DEBUG=True, так что отладка будет включена.
DEBUG = os.environ.get('DEBUG', 'False') == 'True'

# Хосты. В Docker обычно разрешают все ('*'), так как IP контейнеров меняются.
ALLOWED_HOSTS = ['media.local', 'localhost', '127.0.0.1', '*']

# ==============================================================================
# ПРИЛОЖЕНИЯ
# ==============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Ваши приложения
    'blog',

    # Сторонние библиотеки
    'django_celery_beat',  # Планировщик задач
    'tinymce',  # Текстовый редактор
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

ROOT_URLCONF = 'mysite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],  # Можно добавить BASE_DIR / 'templates', если создадите общую папку
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # Важно для работы {{ MEDIA_URL }} в шаблонах
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'mysite.wsgi.application'

# ==============================================================================
# БАЗА ДАННЫХ
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE': os.environ.get('SQL_ENGINE', 'django.db.backends.sqlite3'),
        'NAME': BASE_DIR / 'db' / os.environ.get('SQL_DATABASE', 'db.sqlite3'),
    }
}

# ==============================================================================
# ПАРОЛИ И АВТОРИЗАЦИЯ
# ==============================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# Куда перенаправлять после входа/выхода
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# ==============================================================================
# ЯЗЫК И ВРЕМЯ
# ==============================================================================

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = os.environ.get('TIME_ZONE', 'Europe/Moscow')
USE_I18N = True
USE_TZ = True

# ==============================================================================
# СТАТИЧЕСКИЕ И МЕДИА ФАЙЛЫ
# ==============================================================================

# Статика (CSS, JS, Картинки админки)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_FINDERS = [
    'django.contrib.staticfiles.finders.FileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]

# Медиа (Ваши фильмы, обложки, музыка)
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')  # В Docker это мапится на папку Ready

# ==============================================================================
# НАСТРОЙКИ ЗАГРУЗКИ ФАЙЛОВ
# ==============================================================================

# Разрешаем загрузку больших файлов (до 10 ГБ) через админку/формы
DATA_UPLOAD_MAX_MEMORY_SIZE = 10737418240  # 10 GB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10737418240  # 10 GB
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000  # Увеличиваем лимит полей формы

# ==============================================================================
# ИНТЕГРАЦИИ И API (ЧИТАЕМ ИЗ .ENV)
# ==============================================================================

# 1. TMDb (Кинобаза)
TMDB_API_KEY = os.environ.get('TMDB_API_KEY')
TMDB_LANGUAGE = os.environ.get('TMDB_LANGUAGE', 'ru-RU')

# 2. Telegram Bot
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# 3. Погода
WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY')
WEATHER_CITY = os.environ.get('WEATHER_CITY', 'Moscow')

# 4. Email (для разработки выводим в консоль)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ==============================================================================
# CELERY (ФОНОВЫЕ ЗАДАЧИ)
# ==============================================================================

CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE

# Расписание задач (Beat)
CELERY_BEAT_SCHEDULE = {
    'send-morning-briefing': {
        'task': 'blog.tasks.send_daily_summary',
        'schedule': 86400.0,  # Раз в сутки
    },
    'cleanup-logs-daily': {
        'task': 'blog.tasks.cleanup_old_logs',
        'schedule': 86400.0,  # Раз в сутки очищаем старые логи
    },
}

# ==============================================================================
# СПЕЦИФИЧЕСКИЕ НАСТРОЙКИ ПРОЕКТА
# ==============================================================================

# Путь внутри контейнера, где лежат исходники фильмов (D:\mediaserver\Movies)
MOVIES_SCAN_DIR = '/source_movies'

# === НАСТРОЙКИ ДИСКОВ ===
# Читаем список дисков из .env (C,D,E...)
RAW_DRIVES = os.environ.get('MOUNTED_DRIVES', 'D').split(',')
READ_ONLY_LIST = os.environ.get('READ_ONLY_DRIVES', 'C').split(',')

INDEXER_LOCATIONS = {}

for drive in RAW_DRIVES:
    drive_letter = drive.strip().upper()  # "D"
    drive_slug = f"disk-{drive_letter.lower()}"  # "disk-d"

    # Путь внутри контейнера (как мы договорились в docker-compose)
    container_path = f"/drives/{drive_letter.lower()}"

    INDEXER_LOCATIONS[drive_slug] = {
        'name': f"Диск {drive_letter}",  # Красивое имя
        'container_path': container_path,  # Путь (/drives/d)
        'read_only': drive_letter in READ_ONLY_LIST  # Защита (True/False)
    }

# Пример того, что получится автоматически:
# {
#    'disk-c': {'name': 'Диск C', 'container_path': '/drives/c', 'read_only': True},
#    'disk-d': {'name': 'Диск D', 'container_path': '/drives/d', 'read_only': False},
# }
# ==============================================================================
# TINYMCE (ВИЗУАЛЬНЫЙ РЕДАКТОР)
# ==============================================================================

TINYMCE_DEFAULT_CONFIG = {
    'height': 500,
    'width': '100%',
    'menubar': True,
    'plugins': 'advlist autolink lists link image charmap preview anchor '
               'searchreplace visualblocks code fullscreen insertdatetime '
               'table help wordcount codesample',
    'toolbar': 'undo redo | blocks | bold italic forecolor | '
               'alignleft aligncenter alignright alignjustify | '
               'bullist numlist outdent indent | '
               'table link image codesample | removeformat | fullscreen',
    'custom_undo_redo_levels': 10,
    'language': 'ru',
}

# ==============================================================================
# ЛОГИРОВАНИЕ (LOGGING)
# ==============================================================================
# Чтобы видеть ошибки Celery и Django в консоли (docker logs)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{asctime} [{levelname}] {message}',
            'style': '{',
            'datefmt': '%H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'media_server.log',
            'formatter': 'verbose',
            'level': 'INFO',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'blog.tasks': {  # Логи ваших задач
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Создаем папку для логов, если её нет
LOGS_DIR = BASE_DIR / 'logs'
if not LOGS_DIR.exists():
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # Если не вышло создать, будем писать только в консоль

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

SESSION_COOKIE_NAME = 'media_sessionid'
CSRF_COOKIE_NAME = 'media_csrftoken'