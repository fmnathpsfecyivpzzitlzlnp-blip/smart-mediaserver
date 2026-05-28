FROM python:3.12-slim

# Устанавливаем системные зависимости, необходимые для компиляции dlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --upgrade pip

# --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ: Чиним setuptools ---
# Устанавливаем и обновляем setuptools, чтобы pkg_resources работал корректно.
# Это современный аналог команды `pip install distribute`.
RUN pip install --upgrade setuptools
# ===============================================

# Копируем файл с нашими зависимостями
COPY requirements.txt .

# Устанавливаем все библиотеки. Теперь они установятся в рабочее окружение.
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код нашего приложения
COPY . .

EXPOSE 5001
CMD ["python", "app.py"]
