# blog/tasks.py
import os
import re
import shutil
import subprocess
import json
import uuid
import math
import datetime
from pathlib import Path

import requests
import telebot # Новый импорт

from celery import shared_task
from django.conf import settings
from django.core.files import File # <--- Важный импорт для нового кода
from django.core.files.base import ContentFile
from django.utils import timezone, duration
from slugify import slugify
from PIL import Image

from .models import Video, Genre, Country, UserProfile, Task, Person, Purchase
from .models import ProcessingLog # Импорт
from .utils import generate_cover_image
from django.contrib.auth.models import User # <-- КЛЮЧЕВОЙ ИМПОРТ
from mysite.celery import app
import telebot
import logging
# Создаем логгер, который будет писать в консоль и файл
logger = logging.getLogger(__name__)


# --- ЗАДАЧА 1: ОТПРАВКА УВЕДОМЛЕНИЙ В TELEGRAM ---
@shared_task
def send_telegram_notification(user_id, message):
    print(f"--- TELEGRAM TASK STARTED for user: {user_id} ---")
    try:
        user = User.objects.get(id=user_id)
        chat_id = user.profile.telegram_chat_id
        token = settings.TELEGRAM_BOT_TOKEN

        if not token:
            print("TELEGRAM ERROR: Bot token is not configured in settings.py")
            return

        if not chat_id:
            print(f"TELEGRAM INFO: User {user.username} has no chat_id.")
            return

        print(f"TELEGRAM INFO: Attempting to send to chat_id={chat_id}")
        bot = telebot.TeleBot(token)
        bot.send_message(chat_id, message, parse_mode='Markdown')
        print(f"--- TELEGRAM TASK SUCCEEDED for user: {user.username} ---")

    except User.DoesNotExist:
        print(f"TELEGRAM ERROR: User {user_id} not found.")
    except Exception as e:
        print(f"!!! TELEGRAM CRITICAL ERROR !!! Could not send message to user {user_id}.")
        print(f"Error Details: {e}")


# --- ЗАДАЧА 2: Ежедневная сводка ---
@shared_task
def send_daily_summary():
    bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
    today = timezone.localdate()

    # Ищем пользователей с Telegram ID
    for profile in UserProfile.objects.filter(telegram_chat_id__isnull=False):
        user = profile.user

        # 1. Задачи на сегодня
        tasks = Task.objects.filter(
            assigned_to=user,
            is_completed=False,
            due_date__date=today
        )

        if not tasks.exists():
            continue  # Если задач нет, можно молчать (или пожелать хорошего дня)

        # 2. Серия (Streak) - простая проверка
        # (Сюда можно вставить логику расчета стрика из views.py, если хочешь точную цифру)

        # Формируем сообщение
        msg = f"🌅 <b>Доброе утро, {user.username}!</b>\n\n"
        msg += f"План на сегодня ({today.strftime('%d.%m')}):\n"

        for t in tasks:
            icon = "🎓" if "Изучение" in t.project.name else "▫️"
            msg += f"{icon} {t.title}\n"

        msg += "\n<i>Не прерывай цепочку обучения! 🔥</i>"
        msg += f"\n<a href='http://127.0.0.1/dashboard/'>Открыть дашборд</a>"  # Замени IP на свой VPN IP

        try:
            bot.send_message(profile.telegram_chat_id, msg, parse_mode='HTML')
        except Exception as e:
            print(f"Error sending tg to {user.username}: {e}")


