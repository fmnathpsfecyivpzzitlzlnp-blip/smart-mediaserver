from django.apps import AppConfig


class BlogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'blog'

    def ready(self):
        # 1. АКТИВИРУЕМ СИГНАЛЫ ДЛЯ TELEGRAM И НАГРАД (Добавляем в самое начало ready)
        import blog.signals

        # Импорты должны быть ВНУТРИ метода ready,
        # чтобы избежать циклических зависимостей при запуске
        from django.contrib import admin
        from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
        from django.contrib.auth.models import User
        from .models import UserProfile



        class UserProfileInline(admin.StackedInline):
            model = UserProfile
            can_delete = False
            verbose_name_plural = 'Профиль'

        class UserAdmin(BaseUserAdmin):
            inlines = (UserProfileInline,)

        # Отменяем регистрацию стандартной админки User и регистрируем нашу
        admin.site.unregister(User)
        admin.site.register(User, UserAdmin)