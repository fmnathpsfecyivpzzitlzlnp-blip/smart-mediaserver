# blog/management/commands/scan_materials.py
import mimetypes
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from slugify import slugify
from blog.models import LearningMaterial, LearningCategory, Tag

# Определяем, какие расширения к какому тегу относятся
VIDEO_EXTS = ['.mp4', '.mkv', '.avi', '.mov', '.webm']
BOOK_EXTS = ['.pdf', '.epub', '.fb2', '.djvu']
DOC_EXTS = ['.docx', '.doc', '.txt', '.md', '.rtf']


class Command(BaseCommand):
    help = 'Сканирует директорию с учебными материалами, индексирует файлы и создает для них теги.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            required=True,
            help='Полный путь к папке, которую нужно сканировать (например, "D:/c++").'
        )
        parser.add_argument(
            '--category-slug',
            type=str,
            required=True,
            help='Slug категории обучения, к которой относятся материалы (например, "code-lab").'
        )

    def handle(self, *args, **options):
        scan_path_str = options['path']
        category_slug = options['category_slug']

        scan_path = Path(scan_path_str)
        if not scan_path.exists() or not scan_path.is_dir():
            raise CommandError(f"Ошибка: Директория '{scan_path_str}' не найдена.")

        try:
            category = LearningCategory.objects.get(slug=category_slug)
        except LearningCategory.DoesNotExist:
            raise CommandError(f"Ошибка: Категория с slug='{category_slug}' не найдена. Создайте ее в админ-панели.")

        self.stdout.write(self.style.SUCCESS(f"--- Начало сканирования папки: {scan_path} ---"))
        self.stdout.write(self.style.SUCCESS(f"--- Категория: {category.name} ---"))

        # Получаем или создаем нужные теги
        tag_video, _ = Tag.objects.get_or_create(name='видео', defaults={'slug': 'video', 'color': '#0d6efd'})
        tag_book, _ = Tag.objects.get_or_create(name='книга', defaults={'slug': 'book', 'color': '#198754'})
        tag_doc, _ = Tag.objects.get_or_create(name='документ', defaults={'slug': 'document', 'color': '#6c757d'})

        found_count = 0
        # Проходим по папкам-курсам внутри основной директории
        for course_dir in scan_path.iterdir():
            if not course_dir.is_dir():
                continue

            self.stdout.write(f"\nНайдена папка курса: {course_dir.name}")

            # Рекурсивно ищем все файлы внутри папки курса
            for file_path in course_dir.rglob('*'):
                if not file_path.is_file():
                    continue

                # Проверяем, не индексировали ли мы этот файл ранее
                if LearningMaterial.objects.filter(file_path=str(file_path)).exists():
                    continue

                # Создаем запись в базе
                material = LearningMaterial.objects.create(
                    title=file_path.name,
                    file_path=str(file_path),
                    course_name=course_dir.name,
                    learning_category=category
                )

                # Определяем тип файла и добавляем тег
                ext = file_path.suffix.lower()
                if ext in VIDEO_EXTS:
                    material.tags.add(tag_video)
                    self.stdout.write(self.style.NOTICE(f"  [+] Добавлено видео: {file_path.name}"))
                elif ext in BOOK_EXTS:
                    material.tags.add(tag_book)
                    self.stdout.write(self.style.NOTICE(f"  [+] Добавлена книга: {file_path.name}"))
                elif ext in DOC_EXTS:
                    material.tags.add(tag_doc)
                    self.stdout.write(self.style.NOTICE(f"  [+] Добавлен документ: {file_path.name}"))
                else:
                    self.stdout.write(f"  [?] Пропущен файл с неизвестным расширением: {file_path.name}")
                    continue  # Не сохраняем файлы, тип которых не определили

                found_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"\n--- Сканирование завершено. Добавлено новых файлов: {found_count}. ---"))