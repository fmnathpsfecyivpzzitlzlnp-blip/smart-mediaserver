import os
import json
import subprocess
import datetime
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
# Импортируем все необходимые модели
from .models import Course, Video, Task, Project, StudyPlan, LearningCategory, Tag


# ==========================================================
# 1. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==========================================================

def get_video_duration(file_path):
    """
    Возвращает длительность видео в секундах через ffprobe.
    Встроена сюда, чтобы избежать ошибок импорта.
    """
    if not os.path.exists(file_path):
        return 0
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', str(file_path)
        ]
        # shell=False безопаснее для путей с пробелами
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        duration = float(data.get('format', {}).get('duration', 0))
        return int(duration)
    except Exception as e:
        print(f"⚠️ Ошибка длительности {file_path}: {e}")
        return 0


# ==========================================================
# 2. СКАНЕР ФАЙЛОВ (Наполняет курс)
# ==========================================================

def scan_course_directory(course):
    """
    Сканирует папку курса и добавляет файлы в БД (модель Video).
    """
    if not course.source_path:
        print("❌ У курса нет пути (source_path)")
        return 0

    base_path = Path(course.source_path)

    if not base_path.exists():
        print(f"❌ Путь не найден на диске: {base_path}")
        return 0

    print(f"📂 Сканирую папку: {base_path}")
    count_created = 0

    # Поддерживаемые форматы
    VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.mov', '.webm', '.ts'}

    # Проходим по всем файлам (рекурсивно)
    for file_path in sorted(base_path.rglob('*')):
        if file_path.is_file():
            ext = file_path.suffix.lower()

            # Игнорируем системный мусор
            if file_path.name.startswith('.') or ext in {'.jpg', '.png', '.vtt', '.srt', '.db', '.nfo'}:
                continue

            video_type = Video.VideoType.LESSON

            # 1. Вычисляем длительность
            duration = 0
            if ext in VIDEO_EXTS:
                # Если файл уже есть в базе, не пересчитываем длительность
                existing = Video.objects.filter(course=course, movie_path=str(file_path)).first()
                if existing and existing.duration > 0:
                    duration = existing.duration
                else:
                    duration = get_video_duration(str(file_path))

            title = file_path.stem
            clean_ext = ext.replace('.', '').lower()

            # 2. Создаем или Обновляем запись
            video, created = Video.objects.update_or_create(
                course=course,
                movie_path=str(file_path),
                defaults={
                    'title': title,
                    'file_ext': clean_ext,
                    'duration': duration,
                    'status': Video.StatusChoices.READY,
                    'learning_category': course.learning_category,
                    'video_type': video_type
                }
            )

            if created:
                count_created += 1
                print(f"✅ Добавлен: {title} ({duration} сек)")

    print(f"🏁 Сканирование завершено. Добавлено: {count_created}")
    return count_created


# ==========================================================
# 3. МАССОВЫЙ ИМПОРТ (Для Админки)
# ==========================================================

def run_bulk_import(root_path_input, category, tag=None):
    """
    Логика массового импорта для админки.
    """
    log_messages = []

    def log(msg):
        log_messages.append(msg)

    # Логика поиска пути
    container_path = root_path_input
    if ':' in root_path_input:
        drive_letter = root_path_input.split(':')[0].lower()  # d
        for slug, conf in settings.INDEXER_LOCATIONS.items():
            if slug.endswith(f"-{drive_letter}"):
                rel_path = root_path_input.split(':', 1)[1].replace('\\', '/').lstrip('/')
                container_path = os.path.join(conf['container_path'], rel_path)
                break

    scan_path = Path(container_path)

    if not scan_path.exists():
        return f"❌ Путь не найден: {scan_path}"

    created_count = 0

    try:
        for entry in scan_path.iterdir():
            if entry.is_dir():
                course_title = entry.name

                slug = slugify(course_title) or f"course-{int(timezone.now().timestamp())}"

                course, created = Course.objects.get_or_create(
                    title=course_title,
                    defaults={
                        'slug': slug,
                        'source_path': str(entry),
                        'learning_category': category
                    }
                )

                if tag:
                    course.tags.add(tag)

                added = scan_course_directory(course)
                status = "🆕 Создан" if created else "🔄 Обновлен"
                log(f"{status}: {entry.name} ({added} файлов)")
                created_count += 1
    except Exception as e:
        log(f"❌ Ошибка: {e}")

    return "\n".join(log_messages)


