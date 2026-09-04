FROM python:3.12-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libmagic1 \
    gettext \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

RUN pip install --upgrade pip

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 👇 ДОБАВИТЬ ВОТ ЭТИ СТРОКИ ОБЯЗАТЕЛЬНО:
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

COPY . .