# ===============================================
# ЗАДАЧА 2: ЗАГРУЗКА МЕТАДАННЫХ С TMDB
# ===============================================
@shared_task
def fetch_tmdb_metadata(video_id):
    """
    Получает расширенные метаданные с TMDb: постер, описание, рейтинг, год,
    жанры, страны, актеров и режиссеров. Имеет улучшенную логику очистки названия.
    """
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return

    try:
        api_key = settings.TMDB_API_KEY
        if not api_key:
            print("METADATA WARNING: No TMDB API key is configured.")
            return

        # --- УЛУЧШЕННАЯ И ОЧИЩЕННАЯ ЛОГИКА ОЧИСТКИ НАЗВАНИЯ ---
        # 1. Берем исходное название из базы
        temp_title = video.title

        # 2. Пытаемся извлечь год и сохранить его, если он еще не задан.
        year_match = re.search(r'\b(19[89]\d|20\d{2})\b', temp_title)
        search_year = video.year
        if year_match and not search_year:
            search_year = int(year_match.group(0))
            # Не сохраняем в модель сразу, используем только для поиска

        # 3. Удаляем все в скобках [] и (), год, и "мусорные" слова
        temp_title = re.sub(r'\[.*?\]|\(.*?\)', '', temp_title)
        temp_title = re.sub(r'\b(19[89]\d|20\d{2})\b', '', temp_title)  # Удаляем год
        temp_title = re.sub(r'1080p|720p|HD|BluRay|BDRip|WEB-DL|NNMCLUB', '', temp_title, flags=re.IGNORECASE)

        # 4. Убираем лишние пробелы по краям
        clean_title = temp_title.strip()
        print(f"METADATA: Searching TMDb for title='{clean_title}', year='{search_year}'")
        # --- КОНЕЦ ЛОГИКИ ОЧИСТКИ ---

        # Шаг 1: Ищем фильм, добавляя год для точности, если он есть
        search_params = {'api_key': api_key, 'query': clean_title, 'language': 'ru-RU'}
        if search_year:
            search_params['year'] = search_year

        search_res = requests.get("https://api.themoviedb.org/3/search/movie", params=search_params, timeout=10)
        search_res.raise_for_status()
        search_data = search_res.json()
        if not search_data.get('results'):
            print(f"METADATA INFO: Movie '{clean_title}' not found on TMDb. Technical cover will be used.")
            return

        tmdb_id = search_data['results'][0]['id']

        # Шаг 2: Загружаем детали и каст/съемочную группу
        details_url = f"https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={api_key}&language=ru-RU&append_to_response=credits"
        details_res = requests.get(details_url, timeout=10)
        details_res.raise_for_status()
        details_data = details_res.json()
        credits_data = details_data.get('credits', {})

        # Шаг 3: Обновляем все поля в объекте video
        video.description = details_data.get('overview', '')
        video.rating = details_data.get('vote_average', 0.0)
        if details_data.get('release_date'):
            video.year = int(details_data['release_date'].split('-')[0])

        poster_path = details_data.get('poster_path')
        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
            img_res = requests.get(poster_url, stream=True, timeout=10)
            if img_res.status_code == 200:
                file_name = f"poster_{video.pk}.jpg"
                video.cover.save(file_name, ContentFile(img_res.content), save=False)

        # Сохраняем все простые поля и путь к обложке разом
        video.save()

        # Шаг 4: Очищаем старые и добавляем новые M2M связи
        video.genres.clear()
        for g in details_data.get('genres', []):
            genre, _ = Genre.objects.get_or_create(name=g['name'])
            video.genres.add(genre)

        video.countries.clear()
        for c in details_data.get('production_countries', []):
            country, _ = Country.objects.get_or_create(name=c['name'])
            video.countries.add(country)

        video.actors.clear()
        for cast_member in credits_data.get('cast', [])[:15]:
            person, _ = Person.objects.get_or_create(name=cast_member['name'])
            video.actors.add(person)

        video.directors.clear()
        for crew_member in credits_data.get('crew', []):
            if crew_member.get('job') == 'Director':
                person, _ = Person.objects.get_or_create(name=crew_member['name'])
                video.directors.add(person)

        print(f"METADATA: Successfully fetched and saved all data for '{video.title}'.")

    except Exception as e:
        import traceback
        print(f"!!! METADATA TASK FAILED for '{video.title}': {traceback.format_exc()}")
    finally:
        # Что бы ни случилось, в конце помечаем видео как готовое
        video.status = Video.StatusChoices.READY
        video.save(update_fields=['status'])
        print(f"METADATA: Finished. Status for '{video.title}' set to READY.")