# ==========================================================
# 4. ПЛАНИРОВЩИК ЗАДАЧ (С поддержкой MODE)
# ==========================================================

def create_study_schedule(study_plan, mode='sprint', limit_days=14):
    user = study_plan.user
    course = study_plan.course
    target_seconds = study_plan.minutes_per_day * 60

    project, _ = Project.objects.get_or_create(owner=user, name=f"🎓 Изучение: {course.title}")

    # 1. 🛠 УДАЛЯЕМ ВСЕ НЕВЫПОЛНЕННЫЕ ЗАДАЧИ (и будущие, и просроченные)
    # Это нужно, чтобы перенести "хвосты" на новую дату без дубликатов
    Task.objects.filter(project=project, is_completed=False).delete()

    # 2. 🧠 НАХОДИМ УЖЕ ИЗУЧЕННЫЕ УРОКИ (из WatchHistory)
    # Мы берем только те видео этого курса, где стоит галочка "is_finished"
    from .models import WatchHistory
    finished_lesson_ids = WatchHistory.objects.filter(
        user=user,
        video__course=course,
        is_finished=True
    ).values_list('video_id', flat=True)

    # 3. 🎯 БЕРЕМ ТОЛЬКО ОСТАВШИЕСЯ УРОКИ
    lessons = course.lessons.exclude(id__in=finished_lesson_ids).order_by('title')

    if not lessons.exists():
        return 0

    current_date = study_plan.start_date
    allowed_days = [int(d) for d in study_plan.days_of_week.split(',') if d.strip().isdigit()]
    if not allowed_days: allowed_days = [0, 1, 2, 3, 4]

    accumulated_duration, current_batch, tasks_created, days_planned = 0, [], 0, 0

    for lesson in lessons:
        if limit_days > 0 and days_planned >= limit_days:
            break

        # (Веса файлов оставляем как были...)
        ext = (lesson.file_ext or '').lower()
        duration = lesson.duration if (lesson.duration and lesson.duration > 0) else 600
        if ext in ['pdf', 'doc', 'docx', 'txt']:
            duration = 15 * 60
        elif ext in ['zip', 'rar', '7z', 'py', 'cpp', 'js']:
            duration = 40 * 60

        should_create = (mode == 'step') or (accumulated_duration + duration > target_seconds and current_batch)

        if should_create:
            while current_date.weekday() not in allowed_days:
                current_date += datetime.timedelta(days=1)

            _create_task_for_batch(project, user, current_date, current_batch, course.slug)
            tasks_created += 1
            days_planned += 1
            current_date += datetime.timedelta(days=1)
            accumulated_duration, current_batch = 0, []

        accumulated_duration += duration
        current_batch.append(lesson)

    # Хвост
    if current_batch and (limit_days == 0 or days_planned < limit_days):
        while current_date.weekday() not in allowed_days:
            current_date += datetime.timedelta(days=1)
        _create_task_for_batch(project, user, current_date, current_batch, course.slug)
        tasks_created += 1

    return tasks_created


def _create_task_for_batch(project, user, date, lessons, course_slug):
    """Создает запись Task в базе данных"""
    if not lessons: return

    count = len(lessons)
    title = f"Урок: {lessons[0].title}" if count == 1 else f"Уроки ({count} шт): {lessons[0].title}..."

    description = "План на день:\n"
    for lesson in lessons:
        description += f"- {lesson.title} ({int((lesson.duration or 0) / 60)} мин)\n"

    description += f"\n👉 К курсу: /learning/course/{course_slug}/"

    due_dt = timezone.make_aware(datetime.datetime.combine(date, datetime.time(20, 0)))

    Task.objects.create(
        project=project,
        title=title,
        description=description,
        created_by=user,
        assigned_to=user,
        due_date=due_dt,
        position=0
    )