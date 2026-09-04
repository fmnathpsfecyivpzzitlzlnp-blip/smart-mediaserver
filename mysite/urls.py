# mysite/urls.py
"""
URL configuration for mysite project...
"""
from django.contrib import admin
from django.urls import path, include  # <-- Добавьте include, если его нет
from django.conf import settings
from django.conf.urls.static import static

# УДАЛИТЕ СТРОКУ 'from . import views'

urlpatterns = [
    path('admin/', admin.site.urls),
    # Эта строка говорит: "все URL-адреса, кроме /admin/,
    # ищи в файле blog/urls.py"
    # Это добавит URL'ы типа /accounts/login/, /accounts/logout/ и т.д.
    path('tinymce/', include('tinymce.urls')), # <--- ДОБАВИТЬ ЭТУ СТРОКУ
    path('accounts/', include('django.contrib.auth.urls')),
    path('i18n/', include('django.conf.urls.i18n')),
    path('', include('blog.urls')),
]

# Этот блок добавляет раздачу медиафайлов в режиме отладки (DEBUG=True),
# чтобы вам не приходилось каждый раз запускать Nginx для локальной разработки.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

