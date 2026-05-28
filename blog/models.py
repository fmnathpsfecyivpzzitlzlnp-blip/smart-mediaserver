# blog/models.py

import os
import datetime
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from tinymce.models import HTMLField # <--- Добавить импорт
from django.utils.text import slugify

import uuid
from django.utils.text import slugify

class TagCategory(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Название категории")
    # Можно добавить поле для цвета по умолчанию для всей категории, если захотите

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Категория тега"
        verbose_name_plural = "Категории тегов"
        ordering = ['name']


# --- ИЗМЕНЯЕМ СУЩЕСТВУЮЩУЮ МОДЕЛЬ Tag ---
class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True, verbose_name="Название тега")
    slug = models.SlugField(max_length=50, unique=True, allow_unicode=True)

    # Новые поля
    category = models.ForeignKey(
        TagCategory,
        on_delete=models.SET_NULL,  # Если удалить категорию, теги не удаляются
        null=True,
        blank=True,
        related_name='tags',
        verbose_name="Категория"
    )
    color = models.CharField(
        max_length=7,  # Для формата #RRGGBB
        default='#6c757d',  # Bootstrap "secondary" цвет по умолчанию
        verbose_name="Цвет"
    )

    def __str__(self): return self.name

    class Meta:
        verbose_name = "Тег";
        verbose_name_plural = "Теги"

