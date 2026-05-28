# Расположение: blog/management/commands/scan_movies.py
from pathlib import Path
import re
from django.core.management.base import BaseCommand, CommandError
from blog.models import Video
from blog.tasks import process_video_task

SOURCE_MOVIES_DIR = Path("/source_movies")


class Command(BaseCommand):
    help = 'Сканирует директорию /source_movies и добавляет новые видео указанного типа.'

    # --- НОВЫЙ БЛОК: Добавляем аргумент командной строки ---
    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            help='Тип загружаемого видео (MOVIE или LESSON)',
            default=Video.VideoType.MOVIE,  # По умолчанию, если тип не указан, считаем, что это фильм
            choices=[Video.VideoType.MOVIE, Video.VideoType.LESSON]
        )

    # --------------------------------------------------------

    def handle(self, *args, **options):
        # --- Получаем тип из аргументов ---
        video_type_to_add = options['type']

        self.stdout.write(self.style.SUCCESS(f"--- Запуск сканирования для типа: {video_type_to_add} ---"))
        self.stdout.write(f"Поиск новых видео в: {SOURCE_MOVIES_DIR}")

        # ... (проверка существования директории)

        existing_video_paths_in_db = set(Video.objects.values_list('movie_path', flat=True))

        found_new_videos_count = 0
        video_extensions = ('*.mkv', '*.mp4', '*.avi', '*.mov')

        for extension in video_extensions:
            for file_path in SOURCE_MOVIES_DIR.rglob(extension):
                path_to_save_in_db = str(file_path)
                if path_to_save_in_db in existing_video_paths_in_db:
                    continue

                self.stdout.write(self.style.NOTICE(f"\n[+] Найден новый файл: {file_path.name}"))

                try:
                    raw_title = file_path.stem.replace('.', ' ').replace('_', ' ').strip()
                    clean_title = re.sub(r'\[.*?\]|\(.*?\)|1080p|720p|1440p|HD|BluRay', '', raw_title,
                                         flags=re.IGNORECASE).strip()

                    self.stdout.write(f" > Название: '{clean_title}'")

                    new_video = Video.objects.create(
                        title=clean_title,
                        movie_path=path_to_save_in_db,
                        status=Video.StatusChoices.PENDING,
                        video_type=video_type_to_add  # <--- Присваиваем правильный тип!
                    )

                    self.stdout.write(
                        f" > Запись с ID {new_video.id} создана (Тип: {new_video.get_video_type_display()})")

                    process_video_task.delay(new_video.pk)
                    self.stdout.write(self.style.SUCCESS(f" > Задача на обработку отправлена."))

                    existing_video_paths_in_db.add(path_to_save_in_db)
                    found_new_videos_count += 1

                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"!!! Ошибка при добавлении {file_path.name}: {e}"))

        if found_new_videos_count > 0:
            self.stdout.write(
                self.style.SUCCESS(f"\n--- Сканирование завершено. Добавлено: {found_new_videos_count}. ---"))
        else:
            self.stdout.write("\n--- Сканирование завершено. Новых файлов не найдено. ---")