# ===============================================
# ЗАДАЧА 1: ОСНОВНАЯ ОБРАБОТКА ВИДЕОФАЙЛА
# ===============================================
# Добавляем параметры надежности
@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2}, retry_backoff=180)
def process_video_task(self, video_id):
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return

    def log(msg):
        print(f"🎬 [{video.title}] {msg}")
        ProcessingLog.objects.create(video=video, message=msg)

    # 1. Сбрасываем статус на "В процессе"
    video.status = Video.StatusChoices.PROCESSING
    video.save(update_fields=['status'])
    log("🚀 Старт обработки (FFmpeg)...")

    try:
        source_path = str(video.movie_path)

        # 2. Анализ длительности
        ffprobe_cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', source_path]
        res = subprocess.run(ffprobe_cmd, check=True, capture_output=True, text=True)
        meta = json.loads(res.stdout)
        duration = int(float(meta.get('format', {}).get('duration', 0)))
        video.duration = duration

        # 3. Конвертация
        web_dir = Path(settings.MEDIA_ROOT) / 'movies_web'
        web_dir.mkdir(parents=True, exist_ok=True)

        out_name = f"{slugify(video.title)}_{video.pk}.mp4"
        out_path = web_dir / out_name

        # Команда конвертации
        cmd = [
            'ffmpeg', '-y', '-i', source_path,
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart', str(out_path)
        ]
        subprocess.run(cmd, check=True)

        video.web_player_path.name = f"movies_web/{out_name}"

        # 4. Обложка
        cover = generate_cover_image(str(out_path), video.pk)
        if cover:
            video.cover.save(f"cover_{video.pk}.jpg", cover, save=False)

        video.status = Video.StatusChoices.READY
        video.save()
        log("✅ Готово!")

    except Exception as e:
        log(f"💥 Ошибка: {e}")
        video.status = Video.StatusChoices.ERROR
        video.save(update_fields=['status'])

# --- ЗАДАЧА 2: Ежедневная сводка ---
@shared_task
def send_daily_summary():
    print("--- DAILY SUMMARY TASK STARTED ---")
    bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN, parse_mode='Markdown')
    today = timezone.localdate()

    # Находим всех пользователей, у кого есть chat_id
    for profile in UserProfile.objects.filter(telegram_chat_id__isnull=False):
        user = profile.user
        tasks_today = Task.objects.filter(
            assigned_to=user,
            is_completed=False,
            due_date__date=today
        )

        if tasks_today.exists():
            message = f"👋 *Доброе утро, {user.username}!* \n\nВаши задачи на сегодня:\n\n"
            for task in tasks_today:
                message += f"▪️ `{task.title}`\n"

            bot.send_message(profile.telegram_chat_id, message)
            print(f"Daily summary sent to {user.username}")


