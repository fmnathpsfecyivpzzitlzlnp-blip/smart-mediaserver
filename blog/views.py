# blog/views.py

import json
import os
import mimetypes # Добавил, т.к. используется для FileResponse
from datetime import datetime, timedelta # timedelta используется для отчетов
from pathlib import Path
from urllib.parse import quote, unquote

import requests
import telebot
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, Count, Sum # Count и Sum используются
from django.http import JsonResponse, Http404, FileResponse # FileResponse добавил
from django.shortcuts import get_object_or_404, redirect, render, reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_POST, require_http_methods
from slugify import slugify
from django.db.models import Q # <--- Не забудьте этот импорт наверху!
from django.core.management import call_command
from django.contrib.admin.views.decorators import staff_member_required
from io import StringIO
import json
import mimetypes
from django.http import FileResponse, Http404
from urllib.parse import quote
from .models import Video, Course, ProcessingLog, TVShow, RewardItem, Purchase, EventType, TrackerEvent, ChildTask, \
    PurchaseLog, PlannedEvent, FamilyBoss
from django.db.models import Count
import mimetypes
from django.http import HttpResponse, FileResponse, Http404
from .streaming import HLSManager

# Импорты моделей из вашего файла blog/models.py
from .models import (
    ClockItem, Country, Genre, Post, Project, Tag, Task,
    TimestampNote, UserProfile, Video, ProjectTemplate, WatchHistory,
    TagCategory, LearningCategory, Course, CourseFile, # CourseFile и LearningCategory
    ProcessingLog, IndexedItem # IndexedItem тоже нужен
)

# Импорты форм
from .forms import ClockItemForm, CustomUserCreationForm, VideoUploadForm

# Импорты Celery задач
from .tasks import send_telegram_notification, process_video_task # process_video_task тоже нужен

from django.views.decorators.csrf import csrf_exempt

from .models import StudyPlan # Импортируем модель
from .services import create_study_schedule, scan_course_directory  # Импортируем сервис

from django.http import HttpResponse
from django.db.models.functions import TruncDate # <--- Добавь этот импорт для группировки по датам
from .models import SearchHistory, SearchConfig # Импортируй новые модели!
from django.db.models import Q  # <--- Обязательно добавьте этот импорт в начало файла!
from .models import SearchHistory, SearchConfig, Video, Course, CourseFile, Task
from mysite.celery import app as celery_app # Импортируем наше Celery приложение

from django.contrib import admin
from .models import Video, ProcessingLog, ClockItem

from .models import Course, Video # Импортируем наши модели
from .models import Course, Video, WatchHistory, LearningCategory # Убедитесь, что WatchHistory импортирован!

from .models import EventType  # <--- ВОТ ЭТОТ ИМПОРТ ВСЁ ЧИНИТ

# ==================================
# БЛОК 1: Главная страница и блог
# ==================================


def get_greeting():
    """Генерирует приветствие в зависимости от времени суток."""
    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
    # Мы используем datetime.now(), а не datetime.datetime.now()
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        return "Доброе утро, сэр!"
    if 12 <= current_hour < 18:
        return "Добрый день, сэр!"
    if 18 <= current_hour < 23:
        return "Добрый вечер, сэр!"
    return "Доброй ночи, сэр!"


def get_weather():
    """Получает погоду с OpenWeatherMap API."""
    api_key = settings.WEATHER_API_KEY
    city = settings.WEATHER_CITY
    url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=ru'
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {
            'city': city,
            'temp': round(data['main']['temp']),
            'description': data['weather'][0]['description'].capitalize(),
            'icon': data['weather'][0]['icon'],
        }
    except requests.exceptions.RequestException as e:
        print(f"Ошибка получения погоды: {e}")
        return None


def cinema_list(request):
    """Только фильмы, мультфильмы и сериалы."""
    movies = Video.objects.filter(
        status=Video.StatusChoices.READY,
        video_type=Video.VideoType.MOVIE
    ).order_by('-created_at')

    # ... (сюда копируем логику фильтров из старого post_list)
    genre_filter = request.GET.get('genre')
    if genre_filter: movies = movies.filter(genres__name=genre_filter)
    # ... (остальные фильтры)

    context = {
        'greeting': get_greeting(),
        'weather': get_weather(),
        'movies': movies,
        'page_title': 'Кинотеатр',
        'all_genres': Genre.objects.all(),  # Можно фильтровать жанры, если нужно
        'current_filters': request.GET
    }
    return render(request, 'blog/video_list.html', context)  # Используем общий шаблон


# ==================================
# БЛОК 2: Загрузка и Логи
# ==================================

@login_required
def upload_video(request):
    """Страница загрузки нового видео через браузер."""
    if request.method == 'POST':
        form = VideoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            video = form.save(commit=False)
            video.status = Video.StatusChoices.PENDING
            video.save()

            # Создаем первый лог
            ProcessingLog.objects.create(video=video, message="Файл загружен через веб. Ожидание очереди.")

            # Запускаем Celery задачу
            from .tasks import process_video_task
            process_video_task.delay(video.pk)

            return redirect('processing_logs')
    else:
        form = VideoUploadForm()

    return render(request, 'blog/upload_video.html', {'form': form})


@login_required
def processing_logs(request):
    """Страница мониторинга конвертации."""
    # Видео, которые в процессе или в очереди
    active_videos = Video.objects.filter(
        status__in=[Video.StatusChoices.PENDING, Video.StatusChoices.PROCESSING]
    ).order_by('-created_at')

    # Видео с ошибками
    error_videos = Video.objects.filter(status=Video.StatusChoices.ERROR).order_by('-created_at')[:5]

    # Последние завершенные
    completed_videos = Video.objects.filter(status=Video.StatusChoices.READY).order_by('-created_at')[:5]

    return render(request, 'blog/processing_logs.html', {
        'active_videos': active_videos,
        'error_videos': error_videos,
        'completed_videos': completed_videos
    })


# ==================================
# БЛОК 3: Планирование (Task из Video)
# ==================================

@require_POST
@login_required
def schedule_video_view(request, pk):
    """Создает задачу в органайзере 'Посмотреть [Название]'."""
    video = get_object_or_404(Video, pk=pk)
    try:
        data = json.loads(request.body)
        date_str = data.get('date')

        # Находим или создаем проект "План обучения/просмотра"
        project, _ = Project.objects.get_or_create(
            owner=request.user,
            name="План просмотра"
        )

        # Создаем задачу
        due_date = None
        if date_str:
            due_date = timezone.make_aware(datetime.strptime(date_str, '%Y-%m-%d').replace(hour=20, minute=0))

        Task.objects.create(
            project=project,
            title=f"Посмотреть: {video.title}",
            created_by=request.user,
            assigned_to=request.user,
            due_date=due_date,
            description=f"Ссылка на видео: /movie/{video.pk}/"
        )
        return JsonResponse({'status': 'ok', 'message': 'Добавлено в задачи!'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==================================
# БЛОК 4: Управление тегами
# ==================================
@login_required
def tag_library(request):
    # Получаем ТОЛЬКО те категории, в которых есть хотя бы один тег
    categories_with_tags = TagCategory.objects.filter(tags__isnull=False).prefetch_related('tags').distinct().order_by('name')

    # Получаем все категории для выпадающего списка в модалке
    all_categories = TagCategory.objects.all().order_by('name')

    # Получаем теги без категории
    tags_without_category = Tag.objects.filter(category__isnull=True).annotate(
        video_count=Count('video')
    )

    return render(request, 'blog/tag_library.html', {
        'categories_with_tags': categories_with_tags,
        'all_categories': all_categories, # Передаем все категории для формы
        'tags_without_category': tags_without_category
    })

# ==================================
# БЛОК 2: Фильмы и заметки
# ==================================

def movie_detail(request, pk):
    movie = get_object_or_404(Video, pk=pk)
    notes = []
    assigned_tags = []
    unassigned_tags = []

    if request.user.is_authenticated:
        notes = TimestampNote.objects.filter(
            Q(video=movie, user=request.user) | Q(video=movie, is_public=True)
        ).distinct().order_by('timestamp')
        assigned_tags = movie.tags.all()
        unassigned_tags = Tag.objects.exclude(pk__in=assigned_tags.values_list('pk'))

    context = {
        'movie': movie,
        'notes': notes,
        'assigned_tags': assigned_tags,
        'unassigned_tags': unassigned_tags,
    }
    return render(request, 'blog/movie_detail.html', context)


# ==================================
# БЛОК 3: Аутентификация
# ==================================

def signup(request):
    """Обрабатывает регистрацию нового пользователя."""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('post_list')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})


# ==================================
# БЛОК 4: API (для AJAX запросов)
# ==================================

def get_movie_status(request, pk):
    """API для "живого" обновления статуса фильма."""
    movie = get_object_or_404(Video, pk=pk)
    return JsonResponse({
        'status': movie.status,
        'status_display': movie.get_status_display(),
        'player_html': render_to_string(
            'blog/partials/player.html',
            {'movie': movie}
        ) if movie.status == Video.StatusChoices.READY else ''
    })