# --- НОВАЯ МОДЕЛЬ ДЛЯ КАТЕГОРИЙ ОБУЧЕНИЯ ("СТИКЕРОВ") ---
class LearningCategory(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название категории")
    slug = models.SlugField(max_length=100, unique=True, allow_unicode=True)
    description = models.CharField(max_length=255, blank=True, verbose_name="Краткое описание")
    svg_icon = models.TextField(verbose_name="SVG иконка (код)", blank=True, help_text="Вставьте сюда полный SVG код иконки")
    css_class = models.CharField(max_length=50, blank=True, verbose_name="CSS класс для цвета", help_text="Например, sticker-blue, sticker-green, sticker-pink")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Категория обучения"
        verbose_name_plural = "Категории обучения"
        ordering = ['name']


# ==================================
# СЕКЦИЯ 4: Курсы (Связываем с вашими существующими моделями)
# =====================

class Course(models.Model):
    title = models.CharField(max_length=200, verbose_name="Название курса")
    slug = models.SlugField(unique=True, verbose_name="URL (Slug)")
    description = HTMLField(verbose_name="Описание", blank=True)

    # --- НОВОЕ ПОЛЕ: Путь к папке на диске ---
    source_path = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
        verbose_name=r"Путь к папке курса (D:\...)",
        help_text="Укажите абсолютный путь к папке, чтобы просканировать файлы автоматически."
    )

    learning_category = models.ForeignKey(
        LearningCategory,
        on_delete=models.CASCADE,
        related_name='courses',
        verbose_name="Категория обучения"
    )

    tags = models.ManyToManyField(
        Tag,
        related_name='courses',
        verbose_name="Теги / Технологии"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата создания")

    # Добавьте этот метод, чтобы видеть общую длительность курса
    @property
    def total_duration_formatted(self):
        total_seconds = sum(f.duration for f in self.files.all())
        m, s = divmod(total_seconds, 60)
        h, m = divmod(m, 60)
        return f"{h}ч {m}мин"

    def save(self, *args, **kwargs):
        if not self.slug:
            # 1. Пробуем сделать слаг стандартным способом
            self.slug = slugify(self.title)

            # 2. Если получилось пусто (например, название русское), генерируем код
            if not self.slug:
                self.slug = f"course-{uuid.uuid4().hex[:8]}"

            # 3. Проверка на уникальность (чтобы точно не совпало)
            if Course.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug += f"-{uuid.uuid4().hex[:4]}"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Курс"
        verbose_name_plural = "Курсы"

# ==================================
# СЕКЦИЯ 1: Базовые модели
# ==================================

class Post(models.Model):
    title = models.CharField(max_length=200, verbose_name="Заголовок")
    content = models.TextField(verbose_name="Содержание")
    published_date = models.DateTimeField(default=timezone.now, verbose_name="Дата публикации")
    def __str__(self): return self.title

    class Meta:
        verbose_name = "Статья";
        verbose_name_plural = "Статьи"


# ==================================
# СЕКЦИЯ 2: Модели для Медиатеки
# ==================================
# --- НОВАЯ МОДЕЛЬ ДЛЯ КАТЕГОРИЙ ТЕГОВ ---




class Genre(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название жанра")
    def __str__(self): return self.name

    class Meta:
        verbose_name = "Жанр";
        verbose_name_plural = "Жанры";
        ordering = ['name']


class Country(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название страны")
    def __str__(self): return self.name

    class Meta:
        verbose_name = "Страна";
        verbose_name_plural = "Страны";
        ordering = ['name']

class Person(models.Model):
    name = models.CharField(max_length=255, unique=True, verbose_name="Имя")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Персона (актер/режиссер)"
        verbose_name_plural = "Персоны (актеры/режиссеры)"
        ordering = ['name']


class TVShow(models.Model):
    title = models.CharField(max_length=255, verbose_name="Название сериала")
    description = models.TextField(blank=True, verbose_name="Описание")
    poster = models.ImageField(upload_to='posters/shows/', blank=True, verbose_name="Постер")

    # Можно добавить жанр, если хотите разделять Аниме/Сериалы
    SHOW_TYPES = [('SERIES', 'Сериал'), ('ANIME', 'Аниме'), ('CARTOON', 'Мультсериал')]
    show_type = models.CharField(max_length=20, choices=SHOW_TYPES, default='SERIES', verbose_name="Тип")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Сериал"
        verbose_name_plural = "Сериалы"



# --- МОДЕЛЬ ПЕРЕИМЕНОВАНА и РАСШИРЕНА ---
class Video(models.Model):
    class VideoType(models.TextChoices):
        MOVIE = 'MOVIE', 'Фильм'
        LESSON = 'LESSON', 'Урок'
        CLIP = 'CLIP', 'Клип'
        EPISODE = 'EPISODE', 'Эпизод сериала'  # <-- ДОБАВИТЬ ЭТУ СТРОКУ

    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', 'Ожидает обработки'
        PROCESSING = 'PROCESSING', 'Обрабатывается'
        READY = 'READY', 'Готов к просмотру'
        ERROR = 'ERROR', 'Ошибка обработки'

    # --- СВЯЗИ ---
    learning_category = models.ForeignKey(
        'LearningCategory',  # Используем строку, чтобы не зависеть от порядка объявления
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='videos',
        verbose_name="Категория обучения"
    )
    course = models.ForeignKey(
        'Course',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lessons'
    )

    # --- ОСНОВНАЯ ИНФОРМАЦИЯ ---
    # 👇 НОВЫЕ ПОЛЯ ДЛЯ ИЗБРАННОГО И СПИСКА ПРОСМОТРА
    favorites = models.ManyToManyField(User, related_name='favorite_videos', blank=True, verbose_name="В избранном у")
    watchlist = models.ManyToManyField(User, related_name='watchlist_videos', blank=True,
                                       verbose_name="Посмотреть позже")
    # Новые поля для сериалов
    tv_show = models.ForeignKey(TVShow, on_delete=models.SET_NULL, null=True, blank=True, related_name='episodes',
                                verbose_name="Сериал")
    season_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Номер сезона")
    episode_number = models.PositiveIntegerField(null=True, blank=True, verbose_name="Номер серии")

    tmdb_id = models.IntegerField(null=True, blank=True, verbose_name="ID на TMDb")
    title = models.CharField(max_length=200, verbose_name="Название")
    description = models.TextField(verbose_name="Описание", blank=True, default="")
    cover = models.ImageField(upload_to='covers/', verbose_name="Обложка", blank=True, null=True)

    # --- ПУТИ К ФАЙЛАМ ---
    movie_path = models.FileField(upload_to='source_videos', max_length=500, blank=True, null=True,
                                  verbose_name="Путь к оригиналу")
    web_player_path = models.FileField(upload_to='movies_web', max_length=500, blank=True, null=True,
                                       verbose_name="Путь к веб-версии (mp4)")
    vtt_thumbnails_path = models.FileField(upload_to='previews', max_length=500, blank=True, null=True,
                                           verbose_name="Путь к VTT")
    subtitles_path = models.FileField(upload_to='subtitles', max_length=500, blank=True, null=True,
                                      verbose_name="Путь к субтитрам")

    LEARNING_STATUS_CHOICES = [
        ('new', '🆕 Новый'),
        ('in_progress', '▶️ Смотрю'),
        ('completed', '✅ Изучено'),
    ]

    learning_status = models.CharField(
        max_length=20,
        choices=LEARNING_STATUS_CHOICES,
        default='new',
        verbose_name="Статус обучения"
    )

    last_viewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Когда смотрел"
    )

    # --- МЕТАДАННЫЕ ---
    status = models.CharField(max_length=10, choices=StatusChoices.choices, default=StatusChoices.PENDING,
                              verbose_name="Статус")
    year = models.PositiveIntegerField(verbose_name="Год выпуска", blank=True, null=True)
    rating = models.FloatField(verbose_name="Рейтинг", blank=True, null=True)
    duration = models.IntegerField(verbose_name="Длительность (сек)", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Новые поля
    processing_progress = models.IntegerField(default=0, verbose_name="Прогресс обработки (%)")
    file_ext = models.CharField(max_length=10, blank=True, null=True, verbose_name="Расширение")
    video_type = models.CharField(max_length=10, choices=VideoType.choices, default=VideoType.MOVIE,
                                  verbose_name="Тип видео")

    # --- MANY-TO-MANY ---
    tags = models.ManyToManyField('Tag', blank=True, verbose_name="Теги")
    genres = models.ManyToManyField('Genre', blank=True, verbose_name="Жанры")
    countries = models.ManyToManyField('Country', blank=True, verbose_name="Страны")
    actors = models.ManyToManyField('Person', related_name="filmography_actor", blank=True, verbose_name="Актеры")
    directors = models.ManyToManyField('Person', related_name="filmography_director", blank=True,
                                       verbose_name="Режиссеры")

    # 👇 ИСПРАВЛЕННЫЙ МЕТОД: УМНОЕ ФОРМАТИРОВАНИЕ ВРЕМЕНИ
    @property
    def duration_formatted(self):
        if not self.duration:
            return "00:00"

        hours = self.duration // 3600
        minutes = (self.duration % 3600) // 60
        seconds = self.duration % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"  # 1:05:30
        return f"{minutes:02d}:{seconds:02d}"  # 05:30

    # 👇 АВТО-ЗАПОЛНЕНИЕ РАСШИРЕНИЯ ПРИ СОХРАНЕНИИ
    def save(self, *args, **kwargs):
        if self.movie_path and not self.file_ext:
            # Берем имя файла и вытаскиваем расширение
            try:
                name, ext = os.path.splitext(self.movie_path.name)
                self.file_ext = ext.lower().replace('.', '')
            except:
                pass  # Если что-то пошло не так, не ломаем сохранение
        super().save(*args, **kwargs)

    # 👇 УДАЛЕНИЕ ФАЙЛОВ С ДИСКА ПРИ УДАЛЕНИИ ЗАПИСИ
    def delete(self, *args, **kwargs):
        paths_to_remove = []
        files_to_check = [
            self.movie_path, self.web_player_path, self.cover,
            self.vtt_thumbnails_path, self.subtitles_path
        ]

        for f in files_to_check:
            if f and f.name:
                try:
                    path = str(f.name)
                    if os.path.isabs(path):
                        paths_to_remove.append(path)
                    else:
                        paths_to_remove.append(os.path.join(settings.MEDIA_ROOT, path))
                except:
                    pass

        super().delete(*args, **kwargs)

        # Удаляем физически
        for path in paths_to_remove:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except:
                    pass

    def get_total_size(self):
        total_bytes = 0
        files = [self.movie_path, self.web_player_path]
        for f in files:
            if f and f.name:
                try:
                    path = str(f.name)
                    if not os.path.isabs(path):
                        path = os.path.join(settings.MEDIA_ROOT, path)
                    if os.path.exists(path):
                        total_bytes += os.path.getsize(path)
                except:
                    pass

        gb = total_bytes / (1024 * 1024 * 1024)
        if gb >= 1: return f"{gb:.2f} GB"
        mb = total_bytes / (1024 * 1024)
        return f"{mb:.1f} MB"

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Видео"
        verbose_name_plural = "Видео"
        ordering = ['-created_at']

# --- НОВАЯ МОДЕЛЬ ДЛЯ ЛОГОВ ОБРАБОТКИ ---
class ProcessingLog(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='logs')
    message = models.TextField(verbose_name="Сообщение")
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.timestamp.strftime('%H:%M:%S')}] {self.video.title}: {self.message}"

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Лог обработки"
        verbose_name_plural = "Логи обработки"

class ClockItem(models.Model):
    class ItemType(models.TextChoices):
        ALARM = 'ALARM', 'Будильник'
        TIMER = 'TIMER', 'Таймер'

    name = models.CharField(max_length=100, verbose_name="Название")
    item_type = models.CharField(max_length=5, choices=ItemType.choices, verbose_name="Тип")
    alarm_time = models.TimeField(verbose_name="Время срабатывания", blank=True, null=True, help_text="Для будильников")
    is_active = models.BooleanField(default=True, verbose_name="Активен")
    days_of_week = models.CharField(
        max_length=15, blank=True,
        verbose_name="Дни недели (Пн=1)",
        help_text="Укажите дни через запятую (напр. 1,3,5). Оставьте пустым для ежедневного."
    )
    timer_duration = models.PositiveIntegerField(
        verbose_name="Длительность (секунды)", blank=True, null=True,
        help_text="Для таймеров"
    )
    sound_file = models.FileField(
        upload_to='sounds/', verbose_name="Аудиофайл",
        help_text="MP3, WAV, OGG файлы", blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def get_days_as_list(self):
        if not self.days_of_week:
            return []
        return [int(day) for day in self.days_of_week.split(',') if day.isdigit()]

    def __str__(self):
        return f"{self.get_item_type_display()}: {self.name}"

    class Meta:
        verbose_name = "Элемент часов"
        verbose_name_plural = "Элементы часов"
        ordering = ['-created_at']


# --- НОВАЯ МОДЕЛЬ ДЛЯ ЗАМЕТОК ---
class TimestampNote(models.Model):
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name='notes', verbose_name="Видео")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Пользователь")
    timestamp = models.PositiveIntegerField(verbose_name="Время (секунды)")
    text = models.TextField(verbose_name="Текст заметки")
    is_public = models.BooleanField(default=False, verbose_name="Общая заметка")
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f'Заметка от {self.user.username} к "{self.video.title}"'
    class Meta:
        verbose_name = "Заметка к видео"; verbose_name_plural = "Заметки к видео"; ordering = ['timestamp']

    class Meta:
        verbose_name = "Заметка к видео"
        verbose_name_plural = "Заметки к видео"
        ordering = ['timestamp']


class TaskList(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_task_lists")
    name = models.CharField(max_length=100, verbose_name="Название списка")
    # Участники списка, с которыми поделился владелец
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="shared_task_lists", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_recurring = models.BooleanField(default=False, verbose_name="Повторяющаяся")
    repeat_days = models.IntegerField(default=7, verbose_name="Повторять каждые X дней")

    def __str__(self):
        return f'"{self.name}" (владелец: {self.owner.username})'

    class Meta:
        verbose_name = "Список задач"
        verbose_name_plural = "Списки задач"

# ===================================================
# --- НОВЫЕ МОДЕЛИ ДЛЯ "СЕМЕЙНОГО ОРГАНАЙЗЕРА" ---
# ===================================================

# 'Project' - это более общее название, чем TaskList, и оно лучше подходит
# для описания как "Списка покупок", так и IT-проектов.
class Project(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название проекта/списка")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owned_projects",
                              verbose_name="Владелец")
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="shared_projects", blank=True,
                                     verbose_name="Участники")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Проект / Список задач"
        verbose_name_plural = "Проекты / Списки задач"


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Низкий'
        MEDIUM = 'MEDIUM', 'Обычный'
        HIGH = 'HIGH', 'Высокий'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="tasks", verbose_name="Проект")
    title = models.CharField(max_length=255, verbose_name="Задача")
    description = models.TextField(verbose_name="Описание", blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="created_tasks",
                                   verbose_name="Создал")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="assigned_tasks", verbose_name="Исполнитель")

    due_date = models.DateTimeField(verbose_name="Срок выполнения", null=True, blank=True)
    is_completed = models.BooleanField(default=False, verbose_name="Выполнено")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Время завершения")

    # Ваши кастомные поля
    is_private = models.BooleanField(default=False, verbose_name="Личная задача (видна только создателю)")
    priority = models.CharField(max_length=6, choices=Priority.choices, default=Priority.MEDIUM,
                                verbose_name="Приоритет")
    position = models.PositiveIntegerField(default=0, verbose_name="Позиция в списке")
    # Поле для скрытых задач

    created_at = models.DateTimeField(auto_now_add=True)

    # 👇 ДОБАВЬТЕ ЭТУ СТРОКУ В КОНЕЦ КЛАССА TASK:
    # ПРИМЕЧАНИЕ: Если у вас вдруг нет полей для суммы награды, добавьте и их:
    reward_xp = models.IntegerField(default=50, verbose_name="Опыт за задачу")
    reward_coins = models.IntegerField(default=10, verbose_name="Монеты за задачу")
    rewards_claimed = models.BooleanField(default=False, verbose_name="Награды выданы (защита от дублей)")
    was_notified = models.BooleanField(default=False, verbose_name="Уведомление отправлено")

    def __str__(self):
        return self.title

    class Meta:
        # --- ИЗМЕНЕНИЕ В СОРТИРОВКЕ ---
        # Теперь главный критерий сортировки - это position.
        ordering = ['is_completed', 'position', 'due_date']
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"


