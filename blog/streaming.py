import os
import shutil
import subprocess
import time
from pathlib import Path
from django.conf import settings
from .models import Video

class HLSManager:
    # Папка для временных файлов сессий просмотра
    HLS_DIR = Path(settings.MEDIA_ROOT) / 'hls_sessions'

    @classmethod
    def start_session(cls, video_id, audio_idx=0):
        video = Video.objects.get(id=video_id)
        session_id = f"session_{video_id}_a{audio_idx}"
        session_dir = cls.HLS_DIR / session_id
        playlist_path = session_dir / 'index.m3u8'

        # Если сессия уже активна, просто возвращаем её ID
        if playlist_path.exists():
            return session_id

        # Подготавливаем чистую директорию
        if session_dir.exists():
            shutil.rmtree(session_dir)
        session_dir.mkdir(parents=True, exist_ok=True)

        source_path = str(video.movie_path)

        # Боевая команда FFmpeg (Транскодинг на лету)
        cmd = [
            'ffmpeg',
            '-i', source_path,
            '-map', '0:v:0',             # Берем первую видеодорожку
            '-map', f'0:a:{audio_idx}',  # Берем выбранную аудиодорожку
            '-c:v', 'libx264',           # Универсальный кодек для всех браузеров
            '-preset', 'ultrafast',      # Максимальная скорость кодирования
            '-crf', '23',                # Баланс качества и сжатия
            '-c:a', 'aac', '-b:a', '192k',
            '-f', 'hls',                 # Формат Apple HLS
            '-hls_time', '5',            # Кусочки по 5 секунд
            '-hls_list_size', '0',       # Хранить весь плейлист целиком
            '-hls_segment_filename', str(session_dir / 'seg_%03d.ts'),
            str(playlist_path)
        ]

        # Запускаем FFmpeg как независимый фоновый процесс
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Ждем максимум 10 секунд, пока сгенерируется первый кусочек и плейлист
        for _ in range(10):
            if playlist_path.exists():
                break
            time.sleep(1)

        return session_id