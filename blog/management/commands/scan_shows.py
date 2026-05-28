import re
import os
from pathlib import Path
from django.core.management.base import BaseCommand
from blog.models import Video, TVShow
from blog.tasks import process_video_task


class Command(BaseCommand):
    help = 'Сканирует папку на наличие сериалов SxxExx'

    def add_arguments(self, parser):
        # Разрешаем принимать путь как аргумент
        parser.add_argument('--path', type=str, default='/source_shows', help='Путь к папке')

    def handle(self, *args, **options):
        root_path = Path(options['path'])  # Берем путь из аргументов
        self.stdout.write(f"🕵️‍♂️ Ищу сериалы в: {root_path}")

        if not root_path.exists():
            self.stdout.write(self.style.ERROR(f"❌ Папка не найдена: {root_path}"))
            return

        # Регулярка ловит: S01E01, s1e5, 1x05
        pattern = re.compile(r'[sS](\d{1,2})[eE](\d{1,2})|(\d{1,2})x(\d{1,2})')
        VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.webm'}
        count_new = 0

        for file_path in sorted(root_path.rglob('*')):
            if file_path.is_file() and file_path.suffix.lower() in VIDEO_EXTS:
                if file_path.name.startswith('.'): continue

                match = pattern.search(file_path.name)
                if match:
                    s_str = match.group(1) or match.group(3)
                    e_str = match.group(2) or match.group(4)
                    season_num = int(s_str)
                    episode_num = int(e_str)

                    # Логика названия
                    folder_name = file_path.parent.name
                    grandparent = file_path.parent.parent.name

                    if "season" in folder_name.lower() or "сезон" in folder_name.lower():
                        raw_title = grandparent
                    else:
                        raw_title = folder_name.replace('.', ' ')
                        split_match = re.split(r'[sS]\d{2}', raw_title)
                        if split_match: raw_title = split_match[0]

                    show_title = raw_title.strip()

                    show, _ = TVShow.objects.get_or_create(title=show_title)

                    video, created = Video.objects.get_or_create(
                        movie_path=str(file_path),
                        defaults={
                            'title': f"{show.title} S{season_num:02}E{episode_num:02}",
                            'video_type': Video.VideoType.EPISODE,
                            'tv_show': show,
                            'season_number': season_num,
                            'episode_number': episode_num,
                            'status': Video.StatusChoices.PROCESSING
                        }
                    )

                    if created:
                        count_new += 1
                        self.stdout.write(f"Found: {show.title} - S{season_num}E{episode_num}")
                        process_video_task.delay(video.pk)

        self.stdout.write(self.style.SUCCESS(f"✨ Сканирование завершено! Новых серий: {count_new}"))