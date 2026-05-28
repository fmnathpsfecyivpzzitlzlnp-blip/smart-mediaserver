import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from blog.models import EventType


class Command(BaseCommand):
    help = 'Автоматически загружает большую библиотеку трекеров привычек из шаблонов'

    def handle(self, *args, **options):
        # Библиотека наших привычек (Название, Иконка Bootstrap, Цвет)
        habits_library = [
            # 🧘 Здоровье и дух
            {"name": "Упражнения", "icon": "bi-activity", "color": "#0d6efd"},
            {"name": "Медитация", "icon": "bi-yin-yang", "color": "#0dcaf0"},
            {"name": "Сон 8 часов", "icon": "bi-moon-stars", "color": "#6f42c1"},
            {"name": "Прогулка", "icon": "bi-tree", "color": "#198754"},

            # 🍎 Питание
            {"name": "Вода (1 стакан)", "icon": "bi-droplet", "color": "#0dcaf0"},
            {"name": "Без сахара", "icon": "bi-slash-circle", "color": "#dc3545"},
            {"name": "Без кофе", "icon": "bi-cup-hot", "color": "#fd7e14"},
            {"name": "Здоровая еда", "icon": "bi-apple", "color": "#198754"},
            {"name": "Ел на ночь", "icon": "bi-clock-history", "color": "#dc3545"},

            # 🧹 Дом и быт (в т.ч. для детского Do it!)
            {"name": "Уборка", "icon": "bi-stars", "color": "#ffc107"},
            {"name": "Вынес мусор", "icon": "bi-trash3", "color": "#6c757d"},
            {"name": "Помыл посуду", "icon": "bi-cup-straw", "color": "#0dcaf0"},
            {"name": "Почистил зубы", "icon": "bi-bandaid", "color": "#ffffff"},
            {"name": "Собрал игрушки", "icon": "bi-box-seam", "color": "#fbbc04"},

            # 🧠 Развитие
            {"name": "Чтение", "icon": "bi-book", "color": "#6f42c1"},
            {"name": "Дневник", "icon": "bi-journal-bookmark", "color": "#adb5bd"},
            {"name": "Новый язык", "icon": "bi-translate", "color": "#0d6efd"},
            {"name": "Творчество/Поделка", "icon": "bi-palette", "color": "#d63384"},

            # 💰 Финансы
            {"name": "Отложил деньги", "icon": "bi-piggy-bank", "color": "#198754"},
            {"name": "Спонтанная покупка", "icon": "bi-wallet2", "color": "#dc3545"},
        ]

        # Получаем всех пользователей (вас и детские аккаунты)
        users = User.objects.all()
        if not users.exists():
            self.stdout.write(self.style.ERROR('❌ В базе нет пользователей! Создайте хотя бы одного.'))
            return

        total_added = 0

        for user in users:
            self.stdout.write(f'⏳ Добавляем привычки для пользователя: {user.username}...')
            for h in habits_library:
                # get_or_create защищает от дубликатов (если скрипт запустить дважды)
                obj, created = EventType.objects.get_or_create(
                    user=user,
                    name=h['name'],
                    defaults={'icon': h['icon'], 'color': h['color']}
                )
                if created:
                    total_added += 1

        self.stdout.write(self.style.SUCCESS(f'✅ Готово! Успешно добавлено {total_added} новых кнопок трекера.'))