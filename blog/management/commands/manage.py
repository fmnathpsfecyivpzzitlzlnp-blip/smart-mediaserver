from django.contrib.auth.models import User
from blog.models import UserProfile, RewardItem

# --- 1. ЗАВОДИМ ПОЛЬЗОВАТЕЛЕЙ ---
# Создаем аккаунт для Лизы (если его еще нет)
liza, created = User.objects.get_or_create(username='Liza')
if created:
    liza.set_password('jarvis123') # Простой пароль для старта
    liza.save()
    print("✅ Пользователь Liza создан!")

# --- 2. НАЧИСЛЯЕМ СТАРТОВЫЙ БАЛАНС ---
# Выдаем всем пользователям (и вам, и Лизе) по 500 монет и 1500 опыта (Сразу 2-й уровень!)
for u in User.objects.all():
    profile, _ = UserProfile.objects.get_or_create(user=u)
    profile.coins += 500
    profile.xp += 1500
    profile.save()
print("💰 Стартовый капитал выдан всем пользователям!")

# --- 3. ЗАПОЛНЯЕМ ВИТРИНУ МАГАЗИНА ---
items = [
    {"title": "📺 30 минут YouTube", "cost": 50, "icon": "bi-youtube", "desc": "Дополнительное время на мультики или любимые каналы."},
    {"title": "🍕 Пицца на ужин", "cost": 200, "icon": "bi-pie-chart-fill", "desc": "Твое право выбрать ужин для всей семьи!"},
    {"title": "🌙 Лечь спать на час позже", "cost": 150, "icon": "bi-moon-stars-fill", "desc": "Официальная отсрочка отбоя на один час."},
    {"title": "🎮 Час видеоигр", "cost": 100, "icon": "bi-controller", "desc": "Дополнительный час за приставкой или компьютером."},
    {"title": "🧸 Новая игрушка", "cost": 1000, "icon": "bi-box2-heart-fill", "desc": "Поход в магазин за любой игрушкой в пределах оговоренного лимита."},
    {"title": "💳 100 рублей на карту", "cost": 100, "icon": "bi-credit-card-fill", "desc": "Реальные карманные деньги на твои расходы."},
    {"title": "🧹 Отгул от уборки", "cost": 120, "icon": "bi-wind", "desc": "Освобождение от одной домашней обязанности на выбор."},
]

for item in items:
    RewardItem.objects.get_or_create(
        title=item["title"],
        defaults={"cost": item["cost"], "icon": item["icon"], "description": item["desc"]}
    )
print("🏪 Магазин JARVIS успешно заполнен!")
quit()