# blog/admin.py
import os
import requests  # <--- Добавьте эту строку
from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .services import scan_course_directory, run_bulk_import
from django.core.files.base import ContentFile
from .tmdb_client import search_movie, get_movie_details # Наш новый файл

from .services import scan_course_directory  # 🔥 ОБЯЗАТЕЛЬНО ДОБАВИТЬ ЭТОТ ИМПОРТ
from pathlib import Path

from .models import (
    Post, Video, ClockItem, Tag, Genre, Country, TimestampNote,
    Project, Task, UserProfile, ProjectTemplate, TaskTemplate, TagCategory,
    LearningCategory, IndexedItem, CourseFile, Course,
    CourseImportSession, SearchConfig, SearchHistory, ProcessingLog, EventType, TrackerEvent, MetricGoal
)
from .tasks import process_video_task # Проверьте, что этот импорт есть!
from .models import Task, RewardItem, Purchase


# 👇 1. СОЗДАЕМ "ВСТРАИВАЕМЫЙ" СПИСОК ВИДЕО
class VideoInline(admin.TabularInline):
    model = Video  # <--- ВАЖНО: Мы используем модель Video, а не CourseFile
    fields = ('title', 'status', 'movie_path', 'video_type')
    readonly_fields = ('status', 'movie_path')
    extra = 0 # Не показывать пустые строки для добавления
    can_delete = True
    show_change_link = True # Кнопка "Редактировать" для каждого урока


# --- 1. ПИШЕМ САМУ ФУНКЦИЮ (ДОЛЖНА БЫТЬ ПЕРЕД КЛАССОМ) ---
@admin.action(description='🔄 Отправить на конвертацию (MP4)')
def restart_conversion(modeladmin, request, queryset):
    for video in queryset:
        video.status = 'pending'
        video.save()
        # 👇 ВОТ ЭТА СТРОКА ГОВОРИТ ВОРКЕРУ: "ПРОСНИСЬ И РАБОТАЙ!"
        process_video_task.delay(video.id)

    modeladmin.message_user(request, f"Задачи отправлены воркеру для {queryset.count()} видео.")

# ============================================
# 1. ГЛОБАЛЬНЫЕ ДЕЙСТВИЯ (ACTIONS)
# ============================================

@admin.action(description='❌ Полное удаление (вместе с файлом)')
def delete_with_file(modeladmin, request, queryset):
    """Удаляет запись из БД и физический файл с диска."""
    count = 0
    for obj in queryset:
        # Если у модели есть метод delete(), вызываем его (он содержит логику удаления файла)
        obj.delete()
        count += 1
    modeladmin.message_user(request, f"Удалено объектов и файлов: {count}", level=messages.SUCCESS)


@admin.action(description='📂 Сканировать файлы курса')
def scan_course_files_action(modeladmin, request, queryset):
    """Запускает сканирование папки для выбранных курсов (через сервис)."""
    total_added = 0
    for course in queryset:
        added = scan_course_directory(course)
        total_added += added
    modeladmin.message_user(request, f"Сканирование завершено! Добавлено файлов: {total_added}", level=messages.SUCCESS)


# --- ДОБАВИТЬ НОВОЕ ACTION (перед классами админки) ---
@admin.action(description='🎬 Найти информацию на TMDb (авто)')
def fill_tmdb_data(modeladmin, request, queryset):
    updated = 0
    for video in queryset:
        # 1. Ищем фильм по названию файла (или текущему title)
        search_query = video.title if video.title else str(video.movie_path)
        movie_data = search_movie(search_query)

        if movie_data:
            # 2. Обновляем поля
            video.title = movie_data.get('title')
            video.description = movie_data.get('overview')
            video.rating = movie_data.get('vote_average')

            # Дата выхода "YYYY-MM-DD" -> берем год
            release_date = movie_data.get('release_date')
            if release_date:
                video.year = int(release_date.split('-')[0])

            video.tmdb_id = movie_data.get('id')

            # 3. Скачиваем обложку
            poster_path = movie_data.get('poster_path')
            if poster_path:
                poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
                try:
                    img_resp = requests.get(poster_url)
                    if img_resp.status_code == 200:
                        # Сохраняем картинку в поле cover
                        file_name = f"{video.pk}_poster.jpg"
                        video.cover.save(file_name, ContentFile(img_resp.content), save=False)
                except Exception as e:
                    print(f"Ошибка загрузки обложки: {e}")

            video.save()
            updated += 1

    modeladmin.message_user(request, f"Обновлено фильмов: {updated}", level=messages.SUCCESS)

