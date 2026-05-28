import telebot
from django.core.management.base import BaseCommand
from django.conf import settings
from blog.models import Task, UserProfile
from django.contrib.auth.models import User

bot = telebot.TeleBot(settings.TELEGRAM_BOT_TOKEN)


@bot.message_handler(commands=['start'])
def start_message(message):
    bot.reply_to(message,
                 "🤖 Джарвис на связи! Напиши /tasks, чтобы увидеть свои дела, или /status, чтобы узнать баланс монет.")


@bot.message_handler(commands=['status'])
def get_status(message):
    # Пытаемся найти пользователя по его Telegram ID (если вы его сохранили в профиле)
    try:
        profile = UserProfile.objects.get(telegram_chat_id=str(message.chat.id))
        text = (f"👤 Профиль: {profile.user.username}\n"
                f"⭐ Уровень: {profile.level}\n"
                f"💰 Монеты: {profile.coins}\n"
                f"📈 Опыт: {profile.xp} XP")
        bot.send_message(message.chat.id, text)
    except UserProfile.DoesNotExist:
        bot.send_message(message.chat.id, "❌ Твой Telegram ID не привязан к профилю на сайте. Сделай это в админке!")


@bot.message_handler(commands=['tasks'])
def get_tasks(message):
    # Берем топ-5 невыполненных задач
    tasks = Task.objects.filter(is_completed=False).order_by('due_date')[:5]

    if tasks:
        response = "📝 <b>Актуальные задачи:</b>\n\n"
        for t in tasks:
            user = t.assigned_to.username if t.assigned_to else "Общая"
            response += f"🔹 {t.title} (👤 {user})\n"
        bot.send_message(message.chat.id, response, parse_mode='HTML')
    else:
        bot.send_message(message.chat.id, "✅ Все задачи выполнены! Отдыхайте.")


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("🤖 Бот Джарвис запущен и слушает команды...")
        bot.polling(none_stop=True)