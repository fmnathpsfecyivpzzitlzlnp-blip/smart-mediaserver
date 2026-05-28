import os
from django.core.management.base import BaseCommand
from blog.models import Video


class Command(BaseCommand):
    help = 'Восстанавливает расширения файлов (file_ext) для иконок и фильтров'

    def handle(self, *args, **options):
        self.stdout.write("⏳ Начинаю обновление расширений...")

        videos = Video.objects.all()
        count = 0
        updated = 0

        for v in videos:
            if v.movie_path:
                # Получаем имя файла
                filename = v.movie_path.name

                # Вытаскиваем расширение (например .mp4)
                _, ext = os.path.splitext(filename)

                # Убираем точку и приводим к нижнему регистру (mp4, pdf, zip)
                clean_ext = ext.lower().replace('.', '')

                # Если расширения не было или оно отличается — обновляем
                if v.file_ext != clean_ext:
                    v.file_ext = clean_ext
                    v.save()
                    updated += 1
            count += 1

        # 👇 ИСПРАВЛЕНО: Добавлена вторая закрывающая скобка в конце
        self.stdout.write(self.style.SUCCESS(f"✅ Готово! Всего видео: {count}. Обновлено: {updated}."))