import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils.text import slugify
from blog.models import Course, LearningCategory, Tag
from blog.services import scan_course_directory


class Command(BaseCommand):
    help = 'Массовый импорт курсов из корневой папки. Каждая подпапка становится отдельным Курсом.'

    def add_arguments(self, parser):
        parser.add_argument('root_path', type=str,
                            help='Путь к папке, содержащей папки курсов (например D:\\Education)')
        parser.add_argument('category_slug', type=str, help='Slug категории обучения (например, code-lab)')
        parser.add_argument('--tag', type=str, help='Slug тега для добавления ко всем курсам (необязательно)')

    def handle(self, *args, **options):
        root_path_input = options['root_path']
        category_slug = options['category_slug']
        tag_slug = options.get('tag')

        # 1. Поиск категории
        try:
            category = LearningCategory.objects.get(slug=category_slug)
        except LearningCategory.DoesNotExist:
            raise CommandError(f"Категория '{category_slug}' не найдена. Создайте её в админке.")

        # 2. Поиск тега (если передан)
        tag_obj = None
        if tag_slug:
            try:
                tag_obj = Tag.objects.get(slug=tag_slug)
            except Tag.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Тег '{tag_slug}' не найден, пропускаем."))

        # 3. Конвертация пути (Windows -> Docker)
        container_root_path = None
        for slug, root in settings.INDEXER_LOCATIONS.items():
            if root_path_input.lower().startswith(root['host_path'].lower()):
                container_root_path = root_path_input.replace(root['host_path'], root['container_path'], 1)
                # Исправляем слеши на Linux-style
                container_root_path = container_root_path.replace('\\', '/')
                break

        if not container_root_path:
            # Если путь уже похож на линуксовый или не найден в маппинге, пробуем использовать как есть
            container_root_path = root_path_input

        scan_path = Path(container_root_path)
        if not scan_path.exists() or not scan_path.is_dir():
            raise CommandError(f"Путь '{container_root_path}' не найден внутри контейнера.")

        self.stdout.write(self.style.SUCCESS(f"--- Сканирование корневой папки: {scan_path} ---"))

        # 4. Проход по папкам (каждая папка = 1 курс)
        for entry in scan_path.iterdir():
            if entry.is_dir():
                course_title = entry.name
                # Генерируем slug из названия (если кириллица, лучше использовать slugify(..., allow_unicode=True) или транслит)
                # Для простоты используем стандартный, но учтите, что для русских названий нужен django-slugify или подобное
                course_slug = slugify(course_title, allow_unicode=True)

                # Если slug получился пустым (например, символы не прошли), добавим random
                if not course_slug:
                    course_slug = f"course-{entry.stat().st_mtime}"

                # Создаем или получаем курс
                course, created = Course.objects.get_or_create(
                    slug=course_slug,
                    defaults={
                        'title': course_title,
                        'source_path': str(entry),
                        'learning_category': category,
                        'description': f"<p>Автоматически импортированный курс: <strong>{course_title}</strong></p>"
                    }
                )

                if created:
                    self.stdout.write(f"[+] Создан курс: {course_title}")
                else:
                    self.stdout.write(f"[*] Курс уже есть: {course_title} (обновляем файлы)")
                    # Если курс был, можно обновить путь, на всякий случай
                    if course.source_path != str(entry):
                        course.source_path = str(entry)
                        course.save()

                # Добавляем тег, если нужно
                if tag_obj:
                    course.tags.add(tag_obj)

                # 5. Сканируем файлы внутри этого курса
                added_files = scan_course_directory(course)
                if added_files > 0:
                    self.stdout.write(self.style.SUCCESS(f"    -> Добавлено файлов: {added_files}"))
                else:
                    self.stdout.write(self.style.WARNING(f"    -> Файлов не добавлено (возможно, уже есть)"))

        self.stdout.write(self.style.SUCCESS("\n✅ Массовый импорт завершен!"))