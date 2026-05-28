import os
import telebot
from django.core.management.base import BaseCommand
from django.utils import timezone
from blog.models import Task


class Command(BaseCommand):
    help = 'Отправляет план задач на сегодня в Telegram'

    def handle(self, *args, **kwargs):
        token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not token or not chat_id:
            self.stdout.write(self.style.ERROR('Ошибка: .env файл не настроен'))
            return

        bot = telebot.TeleBot(token)
        today = timezone.localdate()

        # ОТЛАДКА: Пишем в консоль, какую дату ищем
        self.stdout.write(f"🔎 Ищем задачи на дату: {today}")

        # 👇 ИСПРАВЛЕНИЕ: используем due_date__date (сравнение только по дате, без времени)
        tasks = Task.objects.filter(
            due_date__date=today,
            is_completed=False
        )

        # ОТЛАДКА: Сколько нашли?
        self.stdout.write(f"🔎 Найдено задач: {tasks.count()}")

        if not tasks.exists():
            self.stdout.write(self.style.WARNING('Задач нет (или они уже выполнены).'))
            return

        # Формируем сообщение
        message = f"📅 **План на сегодня ({today.strftime('%d.%m')}):**\n\n"
        for i, task in enumerate(tasks, 1):
            message += f"{i}. ▫️ {task.title}\n"

        message += f"\nВсего: {len(tasks)}"

        try:
            bot.send_message(chat_id, message, parse_mode='Markdown')
            self.stdout.write(self.style.SUCCESS(f'✅ Отправлено!'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Ошибка Телеграм: {e}'))