import os
from django.core.management.base import BaseCommand
from blog.models import Course, Video, LearningCategory


class Command(BaseCommand):
    help = 'Сканирует курсы. Можно указать категорию ID.'

    def add_arguments(self, parser):
        parser.add_argument('--path', type=str, default='/source_courses')
        # 👇 Добавляем аргумент ID категории
        parser.add_argument('--category_id', type=int, default=0)

    def handle(self, *args, **options):
        root_path = options['path']
        category_id = options['category_id']

        # 1. ОПРЕДЕЛЯЕМ КАТЕГОРИЮ
        target_category = None

        # Если ID передали, ищем такую категорию
        if category_id > 0:
            try:
                target_category = LearningCategory.objects.get(id=category_id)
                self.stdout.write(self.style.SUCCESS(f"📂 Выбрана категория: {target_category.name}"))
            except LearningCategory.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"⚠️ Категория ID={category_id} не найдена."))

        # Если не нашли или не передали — берем/создаем "Новые загрузки"
        if not target_category:
            target_category, _ = LearningCategory.objects.get_or_create(
                slug='new-uploads',
                defaults={'name': '📥 Новые загрузки'}
            )
            self.stdout.write(f"📂 Использую категорию по умолчанию: {target_category.name}")

        self.stdout.write(f"🔍 Сканирую папку: {root_path}")

        if not os.path.exists(root_path):
            self.stdout.write(self.style.ERROR(f"❌ Папка {root_path} не найдена!"))
            return

        # 2. СКАНИРУЕМ ПАПКИ (КУРСЫ)
        courses_created = 0
        lessons_created = 0

        try:
            top_level_items = sorted(os.listdir(root_path))
        except OSError as e:
            self.stdout.write(self.style.ERROR(f"Ошибка чтения: {e}"))
            return

        for item_name in top_level_items:
            course_path = os.path.join(root_path, item_name)
            if not os.path.isdir(course_path):
                continue

            # 3. СОЗДАЕМ КУРС В ВЫБРАННОЙ КАТЕГОРИИ
            course, created = Course.objects.get_or_create(
                title=item_name,
                defaults={
                    'description': 'Автоматически импортирован',
                    'learning_category': target_category  # <--- ИСПОЛЬЗУЕМ ВЫБРАННУЮ
                }
            )

            # Если курс уже был, но мы хотим его переместить в новую категорию — раскомментируйте строчку ниже:
            # course.learning_category = target_category; course.save()

            if created:
                courses_created += 1
                self.stdout.write(f"📚 Создан курс: {item_name}")
            else:
                self.stdout.write(f"ℹ️ Курс уже есть: {item_name}")

            # 4. СКАНИРУЕМ УРОКИ
            for dirpath, _, filenames in os.walk(course_path):
                # Поддерживаем много форматов
                video_files = [f for f in filenames if
                               f.lower().endswith(('.mp4', '.avi', '.mkv', '.mov', '.webm', '.pdf', '.zip', '.rar'))]
                video_files.sort()

                for filename in video_files:
                    full_path = os.path.join(dirpath, filename)

                    # Определяем расширение для правильной иконки
                    _, ext = os.path.splitext(filename)
                    clean_ext = ext.lower().replace('.', '')

                    if not Video.objects.filter(course=course, title=filename).exists():
                        Video.objects.create(
                            title=filename,
                            course=course,
                            movie_path=full_path,
                            video_type='LESSON',
                            status='pending',
                            file_ext=clean_ext
                        )
                        lessons_created += 1
                        self.stdout.write(f"   ➕ Файл: {filename}")

        self.stdout.write(self.style.SUCCESS(f"✅ Готово! Курсов: {courses_created}, Файлов: {lessons_created}"))