# 1. Расширяем Профиль (Кошелек и Уровень)
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    telegram_chat_id = models.CharField(max_length=20, blank=True, null=True)

    # --- ГЕЙМИФИКАЦИЯ ---
    xp = models.IntegerField(default=0, verbose_name="Опыт (XP)")
    coins = models.IntegerField(default=0, verbose_name="Монеты (J-Coins)")
    level = models.IntegerField(default=1, verbose_name="Уровень")

    def add_rewards(self, xp_amount, coins_amount):
        """Метод для начисления наград"""
        self.xp += xp_amount
        self.coins += coins_amount

        # Простая формула уровня: каждые 1000 XP = новый уровень
        new_level = (self.xp // 1000) + 1
        if new_level > self.level:
            self.level = new_level
            # Тут можно отправлять уведомление: "LEVEL UP!"

        self.save()

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
    instance.profile.save()

# --- НОВЫЕ МОДЕЛИ ДЛЯ ШАБЛОНОВ ---

class ProjectTemplate(models.Model):
    name = models.CharField(max_length=100, verbose_name="Название шаблона проекта")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Владелец шаблона")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Шаблон проекта"
        verbose_name_plural = "Шаблоны проектов"


class TaskTemplate(models.Model):
    project_template = models.ForeignKey(ProjectTemplate, on_delete=models.CASCADE, related_name="task_templates",
                                         verbose_name="Шаблон проекта")
    title = models.CharField(max_length=255, verbose_name="Название шаблонной задачи")
    # Новые поля для геймификации
    reward_xp = models.IntegerField(default=10, verbose_name="Награда XP")
    reward_coins = models.IntegerField(default=5, verbose_name="Награда Монет")

    # Защита от накрутки (чтобы не получали награду дважды за одну задачу)
    rewards_claimed = models.BooleanField(default=False, verbose_name="Награда получена")
    # Можно добавить и другие поля, например, шаблонного исполнителя

    def __str__(self):
        return self.title

    class Meta:
        verbose_name = "Шаблон задачи"
        verbose_name_plural = "Шаблоны задач"


class WatchHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="Пользователь"
    )

    # 👇 ГЛАВНОЕ ПОЛЕ (Новая система: и для фильмов, и для уроков)
    video = models.ForeignKey(
        Video,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='history', # Важно: позволяет писать video.history.all()
        verbose_name="Видео/Урок"
    )

    # 👇 Старое поле (оставляем, чтобы старая база не сломалась, но использовать не будем)
    course_file = models.ForeignKey(
        'CourseFile',
        on_delete=models.CASCADE,
        verbose_name="Старый файл курса",
        null=True,
        blank=True
    )

    # 👇 ВРЕМЯ (Секунда, на которой остановились)
    timestamp = models.IntegerField(
        default=0,
        verbose_name="Остановился на секунде"
    )

    # 👇 СТАТУС (Досмотрел до конца?)
    is_finished = models.BooleanField(
        default=False,
        verbose_name="Просмотр завершен"
    )

    # 👇 ДАТА (Когда смотрел последний раз)
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата последнего просмотра"
    )

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "История просмотра"
        verbose_name_plural = "Истории просмотров"
        # Уникальность: один пользователь - одна запись на видео
        unique_together = [['user', 'video']]

    def __str__(self):
        if self.video:
            status = "✅" if self.is_finished else f"⏱ {self.timestamp}сек"
            return f"{self.user} -> {self.video.title} [{status}]"
        return f"{self.user} -> (Старый файл)"


