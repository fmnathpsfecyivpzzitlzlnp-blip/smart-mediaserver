import os
import subprocess
import json
from django.core.management.base import BaseCommand
from blog.models import Video


class Command(BaseCommand):
    help = 'Обновляет длительность видео (duration) с помощью ffprobe'

    def handle(self, *args, **options):
        # Берем только те видео, где длительность 0 или не указана
        videos = Video.objects.filter(duration__lte=0) | Video.objects.filter(duration__isnull=True)
        count = videos.count()

        self.stdout.write(f"🔍 Найдено {count} видео без длительности. Начинаю анализ...")

        for i, video in enumerate(videos):
            if not video.movie_path:
                continue

            # Получаем полный путь к файлу
            # Если путь относительный, добавляем /source_courses (или другой корень, если нужно)
            file_path = video.movie_path.name
            if not file_path.startswith('/'):
                # Пробуем угадать, где лежит файл. Для курсов это обычно /source_courses
                # Но лучше, если в базе уже лежит полный путь.
                if 'source_courses' not in file_path:
                    file_path = os.path.join('/source_courses', file_path)

            if not os.path.exists(file_path):
                # Если файл не найден по прямому пути, попробуем через атрибут .path (если настроен медиа рут)
                try:
                    file_path = video.movie_path.path
                except:
                    self.stdout.write(self.style.WARNING(f"⚠️ Файл не найден: {video.title}"))
                    continue

            try:
                # Запускаем ffprobe (быстрый анализ заголовков)
                cmd = [
                    'ffprobe',
                    '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format',
                    '-show_streams',
                    file_path
                ]
                result = subprocess.run(cmd, capture_output=True, text=True)
                data = json.loads(result.stdout)

                # Ищем длительность
                duration_sec = float(data['format']['duration'])

                # Сохраняем в базу (округляем до целых секунд)
                video.duration = int(duration_sec)
                video.save()

                self.stdout.write(f"[{i + 1}/{count}] ✅ {video.title}: {video.duration} сек.")

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Ошибка {video.title}: {e}"))

        self.stdout.write(self.style.SUCCESS("🎉 Готово! Длительности обновлены."))