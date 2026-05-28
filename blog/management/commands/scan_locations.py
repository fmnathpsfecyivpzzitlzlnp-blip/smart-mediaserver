# blog/management/commands/scan_locations.py
import os
from pathlib import Path
from datetime import datetime
import pytz
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import transaction
from blog.models import IndexedItem, Tag, LearningCategory

# Расширенный список типов файлов
FILE_TYPE_MAPPING = {
    'видео': ('.mp4', '.mkv', '.avi', '.mov', '.webm'),
    'книга': ('.pdf', '.epub', '.fb2', '.djvu'),
    'документ': ('.docx', '.doc', '.txt', '.md', '.rtf', '.odt'),
    'аудио': ('.mp3', '.wav', '.flac', '.ogg'),
    'изображение': ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp'),
    'архив': ('.zip', '.rar', '.7z', '.gz', '.tar'),
}
TAG_COLORS = {'видео': '#0d6efd', 'книга': '#198754', 'документ': '#6c757d', 'аудио': '#fd7e14',
              'изображение': '#ffc107', 'архив': '#dc3545'}


class Command(BaseCommand):
    help = 'Индексирует файлы из указанной локальной директории в базу данных.'

    def add_arguments(self, parser):
        parser.add_argument(
            'scan_path',
            type=str,
            help='Полный путь к папке, которую нужно сканировать (например, "D:\\c++").'
        )
        parser.add_argument(
            'category_slug',
            type=str,
            help='Slug категории обучения, к которой относятся материалы (например, "code-lab").'
        )
        parser.add_argument(
            '--rescan',
            action='store_true',
            help='Удалить старые записи для этого пути перед сканированием.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        scan_path_str = options['scan_path']
        category_slug = options['category_slug']
        rescan = options['rescan']

        # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Находим правильный путь внутри контейнера ---

        # Находим, какой "диск" (локация) содержит наш путь
        target_location_slug = None
        container_path_str = None

        for slug, root in settings.INDEXER_LOCATIONS.items():
            # Проверяем, совпадает ли начало пути с реальным путем на хосте
            # Например, 'D:\c++' начинается с 'D:\'
            # (Приводим к нижнему регистру для надежности)
            if scan_path_str.lower().startswith(root['host_path'].lower()):
                target_location_slug = slug
                # Заменяем хостовую часть пути на внутреннюю часть контейнера
                # 'D:\c++' -> '/media_root/d_drive/c++'
                container_path_str = scan_path_str.replace(root['host_path'], root['container_path'], 1)
                break

        if not container_path_str:
            raise CommandError(
                f"Ошибка: Путь '{scan_path_str}' не соответствует ни одной из разрешенных локаций в INDEXER_LOCATIONS.")

        scan_path = Path(container_path_str)
        if not scan_path.exists() or not scan_path.is_dir():
            raise CommandError(f"Ошибка: Директория '{scan_path}' (внутри контейнера) не найдена.")

        try:
            category = LearningCategory.objects.get(slug=category_slug)
        except LearningCategory.DoesNotExist:
            raise CommandError(f"Ошибка: Категория '{category_slug}' не найдена.")

        # --- КОНЕЦ КЛЮЧЕВОГО ИЗМЕНЕНИЯ ---

        if rescan:
            deleted_count, _ = IndexedItem.objects.filter(absolute_path__startswith=str(scan_path)).delete()
            self.stdout.write(self.style.WARNING(
                f"Полное пересканирование: удалено {deleted_count} старых записей для пути '{scan_path_str}'."))

        self.stdout.write(self.style.SUCCESS(f"Начало индексации: {scan_path_str} (внутри контейнера как {scan_path})"))

        tags_by_name = {
            name: Tag.objects.get_or_create(name=name, defaults={'slug': name, 'color': TAG_COLORS.get(name)})[0] for
            name in FILE_TYPE_MAPPING}

        added_count = 0
        existing_paths = set(
            IndexedItem.objects.filter(absolute_path__startswith=str(scan_path)).values_list('absolute_path',
                                                                                             flat=True))

        for entry in scan_path.rglob('*'):
            absolute_path_str = str(entry)
            if not entry.is_file() or absolute_path_str in existing_paths:
                continue

            try:
                item_data = {
                    'name': entry.name,
                    'absolute_path': absolute_path_str,
                    'location_slug': target_location_slug,
                    'relative_path': str(entry.relative_to(scan_path)),
                    'is_folder': False,
                    'last_modified': datetime.fromtimestamp(entry.stat().st_mtime, tz=pytz.UTC),
                    'file_size': entry.stat().st_size,
                    'extension': entry.suffix.lower()
                }

                indexed_item = IndexedItem.objects.create(**item_data)

                tag_to_add = next(
                    (tags_by_name[name] for name, exts in FILE_TYPE_MAPPING.items() if item_data['extension'] in exts),
                    None)
                if tag_to_add:
                    indexed_item.tags.add(tag_to_add)

                self.stdout.write(f"  [+] {item_data['relative_path']}")
                added_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  [!] Ошибка для {entry}: {e}"))

        self.stdout.write(self.style.SUCCESS(f"Индексация завершена. Добавлено новых файлов: {added_count}."))