# --- НОВАЯ УНИВЕРСАЛЬНАЯ МОДЕЛЬ ДЛЯ ФАЙЛОВ И ПАПОК ---
class IndexedItem(models.Model):
    # Общие поля
    name = models.CharField(max_length=255, verbose_name="Имя")
    # Путь внутри контейнера
    absolute_path = models.CharField(max_length=1000, unique=True, verbose_name="Абсолютный путь")
    # Ключ локации из settings.py (например, 'disk-d')
    location_slug = models.CharField(max_length=50, db_index=True, verbose_name="Slug локации")
    # Относительный путь внутри локации
    relative_path = models.CharField(max_length=1000, db_index=True, verbose_name="Относительный путь")
    is_folder = models.BooleanField(default=False, verbose_name="Это папка?")

    # Поля только для файлов
    file_size = models.BigIntegerField(default=0, verbose_name="Размер (байты)")
    extension = models.CharField(max_length=20, blank=True, verbose_name="Расширение")

    # Теги
    tags = models.ManyToManyField(Tag, blank=True, verbose_name="Теги")

    # === ДОБАВЬТЕ ВОТ ЭТО ПОЛЕ ===
    learning_category = models.ForeignKey(
        LearningCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='indexed_items',
        verbose_name="Категория обучения"
    )
    # =============================

    # Даты
    last_modified = models.DateTimeField(verbose_name="Дата изменения")
    indexed_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата индексации")

    def __str__(self):
        return self.relative_path

    class Meta:
        verbose_name = "Проиндексированный элемент"
        verbose_name_plural = "Проиндексированные элементы"
        ordering = ['-is_folder', 'name']