# ===============================================
# ЗАДАЧА 4: ОСНОВНАЯ ОБРАБОТКА ВИДЕОФАЙЛА
# ===============================================
@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 2}, retry_backoff=180)
def process_video_task(self, video_id):
    # Логирование для нашего монитора на сайте
    logger.info(f"Начало обработки видео ID: {video_id}")
    """
    Основная задача обработки видео с логированием в БД.
    """
    try:
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        return

    # Функция для быстрой записи лога
    def log(msg):
        print(f"[{video.title}] {msg}")
        ProcessingLog.objects.create(video=video, message=msg)

    if video.status == Video.StatusChoices.READY:
        log("Video already READY. Skipping.")
        return

    log("Task started. Status: PROCESSING")
    video.status = Video.StatusChoices.PROCESSING
    video.save(update_fields=['status'])

    source_path_str = str(video.movie_path)

    try:
        # Этап 1: ffprobe
        log("Analyzing file (ffprobe)...")
        ffprobe_cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', source_path_str]
        result = subprocess.run(ffprobe_cmd, check=True, capture_output=True, text=True, encoding='utf-8')
        metadata = json.loads(result.stdout)
        duration = int(float(metadata.get('format', {}).get('duration', 0)))
        log(f"Duration determined: {duration} sec.")

        # Этап 2: ffmpeg
        web_ready_dir = Path(settings.MEDIA_ROOT) / 'movies_web'
        web_ready_dir.mkdir(parents=True, exist_ok=True)
        safe_basename = slugify(Path(source_path_str).stem)
        final_filename_mp4 = f"{safe_basename}_{video.pk}.mp4"
        final_absolute_path = web_ready_dir / final_filename_mp4

        log("Starting conversion (FFmpeg)... This may take a while.")
        ffmpeg_cmd = ['ffmpeg', '-y', '-i', source_path_str, '-c:v', 'libx264', '-preset', 'fast', '-c:a', 'aac', '-movflags', '+faststart', str(final_absolute_path)]
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        log("Conversion finished.")

        # Шаг 3.1: Присваиваем простые поля и сохраняем.
        video.duration = duration
        video.web_player_path.name = os.path.join('movies_web', final_filename_mp4)
        video.save(update_fields=['duration', 'web_player_path'])

        # Шаг 3.2: Генерируем и сохраняем обложку ОТДЕЛЬНО.
        log("Generating technical cover...")
        cover_content_or_path = generate_cover_image(str(final_absolute_path), video.pk)

        if cover_content_or_path:
            cover_filename = f"cover_{video.pk}.jpg"
            if isinstance(cover_content_or_path, ContentFile):
                video.cover.save(cover_filename, cover_content_or_path, save=True)
            else:
                full_cover_path = os.path.join(settings.MEDIA_ROOT, cover_content_or_path)
                with open(full_cover_path, 'rb') as f:
                    video.cover.save(cover_filename, File(f), save=True)
            log("Cover saved.")

        # Шаг 4: Диспетчеризация по типу видео.
        if video.video_type == Video.VideoType.MOVIE:
            log("Type is MOVIE. Launching TMDB fetch...")
            fetch_tmdb_metadata.delay(video.pk)
        else:
            log("Type is LESSON. Metadata fetch skipped.")
            video.status = Video.StatusChoices.READY
            video.save(update_fields=['status'])
            log("Processing fully complete.")

    except Exception as e:
        import traceback
        error_msg = f"CRITICAL ERROR: {str(e)}"
        print(traceback.format_exc())
        log(error_msg)
        video.status = Video.StatusChoices.ERROR
        video.save(update_fields=['status'])

@shared_task
def cleanup_old_logs():
    """Удаляет логи обработки старше 3 дней."""
    retention_period = timezone.now() - datetime.timedelta(days=3)
    # Удаляем старые записи
    deleted_count, _ = ProcessingLog.objects.filter(timestamp__lt=retention_period).delete()
    return f"Очистка завершена. Удалено старых логов: {deleted_count}"