# ============================================
# 2. ПОЛЬЗОВАТЕЛИ И ПРОФИЛИ
# ============================================

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False


# Перерегистрируем UserAdmin, чтобы добавить профиль
try:
    admin.site.unregister(User)
except admin.sites.NotRegistered:
    pass


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)


# ============================================
# 3. ОСНОВНЫЕ МОДЕЛИ (ВИДЕО, КУРСЫ)
# ============================================

@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('title', 'video_type', 'status', 'get_total_size', 'created_at', 'learning_category')
    list_filter = ('status', 'video_type', 'learning_category', 'genres', 'countries')
    search_fields = ('title', 'description')
    filter_horizontal = ('tags', 'genres', 'countries')
    actions = [delete_with_file, fill_tmdb_data, restart_conversion] # <-- Добавили сюда
    # Красивое отображение статуса
    @admin.display(description='Статус')
    def display_status(self, obj):
        from django.utils.html import format_html
        colors = {
            'pending': 'orange',
            'processing': 'blue',
            'ready': 'green',
            'error': 'red'
        }
        # Если статуса нет или он пустой, выводим "Неизвестно"
        status_text = obj.get_status_display() if obj.status else "Нет статуса"
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'gray'),
            status_text
        )

class CourseFileInline(admin.TabularInline):
    model = CourseFile
    extra = 0
    fields = ('name', 'external_path', 'duration_formatted', 'file')
    readonly_fields = ('external_path', 'duration_formatted')

    def duration_formatted(self, obj):
        return obj.duration_formatted

    duration_formatted.short_description = "Длительность"


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    # Убрали file_count, добавили lesson_count
    list_display = ('title', 'learning_category', 'lesson_count', 'total_duration_display')
    search_fields = ('title',)
    list_filter = ('learning_category',)

    # Подключаем список видео
    inlines = [VideoInline]

    # Считаем уроки через правильную связь 'lessons'
    @admin.display(description='Уроков')
    def lesson_count(self, obj):
        # related_name='lessons' мы указали в models.py
        return obj.lessons.count()

    # Считаем общее время (если оно уже есть у видео)
    @admin.display(description='Общая длительность')
    def total_duration_display(self, obj):
        from django.db.models import Sum
        # Суммируем длительность всех уроков (в секундах)
        total_seconds = obj.lessons.aggregate(Sum('duration'))['duration__sum']

        if not total_seconds:
            return "—"

        # Красиво форматируем: часы и минуты
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{int(hours)}ч {int(minutes)}мин"


@admin.register(CourseFile)
class CourseFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'duration_formatted', 'is_external')
    search_fields = ('name', 'course__title')
    list_filter = ('course',)
    actions = [delete_with_file]

    def duration_formatted(self, obj):
        return obj.duration_formatted

    def is_external(self, obj):
        return bool(obj.external_path)

    is_external.boolean = True
    is_external.short_description = "С диска"


# ============================================
# 4. СПРАВОЧНИКИ И ТЕГИ
# ============================================