class CourseFile(models.Model):
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name='files',
        verbose_name="Курс"
    )

    name = models.CharField(max_length=255, verbose_name="Название файла")

    # --- ИЗМЕНЕНИЯ: Делаем загрузку файла необязательной ---
    file = models.FileField(upload_to='course_files/', verbose_name="Загруженный файл", blank=True, null=True)

    # --- НОВОЕ ПОЛЕ: Для хранения пути к файлу на диске ---
    external_path = models.CharField(max_length=1000, blank=True, null=True, verbose_name="Путь к файлу на диске")

    # Сортировка файлов (чтобы они шли по порядку 01, 02, 03)
    ordering = models.IntegerField(default=0, verbose_name="Порядок сортировки")

    # --- НОВОЕ ПОЛЕ ---
    duration = models.PositiveIntegerField(default=0, verbose_name="Длительность (сек)")

    # Хелпер для красивого вывода (например, 05:30)
    @property
    def duration_formatted(self):
        if not self.duration:
            return ""
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Файл курса"
        verbose_name_plural = "Файлы курсов"
        ordering = ['ordering', 'name']  # Автоматическая сортировка


class CourseImportSession(models.Model):
    """
    Модель для запуска массового импорта через админку.
    """
    root_path = models.CharField(
        max_length=500,
        verbose_name="Путь к папке с курсами",
        help_text="Пример: D:\\Education\\My_C_Courses. Каждая папка внутри станет отдельным Курсом."
    )

    target_category = models.ForeignKey(
        LearningCategory,
        on_delete=models.CASCADE,
        verbose_name="В какую категорию положить?"
    )

    tag_to_add = models.ForeignKey(
        Tag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Добавить тег (опционально)"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата запуска")

    import_log = models.TextField(
        blank=True,
        verbose_name="Лог выполнения",
        help_text="Здесь появится отчет после сохранения."
    )

    def __str__(self):
        return f"Импорт от {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        verbose_name = "⚙️ Массовый импорт курсов"
        verbose_name_plural = "⚙️ Массовый импорт курсов"
        ordering = ['-created_at']


