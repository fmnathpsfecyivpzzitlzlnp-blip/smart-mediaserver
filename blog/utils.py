# blog/utils.py

import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from django.core.files.base import ContentFile
import subprocess
import json
import os

def generate_cover_image(text, width=400, height=600):
    """
    Генерирует изображение-заглушку с текстом.
    """
    # Создаем пустое изображение (фон)
    img_bg_color = (35, 35, 35)  # Темно-серый
    img = Image.new('RGB', (width, height), color=img_bg_color)
    draw = ImageDraw.Draw(img)

    # Пытаемся загрузить красивый шрифт, если не получится - используем стандартный
    try:
        # Шрифт Arial хорошо подходит, замените на другой если нужно
        # Для Linux/macOS можно попробовать 'DejaVuSans.ttf'
        font = ImageFont.truetype("arial.ttf", size=40)
    except IOError:
        font = ImageFont.load_default()

    # Переносим длинный текст по строкам
    wrapped_text = "\n".join(textwrap.wrap(text, width=18))  # 18 - примерное кол-во символов в строке

    # Рассчитываем позицию текста, чтобы он был по центру
    text_bbox = draw.textbbox((0, 0), wrapped_text, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]

    x = (width - text_width) / 2
    y = (height - text_height) / 2

    # Рисуем текст на изображении
    text_color = (255, 255, 255)  # Белый
    draw.text((x, y), wrapped_text, font=font, fill=text_color, align="center")

    # Сохраняем изображение в буфер в памяти
    buffer = BytesIO()
    img.save(buffer, format='PNG')

    # Возвращаем его как Django ContentFile
    return ContentFile(buffer.getvalue())


def get_video_duration(file_path):
    """
    Возвращает длительность видеофайла в секундах.
    Использует ffprobe. Если не удалось определить — возвращает 0.
    """
    if not os.path.exists(file_path):
        return 0

    try:
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            file_path
        ]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)

        # Пытаемся найти длительность в container format
        duration = float(data.get('format', {}).get('duration', 0))
        return int(duration)
    except (subprocess.CalledProcessError, ValueError, IndexError, KeyError):
        return 0