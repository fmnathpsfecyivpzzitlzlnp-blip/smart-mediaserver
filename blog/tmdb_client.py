import re
import requests
from django.conf import settings


def clean_filename(filename):
    """Мощная очистка имени файла для поиска."""
    # 1. Оставляем только имя файла
    filename = filename.replace('\\', '/').split('/')[-1]

    # 2. Убираем расширение
    name = filename.rsplit('.', 1)[0]

    # 3. Заменяем разделители на пробелы
    name = re.sub(r'[\.\_\-]', ' ', name)

    # 4. Ищем год (4 цифры от 1900 до 2099)
    # Это самый надежный способ: берем всё, что ДО года
    match_year = re.search(r'\b(19|20)\d{2}\b', name)

    if match_year:
        year_val = match_year.group(0)
        start_pos = match_year.start()
        # Отрезаем всё после начала года (Fly Me To The Moon 2024... -> Fly Me To The Moon)
        clean_name = name[:start_pos]

        # Если имя вдруг стало пустым (например, файл называется "2024.avi"), вернем как было
        if not clean_name.strip():
            return name

        print(f"🧹 (Год найден {year_val}): '{name}' -> '{clean_name.strip()}'")
        return clean_name.strip()

    # 5. Если года нет, чистим мусор вручную
    junk = [
        r'\[.*?\]', r'\(.*?\)',
        r'www\.[a-zA-Z0-9-]+\.[a-z]+',
        r'\b(avi|mp4|mkv|mov|bdrip|dvdrip|web-dl|web-dlrip|h264|x264|1080p|720p|4k|hdr|rip)\b',
        r'\b(rus|eng|dub|dt|ua|ru)\b'  # Добавили ваши теги
    ]
    for pattern in junk:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)

    result = name.strip()
    print(f"🧹 (Без года): '{filename}' -> '{result}'")
    return result


def search_movie(query):
    """Ищет фильм в TMDb API."""
    if not getattr(settings, 'TMDB_API_KEY', None):
        print("❌ ОШИБКА: TMDB_API_KEY не найден в settings.py")
        return None

    clean_query = clean_filename(query)

    # Если имя пустое после чистки, ищем как есть
    if not clean_query:
        clean_query = query

    url = "https://api.themoviedb.org/3/search/movie"
    params = {
        'api_key': settings.TMDB_API_KEY,
        'query': clean_query,
        'language': 'ru-RU',
        'page': 1
    }

    try:
        print(f"🔍 Запрос в TMDb: '{clean_query}'...")  # ЛОГ
        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 401:
            print("❌ ОШИБКА: Неверный API Key TMDb!")
            return None

        response.raise_for_status()
        data = response.json()

        results = data.get('results', [])
        print(f"✅ Найдено результатов: {len(results)}")  # ЛОГ

        if results:
            first = results[0]
            print(f"   -> Выбран: {first.get('title')} ({first.get('release_date')})")
            return first
        else:
            print("   -> Ничего не найдено :(")

    except Exception as e:
        print(f"❌ Ошибка запроса: {e}")

    return None


def get_movie_details(tmdb_id):
    # (эту функцию можно оставить старой, она пока не критична)
    pass