class StudyPlan(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Студент")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, verbose_name="Курс")

    start_date = models.DateField(default=timezone.now, verbose_name="Дата начала")

    # Настройки расписания
    days_of_week = models.CharField(
        max_length=20,
        default="0,1,2,3,4",
        verbose_name="Дни обучения",
        help_text="0=Пн, 6=Вс. Пример: '0,2,4' (Пн, Ср, Пт)"
    )
    minutes_per_day = models.PositiveIntegerField(
        default=60,
        verbose_name="Цель (мин/день)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"План: {self.course.title} ({self.user.username})"

    class Meta:
        verbose_name = "Учебный план"
        verbose_name_plural = "Учебные планы"


class SearchConfig(models.Model):
    """Настройки поиска (управляется из админки)"""
    history_limit = models.PositiveIntegerField(
        default=20,
        verbose_name="Сколько последних поисков показывать?"
    )

    def save(self, *args, **kwargs):
        # Гарантируем, что запись настроек всегда только одна
        if not self.pk and SearchConfig.objects.exists():
            # Если пытаемся создать вторую, просто обновляем первую
            return SearchConfig.objects.first().save(*args, **kwargs)
        return super(SearchConfig, self).save(*args, **kwargs)

    class Meta:
        verbose_name = "Настройка поиска"
        verbose_name_plural = "Настройки поиска"

    def __str__(self):
        return f"Лимит истории: {self.history_limit}"


class SearchHistory(models.Model):
    """История поиска конкретного пользователя"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='search_history')
    query = models.CharField(max_length=255, verbose_name="Запрос")
    created_at = models.DateTimeField(auto_now=True) # auto_now обновляет дату при каждом сохранении

    class Meta:
        ordering = ['-created_at'] # Свежие сверху
        verbose_name = "Запрос поиска"
        verbose_name_plural = "История поиска"
        # Уникальность: чтобы не дублировать "python" 10 раз подряд,
        # мы будем обновлять время существующей записи.

    def __str__(self):
        return f"{self.user.username}: {self.query}"


# 3. Новая модель: Товар в Магазине
class RewardItem(models.Model):
    title = models.CharField(max_length=100, verbose_name="Название награды")
    description = models.TextField(blank=True, verbose_name="Описание")
    cost = models.IntegerField(verbose_name="Цена (монет)")
    icon = models.CharField(max_length=50, default="bi-gift", verbose_name="Bootstrap иконка")

    # Для кого доступна награда (опционально, можно оставить пустым для всех)
    available_for = models.ManyToManyField(User, blank=True, verbose_name="Доступно для")

    def __str__(self):
        return f"{self.title} ({self.cost} 💰)"

    class Meta:
        verbose_name = "Награда магазина"
        verbose_name_plural = "Магазин наград"


# 4. История покупок (чтобы Папа видел, кто что купил)
class Purchase(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    item = models.ForeignKey(RewardItem, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=True, verbose_name="Одобрено родителем")
    is_fulfilled = models.BooleanField(default=False, verbose_name="Выдано родителями")


class EventType(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='event_types', verbose_name="Владелец")
    name = models.CharField(max_length=50, verbose_name="Название типа")
    icon = models.CharField(max_length=50, default="bi-record-circle", verbose_name="Иконка (Bootstrap)")
    color = models.CharField(max_length=10, default="#0d6efd", verbose_name="Цвет (HEX)")

    def __str__(self): return self.name

    class Meta:
        verbose_name = "Тип события"
        verbose_name_plural = "Типы событий"

class TrackerEvent(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tracker_events')
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE, verbose_name="Категория")
    title = models.CharField(max_length=100, verbose_name="Событие")
    value = models.IntegerField(default=1, verbose_name="Значение")
    note = models.TextField(blank=True, verbose_name="Заметка")
    timestamp = models.DateTimeField(default=timezone.now, verbose_name="Время события")

    def __str__(self): return f"[{self.timestamp.strftime('%d.%m %H:%M')}] {self.title}"

    class Meta:
        verbose_name = "Лог трекера"
        verbose_name_plural = "Логи трекера"
        ordering = ['-timestamp']

class MetricGoal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE, null=True, blank=True, verbose_name="Связанная категория")
    title = models.CharField(max_length=100, verbose_name="Название цели")
    target_value = models.IntegerField(verbose_name="Целевое значение")
    current_value = models.IntegerField(default=0, verbose_name="Текущий прогресс")
    period_start = models.DateField(verbose_name="Начало периода")
    period_end = models.DateField(verbose_name="Конец периода")

    def __str__(self): return f"{self.title}: {self.current_value} / {self.target_value}"

    class Meta:
        verbose_name = "Цель"
        verbose_name_plural = "Цели"

class ChildTask(models.Model):
    """Модель для детских заданий (Do it!)"""
    user = models.ForeignKey(User, on_delete=models.CASCADE) # Чье это задание
    title = models.CharField(max_length=200)                 # Название (Полить цветы)
    reward = models.IntegerField(default=1)                  # Награда в монетах
    icon = models.CharField(max_length=50, default='🌟')      # Эмодзи-иконка
    is_completed = models.BooleanField(default=False)        # Выполнено или нет
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.reward} ★)"

class PurchaseLog(models.Model):
    """Журнал покупок детей в магазине наград"""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200) # Название награды (Пицца, Час игр)
    cost = models.IntegerField()             # Сколько монет потрачено
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} купил {self.title}"