# --- ЗАДАЧА 1: ОТПРАВКА В TELEGRAM С РАЗБИВКОЙ ---
@app.task
def task_send_folder_to_telegram(user_id, path_str, item_type='folder'):
    """
    Архивирует папку (если надо) и отправляет в TG.
    Если файл огромный (>1.8GB), разбивает его.
    """
    bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
    base_dir = Path(settings.INDEXER_LOCATIONS['disk-d']['container_path'])

    # Декодируем путь
    from urllib.parse import unquote
    decoded_path = unquote(path_str)
    full_path = base_dir.joinpath(decoded_path).resolve()

    if not full_path.exists():
        bot.send_message(user_id, "❌ Ошибка: Файл не найден на диске.")
        return

    bot.send_message(user_id, f"📦 Начинаю обработку: {full_path.name}\nЖдите...")

    file_to_send = full_path
    temp_dir = Path(settings.MEDIA_ROOT) / 'temp_zip'
    temp_dir.mkdir(exist_ok=True)
    created_zip = None

    try:
        # 1. Если это папка - архивируем
        if item_type == 'folder' or full_path.is_dir():
            archive_name = temp_dir / f"{full_path.name}"  # shutil добавит .zip сам
            shutil.make_archive(str(archive_name), 'zip', str(full_path))
            file_to_send = Path(str(archive_name) + ".zip")
            created_zip = file_to_send
            bot.send_message(user_id, f"🗜 Архив создан: {file_to_send.name}")

        # 2. Проверяем размер (1.8 GB = 1.8 * 1024 * 1024 * 1024 байт)
        LIMIT_BYTES = 1.8 * 1024 * 1024 * 1024
        # ВАЖНО: Для обычных ботов лимит 50МБ. Если у вас нет локального сервера Bot API,
        # файлы 1.8ГБ не уйдут. Но я делаю как вы просили.

        file_size = file_to_send.stat().st_size

        if file_size > LIMIT_BYTES:
            bot.send_message(user_id,
                             f"⚠️ Файл {file_to_send.name} ({file_size // (1024 * 1024)} MB) больше 1.8 ГБ.\n🔪 Разбиваю на части...")

            # Логика разбивки (chunking)
            chunk_num = 1
            with open(file_to_send, 'rb') as f:
                while True:
                    chunk = f.read(int(LIMIT_BYTES))  # Читаем кусок 1.8ГБ
                    if not chunk:
                        break

                    part_name = temp_dir / f"{file_to_send.name}.part{chunk_num:03d}"
                    with open(part_name, 'wb') as part_file:
                        part_file.write(chunk)

                    # Отправляем кусок
                    bot.send_message(user_id, f"⬆️ Загружаю часть {chunk_num}...")
                    with open(part_name, 'rb') as pf:
                        bot.send_document(user_id, pf, caption=f"Часть {chunk_num}")

                    # Удаляем кусок сразу
                    os.remove(part_name)
                    chunk_num += 1

            bot.send_message(user_id, "✅ Все части отправлены. Соберите их в Total Commander.")

        else:
            # Отправляем целиком
            bot.send_message(user_id, "⬆️ Загружаю файл...")
            with open(file_to_send, 'rb') as f:
                bot.send_document(user_id, f, caption=f"Файл: {full_path.name}")
            bot.send_message(user_id, "✅ Готово!")

    except Exception as e:
        bot.send_message(user_id, f"❌ Ошибка при отправке: {str(e)}")
        print(f"Error sending to TG: {e}")

    finally:
        # Чистим временный архив
        if created_zip and created_zip.exists():
            os.remove(created_zip)


# --- ЗАДАЧА 2: СОЗДАНИЕ КУРСА ИЗ ПАПКИ ---
@app.task
def task_create_course_from_folder(user_id, path_str):
    from .models import Course, Video, LearningCategory
    from .services import scan_course_directory  # Используем вашу готовую функцию!

    base_dir = Path(settings.INDEXER_LOCATIONS['disk-d']['container_path'])
    from urllib.parse import unquote
    decoded_path = unquote(path_str)
    full_path = base_dir.joinpath(decoded_path).resolve()

    # 1. Создаем категорию "Новые загрузки" (если нет)
    category, _ = LearningCategory.objects.get_or_create(
        name="Новые загрузки",
        defaults={'slug': 'new-uploads'}
    )

    # 2. Создаем курс
    course_name = full_path.name
    # Путь для поля source_path должен быть абсолютным
    course, created = Course.objects.get_or_create(
        title=course_name,
        defaults={
            'learning_category': category,
            'source_path': str(full_path),
            'description': f"Импортировано из проводника: {full_path}"
        }
    )

    # 3. Запускаем сканирование
    added_count = scan_course_directory(course)

    return f"Курс '{course.title}' создан. Найдено видео: {added_count}"

@shared_task
def send_daily_report():
    today = timezone.now().date()
    tasks = Task.objects.filter(is_completed=True, updated_at__date=today)
    purchases = Purchase.objects.filter(created_at__date=today)

    earned = sum([t.reward_coins for t in tasks])
    spent = sum([p.item.cost for p in purchases])

    msg = (f"📊 <b>Итоги дня:</b>\n\n"
           f"✅ Выполнено задач: {tasks.count()}\n"
           f"💰 Заработано монет: {earned}\n"
           f"🛒 Покупок совершено: {purchases.count()}\n"
           f"📉 Потрачено монет: {spent}\n\n"
           f"<i>Джарвис желает вам спокойной ночи!</i>")

    bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
    bot.send_message(settings.TELEGRAM_CHAT_ID, msg, parse_mode='HTML')
