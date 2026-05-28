# blog/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # =========================================================================
    # 1. ГЛАВНЫЕ СТРАНИЦЫ И СЕРВИСЫ
    # =========================================================================
    path('', views.dashboard_view, name='dashboard_root'),  # Дашборд (Главная по умолчанию)
    path('cinema/', views.cinema_list, name='cinema_list'),  # Кинотеатр переехал на /cinema/
    path('dashboard/', views.dashboard_view, name='dashboard'), # Старая ссылка на Дашборд (можно оставить для совместимости)

    path('search/', views.global_search, name='global_search'),  # Глобальный поиск системы
    path('signup/', views.signup, name='signup'),  # Регистрация
    path('serve-indexed-file/<int:pk>/', views.serve_indexed_file, name='serve_indexed_file'),
    # Отдача проиндексированных файлов

    # =========================================================================
    # 2. МЕДИАТЕКА (КИНОТЕАТР, СЕРИАЛЫ, КЛИПЫ)
    # =========================================================================
    path('movie/<int:pk>/', views.movie_detail, name='movie_detail'),  # Детали фильма/урока
    path('shows/', views.tv_show_list, name='tv_show_list'),  # Список сериалов
    path('shows/<int:pk>/', views.tv_show_detail, name='tv_show_detail'),  # Детали сериала
    path('clips/', views.clip_list, name='clip_list'),  # Список клипов

    # =========================================================================
    # 3. ЦЕНТР ОБУЧЕНИЯ (LEARNING MODULE)
    # =========================================================================
    path('learning/', views.learning_root, name='learning_root'),  # Корень обучения (Категории)

    # Специфичные пути для IndexedItem (должны быть выше общих слагов категорий)
    path('learning/files/<slug:category_slug>/', views.learning_category_view, name='learning_indexed_files_root'),
    path('learning/files/<slug:category_slug>/<path:path>/', views.learning_category_view,
         name='learning_indexed_files_path'),

    path('learning/course/<slug:course_slug>/', views.course_detail, name='course_detail'),  # Детали курса
    path('learning/watch/<int:file_id>/', views.course_file_player, name='course_file_player'),  # Плеер студента
    path('learning/stream/<int:file_id>/', views.serve_course_file, name='serve_course_file'),
    # Стрим файла через Nginx
    path('learning/<slug:category_slug>/tag/<slug:tag_slug>/', views.courses_by_tag, name='courses_by_tag'),
    # Фильтр по тегу в категории
    path('learning/<slug:category_slug>/', views.learning_category_detail, name='learning_category_detail'),
    # Страница категории

    # =========================================================================
    # 4. ФАЙЛОВЫЙ ПРОВОДНИК (FILE EXPLORER)
    # =========================================================================
    # Скачивание/Просмотр файла (Самое важное — ВВЕРХУ секции)
    path('explorer/file/<path:path>/', views.serve_file_from_explorer, name='serve_file_from_explorer'),
    path('explorer/', views.file_explorer_view, name='file_explorer_root'),  # Корень ("Мой компьютер")
    path('explorer/<path:path>/', views.file_explorer_view, name='file_explorer_path'),  # Навигация по папкам дисков

    # Стриминг видео напрямую из проводника
    path('stream/video/<int:video_id>/', views.serve_video_stream, name='serve_video_stream'),

    # Старая система браузера локаций (сохранена для совместимости)
    path('locations/', views.location_list_view, name='location_list'),
    path('browser/<slug:location_slug>/', views.file_browser_view, name='file_browser_root'),
    path('browser/<slug:location_slug>/<path:path>/', views.file_browser_view, name='file_browser_path'),

    # =========================================================================
    # 5. ОРГАНАЙЗЕР И ИНСТРУМЕНТЫ ВРЕМЕНИ
    # =========================================================================
    path('organizer/', views.organizer_view, name='organizer'),  # Органайзер (Задачи/Проекты)
    path('organizer/add_project/', views.add_project, name='add_project'),  # Быстрое добавление проекта
    path('clock/', views.clock_view, name='clock'),  # Будильники и таймеры
    path('clock/item/<int:pk>/toggle/', views.toggle_clock_item, name='toggle_clock_item'),  # Вкл/Выкл будильника
    path('clock/item/<int:pk>/delete/', views.delete_clock_item, name='delete_clock_item'),  # Удаление будильника

    # =========================================================================
    # 6. БИБЛИОТЕКА ТЕГОВ
    # =========================================================================
    path('tags/', views.tag_library, name='tag_library'),  # Библиотека тегов и категорий
    path('tags/<str:tag_slug>/', views.indexed_files_by_tag, name='files_by_tag'),  # Файлы по определенному тегу
    path('movie-tags/<slug:tag_slug>/', views.videos_by_tag, name='videos_by_tag'),  # Видео по определенному тегу

    # =========================================================================
    # 7. ДЕТСКИЙ МОДУЛЬ "DO IT!" И ГЕЙМИФИКАЦИЯ
    # =========================================================================
    path('do-it/', views.do_it_welcome_view, name='do_it_welcome'),  # Главный экран ребенка
    path('child-tasks/', views.child_tasks_view, name='child_tasks'),  # Список детских задач
    path('rewards/', views.reward_store, name='reward_store'),  # Магазин наград JARVIS
    path('habits/library/', views.habits_library_view, name='habits_library'),  # Готовая библиотека привычек
    path('tracker/today/', views.tracker_today_view, name='tracker_today'),  # Интерфейс трекера привычек "Сегодня"

    # Меню родителей
    path('parent-menu/', views.parent_dashboard_view, name='parent_dashboard'),  # Панель родителей
    path('parent-menu/setup-tasks/', views.setup_tasks_view, name='setup_tasks'),  # Настройка привычек/задач
    path('parent-menu/setup-tasks/custom/', views.custom_task_view, name='custom_task'),  # Кастомные задачи
    path('parent-menu/statistics/', views.child_statistics_view, name='child_statistics'),  # Статистика детей
    path('parent-menu/add-reward/', views.add_reward_view, name='add_reward'),  # Добавление наград в магазин
    path('parent-menu/add-child/', views.add_child_view, name='add_child'),  # Управление профилями детей

    # =========================================================================
    # 8. СИСТЕМНЫЕ ИНСТРУМЕНТЫ (АДМИН-ПАНЕЛЬ СЕРВЕРА)
    # =========================================================================
    path('upload/', views.upload_video, name='upload_video'),  # Загрузка видео через браузер
    path('logs/', views.processing_logs, name='processing_logs'),  # Логи конвертации видео
    path('staff/tools/', views.admin_tools_view, name='admin_tools'),  # Админские инструменты сервера

    # =========================================================================
    # 9. ЧИСТЫЙ API МАРШРУТИЗАТОР (AJAX / ВНУТРЕННИЕ ЗАПРОСЫ ТЕХНОЛОГИЙ)
    # =========================================================================
    # Аутентификация
    path('api/face-login/', views.face_login_api, name='face_login_api'),

    # Видео, плеер и прогресс
    path('api/notes/add/', views.add_note, name='add_note'),
    path('api/videos/<int:pk>/progress/', views.update_progress_api, name='update_progress_api'),
    path('api/videos/<int:pk>/status/', views.get_movie_status, name='get_movie_status'),
    path('api/videos/<int:pk>/schedule/', views.schedule_video_view, name='schedule_video_api'),
    path('api/video/<int:pk>/toggle-list/', views.toggle_video_list, name='toggle_video_list'),
    path('api/track_progress/', views.track_video_progress, name='track_video_progress'),

    # Управление тегами через API
    path('api/videos/<int:video_pk>/tags/add/', views.add_tag_to_movie_api, name='add_tag_to_movie_api'),
    path('api/videos/<int:video_pk>/tags/remove/', views.remove_tag_from_movie_api, name='remove_tag_from_movie_api'),
    path('api/tags/create/', views.create_tag_api, name='create_tag_api'),
    path('api/tags/manage/', views.manage_tag_api, name='manage_tag_api_root'),
    path('api/tags/manage/<int:pk>/', views.manage_tag_api, name='manage_tag_api_detail'),

    # Органайзер и календарь задач
    path('api/tasks/add/', views.add_task, name='add_task'),
    path('api/tasks/<int:pk>/', views.task_detail_api, name='task_detail_api'),
    path('api/tasks/<int:pk>/toggle/', views.toggle_task, name='toggle_task'),
    path('api/tasks/<int:pk>/delete/', views.delete_task_api, name='delete_task_api'),
    path('api/tasks/reorder/', views.reorder_tasks, name='reorder_tasks'),
    path('api/tasks/check-notifications/', views.check_notifications_api, name='check_notifications_api'),
    path('api/templates/apply/', views.apply_project_template, name='apply_template'),
    path('api/projects/<int:pk>/delete/', views.delete_project_api, name='delete_project_api'),
    path('api/calendar/events/', views.get_tasks_json, name='calendar_events'),

    # Трекер привычек и событий
    path('api/tracker/add/', views.add_tracker_event, name='add_tracker_event'),
    path('api/tracker/category/add/', views.add_event_type, name='add_event_type'),
    path('api/tracker/category/<int:pk>/delete/', views.delete_event_type, name='delete_event_type'),
    path('api/tracker/event/<int:pk>/delete/', views.delete_tracker_event_api, name='delete_tracker_event'),
    path('api/tracker/toggle/<int:type_id>/', views.toggle_habit_checkbox_api, name='toggle_habit_checkbox'),

    # Модуль обучения и планирования
    path('api/course/<slug:course_slug>/plan/', views.create_study_plan_api, name='create_study_plan_api'),
    path('api/course/<int:course_id>/delete/', views.delete_course_api, name='delete_course_api'),
    path('api/course/<int:course_id>/move/', views.move_course_api, name='move_course_api'),
    path('api/learning/progress/<int:file_id>/', views.update_course_progress_api, name='update_course_progress_api'),

    # Проводник (File Explorer Actions)
    path('api/explorer/telegram/', views.explorer_send_telegram, name='explorer_send_telegram'),
    path('api/explorer/create_course/', views.explorer_create_course, name='explorer_create_course'),
    path('api/delete_item/', views.delete_file_api, name='delete_file_api'),

    # Детские задачи и награды
    path('api/child-tasks/add/', views.add_child_task_api, name='add_child_task_api'),
    path('api/child-tasks/<int:task_id>/toggle/', views.toggle_child_task_api, name='toggle_child_task_api'),
    path('api/rewards/add-custom/', views.save_reward_api, name='save_reward_api'),
    path('api/habits/activate/', views.activate_habit_api, name='activate_habit_api'),
    path('api/add-child/', views.add_child_api, name='add_child_api'),
    path('api/delete-child/<int:child_id>/', views.delete_child_api, name='delete_child_api'),
    path('api/rewards/buy/<int:item_id>/', views.buy_reward, name='buy_reward_api_deprecated'),
    # Дублирующий роут сохранен
    path('api/buy-reward/', views.buy_reward_api, name='buy_reward_api'),

    # Служебные API Celery, логов и поиска
    path('api/search/delete/<int:history_id>/', views.delete_search_history, name='delete_search_history'),
    path('api/run-scanner/', views.run_scanner_api, name='run_scanner_api'),
    path('api/logs/', views.get_celery_logs, name='get_celery_logs'),
    path('api/logs/live/', views.get_live_logs, name='get_live_logs'),
    path('api/purge-tasks/', views.purge_tasks_api, name='purge_tasks_api'),

    # Инструменты тестирования (Скрытые)
    path('api/test-bot/', views.test_telegram_bot_token, name='test_telegram_bot_token'),
    path('sandbox/styles/', views.style_test_page, name='style_test_page'),
]