@require_POST
@login_required
def add_note(request):
    try:
        data = json.loads(request.body)
        video = get_object_or_404(Video, pk=data.get('video_id'))
        note = TimestampNote.objects.create(
            video=video, user=request.user,
            timestamp=int(data.get('timestamp')), text=data.get('text', '').strip()
        )
        return JsonResponse({
            'status': 'ok',
            'note': {
                'id': note.id,
                'timestamp': note.timestamp,
                'text_html': note.text.replace('\n', '<br>')
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==================================
# БЛОК 5: Центр управления временем
# ==================================

def clock_view(request):
    """Отображает страницу будильников и таймеров."""
    if request.method == 'POST':
        form = ClockItemForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            return JsonResponse({'status': 'ok'})
        return JsonResponse({'status': 'error', 'errors': form.errors})

    form = ClockItemForm()
    alarms = ClockItem.objects.filter(item_type='ALARM')
    timers = ClockItem.objects.filter(item_type='TIMER')
    sounds = [{'id': item.id, 'name': item.name, 'url': item.sound_file.url}
              for item in ClockItem.objects.all() if item.sound_file]

    alarms_list_for_json = [{
        'id': a.id, 'name': a.name, 'alarm_time': a.alarm_time, 'is_active': a.is_active,
        'sound_file_url': a.sound_file.url if a.sound_file else None,
        'days_of_week': a.get_days_as_list()
    } for a in alarms]

    context = {
        'form': form, 'alarms': alarms, 'timers': timers,
        'sounds': sounds, 'alarms_json': json.dumps(alarms_list_for_json, cls=DjangoJSONEncoder),
    }
    return render(request, 'blog/clock.html', context)


@require_POST
@login_required
def toggle_clock_item(request, pk):
    """API для включения/выключения элемента часов."""
    # Для безопасности лучше добавить проверку `user=request.user`
    item = get_object_or_404(ClockItem, pk=pk)
    item.is_active = not item.is_active
    item.save()
    return JsonResponse({'status': 'ok', 'is_active': item.is_active})


@require_POST
@login_required
def delete_clock_item(request, pk):
    """API для удаления элемента часов."""
    # Для безопасности лучше добавить проверку `user=request.user`
    item = get_object_or_404(ClockItem, pk=pk)
    item.delete()
    return JsonResponse({'status': 'ok'})


@require_POST
@login_required
def add_tag_to_movie_api(request, video_pk):
    try:
        movie = get_object_or_404(Video, pk=video_pk)
        data = json.loads(request.body)
        tag_id = data.get('tag_id')
        if not tag_id: return JsonResponse({'status': 'error', 'message': 'Tag ID is required'}, status=400)
        tag = get_object_or_404(Tag, pk=tag_id)
        movie.tags.add(tag)
        return JsonResponse({'status': 'ok', 'tag': { 'id': tag.id, 'name': tag.name }})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def remove_tag_from_movie_api(request, video_pk):
    try:
        movie = get_object_or_404(Video, pk=video_pk)
        data = json.loads(request.body)
        tag_id = data.get('tag_id')
        if not tag_id: return JsonResponse({'status': 'error', 'message': 'Tag ID is required'}, status=400)
        tag = get_object_or_404(Tag, pk=tag_id)
        movie.tags.remove(tag)
        return JsonResponse({'status': 'ok', 'removed_tag_id': tag.id, 'removed_tag_name': tag.name})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def create_tag_api(request):
    try:
        data = json.loads(request.body)
        tag_name = data.get('tag_name', '').strip()
        video_id = data.get('video_id')
        if not tag_name or not video_id: return JsonResponse({'status': 'error', 'message': 'Missing data'}, status=400)

        tag, created = Tag.objects.get_or_create(name__iexact=tag_name,
                                                 defaults={'name': tag_name, 'slug': slugify(tag_name)})
        movie = get_object_or_404(Video, pk=video_id)
        movie.tags.add(tag)

        return JsonResponse({'status': 'ok', 'tag': {'id': tag.id, 'name': tag.name}, 'created_new': created})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ==================================
# БЛОК 6: ОРГАНАЙЗЕР
# ==================================

@login_required
def organizer_view(request):
    user = request.user
    # Считаем общее количество, выполненные и оставшиеся задачи
    user_projects = Project.objects.filter(Q(owner=user) | Q(members=user)).distinct().annotate(
        total_tasks=Count('tasks'),
        completed_tasks=Count('tasks', filter=Q(tasks__is_completed=True)),
        remaining_tasks=Count('tasks', filter=Q(tasks__is_completed=False))
    ).order_by('name')
    # 👆 КОНЕЦ ИЗМЕНЕНИЙ 👆

    if not user_projects.exists():
        Project.objects.create(owner=user, name=f"Мои задачи")
        user_projects = Project.objects.filter(owner=user)

    default_project = user_projects.first()
    selected_project_id = request.GET.get('project_id')
    selected_project = user_projects.get(id=selected_project_id) if selected_project_id else default_project

    tasks_query = Task.objects.filter(project=selected_project)
    # Сортируем по дате, чтобы ближайшие были сверху
    raw_tasks = tasks_query.filter(Q(is_private=False) | Q(created_by=user) | Q(assigned_to=user)).distinct().order_by('is_completed', 'due_date', 'position')

    project_members = sorted(list(set([selected_project.owner] + list(selected_project.members.all()))), key=lambda u: u.username)
    project_templates = ProjectTemplate.objects.filter(owner=request.user)

    # 🔥 УМНАЯ ГРУППИРОВКА ЗАДАЧ ДЛЯ СПИСКА 🔥
    grouped_tasks = []
    processed_titles = set()

    for t in raw_tasks:
        if not t.is_completed:
            # Если задача не выполнена и мы уже видели такое название
            if t.title in processed_titles:
                # Увеличиваем счетчик у главной карточки
                for gt in grouped_tasks:
                    if gt['task'].title == t.title:
                        gt['count'] += 1
                        break
                continue
            else:
                # Встретили первый раз - добавляем как главную
                processed_titles.add(t.title)
                grouped_tasks.append({'task': t, 'count': 1})
        else:
            # Выполненные задачи не группируем, просто выводим
            grouped_tasks.append({'task': t, 'count': 1})

    # 👇 ДОБАВИТЬ ЭТО 👇
    event_types = EventType.objects.filter(user=request.user)
    recent_events = TrackerEvent.objects.filter(user=request.user)[:5]  # Последние 5 событий

    # 1. Получаем события за сегодня
    today = timezone.localdate()
    events = TrackerEvent.objects.filter(user=request.user, timestamp__date=today)

    # 2. Считаем статистику для каждой кнопки
    grouped_events = []
    for e_type in EventType.objects.filter(user=request.user):
        # Сумма всех значений (например, отжиманий) за сегодня
        count = events.filter(event_type=e_type).aggregate(total=Sum('value'))['total'] or 0
        grouped_events.append({
            'name': e_type.name,
            'count': count,
            'icon': e_type.icon
        })

    context = {
        'projects': user_projects,
        'selected_project': selected_project,
        'grouped_tasks': grouped_tasks,  # <--- ИЗМЕНЕНО: Передаем сгруппированные задачи
        'project_members': project_members,
        'project_templates': project_templates,
        # 👇 И ДОБАВИТЬ ИХ В КОНТЕКСТ 👇
        'event_types': event_types,
        'recent_events': recent_events,
        'grouped_events': grouped_events,
    }

    return render(request, 'blog/organizer.html', context)


@require_POST
@login_required
def add_project(request):
    name = request.POST.get('name', '').strip()
    if name: Project.objects.create(name=name, owner=request.user)
    return redirect('organizer')

@require_POST
@login_required
def add_task(request):
    try:
        data = json.loads(request.body)
        project = get_object_or_404(Project, id=data.get('project_id'))

        if not (request.user == project.owner or request.user in project.members.all()):
            return JsonResponse({'status': 'error', 'message': 'Access Denied'}, status=403)

        title = data.get('title', '').strip()
        description = data.get('description', '').strip()  # <--- ДОБАВИТЬ ЭТО
        is_private = data.get('is_private', False)

        assigned_to_user = None
        if data.get('assigned_to_id'):
            assigned_to_user = get_object_or_404(User, id=data.get('assigned_to_id'))

        due_date_str = data.get('due_date')
        is_recurring = data.get('is_recurring', False)

        # 1. Определяем базовую дату
        if due_date_str:
            start_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        else:
            start_date = timezone.localdate()

        # 2. Обрабатываем массив времени (например: ["08:15", "12:30", "15:15"])
        times_str = data.get('recurring_times', [])
        task_times = []
        for t_str in times_str:
            try:
                task_times.append(datetime.strptime(t_str, '%H:%M').time())
            except ValueError:
                continue

        # Если время вообще не указали, ставим дедлайн по умолчанию (конец дня 23:59)
        if not task_times:
            task_times = [datetime.min.time().replace(hour=23, minute=59)]

        tasks_created = []

        # 🔥 ЛОГИКА ГЕНЕРАЦИИ ЗАДАЧ 🔥
        with transaction.atomic():  # Генерируем пачкой
            if is_recurring:
                recurring_days = data.get('recurring_days', [])
                duration_weeks = data.get('recurring_duration_weeks', 2)

                if not recurring_days:
                    return JsonResponse({'status': 'error', 'message': 'Выберите хотя бы один день!'}, status=400)

                end_date = start_date + timedelta(weeks=duration_weeks)
                current_date = start_date

                # Перебираем дни
                while current_date <= end_date:
                    if current_date.weekday() in recurring_days:
                        # Внутри дня перебираем время
                        for t_time in task_times:
                            due_dt = timezone.make_aware(datetime.combine(current_date, t_time))

                            task = Task.objects.create(
                                project=project,
                                title=title,
                                description=description,
                                created_by=request.user,
                                assigned_to=assigned_to_user,
                                is_private=is_private,
                                due_date=due_dt
                            )
                            tasks_created.append(task)

                    current_date += timedelta(days=1)
            else:
                # ЕСЛИ ЗАДАЧА НЕ ПОВТОРЯЮЩАЯСЯ, но указано несколько часов (например 3 раза за сегодня)
                for t_time in task_times:
                    due_dt = timezone.make_aware(datetime.combine(start_date, t_time))
                    task = Task.objects.create(
                        project=project,
                        title=title,
                        created_by=request.user,
                        assigned_to=assigned_to_user,
                        is_private=is_private,
                        due_date=due_dt
                    )
                    tasks_created.append(task)

        # Отправка уведомления (опционально)
        if tasks_created and assigned_to_user and assigned_to_user != request.user:
            msg_title = f"{title} (Повторяется)" if is_recurring else title
            message = f"Привет, {assigned_to_user.username}! 👋\nВам назначена задача в проекте *'{project.name}'*:\n\n`{msg_title}`"
            send_telegram_notification.delay(assigned_to_user.id, message)

        # Возвращаем HTML с новыми задачами
        tasks_html = "".join(
            [render_to_string('blog/partials/task_item.html', {'task': t}, request=request) for t in tasks_created])

        return JsonResponse({'status': 'ok', 'task_html': tasks_html})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def toggle_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    user = request.user
    if task.project.owner == user or user in task.project.members.all() or task.assigned_to == user:
        task.is_completed = not task.is_completed
        task.completed_at = timezone.now() if task.is_completed else None
        task.save()
        return JsonResponse({'status': 'ok', 'is_completed': task.is_completed})
    return JsonResponse({'status': 'error', 'message': 'Нет доступа'}, status=403)


def test_telegram_bot_token(request):
    try:
        bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)
        bot_info = bot.get_me()
        return JsonResponse({'status': 'ok', 'bot_username': bot_info.username})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def task_detail_api(request, pk):
    task = get_object_or_404(Task, pk=pk)
    project = task.project

    if not (request.user == project.owner or request.user in project.members.all()):
        return JsonResponse({'status': 'error', 'message': 'Access Denied'}, status=403)

    if request.method == 'GET':
        local_task_dt = timezone.localtime(task.due_date) if task.due_date else timezone.now()
        local_task_date = local_task_dt.date()
        base_date = local_task_dt.replace(hour=0, minute=0, second=0)

        similar_tasks = Task.objects.filter(project=project, title=task.title, is_completed=False,
                                            due_date__gte=base_date)

        is_series = similar_tasks.count() > 1
        recurring_days = set()
        recurring_times = set()

        if is_series:
            for t in similar_tasks:
                if t.due_date:
                    local_dt = timezone.localtime(t.due_date)
                    recurring_days.add(local_dt.weekday())

                    # Берем время ТОЛЬКО из задач того же дня, по которому кликнули
                    if local_dt.date() == local_task_date:
                        recurring_times.add(local_dt.strftime('%H:%M'))
        else:
            if task.due_date:
                recurring_times.add(local_task_dt.strftime('%H:%M'))

        return JsonResponse({
            'id': task.id,
            'title': task.title,
            'description': task.description,
            'assigned_to_id': task.assigned_to.id if task.assigned_to else '',
            'due_date': local_task_date.strftime('%Y-%m-%d'),
            'is_private': task.is_private,
            'is_series': is_series,
            'recurring_days': list(recurring_days),
            'recurring_times': sorted(list(recurring_times))
        })

    elif request.method == 'POST':
        data = json.loads(request.body)
        old_title = task.title
        new_title = data.get('title', task.title).strip()
        new_desc = data.get('description', task.description).strip()
        assigned_to_id = data.get('assigned_to_id')
        new_assigned = get_object_or_404(User, id=assigned_to_id) if assigned_to_id else None
        is_private = data.get('is_private', task.is_private)

        date_str = data.get('due_date')

        # 🔥 ГЛАВНОЕ ИСПРАВЛЕНИЕ: Читаем правильный флаг 'is_recurring', который шлет браузер
        update_all = data.get('is_recurring', False)

        recurring_days = data.get('recurring_days', [])
        duration_weeks = data.get('recurring_duration_weeks', 2)

        # Очищаем время от возможных дубликатов (если случайно ввели два одинаковых)
        raw_times = data.get('recurring_times', [])
        times_str = []
        for t in raw_times:
            if t and t not in times_str:
                times_str.append(t)
        if not times_str:
            times_str = ['23:59']

        d_obj = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else (
            timezone.localtime(task.due_date).date() if task.due_date else timezone.localdate())

        with transaction.atomic():
            if update_all:
                # 1. Сносим старую серию (будущие задачи)
                local_base = timezone.localtime(task.due_date).replace(hour=0, minute=0,
                                                                       second=0) if task.due_date else timezone.now()
                Task.objects.filter(project=project, title=old_title, is_completed=False,
                                    due_date__gte=local_base).delete()

                # 2. Создаем новую чистую серию с НОВЫМ временем
                end_date = d_obj + timedelta(weeks=duration_weeks)
                current_date = d_obj

                while current_date <= end_date:
                    if current_date.weekday() in recurring_days:
                        for t_str in times_str:
                            t_obj = datetime.strptime(t_str, '%H:%M').time()
                            due_dt = timezone.make_aware(datetime.combine(current_date, t_obj))
                            Task.objects.create(
                                project=project, title=new_title, description=new_desc,
                                created_by=request.user, assigned_to=new_assigned,
                                is_private=is_private, due_date=due_dt
                            )
                    current_date += timedelta(days=1)
                return JsonResponse({'status': 'ok', 'reload': True})
            else:
                # Одиночное обновление (В РАМКАХ ОДНОГО ДНЯ)
                day_start = timezone.make_aware(datetime.combine(d_obj, datetime.min.time()))
                day_end = timezone.make_aware(datetime.combine(d_obj, datetime.max.time()))

                Task.objects.filter(
                    project=project, title=old_title, is_completed=False,
                    due_date__range=(day_start, day_end)
                ).exclude(pk=task.pk).delete()

                # Обновляем текущую задачу первым временем
                task.title = new_title
                task.description = new_desc
                task.assigned_to = new_assigned
                task.is_private = is_private

                t_obj = datetime.strptime(times_str[0], '%H:%M').time()
                task.due_date = timezone.make_aware(datetime.combine(d_obj, t_obj))
                task.save()

                # Досоздаем остальные часы на этот же день (если их больше 1)
                for t_str in times_str[1:]:
                    t_obj_ex = datetime.strptime(t_str, '%H:%M').time()
                    Task.objects.create(
                        project=project, title=new_title, description=new_desc,
                        created_by=request.user, assigned_to=new_assigned,
                        is_private=is_private, due_date=timezone.make_aware(datetime.combine(d_obj, t_obj_ex))
                    )

                return JsonResponse({'status': 'ok', 'reload': True})

@require_POST
@login_required
def reorder_tasks(request):
    """
    API для обновления порядка задач.
    Финальная, надежная версия с проверкой прав на каждую задачу.
    """
    try:
        data = json.loads(request.body)
        task_ids_order = data.get('order', [])

        if not isinstance(task_ids_order, list):
            return JsonResponse({'status': 'error', 'message': 'Invalid data format.'}, status=400)

        # Получаем все задачи, которые пользователь отправил на сортировку
        tasks_to_reorder = Task.objects.filter(pk__in=task_ids_order)

        # Создаем словарь {id: task_object} для быстрого доступа
        tasks_map = {task.pk: task for task in tasks_to_reorder}

        with transaction.atomic():
            for index, task_id_str in enumerate(task_ids_order):
                task_id = int(task_id_str)
                task = tasks_map.get(task_id)

                if not task:
                    # Пропускаем, если задача не найдена (например, удалена)
                    continue

                # --- ГЛАВНАЯ ПРОВЕРКА БЕЗОПАСНОСТИ ---
                # Проверяем, имеет ли пользователь право редактировать эту конкретную задачу
                project = task.project
                can_reorder = (
                        request.user == project.owner or
                        request.user in project.members.all()
                )

                if can_reorder:
                    # Обновляем позицию только если есть права
                    task.position = index
                    task.save(update_fields=['position'])
                else:
                    # В реальном проекте здесь можно было бы логировать попытку доступа
                    # или даже возвращать ошибку, но для нашей цели достаточно просто пропустить.
                    print(f"User {request.user} cannot reorder task {task.pk}")

        return JsonResponse({'status': 'ok'})

    except (ValueError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Invalid task ID found.'}, status=400)
    except Exception as e:
        # Для отладки можно временно раскомментировать, чтобы видеть полные ошибки
        # import traceback
        # print(traceback.format_exc())
        return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)


@require_POST
@login_required
def apply_project_template(request):
    try:
        data = json.loads(request.body)
        template_id = data.get('template_id')
        project_id = data.get('project_id')

        template = get_object_or_404(ProjectTemplate, pk=template_id, owner=request.user)
        project = get_object_or_404(Project, pk=project_id)

        # Проверка прав доступа к проекту
        if not (request.user == project.owner or request.user in project.members.all()):
            return JsonResponse({'status': 'error', 'message': 'Access Denied'}, status=403)

        new_tasks = []
        for task_template in template.task_templates.all():
            task = Task.objects.create(
                project=project,
                title=task_template.title,
                created_by=request.user,
                # Можно добавить другие поля, если они есть в шаблоне
            )
            new_tasks.append(task)

        # Возвращаем HTML для всех новых задач
        tasks_html = "".join(
            [render_to_string('blog/partials/task_item.html', {'task': t}, request=request) for t in new_tasks])

        return JsonResponse({'status': 'ok', 'tasks_html': tasks_html})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def delete_task(request, pk):
    task = get_object_or_404(Task, pk=pk)
    # Проверяем, что удалить пытается либо создатель, либо владелец проекта
    if request.user == task.created_by or request.user == task.project.owner:
        task.delete()
        return JsonResponse({'status': 'ok'})
    return JsonResponse({'status': 'error', 'message': 'Нет прав на удаление'}, status=403)


@login_required
def reports_view(request):
    user = request.user

    # 1. Задачи, выполненные за последние 7 дней
    seven_days_ago = timezone.now() - timedelta(days=7)
    completed_tasks_weekly = Task.objects.filter(
        project__in=Project.objects.filter(Q(owner=user) | Q(members=user)),
        is_completed=True,
        completed_at__gte=seven_days_ago
    )

    # 2. Статистика по дням недели
    # Создаем словарь вида {0: 'Пн', 1: 'Вт', ...}
    days_of_week = {i: 0 for i in range(7)}
    # weekday() -> Пн=0, Вт=1...
    for task in completed_tasks_weekly:
        days_of_week[task.completed_at.weekday()] += 1

    # Преобразуем в формат, удобный для Chart.js
    completed_by_weekday_data = list(days_of_week.values())

    # 3. Статистика по проектам
    project_stats = Project.objects.filter(
        Q(owner=user) | Q(members=user)
    ).annotate(
        total_tasks=Count('tasks'),
        completed_tasks=Count('tasks', filter=Q(tasks__is_completed=True))
    ).order_by('-total_tasks')

    context = {
        'total_completed_weekly': completed_tasks_weekly.count(),
        'project_stats': project_stats,
        'completed_by_weekday_data': json.dumps(completed_by_weekday_data),
    }
    return render(request, 'blog/reports.html', context)


@require_POST
def face_login_api(request):
    """
    API для входа пользователя по имени, полученному от сервиса распознавания.
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')

        if not username:
            return JsonResponse({'status': 'error', 'message': 'Имя пользователя не предоставлено.'}, status=400)

        # Пытаемся найти пользователя с таким именем в базе данных
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': f'Пользователь {username} не найден.'}, status=404)

        # --- Ключевой момент: Авторизуем пользователя в сессии Django ---
        # Эта функция делает то же самое, что и стандартный вход, но без проверки пароля.
        login(request, user)

        print(f"Пользователь {username} успешно вошел в систему по лицу.")

        # Возвращаем успешный ответ
        return JsonResponse({
            'status': 'ok',
            'message': f'Добро пожаловать, {username}!',
            'username': user.username
        })

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def update_progress_api(request, pk):
    try:
        video = get_object_or_404(Video, pk=pk)
        data = json.loads(request.body)
        timestamp = int(data.get('timestamp', 0))
        # Получаем флаг "завершено" от плеера
        is_finished_front = data.get('is_finished', False)

        history_item, created = WatchHistory.objects.update_or_create(
            user=request.user,
            video=video,
            defaults={'timestamp': timestamp}
        )

        # Если плеер сказал, что доиграл до конца, ИЛИ по времени вышло > 95%
        if is_finished_front or (video.duration and timestamp >= video.duration * 0.95):
            history_item.is_finished = True
            history_item.save()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# --- НОВАЯ VIEW ДЛЯ ФИЛЬТРАЦИИ ---
def videos_by_tag(request, tag_slug):
    tag = get_object_or_404(Tag, slug=tag_slug)

    # Сначала получаем все видео для этого тега
    videos_query = tag.video_set.filter(status=Video.StatusChoices.READY).order_by('-created_at')

    # Проверяем, есть ли дополнительный фильтр по типу (фильм/урок)
    video_type_filter = request.GET.get('type')
    if video_type_filter in [Video.VideoType.MOVIE, Video.VideoType.LESSON]:
        videos_query = videos_query.filter(video_type=video_type_filter)

    context = {
        'tag': tag,
        'videos': videos_query,
        'current_type_filter': video_type_filter,
        'page_title': f'Видео по тегу: {tag.name}'
    }
    return render(request, 'blog/videos_by_tag.html', context)


# --- НОВАЯ VIEW ДЛЯ API УПРАВЛЕНИЯ ТЕГАМИ ---
@login_required
@require_http_methods(["GET", "POST", "PUT", "DELETE"])
def manage_tag_api(request, pk=None):
    """
    Универсальный API для CRUD операций с тегами.
    - POST (/api/tags/manage/): Создает новый тег.
    - GET (/api/tags/manage/<pk>/): Получает данные для одного тега.
    - PUT (/api/tags/manage/<pk>/): Обновляет существующий тег.
    - DELETE (/api/tags/manage/<pk>/): Удаляет тег.
    """
    # === СОЗДАНИЕ НОВОГО ТЕГА (POST) ===
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name', '').strip()
            if not name:
                return JsonResponse({'status': 'error', 'message': 'Название тега не может быть пустым.'}, status=400)

            tag, created = Tag.objects.get_or_create(
                name__iexact=name,
                defaults={
                    'name': name,
                    'slug': slugify(name),
                    'color': data.get('color', '#6c757d'),
                    'category_id': data.get('category_id')
                }
            )
            if not created:
                return JsonResponse({'status': 'error', 'message': 'Тег с таким названием уже существует.'}, status=409)

            return JsonResponse({
                'status': 'ok',
                'tag': {
                    'id': tag.id, 'name': tag.name, 'slug': tag.slug,
                    'color': tag.color, 'category_id': tag.category_id,
                    'category_name': tag.category.name if tag.category else None,
                    'video_count': 0
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    # Для GET, PUT, DELETE нам нужен конкретный тег
    tag = get_object_or_404(Tag, pk=pk)

    # === ПОЛУЧЕНИЕ ДАННЫХ ТЕГА (GET) ===
    if request.method == 'GET':
        return JsonResponse({
            'id': tag.id, 'name': tag.name,
            'color': tag.color, 'category_id': tag.category_id
        })

    # === ОБНОВЛЕНИЕ ТЕГА (PUT) ===
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            tag.name = data.get('name', tag.name).strip()
            tag.slug = slugify(tag.name)
            tag.color = data.get('color', tag.color)
            tag.category_id = data.get('category_id')
            tag.save()
            return JsonResponse({'status': 'ok', 'message': 'Тег обновлен.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    # === УДАЛЕНИЕ ТЕГА (DELETE) ===
    if request.method == 'DELETE':
        try:
            tag.delete()
            return JsonResponse({'status': 'ok', 'message': 'Тег удален.'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Недопустимый метод.'}, status=405)


def style_test_page(request):
    """Временная view для страницы-песочницы."""
    return render(request, 'blog/home.html')


# --- НОВАЯ VIEW ДЛЯ ФАЙЛОВОГО МЕНЕДЖЕРА ---
# 1. ИСПРАВЛЕННЫЙ ПРОВОДНИК
def file_explorer_view(request, path=''):
    decoded_path = unquote(path)

    # А. КОРЕНЬ (МОЙ КОМПЬЮТЕР)
    if not decoded_path:
        drives = []
        for slug, data in settings.INDEXER_LOCATIONS.items():
            # Показываем диск, только если папка реально существует в Docker
            if os.path.exists(data['container_path']):
                drives.append({
                    'name': data['name'],
                    'path': slug,
                    'is_drive': True,
                    'read_only': data['read_only'],
                    'icon': 'bi-hdd-fill' if not data['read_only'] else 'bi-hdd-network-fill'
                })

        return render(request, 'blog/learning_explorer.html', {
            'folders': sorted(drives, key=lambda x: x['name']),
            'files': [],
            'breadcrumbs': [],
            'current_folder_name': 'Мой Компьютер',
            'is_root': True,
            'parent_path': None  # Нет родителя, мы в самом верху
        })

    # Б. ВНУТРИ ДИСКА
    parts = decoded_path.split('/', 1)
    current_drive_slug = parts[0]
    relative_path = parts[1] if len(parts) > 1 else ''

    drive_config = settings.INDEXER_LOCATIONS.get(current_drive_slug)
    if not drive_config:
        raise Http404(f"Диск {current_drive_slug} не настроен или отключен.")

    base_dir = Path(drive_config['container_path']).resolve()
    absolute_req_path = base_dir.joinpath(relative_path).resolve()

    if not absolute_req_path.exists():
        # Если папка не найдена, пробуем вернуть в корень диска, чтобы не было 404
        return redirect('file_explorer_path', path=current_drive_slug)

    # Сканируем
    folders = []
    files = []
    try:
        for entry in absolute_req_path.iterdir():
            entry_rel = str(entry.relative_to(base_dir)).replace(os.sep, '/')
            full_url_path = f"{current_drive_slug}/{entry_rel}"

            if entry.is_dir():
                folders.append({'name': entry.name, 'path': quote(full_url_path)})
            else:
                files.append({
                    'name': entry.name,
                    'path': quote(full_url_path),
                    'extension': entry.suffix.replace('.', '').upper()
                })
    except Exception:
        pass

    # Навигация "Назад"
    parent_path = None
    if absolute_req_path != base_dir:
        # Если мы глубже корня диска
        parent_rel = absolute_req_path.parent.relative_to(base_dir)
        if str(parent_rel) == '.':
            parent_path = current_drive_slug  # Ссылка на корень диска
        else:
            parent_path = quote(f"{current_drive_slug}/{str(parent_rel).replace(os.sep, '/')}")
    else:
        # Если мы в корне диска -> ссылка на "Мой компьютер" (пустая строка для file_explorer_root)
        parent_path = "root"

    context = {
        'current_path': decoded_path,
        'folders': sorted(folders, key=lambda x: x['name'].lower()),
        'files': sorted(files, key=lambda x: x['name'].lower()),
        'parent_path': parent_path,
        'current_folder_name': absolute_req_path.name if relative_path else drive_config['name'],
        'breadcrumbs': [{'name': 'Мой Компьютер', 'path': ''}],
        'is_read_only': drive_config['read_only']
    }

    return render(request, 'blog/learning_explorer.html', context)

def location_list_view(request):
    """Отображает список доступных локаций."""
    locations = []
    for slug, path in settings.INDEXER_LOCATIONS.items():
        locations.append({'name': path, 'slug': slug})
    return render(request, 'blog/location_list.html', {'locations': locations})

def file_browser_view(request, location_slug, path=''):
    """Отображает содержимое папки (файловый менеджер)."""
    # Проверяем, что локация существует в настройках
    if location_slug not in settings.INDEXER_LOCATIONS:
        raise Http404("Локация не найдена")

    parent_path = str(Path(path).parent)
    if parent_path == '.': parent_path = ''

    items = IndexedItem.objects.filter(
        location_slug=location_slug,
        relative_path__startswith=path,
    ).exclude(relative_path=path) # Исключаем саму папку

    folders = [item for item in items if item.is_folder and str(Path(item.relative_path).parent) == path]
    files = [item for item in items if not item.is_folder and str(Path(item.relative_path).parent) == path]

    context = {
        'location_slug': location_slug,
        'current_path': path,
        'folders': folders,
        'files': files,
        'parent_path': parent_path if path else None
    }
    return render(request, 'blog/file_explorer.html', context)


@login_required
@login_required
def serve_file_from_explorer(request, path):
    decoded_path = unquote(path)  # Пример: disk-d/Movies/film.mp4

    # 1. Извлекаем slug диска (disk-d)
    parts = decoded_path.split('/', 1)
    drive_slug = parts[0]
    relative_path = parts[1] if len(parts) > 1 else ''

    # 2. Ищем конфиг диска
    drive_config = settings.INDEXER_LOCATIONS.get(drive_slug)
    if not drive_config:
        raise Http404("Диск не найден конфигурации.")

    base_dir = Path(drive_config['container_path']).resolve()
    absolute_req_path = base_dir.joinpath(relative_path).resolve()

    # 3. Безопасность
    if base_dir not in absolute_req_path.parents and absolute_req_path != base_dir:
        raise Http404("Access denied")

    if not absolute_req_path.exists():
        raise Http404("File not found")

    content_type, _ = mimetypes.guess_type(absolute_req_path)
    content_type = content_type or 'application/octet-stream'

    f = open(absolute_req_path, 'rb')
    response = FileResponse(f, content_type=content_type)
    response['Content-Disposition'] = f'inline; filename="{absolute_req_path.name}"'
    response['Accept-Ranges'] = 'bytes'
    return response

# ==================================
# БЛОК 1: Главная страница и блог
# ==================================

def get_greeting():
    """Генерирует приветствие в зависимости от времени суток."""
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        return "Доброе утро, сэр!"
    if 12 <= current_hour < 18:
        return "Добрый день, сэр!"
    if 18 <= current_hour < 23:
        return "Добрый вечер, сэр!"
    return "Доброй ночи, сэр!"


def get_weather():
    """Получает погоду с OpenWeatherMap API."""
    api_key = settings.WEATHER_API_KEY
    city = settings.WEATHER_CITY
    url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric&lang=ru'
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {
            'city': city,
            'temp': round(data['main']['temp']),
            'description': data['weather'][0]['description'].capitalize(),
            'icon': data['weather'][0]['icon'],
        }
    except requests.exceptions.RequestException as e:
        print(f"Ошибка получения погоды: {e}")
        return None


def cinema_list(request):
    """Только фильмы, мультфильмы и сериалы."""
    movies = Video.objects.filter(
        status=Video.StatusChoices.READY,
        video_type=Video.VideoType.MOVIE
    ).order_by('-created_at')

    genre_filter = request.GET.get('genre')
    if genre_filter: movies = movies.filter(genres__name=genre_filter)
    # Здесь можно добавить другие фильтры (актер, год и т.д.)

    context = {
        'greeting': get_greeting(),
        'weather': get_weather(),
        'movies': movies,
        'page_title': 'Кинотеатр',
        'all_genres': Genre.objects.all(),
        'current_filters': request.GET
    }
    return render(request, 'blog/video_list.html', context)


# --- НОВАЯ ВЕРСИЯ learning_category_view (для IndexedItem) ---
# Предполагается, что в IndexedItem добавлено поле:
# learning_category = models.ForeignKey(LearningCategory, on_delete=models.SET_NULL, null=True, blank=True, related_name='indexed_items_in_category')
def learning_category_view(request, category_slug, path=''):
    """Отображает проиндексированные файлы и папки, привязанные к LearningCategory,
    с возможностью навигации по подпапкам (path).
    """
    learning_category = get_object_or_404(LearningCategory, slug=category_slug)
    decoded_path = unquote(path)

    # Хлебные крошки
    breadcrumbs = [
        {'name': learning_category.name, 'path': reverse('learning_category_view', args=[learning_category.slug])}]
    current_full_path_for_filter = decoded_path  # Путь для фильтрации IndexedItem.relative_path

    if decoded_path:
        parts = Path(decoded_path).parts
        path_builder_segments = []
        for part in parts:
            path_builder_segments.append(part)
            current_breadcrumb_path = str(Path(*path_builder_segments))
            breadcrumbs.append({
                'name': part,
                'path': reverse('learning_category_view', args=[learning_category.slug, quote(current_breadcrumb_path)])
            })

    # Фильтруем IndexedItem, которые принадлежат данной learning_category
    # и являются прямыми потомками текущего `decoded_path`
    all_category_items = IndexedItem.objects.filter(
        learning_category=learning_category  # <-- Это требует добавления FK в IndexedItem
    ).order_by('-is_folder', 'name')

    folders = []
    files = []

    for item in all_category_items:
        item_path_obj = Path(item.relative_path)
        # Получаем родительский путь элемента относительно корня категории
        item_parent_path_str = str(item_path_obj.parent).replace('.',
                                                                 '')  # 'file.txt' -> '', 'folder/file.txt' -> 'folder'

        # Если родительский путь элемента совпадает с текущим путем навигации
        if item_parent_path_str == current_full_path_for_filter:
            if item.is_folder:
                folders.append(item)
            else:
                files.append(item)

    # Для хлебных крошек - путь назад
    parent_path_segment = None
    if decoded_path:
        parent_path_obj = Path(decoded_path).parent
        if parent_path_obj != Path('.'):
            parent_path_segment = quote(str(parent_path_obj))

    context = {
        'learning_category': learning_category,
        'current_path': decoded_path,
        'folders': folders,
        'files': files,
        'breadcrumbs': breadcrumbs,
        'parent_path_segment': parent_path_segment,  # Передаем для кнопки "назад"
        'page_title': f'Категория: {learning_category.name}'
    }
    return render(request, 'blog/learning_explorer.html', context)


@login_required
def serve_indexed_file(request, pk):
    """Безопасно отдает проиндексированный файл по его ID."""
    item = get_object_or_404(IndexedItem, pk=pk)
    file_path = Path(item.absolute_path)
    if not file_path.exists() or not file_path.is_file():
        raise Http404("Файл не найден на диске.")
    content_type, _ = mimetypes.guess_type(file_path)
    response = FileResponse(open(file_path, 'rb'), content_type=content_type or 'application/octet-stream')
    response['Content-Disposition'] = f'inline; filename="{file_path.name}"'
    return response


def indexed_files_by_tag(request, tag_slug):
    tag = get_object_or_404(Tag, slug=tag_slug)
    items = IndexedItem.objects.filter(tags=tag)

    context = {
        'tag': tag,
        'items': items,
        'page_title': f'Файлы по тегу: {tag.name}'
    }
    return render(request, 'blog/indexed_files_by_tag.html', context)


def learning_root(request):
    """Главная страница обучения: Категории (как раньше) + Быстрые уроки (снизу)"""
    # 1. Получаем категории (используем правильное имя модели LearningCategory)
    categories = LearningCategory.objects.annotate(
        course_count=Count('courses')
    ).order_by('name')

    # 2. Получаем быстрые уроки (Тип=LESSON, без привязки к курсу)
    single_lessons = Video.objects.filter(
        video_type=Video.VideoType.LESSON,
        course__isnull=True
    ).order_by('-created_at')

    context = {
        'categories': categories,
        'single_lessons': single_lessons,
        'page_title': 'Центр обучения'
    }

    # ВАЖНО: Указываем твой основной шаблон
    return render(request, 'blog/course_list.html', context)



# --- НОВАЯ ВЕРСИЯ category_detail (для LearningCategory) ---
def learning_category_detail(request, category_slug):
    """
    Показывает курсы в категории и считает количество уроков.
    """
    learning_category = get_object_or_404(LearningCategory, slug=category_slug)

    # 👇 ГЛАВНОЕ ИЗМЕНЕНИЕ: Добавляем .annotate(lesson_count=Count('lessons'))
    courses = Course.objects.filter(learning_category=learning_category).annotate(
        lesson_count=Count('lessons')
    ).order_by('title')

    # Теги для фильтра
    tags_in_courses = Tag.objects.filter(courses__learning_category=learning_category).distinct().order_by('name')

    context = {
        'learning_category': learning_category,
        'courses': courses,
        'tags': tags_in_courses,
        'page_title': f'Курсы: {learning_category.name}'
    }
    return render(request, 'blog/learning_category_detail.html', context)


# --- НОВАЯ ВЕРСИЯ courses_by_tag ---
def courses_by_tag(request, category_slug, tag_slug):
    """
    Показывает курсы, принадлежащие определенной LearningCategory и имеющие определенный Tag.
    """
    # Получаем LearningCategory
    learning_category = get_object_or_404(LearningCategory, slug=category_slug)

    # Получаем Tag
    tag = get_object_or_404(Tag, slug=tag_slug)  # Tag.category относится к TagCategory, не к LearningCategory

    # Фильтруем курсы по LearningCategory И по Tag
    courses = Course.objects.filter(
        learning_category=learning_category,
        tags=tag
    ).order_by('title')

    context = {
        'learning_category': learning_category,
        'tag': tag,
        'courses': courses,
        'page_title': f'Курсы "{learning_category.name}" по тегу "{tag.name}"'
    }
    return render(request, 'blog/courses_list.html', context)

def course_detail(request, course_slug):
    # 1. Получаем курс
    course = get_object_or_404(Course, slug=course_slug)

    # Берем ВСЕ уроки
    lessons = course.lessons.all().order_by('title')

    # 2. Получаем ИСТОРИЮ (оптимизированный запрос)
    history_map = {}
    if request.user.is_authenticated:
        histories = WatchHistory.objects.filter(user=request.user, video__in=lessons)
        history_map = {h.video.id: h for h in histories}

    # 3. Собираем данные (files_data)
    files_data = []
    total_seconds = 0
    watched_seconds = 0
    completed_items = 0
    total_items = len(lessons)

    for lesson in lessons:
        # Ищем историю для этого урока
        history = history_map.get(lesson.id)

        # Длительность
        duration = lesson.duration if lesson.duration else 0
        total_seconds += duration

        # Статус просмотра
        is_finished = False
        timestamp = 0

        if history:
            timestamp = history.timestamp
            if history.is_finished:
                is_finished = True
                watched_seconds += duration
                completed_items += 1  # Считаем количество завершенных уроков

        # ОПРЕДЕЛЯЕМ СТАТУС ДЛЯ ФИЛЬТРА
        status_group = 'new'
        if is_finished:
            status_group = 'completed'
        elif timestamp > 0:
            status_group = 'in_progress'

        # ОПРЕДЕЛЯЕМ ТИП ФАЙЛА И ИКОНКУ
        ext = lesson.file_ext or 'video'

        if ext in ['mp4', 'avi', 'mkv', 'mov', 'webm']:
            type_group = 'video'
            icon_class = "bi-play-circle-fill text-danger"
        elif ext in ['pdf', 'doc', 'docx', 'txt', 'md']:
            type_group = 'doc'
            icon_class = "bi-file-earmark-text-fill text-info"
        elif ext in ['zip', 'rar', '7z']:
            type_group = 'archive'
            icon_class = "bi-file-earmark-zip-fill text-warning"
        elif ext in ['py', 'go', 'js', 'html', 'css', 'cpp']:
            type_group = 'doc'
            icon_class = "bi-file-earmark-code-fill text-success"
        else:
            type_group = 'other'
            icon_class = "bi-file-earmark-fill text-secondary"

        file_url = reverse('serve_video_stream', args=[lesson.id])

        files_data.append({
            'lesson': lesson,
            'history': history,
            'is_finished': is_finished,
            'timestamp': timestamp,
            'icon_class': icon_class,
            'type_group': type_group,
            'status_group': status_group,
            'file_url': file_url
        })

    # 4. Форматируем статистику для карточки слева
    def format_time(sec):
        if not sec: return "0 мин"
        h = sec // 3600
        m = (sec % 3600) // 60
        if h > 0: return f"{int(h)}ч {int(m)}мин"
        return f"{int(m)}мин"

    # Если длительность неизвестна (0 сек), считаем прогресс в штуках!
    if total_seconds == 0:
        stats = {
            'total': f"{total_items} шт.",
            'watched': f"{completed_items} шт.",
            'left': f"{total_items - completed_items} шт.",
            'percent': int((completed_items / total_items * 100)) if total_items > 0 else 0
        }
    else:
        left_seconds = max(0, total_seconds - watched_seconds)
        stats = {
            'total': format_time(total_seconds),
            'watched': format_time(watched_seconds),
            'left': format_time(left_seconds),
            'percent': int((watched_seconds / total_seconds * 100)) if total_seconds > 0 else 0
        }

    # 🔥 ВОТ ОНИ: Категории для выпадающего списка перемещения 🔥
    all_categories = LearningCategory.objects.all().order_by('name')

    return render(request, 'blog/course_detail.html', {
        'course': course,
        'files_data': files_data,
        'stats': stats,
        'all_categories': all_categories  # 🔥 Передаем их в шаблон
    })

    # Статистика
    def format_time(sec):
        if not sec: return "0 мин"
        h = sec // 3600
        m = (sec % 3600) // 60
        if h > 0: return f"{int(h)}ч {int(m)}мин"
        return f"{int(m)}мин"

    left_seconds = max(0, total_seconds - watched_seconds)
    stats = {
        'total': format_time(total_seconds),
        'watched': format_time(watched_seconds),
        'left': format_time(left_seconds),
        'percent': int((watched_seconds / total_seconds * 100)) if total_seconds > 0 else 0
    }

    return render(request, 'blog/course_detail.html', {
        'course': course, 'files_data': files_data, 'stats': stats
    })


@csrf_exempt
@login_required
def serve_course_file(request, file_id):
    """
    Отдает файл через Nginx X-Accel-Redirect для поддержки перемотки.
    """
    course_file = get_object_or_404(CourseFile, pk=file_id)

    file_path = None
    if course_file.external_path:
        file_path = course_file.external_path
    elif course_file.file:
        file_path = course_file.file.path

    if not file_path:
        raise Http404("Файл не найден")

    # Превращаем абсолютный путь в путь для Nginx
    # Было: /media_root/d_drive/Course/video.mp4
    # Стало для Nginx: /internal_media/Course/video.mp4

    # ВАЖНО: Проверьте, какой у вас точный путь в базе.
    # Обычно он начинается с /media_root/d_drive/

    nginx_path = file_path.replace('/media_root/d_drive/', '/internal_media/')

    # Кодируем имя файла для URL (чтобы пробелы и русские буквы работали)
    from django.utils.encoding import escape_uri_path

    response = HttpResponse()
    # Это говорит Nginx'у: "Отдай файл сам"
    response['X-Accel-Redirect'] = escape_uri_path(nginx_path)

    # Заголовки для браузера
    import mimetypes
    content_type, _ = mimetypes.guess_type(file_path)
    response['Content-Type'] = content_type or 'application/octet-stream'
    # Раскомментируйте, если хотите скачивание вместо просмотра
    # response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'

    return response


@require_POST
@login_required
def create_study_plan_api(request, course_slug):
    """
    API для создания/обновления учебного плана и автоматической генерации задач.
    Поддерживает выбор режима (Sprint/Step) и горизонта планирования.
    """
    # 1. Находим курс
    course = get_object_or_404(Course, slug=course_slug)

    try:
        # 2. Получаем данные из JSON-запроса
        data = json.loads(request.body)

        # Режим и лимит дней (новые параметры)
        mode = data.get('mode', 'sprint')
        limit_days = int(data.get('range', 14))  # 0 означает "весь курс"

        # Настройки расписания
        days = data.get('days', [])  # Список чисел [0, 2, 4]
        minutes = int(data.get('minutes', 60))
        start_date_str = data.get('start_date')

        if not start_date_str:
            return JsonResponse({'status': 'error', 'message': 'Дата начала обязательна'}, status=400)

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()

        # 3. Сохраняем или обновляем настройки плана в базе данных
        plan, created = StudyPlan.objects.update_or_create(
            user=request.user,
            course=course,
            defaults={
                'days_of_week': ",".join(map(str, days)),
                'minutes_per_day': minutes,
                'start_date': start_date
            }
        )

        # 4. Запускаем "Умный планировщик" из services.py
        # Мы передаем режим и лимит, чтобы JARVIS не создавал слишком много задач сразу
        tasks_count = create_study_schedule(plan, mode=mode, limit_days=limit_days)

        # 5. Возвращаем результат фронтенду
        return JsonResponse({
            'status': 'ok',
            'message': f'Успешно! Создано/обновлено задач: {tasks_count}'
        })

    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': f'Ошибка формата данных: {str(e)}'}, status=400)
    except Exception as e:
        # Логируем ошибку, если что-то пошло не так при генерации
        import traceback
        print(traceback.format_exc())
        return JsonResponse({'status': 'error', 'message': f'Критическая ошибка: {str(e)}'}, status=500)


@login_required
def get_tasks_json(request):
    tasks = Task.objects.filter(
        Q(created_by=request.user) | Q(assigned_to=request.user)
    ).select_related('project')

    events = []
    for task in tasks:
        color = '#198754' if task.is_completed else '#0d6efd'
        if task.due_date and task.due_date < timezone.now() and not task.is_completed:
            color = '#dc3545'

        # --- НОВАЯ ЛОГИКА ССЫЛОК ---
        # По умолчанию ссылка ведет на фильтр задач в органайзере
        url = f"?project_id={task.project.id}"

        # Но если это проект обучения (начинается с иконки), попробуем найти курс
        if task.project.name.startswith("🎓 Изучение:"):
            # Вырезаем название курса из названия проекта "🎓 Изучение: C++ Red" -> "C++ Red"
            course_title = task.project.name.replace("🎓 Изучение: ", "").strip()
            # Пытаемся найти такой курс в базе
            # (Это не супер-надежно, но для текущей задачи отлично подойдет)
            try:
                course = Course.objects.get(title=course_title)
                # Если нашли - ссылка будет вести прямо в "папку с материалами"
                url = f"/learning/course/{course.slug}/"
            except Course.DoesNotExist:
                pass
                # ---------------------------

        events.append({
            'id': task.id,
            'title': f"{task.title}",  # Убрал название проекта из заголовка, чтобы не захламлять
            'start': task.due_date.isoformat() if task.due_date else None,
            'allDay': True,
            'backgroundColor': color,
            'borderColor': color,
            'url': url  # <-- Сюда подставится ссылка на курс
        })

    return JsonResponse(events, safe=False)


def course_file_player(request, file_id):
    # ИСПРАВЛЕНИЕ: Используем модель Video вместо старой CourseFile
    file = get_object_or_404(Video, pk=file_id)
    course = file.course

    # Навигация (используем lessons)
    previous_file = course.lessons.filter(id__lt=file.id).order_by('-id').first()
    next_file = course.lessons.filter(id__gt=file.id).order_by('id').first()

    # Определение типа файла
    import os
    name_to_check = file.movie_path.name if file.movie_path else file.title
    ext = os.path.splitext(name_to_check)[1].lower()
    base_name = os.path.splitext(name_to_check)[0]

    file_type = 'unknown'
    if ext in ['.mp4', '.mkv', '.avi', '.mov', '.webm']:
        file_type = 'video'
    elif ext in ['.html', '.htm', '.pdf', '.txt']:
        file_type = 'document'

    # Поиск субтитров
    subtitle_file = None
    if file_type == 'video':
        subtitle_file = course.lessons.filter(
            title__istartswith=base_name,
            title__iendswith='.srt'
        ).first()

    context = {
        'file': file,
        'course': course,
        'previous_file': previous_file,
        'next_file': next_file,
        'file_type': file_type,
        'subtitle_file': subtitle_file,
    }
    return render(request, 'blog/course_player.html', context)


@login_required
def dashboard_view(request):
    user = request.user
    today = timezone.localdate()

    # 1. СЧИТАЕМ СЕРИЮ (STREAK)
    completed_dates = Task.objects.filter(
        Q(assigned_to=user) | Q(created_by=user),
        is_completed=True,
        completed_at__isnull=False
    ).annotate(date=TruncDate('completed_at')).values_list('date', flat=True).distinct().order_by('-date')

    completed_dates_set = set(completed_dates)

    current_streak = 0
    check_date = today
    if check_date not in completed_dates_set:
        check_date -= timedelta(days=1)

    while check_date in completed_dates_set:
        current_streak += 1
        check_date -= timedelta(days=1)

    # Данные профиля и статистика для JARVIS
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # Считаем задачи, выполненные СЕГОДНЯ (для отчета)
    tasks_done_today = Task.objects.filter(
        assigned_to=user,
        is_completed=True,
        completed_at__date=today
    ).count()

    # 2. ТЕПЛОВАЯ КАРТА
    year_ago = today - timedelta(days=365)
    activity_qs = Task.objects.filter(
        Q(assigned_to=user) | Q(created_by=user),
        is_completed=True,
        completed_at__gte=year_ago
    ).annotate(date=TruncDate('completed_at')).values('date').annotate(count=Count('id'))

    activity_map = {item['date'].strftime('%Y-%m-%d'): item['count'] for item in activity_qs}

    # 3. РАСЧЕТ ПРОГРЕССА (ПО ВИДЕО)
    study_plans = StudyPlan.objects.filter(user=user).select_related('course')
    courses_progress = []

    for plan in study_plans:
        course = plan.course

        total_lessons = course.lessons.count()
        watched_count = WatchHistory.objects.filter(
            user=user,
            video__course=course,
            is_finished=True
        ).count()

        percent = int((watched_count / total_lessons * 100)) if total_lessons > 0 else 0

        watched_ids = WatchHistory.objects.filter(
            user=user,
            video__course=course,
            is_finished=True
        ).values_list('video_id', flat=True)

        next_lesson = course.lessons.exclude(id__in=watched_ids).order_by('title').first()

        if not next_lesson and total_lessons > 0:
            next_lesson = course.lessons.first()

        courses_progress.append({
            'title': course.title,
            'total': total_lessons,
            'done': watched_count,
            'percent': percent,
            'slug': course.slug,
            'next_lesson_id': next_lesson.id if next_lesson else None
        })

    # Получаем последние 4 видео (Продолжить просмотр)
    continue_watching = WatchHistory.objects.filter(
        user=user,
        is_finished=False,
        timestamp__gt=0
    ).select_related('video', 'video__course').order_by('-updated_at')[:4]

    recent_items = []
    for item in continue_watching:
        video = item.video
        if video:
            progress_percent = int((item.timestamp / video.duration * 100)) if video.duration else 0
            recent_items.append({
                'history': item,
                'video': video,
                'progress': progress_percent
            })

    # 4. ДАННЫЕ ДЛЯ ТРЕКЕРА ЗДОРОВЬЯ/ПРИВЫЧЕК
    tracker_events = TrackerEvent.objects.filter(user=user, timestamp__gte=year_ago).select_related('event_type')

    tracker_data = {}
    for event in tracker_events:
        cat_name = event.event_type.name
        color = event.event_type.color
        date_str = event.timestamp.strftime('%Y-%m-%d')

        if cat_name not in tracker_data:
            tracker_data[cat_name] = {'color': color, 'data': {}}

        if date_str not in tracker_data[cat_name]['data']:
            tracker_data[cat_name]['data'][date_str] = 0

        tracker_data[cat_name]['data'][date_str] += event.value

    first_day_of_month = today.replace(day=1)
    monthly_stats = TrackerEvent.objects.filter(
        user=user, timestamp__gte=first_day_of_month
    ).values('event_type__name', 'event_type__color', 'event_type__icon').annotate(
        total_value=Sum('value'),
        count=Count('id')
    ).order_by('-total_value')

    # 5. ИЩЕМ БЛИЖАЙШИЕ СОБЫТИЯ (ДЛЯ АГЕНДЫ И ГЛАВНОЙ КАРТОЧКИ)
    time_threshold = timezone.now() - timedelta(hours=1)
    upcoming_events_qs = PlannedEvent.objects.filter(
        user=request.user,
        event_date__gte=time_threshold
    ).order_by('event_date')

    # ГЛАВНЫЕ КАРТОЧКИ (Hero Events) - Не отзвеневшие. Сортируем: сначала ВАЖНЫЕ, потом по дате. Берем ТОП-3.
    hero_events_raw = upcoming_events_qs.filter(is_notified=False)
    hero_events = sorted(hero_events_raw, key=lambda x: (not x.is_important, x.event_date))[:3]

    # АГЕНДА НА 7 ДНЕЙ
    agenda = []
    for i in range(7):
        current_day = today + timedelta(days=i)
        start_of_day = timezone.make_aware(datetime.combine(current_day, datetime.min.time()))
        end_of_day = timezone.make_aware(datetime.combine(current_day, datetime.max.time()))

        day_events = upcoming_events_qs.filter(event_date__range=(start_of_day, end_of_day))
        agenda.append({
            'date': current_day,
            'is_today': i == 0,
            'is_tomorrow': i == 1,
            'events': day_events
        })

    # Собираем данные в JSON для JavaScript-будильника
    events_json_data = []
    for ev in upcoming_events_qs:
        if not ev.is_notified and ev.event_date > timezone.now():
            events_json_data.append({
                'id': ev.id,
                'title': ev.title,
                'date_iso': ev.event_date.isoformat(),
                'sound_url': ev.sound_file.url if ev.sound_file else 'https://actions.google.com/sounds/v1/alarms/digital_watch_alarm_long.ogg'
            })

    context = {
        'profile': profile,
        'current_streak': current_streak,
        'activity_map': json.dumps(activity_map),
        'courses_progress': courses_progress,
        'recent_items': recent_items,
        'total_completed_year': sum(activity_map.values()),
        'tasks_done_today': tasks_done_today,
        'tracker_data_json': json.dumps(tracker_data),
        'monthly_stats': monthly_stats,
        'greeting': get_greeting(),
        'weather': get_weather(),
        'hero_events': hero_events,
        'agenda': agenda,
        'events_json': json.dumps(events_json_data),
    }

    return render(request, 'blog/dashboard.html', context)


def global_search(request):
    query = request.GET.get('q', '').strip()

    # === 1. СОХРАНЯЕМ ИСТОРИЮ ===
    if request.user.is_authenticated and query:
        SearchHistory.objects.update_or_create(
            user=request.user,
            query=query,
            defaults={'created_at': timezone.now()}
        )

    results = {
        'movies': [],
        'courses': [],
        'files': [],
        'tasks': []
    }

    if query:
        # 1. Фильмы
        results['movies'] = Video.objects.filter(
            title__icontains=query,
            video_type=Video.VideoType.MOVIE
        )[:5]

        # 2. Курсы
        results['courses'] = Course.objects.filter(title__icontains=query)[:5]

        # 3. Файлы
        results['files'] = CourseFile.objects.filter(name__icontains=query)[:10]

        # 4. Задачи (ИСПРАВЛЕНО: используем Q для поиска по assigned_to ИЛИ created_by)
        if request.user.is_authenticated:
            results['tasks'] = Task.objects.filter(
                Q(title__icontains=query) &
                (Q(assigned_to=request.user) | Q(created_by=request.user))
            )[:5]

    # === 2. ПОЛУЧАЕМ ИСТОРИЮ ===
    search_history = []
    if request.user.is_authenticated:
        config = SearchConfig.objects.first()
        limit = config.history_limit if config else 20
        search_history = SearchHistory.objects.filter(user=request.user)[:limit]

    return render(request, 'blog/search_results.html', {
        'query': query,
        'results': results,
        'search_history': search_history
    })



@require_POST
@login_required
def update_course_progress_api(request, file_id):
    """API для сохранения прогресса УРОКОВ."""
    try:
        video = get_object_or_404(Video, pk=file_id)
        data = json.loads(request.body)
        timestamp = int(data.get('timestamp', 0))
        # Получаем флаг "завершено" от плеера
        is_finished_front = data.get('is_finished', False)

        history_item, created = WatchHistory.objects.update_or_create(
            user=request.user,
            video=video,
            defaults={'timestamp': timestamp}
        )

        # Если плеер сказал, что доиграл до конца, ИЛИ по времени вышло > 90%
        if is_finished_front or (video.duration and timestamp >= video.duration * 0.90):
            history_item.is_finished = True
            history_item.save()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        print(f"Ошибка сохранения прогресса: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def delete_search_history(request, history_id):
    """Удаляет одну запись из истории"""
    try:
        # Удаляем, только если запись принадлежит текущему пользователю
        history = get_object_or_404(SearchHistory, pk=history_id, user=request.user)
        history.delete()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
def delete_file_api(request):
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Нет прав'}, status=403)

    data = json.loads(request.body)
    item_id = data.get('id')
    item_type = data.get('type')

    try:
        file_path = None
        item = None

        if item_type == 'video':
            item = get_object_or_404(Video, pk=item_id)
            if item.file: file_path = item.file.path
        elif item_type == 'course_file':
            item = get_object_or_404(CourseFile, pk=item_id)
            if item.file: file_path = item.file.path

        # 1. Удаляем файл с диска
        if file_path:
            file_path_str = str(file_path)

            # ПРОВЕРКА НА ЗАЩИЩЕННЫЕ ДИСКИ
            for slug, config in settings.INDEXER_LOCATIONS.items():
                # Если файл лежит на этом диске AND диск Read-Only
                if file_path_str.startswith(config['container_path']) and config['read_only']:
                    return JsonResponse(
                        {'status': 'error', 'message': f'Удаление запрещено! {config["name"]} защищен.'}, status=403)

            # Если проверки пройдены - удаляем
            if os.path.exists(file_path):
                os.remove(file_path)

        # 2. Удаляем запись из БД
        if item:
            item.delete()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)




@staff_member_required
def admin_tools_view(request):
    """Отображает страницу с инструментами"""
    # 👇 Получаем список категорий для выпадающего списка
    categories = LearningCategory.objects.all().order_by('name')

    return render(request, 'blog/admin_tools.html', {
        'categories': categories
    })


@staff_member_required
@require_POST
def run_scanner_api(request):
    """
    Запускает management commands через веб-интерфейс.
    Принимает JSON: { "command": "scan_movies", "args": ["--type", "MOVIE"] }
    """
    data = json.loads(request.body)
    command_name = data.get('command')
    args = data.get('args', [])
    kwargs = data.get('kwargs', {})

    # Буфер для перехвата того, что скрипт пишет в консоль (stdout)
    out = StringIO()

    try:
        # Запускаем команду
        # stdout=out перенаправляет вывод print() в переменную out
        call_command(command_name, *args, stdout=out, stderr=out, **kwargs)
        result_text = out.getvalue()
        status = 'ok'
    except Exception as e:
        result_text = str(e)
        status = 'error'

    return JsonResponse({'status': status, 'output': result_text})


@staff_member_required
def get_celery_logs(request):
    """
    Теперь читает логи из Базы Данных (ProcessingLog), а не из файла.
    """
    # Берем последние 50 записей, самые новые сверху
    logs_qs = ProcessingLog.objects.select_related('video').order_by('-timestamp')[:50]

    lines = []
    for log in logs_qs:
        # Форматируем красиво: [ВРЕМЯ] Название фильма: Сообщение
        time_str = log.timestamp.strftime('%H:%M:%S')
        # Добавляем цветовые метки для нашего JS-скрипта
        prefix = ""
        if "Ошибка" in log.message or "Error" in log.message:
            prefix = "Error "
        elif "Успешно" in log.message or "Ready" in log.message:
            prefix = "[+] "

        line = f"[{time_str}] {log.video.title}: {log.message}"

        # Если есть префикс, добавим его для подсветки
        if prefix and not log.message.startswith(prefix):
            line = f"[{time_str}] {log.video.title}: {prefix}{log.message}"

        lines.append(line)

    return JsonResponse({'logs': lines})

@staff_member_required
@require_POST
def purge_tasks_api(request):
    """Очищает очередь задач Celery"""
    try:
        # Эта команда удаляет все задачи, которые стоят в очереди, но еще не начались
        count = celery_app.control.purge()
        return JsonResponse({'status': 'ok', 'count': count})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@csrf_exempt
def track_video_progress(request):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error'}, status=403)

    if request.method == "POST":
        try:
            data = json.loads(request.body)
            video_id = data.get('video_id')
            timestamp = data.get('timestamp', 0)  # Получаем текущее время
            is_finished = data.get('is_finished', False)  # Получаем флаг завершения

            video = get_object_or_404(Video, id=video_id)

            # Находим или создаем запись
            history, created = WatchHistory.objects.get_or_create(
                user=request.user,
                video=video
            )

            # Обновляем время
            history.timestamp = int(timestamp)

            # Если плеер сказал, что все, ИЛИ если мы просмотрели больше 95%
            if is_finished or (video.duration > 0 and history.timestamp > video.duration * 0.95):
                history.is_finished = True

            history.save()
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})

    return JsonResponse({'status': 'error'}, status=400)


# --- API ДЛЯ ПРОВОДНИКА ---

@require_POST
@login_required
def explorer_send_telegram(request):
    """Принимает путь и отправляет в TG (фоново)"""
    try:
        data = json.loads(request.body)
        path = data.get('path')
        item_type = data.get('type', 'file')

        # 1. Пытаемся получить ID из базы данных (профиль)
        chat_id = None
        if hasattr(request.user, 'profile') and request.user.profile.telegram_chat_id:
            chat_id = request.user.profile.telegram_chat_id

        # 2. Если в базе нет, берем из .env (settings.py)
        if not chat_id:
            chat_id = settings.TELEGRAM_CHAT_ID

        # 3. Если нигде нет — ошибка
        if not chat_id:
            return JsonResponse({'status': 'error', 'message': 'Chat ID не найден ни в профиле, ни в .env'})

        # Запускаем задачу
        from .tasks import task_send_folder_to_telegram
        task_send_folder_to_telegram.delay(chat_id, path, item_type)

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@require_POST
@login_required
def explorer_create_course(request):
    try:
        data = json.loads(request.body)
        path_str = data.get('path')  # disk-d/Courses/Python

        decoded_path = unquote(path_str)
        parts = decoded_path.split('/', 1)
        drive_slug = parts[0]
        relative_path = parts[1] if len(parts) > 1 else ''

        drive_config = settings.INDEXER_LOCATIONS.get(drive_slug)
        if not drive_config: return JsonResponse({'status': 'error', 'message': 'Disk not found'})

        base_dir = Path(drive_config['container_path'])
        full_path = base_dir.joinpath(relative_path).resolve()

        # Категория
        cat, _ = LearningCategory.objects.get_or_create(
            name="Импорт из Проводника",
            defaults={'slug': 'explorer-import'}
        )

        # Создаем или получаем курс
        course, created = Course.objects.get_or_create(
            title=full_path.name,
            defaults={
                'learning_category': cat,
                'source_path': str(full_path),  # Сохраняем абсолютный путь!
                'description': f"Папка: {full_path}"
            }
        )

        # Если курс уже был, обновляем путь на всякий случай
        if not created:
            course.source_path = str(full_path)
            course.save()

        # 🔥 ЗАПУСКАЕМ СКАНИРОВАНИЕ ПРЯМО СЕЙЧАС (Синхронно)
        # Это может занять пару секунд, но зато мы сразу увидим результат
        print(f"Запуск сканирования для: {full_path}")
        added_count = scan_course_directory(course)
        print(f"Найдено файлов: {added_count}")

        return JsonResponse({
            'status': 'ok',
            'redirect_url': reverse('course_detail', args=[course.slug]),
            'message': f"Найдено файлов: {added_count}"
        })
    except Exception as e:
        import traceback
        print(traceback.format_exc())  # Пишем ошибку в консоль
        return JsonResponse({'status': 'error', 'message': str(e)})


def serve_video_stream(request, video_id):
    print(f"\n🎬 [DEBUG] ЗАПРОС ФАЙЛА. ID: {video_id}")
    video = get_object_or_404(Video, pk=video_id)

    raw_path = str(video.movie_path)
    file_path = Path(raw_path)

    # Умный поиск по дискам (для Docker)
    if not file_path.exists():
        clean_rel_path = raw_path.replace('\\', '/')
        if ':' in clean_rel_path:
            clean_rel_path = clean_rel_path.split(':', 1)[1]
        clean_rel_path = clean_rel_path.lstrip('/')

        for slug, config in settings.INDEXER_LOCATIONS.items():
            candidate = Path(config['container_path']) / clean_rel_path
            if candidate.exists():
                file_path = candidate
                break

    if not file_path.exists():
        print(f"❌ [DEBUG] ФАЙЛ НЕ НАЙДЕН: {raw_path}")
        raise Http404("Файл не найден")

    # Флаг скачивания
    should_download = request.GET.get('download') == '1'

    # --- УЛУЧШЕННОЕ ОПРЕДЕЛЕНИЕ ТИПОВ ---
    content_type, _ = mimetypes.guess_type(file_path)
    ext = file_path.suffix.lower()

    if not content_type:
        if ext == '.mkv':
            content_type = 'video/x-matroska'
        elif ext == '.ts':
            content_type = 'video/mp2t'  # Важно для TS файлов!
        elif ext == '.docx':
            content_type = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        else:
            content_type = 'application/octet-stream'

    # Если это документ Word или архив - принудительно ставим скачивание
    # Чтобы не было "белого экрана"
    should_download = request.GET.get('download') == '1' or ext in ['.docx', '.xlsx', '.zip', '.rar']

    try:
        f = open(file_path, 'rb')
        response = FileResponse(f, content_type=content_type, as_attachment=should_download)
        # Кодируем имя файла для поддержки кириллицы
        response[
            'Content-Disposition'] = f'{"attachment" if should_download else "inline"}; filename="{quote(file_path.name)}"'
        response['Accept-Ranges'] = 'bytes'
        return response
    except Exception as e:
        raise Http404("Ошибка файла")


@login_required
@require_POST
def toggle_video_list(request, pk):
    """Универсальный переключатель для Избранного и Посмотреть позже"""
    video = get_object_or_404(Video, pk=pk)
    list_type = request.POST.get('list_type')  # Получаем тип: 'favorites' или 'watchlist'

    if list_type not in ['favorites', 'watchlist']:
        return JsonResponse({'status': 'error', 'message': 'Неверный тип списка'}, status=400)

    # Выбираем нужную связь (поле модели)
    collection = getattr(video, list_type)

    if collection.filter(id=request.user.id).exists():
        collection.remove(request.user)
        is_active = False
    else:
        collection.add(request.user)
        is_active = True

    return JsonResponse({
        'status': 'ok',
        'is_active': is_active,
        'list_type': list_type
    })


def get_live_logs(request):
    """
    Отдает последние 50 записей логов для терминала в Центре Управления.
    """
    # Берем последние 50 записей, сортируем от новых к старым
    logs = ProcessingLog.objects.select_related('video').order_by('-timestamp')[:50]

    # Разворачиваем список, чтобы старые были сверху (эффект терминала)
    data = []
    for log in reversed(logs):
        time_str = log.timestamp.strftime('%H:%M:%S')
        data.append(f"[{time_str}] 🎬 {log.video.title}: {log.message}")

    return JsonResponse({'logs': data})


def tv_show_list(request):
    """Страница Сериалов"""
    shows = TVShow.objects.prefetch_related('episodes').all().order_by('-created_at')
    return render(request, 'blog/tv_show_list.html', {'shows': shows})

def clip_list(request):
    """Страница Клипов"""
    clips = Video.objects.filter(video_type='CLIP').order_by('-created_at')
    return render(request, 'blog/clip_list.html', {'clips': clips})


def tv_show_detail(request, pk):
    show = get_object_or_404(TVShow, pk=pk)
    # Получаем все эпизоды, сортируем по сезону и номеру серии
    episodes = show.episodes.all().order_by('season_number', 'episode_number')

    # Группируем по сезонам для удобного вывода в шаблоне
    seasons = {}
    for ep in episodes:
        s_num = ep.season_number or 1
        if s_num not in seasons:
            seasons[s_num] = []
        seasons[s_num].append(ep)

    return render(request, 'blog/tv_show_detail.html', {
        'show': show,
        'seasons': sorted(seasons.items())  # Передаем отсортированные сезоны
    })


@login_required
def reward_store(request):
    """Страница магазина наград"""
    items = RewardItem.objects.all()
    user_profile = request.user.profile
    return render(request, 'blog/reward_store.html', {
        'items': items,
        'profile': user_profile
    })


@require_POST
@login_required
def buy_reward(request, item_id):
    """Логика покупки"""
    item = get_object_or_404(RewardItem, id=item_id)
    profile = request.user.profile

    # 👇 АВТО-НЯНЯ: Лимит 2 покупки в день для всех, кроме staff (вас)
    if not request.user.is_staff:
        purchases_today = Purchase.objects.filter(
            user=request.user,
            created_at__date=timezone.now().date()
        ).count()
        if purchases_today >= 2:
            return JsonResponse({
                'status': 'error',
                'message': 'Джарвис: Лимит покупок на сегодня исчерпан. Подожди до завтра или попроси папу!'
            }, status=403)

    if profile.coins >= item.cost:
        # Списываем монеты
        profile.coins -= item.cost
        profile.save()

        # Фиксируем покупку
        Purchase.objects.create(user=request.user, item=item)

        # Уведомление Папе в Telegram
        message = f"🔔 Покупка! {request.user.username} купил '{item.title}' за {item.cost} монет."
        send_telegram_notification.delay(settings.TELEGRAM_CHAT_ID, message)  # Если настроено

        return JsonResponse({'status': 'ok', 'message': f'Куплено: {item.title}!'})

    return JsonResponse({'status': 'error', 'message': 'Недостаточно монет!'}, status=400)

@require_POST
@login_required
def delete_task_api(request, pk):
    task = get_object_or_404(Task, pk=pk)
    project = task.project

    if request.user != task.created_by and request.user != project.owner:
        return JsonResponse({'status': 'error', 'message': 'Нет прав'}, status=403)

    try:
        data = json.loads(request.body)
        delete_all = data.get('delete_all', False)

        if delete_all:
            # 🔥 ИСПРАВЛЕНИЕ: Удаляем по локальной дате!
            local_base = timezone.localtime(task.due_date).replace(hour=0, minute=0,
                                                                   second=0) if task.due_date else timezone.now()
            Task.objects.filter(project=project, title=task.title, is_completed=False,
                                due_date__gte=local_base).delete()
        else:
            task.delete()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def check_notifications_api(request):
    now = timezone.now()
    # Ищем задачи на ближайшие 2 минуты, которые не выполнены и не были анонсированы
    # Мы берем интервал чуть шире (например, за последние 5 минут до текущего момента)
    start_window = now - timedelta(minutes=5)

    tasks = Task.objects.filter(
        assigned_to=request.user,
        is_completed=False,
        was_notified=False,
        due_date__gte=start_window,
        due_date__lte=now
    )

    data = []
    if tasks.exists():
        for t in tasks:
            data.append({
                'id': t.id,
                'title': t.title,
                'description': t.description[:100] if t.description else "Пора выполнять!"
            })
        # Помечаем, что уведомления отправлены
        tasks.update(was_notified=True)

    return JsonResponse({'status': 'ok', 'notifications': data})


@require_POST
@login_required
def delete_course_api(request, course_id):
    """Удаляет курс целиком (только для админов)"""
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Нет прав для удаления курса'}, status=403)

    try:
        course = get_object_or_404(Course, id=course_id)
        course_title = course.title
        course.delete()  # Удалит курс и все привязанные к нему уроки (Video)
        return JsonResponse({'status': 'ok', 'message': f'Курс "{course_title}" успешно удален'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def move_course_api(request, course_id):
    """API для перемещения курса в другую категорию (только для админов)"""
    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Нет прав'}, status=403)

    try:
        data = json.loads(request.body)
        new_category_id = data.get('category_id')

        if not new_category_id:
            return JsonResponse({'status': 'error', 'message': 'Категория не выбрана'}, status=400)

        course = get_object_or_404(Course, id=course_id)
        new_category = get_object_or_404(LearningCategory, id=new_category_id)

        course.learning_category = new_category
        course.save()

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def add_tracker_event(request):
    """API для быстрого добавления события в трекер"""
    try:
        data = json.loads(request.body)
        event_type_id = data.get('event_type_id')
        value = data.get('value', 1)
        note = data.get('note', '').strip()
        timestamp_str = data.get('timestamp') # Получаем время с фронтенда

        event_type = get_object_or_404(EventType, pk=event_type_id, user=request.user)

        # Обрабатываем переданное время или ставим текущее
        event_time = timezone.now()
        if timestamp_str:
            parsed_time = parse_datetime(timestamp_str)
            if parsed_time:
                event_time = parsed_time

        TrackerEvent.objects.create(
            user=request.user,
            event_type=event_type,
            title=event_type.name,
            value=int(value),
            note=note,
            timestamp=event_time
        )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        print(f"❌ ОШИБКА ДОБАВЛЕНИЯ ЛОГА: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def add_event_type(request):
    """API для создания новой категории трекера прямо с сайта"""
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        color = data.get('color', '#0d6efd')
        icon = data.get('icon', 'bi-record-circle')

        if not name:
            return JsonResponse({'status': 'error', 'message': 'Название не может быть пустым'})

        EventType.objects.create(
            user=request.user,
            name=name,
            color=color,
            icon=icon
        )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        # Теперь, если что-то пойдет не так, ошибка будет видна в логах Docker
        print(f"❌ ОШИБКА СОЗДАНИЯ ТРЕКЕРА: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def delete_event_type(request, pk):
    """API для удаления категории трекера"""
    try:
        event_type = get_object_or_404(EventType, pk=pk, user=request.user)
        event_type.delete() # Это удалит и саму кнопку, и всю её историю
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def delete_project_api(request, pk):
    """API для полного удаления проекта со всеми задачами"""
    try:
        project = get_object_or_404(Project, pk=pk)
        # Проверяем, что удаляет именно владелец
        if project.owner != request.user:
            return JsonResponse({'status': 'error', 'message': 'Только создатель может удалить проект'}, status=403)

        project.delete()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def delete_tracker_event_api(request, pk):
    """API для удаления конкретной записи трекера (одного лога)"""
    try:
        event = get_object_or_404(TrackerEvent, pk=pk, user=request.user)
        event.delete()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def tracker_today_view(request):
    """Главный экран трекера привычек в стиле мобильного приложения"""
    user = request.user
    today = timezone.localdate()

    # 1. Получаем все типы привычек пользователя
    event_types = EventType.objects.filter(user=user)

    # 2. Получаем логи событий за сегодняшний день
    today_events = TrackerEvent.objects.filter(user=user, timestamp__date=today)
    completed_type_ids = set(today_events.values_list('event_type_id', flat=True))

    # 3. Формируем структуру данных для чекклиста
    habits_data = []
    for e_type in event_types:
        is_completed = e_type.id in completed_type_ids
        habits_data.append({
            'type': e_type,
            'is_completed': is_completed,
        })

    # 4. Генерируем динамическую неделю для шапки календаря (начиная с Воскресенья)
    from datetime import timedelta  # <--- ДОБАВЛЯЕМ ИМПОРТ СЮДА

    days_range = []
    weekday_names = ['ВС', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']

    # Вычисляем смещение, чтобы получить воскресенье текущей недели
    current_sun = today - timedelta(days=(today.weekday() + 1) % 7)

    for i in range(7):
        d = current_sun + timedelta(days=i)
        days_range.append({
            'date': d,
            'day_num': d.day,
            'name': weekday_names[i],
            'is_today': d == today
        })

    return render(request, 'blog/tracker_today.html', {
        'habits_data': habits_data,
        'days_range': days_range,
        'today_date_str': today.strftime('%d %b'),
    })


@require_POST
@login_required
def toggle_habit_checkbox_api(request, type_id):
    """API для мгновенного переключения чекбокса (выполнено/не выполнено)"""
    user = request.user
    today = timezone.localdate()
    event_type = get_object_or_404(EventType, pk=type_id, user=user)

    # Проверяем, была ли эта привычка уже залогирована сегодня
    existing_event = TrackerEvent.objects.filter(
        user=user,
        event_type=event_type,
        timestamp__date=today
    ).first()

    if existing_event:
        # Если запись есть — значит пользователь снимает галочку, удаляем лог
        existing_event.delete()
        return JsonResponse({'status': 'unchecked'})
    else:
        # Если записи нет — создаем факт выполнения привычки
        TrackerEvent.objects.create(
            user=user,
            event_type=event_type,
            title=event_type.name,
            value=1
        )
        return JsonResponse({'status': 'checked'})


@login_required
def parent_dashboard_view(request):
    """Главное меню родителя для управления детским аккаунтом"""
    children = User.objects.exclude(id=request.user.id).order_by('id')

    # Смотрим, на какую вкладку нажал родитель (например, ?child_id=5)
    child_id = request.GET.get('child_id')

    if child_id:
        active_child = children.filter(id=child_id).first()
    else:
        # Если ничего не выбрано, показываем первого ребенка по умолчанию
        active_child = children.first()

    child_coins = active_child.profile.coins if active_child and hasattr(active_child, 'profile') else 0

    # 👇 ДОСТАЕМ ИСТОРИЮ ПОКУПОК ВЫБРАННОГО РЕБЕНКА (последние 10 штук) 👇
    purchases = []
    if active_child:
        purchases = PurchaseLog.objects.filter(user=active_child).order_by('-created_at')[:10]

    return render(request, 'blog/parent_dashboard.html', {
        'children': children,
        'active_child': active_child,
        'child_coins': child_coins,
        'purchases': purchases,  # <--- Передаем в шаблон
    })

@login_required
def setup_tasks_view(request):
    """Страница настройки заданий и наград для ребенка (Do it!)"""
    # В будущем мы привяжем сюда модель TaskTemplate,
    # а пока просто выводим красивый интерфейс!
    return render(request, 'blog/setup_tasks.html', {
        'child_name': 'Костя'
    })

@login_required
def custom_task_view(request):
    """Экран создания своего (кастомного) задания для ребенка"""
    return render(request, 'blog/custom_task.html', {
        'child_name': 'Костя' # В будущем сделаем динамическим
    })

@login_required
def do_it_welcome_view(request):
    """Стартовый экран детского приложения Do it! (Выбор роли)"""
    return render(request, 'blog/do_it_welcome.html')


@login_required
def child_tasks_view(request):
    """Экран выполнения заданий для ребенка (Танковый Бой)"""
    profile = request.user.profile
    # Достаем невыполненные задания
    active_tasks = ChildTask.objects.filter(user=request.user, is_completed=False).order_by('-created_at')

    # 👇 Ищем активного босса (танка), которого еще не подбили
    active_boss = FamilyBoss.objects.filter(is_defeated=False).first()

    return render(request, 'blog/child_tasks.html', {
        'child_name': request.user.first_name or request.user.username,
        'child_coins': profile.coins,
        'tasks': active_tasks,
        'boss': active_boss  # <--- Передаем босса на фронтенд
    })


@require_POST
@login_required
def add_child_task_api(request):
    """API для сохранения кастомного задания в базу"""
    try:
        data = json.loads(request.body)
        ChildTask.objects.create(
            user=request.user,
            title=data.get('title', 'Новое задание'),
            reward=int(data.get('reward', 1)),
            icon=data.get('icon', '🌟')
        )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def child_tasks_view(request):
    """Экран выполнения заданий для ребенка (Обновленный)"""
    profile = request.user.profile
    # Достаем из базы только НЕВЫПОЛНЕННЫЕ задания
    active_tasks = ChildTask.objects.filter(user=request.user, is_completed=False).order_by('-created_at')

    return render(request, 'blog/child_tasks.html', {
        'child_name': 'Костя',
        'child_coins': profile.coins,
        'tasks': active_tasks  # <--- Передаем задачи в шаблон
    })


@require_POST
@login_required
def toggle_child_task_api(request, task_id):
    """API для нанесения урона боссу и начисления монет"""
    try:
        task = get_object_or_404(ChildTask, id=task_id, user=request.user)
        profile = request.user.profile
        data = json.loads(request.body)
        is_checked = data.get('completed', False)

        boss = FamilyBoss.objects.filter(is_defeated=False).first()
        damage_dealt = 0
        boss_defeated = False

        if is_checked and not task.is_completed:
            # Снаряд попал в цель: начисляем базовые монеты
            task.is_completed = True
            profile.coins += task.reward

            # Наносим урон боссу
            if boss:
                boss.current_hp -= task.damage
                damage_dealt = task.damage

                # Проверяем, уничтожен ли босс
                if boss.current_hp <= 0:
                    boss.current_hp = 0
                    boss.is_defeated = True
                    boss_defeated = True
                    # Выдаем супер-награду за уничтожение танка!
                    profile.coins += boss.reward_coins

                boss.save()

        elif not is_checked and task.is_completed:
            # Если случайно отменили галочку
            task.is_completed = False
            profile.coins -= task.reward
            if boss:
                boss.current_hp += task.damage
                if boss.current_hp > boss.max_hp:
                    boss.current_hp = boss.max_hp
                boss.save()

        task.save()
        profile.save()

        return JsonResponse({
            'status': 'ok',
            'new_balance': profile.coins,
            'boss_hp': boss.current_hp if boss else 0,
            'boss_max_hp': boss.max_hp if boss else 0,
            'damage_dealt': damage_dealt,
            'boss_defeated': boss_defeated
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def child_statistics_view(request):
    """Экран истории и статистики выполненных заданий для родителя"""

    # Получаем все ВЫПОЛНЕННЫЕ задания, отсортированные по дате (сначала свежие)
    completed_tasks = ChildTask.objects.filter(
        user=request.user,
        is_completed=True
    ).order_by('-created_at')

    return render(request, 'blog/child_statistics.html', {
        'child_name': 'Костя',
        'completed_tasks': completed_tasks
    })


@login_required
def add_reward_view(request):
    """Экран создания нового товара для Магазина Наград"""
    return render(request, 'blog/add_reward.html', {
        'child_name': 'Костя'
    })


@require_POST
@login_required
def save_reward_api(request):
    """API для сохранения новой награды в базу (модель RewardItem)"""
    try:
        data = json.loads(request.body)
        # Импортируем вашу модель магазина
        from .models import RewardItem

        RewardItem.objects.create(
            title=data.get('title', 'Сюрприз'),
            cost=int(data.get('cost', 10)),
            icon=data.get('icon', '🎁')
        )
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def habits_library_view(request):
    """Экран каталога готовых привычек из дизайн-системы"""
    # Собираем все категории и привычки из ваших файлов 4.html и 5.html
    library_data = [
        {
            "category": "Четкость по жизни",
            "subtitle": "У всего должно быть свое место",
            "color": "#ffc107",
            "habits": [
                {"name": "Генеральная уборку", "icon": "🧽", "desc": "Вычистите каждый уголок своего дома"},
                {"name": "Экспресс-уборка", "icon": "🧹", "desc": "Выделите несколько минут на быструю уборку"},
                {"name": "Заправлять постель", "icon": "🛏️", "desc": "Чистая постель — чистый разум"},
                {"name": "Выносить мусор", "icon": "🔥", "desc": "Не оставляйте дома беспорядок"},
                {"name": "Мыть посуду сразу", "icon": "🍽️", "desc": "Тарелки должны быть всегда чистыми"},
                {"name": "Уборка рабочего места", "icon": "🗄️", "desc": "Чем меньше беспорядка, тем меньше стресса"},
            ]
        },
        {
            "category": "Повышайте производительность",
            "subtitle": "Стратегический подход к усилиям и времени",
            "color": "#3b82f6",
            "habits": [
                {"name": "Четкие цели", "icon": "💡", "desc": "Ставьте перед собой конкретные цели"},
                {"name": "Работа с белым шумом", "icon": "🔊", "desc": "Научный способ не отвлекаться"},
                {"name": "Список дел на завтра", "icon": "📋", "desc": "Ваше время должно быть видимым"},
                {"name": "Экранное время", "icon": "📱", "desc": "Блокируйте экран и поддерживайте внимание"},
                {"name": "Ранний подъем", "icon": "🚶‍♂️", "desc": "Светите раньше солнца"},
            ]
        },
        {
            "category": "Процедура подготовки ко сну",
            "subtitle": "Пусть ваш сон сегодня будет сладким",
            "color": "#6f42c1",
            "habits": [
                {"name": "Не есть перед сном", "icon": "🚫", "desc": "Желудку тоже требуется хороший сон"},
                {"name": "Медитация перед сном", "icon": "🧘", "desc": "Погружайтесь в свой внутренний мир"},
                {"name": "Дневник", "icon": "📓", "desc": "Это позволит вам лучше узнать себя"},
                {"name": "Чтение книги", "icon": "📖", "desc": "Книг не бывает много"},
                {"name": "Теплое молоко", "icon": "🥛", "desc": "Помогает видеть хорошие сны"},
            ]
        },
        {
            "category": "Нарабатывайте самодисциплину",
            "subtitle": "Научитесь управлять собой",
            "color": "#dc3545",
            "habits": [
                {"name": "Без импульсивных трат", "icon": "✋", "desc": "Потребности и желания — не одно и то же"},
                {"name": "Отказ от сахара", "icon": "🚫", "desc": "Вы увидите, как изменится ваше тело"},
                {"name": "Ограничение кофеина", "icon": "☕", "desc": "Замените источники на более здоровые"},
                {"name": "Отказ от фастфуда", "icon": "🍳", "desc": "Простой способ поддерживать форму"},
                {"name": "Меньше игр", "icon": "🔒", "desc": "Контролируйте время за компьютером"},
            ]
        },
        {
            "category": "Облегчите стресс",
            "subtitle": "Ваши усилия заслуживают перерыва",
            "color": "#0dcaf0",
            "habits": [
                {"name": "Растяжка / Йога", "icon": "🤸", "desc": "Снимайте физическое напряжение"},
                {"name": "Сон 8+ часов", "icon": "🛌", "desc": "Оставьте достаточно времени для отдыха"},
                {"name": "Прогулка на воздухе", "icon": "🌳", "desc": "Оставьте место для природы в своей жизни"},
                {"name": "Дыхательные практики", "icon": "🗣️", "desc": "Каждый вдох и выдох должны быть осознанными"},
            ]
        }
    ]

    # Получаем уже активированные пользователем привычки, чтобы скрыть кнопку добавления
    existing_habits = EventType.objects.filter(user=request.user).values_list('name', flat=True)

    return render(request, 'blog/habits_library.html', {
        'library': library_data,
        'existing_habits': list(existing_habits)
    })


@require_POST
@login_required
def activate_habit_api(request):
    """Добавление привычки из каталога в персональный органайзер"""
    try:
        data = json.loads(request.body)
        name = data.get('name')
        icon = data.get('icon', '⭐')
        color = data.get('color', '#3b82f6')

        if not name:
            return JsonResponse({'status': 'error', 'message': 'Missing fields'}, status=400)

        # get_or_create защищает от дублирования
        obj, created = EventType.objects.get_or_create(
            user=request.user,
            name=name,
            defaults={'icon': icon, 'color': color}
        )

        return JsonResponse({'status': 'ok', 'created': created})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


from django.contrib.auth.models import User


@login_required
def add_child_view(request):
    """Экран добавления нового детского аккаунта"""
    return render(request, 'blog/add_child.html')


@require_POST
@login_required
def add_child_api(request):
    """API для регистрации нового ребенка (пользователя) в базе Django"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        first_name = data.get('first_name') # <--- ДОБАВИЛИ ПОЛЕ ИМЕНИ

        if not username or not password or not first_name:
            return JsonResponse({'status': 'error', 'message': 'Заполните все поля!'})

        if User.objects.filter(username=username).exists():
            return JsonResponse({'status': 'error', 'message': 'Такой логин уже занят!'})

        # Создаем пользователя с логином, паролем и КРАСИВЫМ ИМЕНЕМ
        new_user = User.objects.create_user(
            username=username,
            password=password,
            first_name=first_name,
            is_staff = True
        )

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def delete_child_api(request, child_id):
    """API для безвозвратного удаления аккаунта ребенка"""
    try:
        child = get_object_or_404(User, id=child_id)

        # Защита от дурака: чтобы родитель случайно не удалил свой аккаунт
        if child.id == request.user.id:
            return JsonResponse({'status': 'error', 'message': 'Нельзя удалить свой собственный аккаунт!'})

        child_name = child.first_name or child.username
        child.delete()  # Удаляем пользователя из базы навсегда

        return JsonResponse({'status': 'ok', 'message': f'Аккаунт {child_name} успешно удален.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def buy_reward_api(request):
    """API для покупки товара ребенком"""
    try:
        data = json.loads(request.body)
        title = data.get('title')
        cost = int(data.get('cost'))

        profile = request.user.profile

        if profile.coins >= cost:
            profile.coins -= cost
            profile.save()

            # 👇 САМОЕ ГЛАВНОЕ: Записываем чек для родителей! 👇
            PurchaseLog.objects.create(user=request.user, title=title, cost=cost)

            return JsonResponse({'status': 'ok', 'new_balance': profile.coins})
        else:
            return JsonResponse({'status': 'error', 'message': 'Не хватает звезд!'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
def mark_event_notified_api(request, event_id):
    """
    API для подтверждения, что будильник события прозвенел и пользователь это увидел.
    Защищает от повторных срабатываний при обновлении страницы.
    """
    from .models import PlannedEvent # Импортируем локально, чтобы избежать циклических импортов
    try:
        event = get_object_or_404(PlannedEvent, pk=event_id, user=request.user)
        event.is_notified = True
        event.save(update_fields=['is_notified'])
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def create_event_api(request):
    """API для создания планового события (теперь с поддержкой is_important)."""
    from .models import PlannedEvent

    title = request.POST.get('title', '').strip()
    description = request.POST.get('description', '').strip()
    event_date_str = request.POST.get('event_date', '').strip()

    # 👇 Читаем галочку: если она нажата, браузер пришлет 'on'
    is_important = request.POST.get('is_important') == 'on'

    sound_file = request.FILES.get('sound_file')
    cover = request.FILES.get('cover')

    if not title or not event_date_str:
        return JsonResponse({'status': 'error', 'message': 'Название и дата обязательны.'}, status=400)

    try:
        # Умный парсинг даты: пробуем стандартный формат, если браузер прислал с секундами - перехватываем
        try:
            dt = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            dt = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M:%S')

        event_date = timezone.make_aware(dt)

        if event_date <= timezone.now():
            return JsonResponse({'status': 'error', 'message': 'Нельзя создать событие в прошлом!'}, status=400)

        PlannedEvent.objects.create(
            user=request.user,
            title=title,
            description=description,
            event_date=event_date,
            is_important=is_important,  # <--- Сохраняем флаг в базу!
            sound_file=sound_file,
            cover=cover
        )
        return JsonResponse({'status': 'ok', 'message': 'Событие успешно запланировано!'})

    except Exception as e:
        # Если сервер падает, возвращаем реальную ошибку, а не молчим
        return JsonResponse({'status': 'error', 'message': f'Ошибка сервера: {str(e)}'}, status=500)

@require_POST
@login_required
def delete_planned_event_api(request, event_id):
    """API для жесткого удаления планового события."""
    from .models import PlannedEvent
    try:
        # get_object_or_404 с проверкой user гарантирует, что чужое событие удалить нельзя
        event = get_object_or_404(PlannedEvent, pk=event_id, user=request.user)
        event.delete()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def edit_planned_event_api(request, event_id):
    """API для редактирования (с поддержкой is_important и защитой от дурака)."""
    from .models import PlannedEvent
    try:
        event = get_object_or_404(PlannedEvent, pk=event_id, user=request.user)

        title = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        event_date_str = request.POST.get('event_date', '').strip()

        # Обновляем флаг важности
        event.is_important = request.POST.get('is_important') == 'on'

        if title: event.title = title
        if description: event.description = description

        if event_date_str:
            try:
                dt = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                dt = datetime.strptime(event_date_str, '%Y-%m-%dT%H:%M:%S')

            event.event_date = timezone.make_aware(dt)
            if event.event_date > timezone.now():
                event.is_notified = False

        sound_file = request.FILES.get('sound_file')
        cover_file = request.FILES.get('cover')

        if cover_file:
            if not cover_file.content_type.startswith('image/'):
                return JsonResponse({'status': 'error', 'message': 'Обложка должна быть картинкой!'}, status=400)
            event.cover = cover_file

        if sound_file:
            if not sound_file.content_type.startswith('audio/') and not sound_file.content_type.startswith('video/'):
                return JsonResponse({'status': 'error', 'message': 'В поле мелодии нужен аудиофайл!'}, status=400)
            event.sound_file = sound_file

        event.save()
        return JsonResponse({'status': 'ok', 'message': 'Событие обновлено!'})

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': f'Внутренняя ошибка: {str(e)}'}, status=500)


@login_required
def omni_search_api(request):
    """
    Глобальный асинхронный поиск по всем сущностям системы (Omni-Search).
    """
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return JsonResponse({'results': []})

    results = []

    # 1. Поиск по ЗАДАЧАМ (Только свои или где назначен)
    tasks = Task.objects.filter(
        Q(title__icontains=query) | Q(description__icontains=query),
        Q(created_by=request.user) | Q(assigned_to=request.user)
    ).order_by('-created_at')[:3]

    for t in tasks:
        results.append({
            'type': 'task',
            'title': t.title,
            'subtitle': 'Задача',
            'url': f"/organizer/?project_id={t.project.id}",
            'icon': 'bi-check2-square text-success'
        })

    # 2. Поиск по СОБЫТИЯМ (Агенда)
    events = PlannedEvent.objects.filter(
        user=request.user,
        title__icontains=query
    ).order_by('event_date')[:3]

    for e in events:
        results.append({
            'type': 'event',
            'title': e.title,
            'subtitle': e.event_date.strftime('%d.%m.%Y %H:%M'),
            'url': '/',  # Ведет на дашборд
            'icon': 'bi-calendar-event text-warning'
        })

        # 3. Поиск по ФИЛЬМАМ И КЛИПАМ
        videos = Video.objects.filter(title__icontains=query)[:3]
        for v in videos:
            # ИСПРАВЛЕНИЕ: просим Django самому правильно собрать ссылку по имени
            if v.video_type == Video.VideoType.MOVIE:
                url = reverse('movie_detail', args=[v.pk])
            else:
                url = reverse('course_file_player', args=[v.pk])

            results.append({
                'type': 'media',
                'title': v.title,
                'subtitle': 'Медиацентр',
                'url': url,
                'icon': 'bi-play-btn-fill text-danger'
            })

    # 4. Поиск по КУРСАМ
    courses = Course.objects.filter(title__icontains=query)[:3]
    for c in courses:
        results.append({
            'type': 'course',
            'title': c.title,
            'subtitle': 'Академия',
            'url': f"/learning/course/{c.slug}/",
            'icon': 'bi-mortarboard-fill text-primary'
        })

    return JsonResponse({'results': results})


@login_required
def start_hls_stream(request, video_id, audio_idx=0):
    """Инициализирует сессию просмотра и отдает плейлист m3u8."""
    session_id = HLSManager.start_session(video_id, audio_idx)
    playlist_path = HLSManager.HLS_DIR / session_id / 'index.m3u8'

    if not playlist_path.exists():
        return HttpResponse("Ошибка запуска транскодера HLS", status=500)

    with open(playlist_path, 'r') as f:
        content = f.read()

    return HttpResponse(content, content_type='application/vnd.apple.mpegurl')


@login_required
def serve_hls_segment(request, video_id, audio_idx, segment_name):
    """Отдает конкретный .ts сегмент видео."""
    session_id = f"session_{video_id}_a{audio_idx}"
    segment_path = HLSManager.HLS_DIR / session_id / segment_name

    if not segment_path.exists():
        raise Http404("Сегмент не найден")

    return FileResponse(open(segment_path, 'rb'), content_type='video/MP2T')


@require_POST
@login_required
def create_course_manual_api(request):
    """API для ручного создания пустого курса через кнопку на сайте"""
    try:
        data = json.loads(request.body)
        title = data.get('title', '').strip()
        category_id = data.get('category_id')

        if not title or not category_id:
            return JsonResponse({'status': 'error', 'message': 'Название и категория обязательны.'}, status=400)

        category = get_object_or_404(LearningCategory, id=category_id)

        # Создаем курс (слаг сгенерируется автоматически благодаря переопределенному методу save в models.py)
        course = Course.objects.create(
            title=title,
            learning_category=category,
            description='<p>Описание пока не добавлено. Нажмите "Редактировать HTML", чтобы вставить информацию о курсе.</p>'
        )

        return JsonResponse({
            'status': 'ok',
            'redirect_url': reverse('course_detail', args=[course.slug])
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@require_POST
@login_required
def update_course_html_api(request, course_id):
    """Надежное сохранение HTML-разметки из TinyMCE и загрузка Обложки"""
    try:
        course = get_object_or_404(Course, id=course_id)

        # 1. Сохраняем огромный HTML-текст
        raw_html = request.POST.get('html_content', '')
        course.description = raw_html

        # 2. Сохраняем обложку, если её загрузили
        if 'cover_image' in request.FILES:
            course.cover = request.FILES['cover_image']

        course.save()
        return redirect('course_detail', course_slug=course.slug)
    except Exception as e:
        return HttpResponse(f"Ошибка сохранения: {str(e)}", status=500)