@admin.register(LearningCategory)
class LearningCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'category', 'color')
    list_filter = ('category',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(TagCategory)
class TagCategoryAdmin(admin.ModelAdmin):
    list_display = ('name',)


# ============================================
# 5. ОРГАНАЙЗЕР
# ============================================

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner')
    filter_horizontal = ('members',)


class TaskTemplateInline(admin.TabularInline):
    model = TaskTemplate
    extra = 1


@admin.register(ProjectTemplate)
class ProjectTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner')
    inlines = [TaskTemplateInline]


# ============================================
# 6. СИСТЕМНЫЕ И ПРОЧИЕ
# ============================================

@admin.register(IndexedItem)
class IndexedItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_folder', 'location_slug', 'relative_path')
    list_filter = ('location_slug', 'is_folder', 'tags')
    search_fields = ('name', 'relative_path')


@admin.register(CourseImportSession)
class CourseImportSessionAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'target_category', 'tag_to_add')
    readonly_fields = ('import_log',)

    def save_model(self, request, obj, form, change):
        # Сохраняем саму сессию импорта
        super().save_model(request, obj, form, change)

        root = Path(obj.root_path)
        if not root.exists() or not root.is_dir():
            obj.import_log = f"❌ Ошибка: Папка {obj.root_path} не найдена на сервере!"
            obj.save()
            return

        log_lines = []

        # Перебираем все папки внутри указанного пути
        for entry in root.iterdir():
            if entry.is_dir():
                # Создаем или получаем курс
                course, created = Course.objects.get_or_create(
                    title=entry.name,
                    defaults={
                        'learning_category': obj.target_category,
                        'source_path': str(entry),
                        'description': f"Автоматически импортирован из {entry}"
                    }
                )

                # Если курс уже был, обновляем ему путь
                if not created:
                    course.source_path = str(entry)
                    course.save()

                if obj.tag_to_add:
                    course.tags.add(obj.tag_to_add)

                # 🔥 МАГИЯ ЗДЕСЬ: Вызываем ту самую умную функцию, которая считает длительность! 🔥
                added_files = scan_course_directory(course)

                status = "Создан" if created else "Обновлен"
                log_lines.append(f"✅ Курс '{course.title}' ({status}): найдено/обновлено {added_files} файлов.")

        # Записываем красивый лог в админку
        obj.import_log = "\n".join(log_lines) if log_lines else "⚠️ В указанной папке нет других папок (курсов)."
        obj.save()


@admin.register(SearchConfig)
class SearchConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SearchConfig.objects.exists()


@admin.register(SearchHistory)
class SearchHistoryAdmin(admin.ModelAdmin):
    list_display = ('user', 'query', 'created_at')
    list_filter = ('user',)


@admin.register(ProcessingLog)
class ProcessingLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'video', 'message')
    list_filter = ('timestamp', 'video')
    readonly_fields = ('timestamp', 'video', 'message')


@admin.register(TimestampNote)
class TimestampNoteAdmin(admin.ModelAdmin):
    list_display = ('text', 'video', 'user', 'timestamp')
    list_filter = ('user', 'video')

# --- Добавьте эту функцию к остальным actions ---
@admin.action(description='🔄 Отправить выбранные на конвертацию (MP4)')
def restart_conversion(modeladmin, request, queryset):
    # Устанавливаем статус "Ожидает обработки" для всех выбранных видео
    updated = queryset.update(status='pending')
    modeladmin.message_user(request, f"Статус изменен для {updated} видео. Конвертация запущена.", messages.SUCCESS)

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'due_date', 'assigned_to', 'is_completed')
    list_filter = ('is_completed', 'due_date', 'assigned_to')
    search_fields = ('title', 'description')
    ordering = ('due_date',)

@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'xp', 'coins', 'level')
    search_fields = ('user__username',)
    list_editable = ('xp', 'coins', 'level') # Позволит вам быстро менять баланс прямо из списка

@admin.register(RewardItem)
class RewardItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'cost', 'icon')
    search_fields = ('title',)

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('user', 'item', 'created_at', 'is_fulfilled')
    list_filter = ('is_fulfilled', 'created_at')
    search_fields = ('user__username', 'item__title')
    list_editable = ('is_fulfilled',) # Галочка "выдано" (например, если купили пиццу, и вы ее заказали)

@admin.register(EventType)
class EventTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'icon', 'color')
    list_filter = ('user',)

@admin.register(TrackerEvent)
class TrackerEventAdmin(admin.ModelAdmin):
    list_display = ('title', 'event_type', 'value', 'timestamp', 'user')
    list_filter = ('event_type', 'user')
    search_fields = ('title', 'note')
    date_hierarchy = 'timestamp'

@admin.register(MetricGoal)
class MetricGoalAdmin(admin.ModelAdmin):
    list_display = ('title', 'target_value', 'current_value', 'period_start', 'period_end')
    list_filter = ('event_type', 'user')

admin.site.register(Post)
admin.site.register(ClockItem)