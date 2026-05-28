import telebot
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.conf import settings
from .models import Task, Purchase
from django.db.models.signals import pre_save, post_save


@receiver(pre_save, sender=Task)
def task_completion_and_rewards(sender, instance, **kwargs):
    # Логирование для отладки (видно в docker compose logs web)
    print(f"🚨 ПРОВЕРКА СИГНАЛА: Задача '{instance.title}' сохраняется.")

    # Если это новая задача (еще нет в БД), просто выходим
    if not instance.pk:
        return

    try:
        old_task = Task.objects.get(pk=instance.pk)
    except Task.DoesNotExist:
        return

    # Проверяем: статус изменился на "Выполнено" и награда еще не выдавалась
    if instance.is_completed and not old_task.is_completed and not getattr(instance, 'rewards_claimed', False):
        if instance.assigned_to:
            profile = instance.assigned_to.profile

            # 1. Получаем награды (если полей нет, даем стандартные 50 XP и 10 монет)
            xp_to_add = getattr(instance, 'reward_xp', 50)
            coins_to_add = getattr(instance, 'reward_coins', 10)

            # Начисляем монеты и опыт напрямую
            profile.xp += xp_to_add
            profile.coins += coins_to_add
            profile.level = (profile.xp // 1000) + 1  # 1 уровень за каждые 1000 XP
            profile.save()

            # Фиксируем, что награда выдана (защита от читерства)
            instance.rewards_claimed = True

            # 2. Отправляем отчет в Telegram
            token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
            chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)

            if token and chat_id:
                try:
                    bot = telebot.TeleBot(token)
                    msg = (
                        f"🎉 <b>Задача выполнена!</b>\n\n"
                        f"👤 Исполнитель: <b>{instance.assigned_to.username}</b>\n"
                        f"📝 Дело: {instance.title}\n"
                        f"🎁 Награда: +{xp_to_add} XP | +{coins_to_add} 💰\n"
                        f"📈 Текущий уровень: {profile.level} ⭐"
                    )
                    bot.send_message(chat_id, msg, parse_mode='HTML')
                    print(f"✅ Уведомление успешно отправлено в Telegram для {instance.assigned_to.username}!")
                except Exception as e:
                    print(f"❌ Ошибка отправки в Telegram: {e}")
            else:
                print("⚠️ ВНИМАНИЕ: TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID отсутствуют в настройках!")


@receiver(post_save, sender=Purchase)
def notify_new_purchase(sender, instance, created, **kwargs):
    # Реагируем ТОЛЬКО на новую покупку (чтобы не спамить, когда вы ставите галочку "Выдано" в админке)
    if created:
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', None)
        chat_id = getattr(settings, 'TELEGRAM_CHAT_ID', None)

        if token and chat_id:
            try:
                bot = telebot.TeleBot(token)
                msg = (
                    f"🛒 <b>Новая покупка в Магазине JARVIS!</b>\n\n"
                    f"👤 Покупатель: <b>{instance.user.username}</b>\n"
                    f"🎁 Товар: {instance.item.title}\n"
                    f"💰 Списано: {instance.item.cost} монет\n\n"
                    f"⚡ Награда ждет выдачи!"
                )
                bot.send_message(chat_id, msg, parse_mode='HTML')
                print(f"✅ Уведомление о покупке отправлено!")
            except Exception as e:
                print(f"❌ Ошибка отправки покупки в Telegram: {e}")