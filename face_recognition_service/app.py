import os
import glob
import face_recognition
import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS  # Импортируем CORS для решения проблемы с кросс-доменными запросами
import cv2

# Инициализируем Flask приложение
app = Flask(__name__)

# --- ВАЖНОЕ ИСПРАВЛЕНИЕ: CORS ---
# Эта строка разрешает браузеру (например, вашему сайту на http://localhost)
# делать запросы к этому Flask-сервису, работающему на http://localhost:5001.
# '*' означает "разрешить с любого источника".
CORS(app)

# --- Глобальные переменные для хранения обученных лиц ---
# Мы будем загружать в них данные один раз при старте сервера.
known_face_encodings = []
known_face_names = []
print("Flask-сервис запускается...")


def load_known_faces():
    """
    Эта функция проходит по всем файлам в папке 'known_faces',
    находит на них лица, кодирует их и сохраняет в память.
    """
    global known_face_encodings, known_face_names
    # Очищаем списки на случай перезапуска
    known_face_encodings = []
    known_face_names = []

    print("--- Начало загрузки известных лиц ---")

    # Проходим по всем файлам с любым расширением в папке known_faces
    for image_path in glob.glob(os.path.join("known_faces", "*.*")):
        try:
            # Получаем имя человека из имени файла (например, "dev-1.jpg" -> "dev")
            basename = os.path.basename(image_path)
            name = basename.split('-')[0]

            # Загружаем изображение и ищем на нем лица
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)

            # Если лицо (или лица) найдено, берем первую кодировку
            if encodings:
                known_face_encodings.append(encodings[0])
                known_face_names.append(name)
                print(f" > Успешно загружен файл '{basename}' для '{name}'")
            else:
                print(f" > Предупреждение: Лица на изображении '{basename}' не найдены.")

        except Exception as e:
            print(f"!!! ОШИБКА при обработке файла {image_path}: {e}")

    # Используем 'set' для подсчета только уникальных имен
    unique_names = set(known_face_names)
    print(
        f"--- Загрузка завершена. Всего кодировок: {len(known_face_encodings)}. Уникальных людей: {len(unique_names)} ---")


@app.route('/recognize', methods=['POST'])
def recognize_face():
    """
    Основная функция API. Она принимает изображение в POST-запросе,
    распознает на нем лица и возвращает список имен в формате JSON.
    """
    if 'image' not in request.files:
        return jsonify({"error": "В запросе отсутствует файл изображения."}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "Файл не выбран."}), 400

    try:
        # Читаем изображение из тела запроса и преобразуем его в формат,
        # понятный для библиотеки face_recognition
        in_memory_file = file.read()
        nparr = np.frombuffer(in_memory_file, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        # Находим все лица и их кодировки на полученном кадре
        face_locations = face_recognition.face_locations(frame)
        face_encodings = face_recognition.face_encodings(frame, face_locations)

        recognized_names = []
        # Проходим по каждому найденному на кадре лицу
        for face_encoding in face_encodings:
            # Сравниваем найденное лицо со всеми известными нам лицами
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding)
            name = "Unknown"

            # Находим наиболее похожее лицо из известных
            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_face_names[best_match_index]

            recognized_names.append(name)

        # Отправляем успешный ответ со списком распознанных имен
        return jsonify({"names": recognized_names})

    except Exception as e:
        # В случае любой другой ошибки отправляем ее описание
        return jsonify({"error": str(e)}), 500


# Эта часть выполняется при запуске скрипта напрямую (python app.py)
if __name__ == '__main__':
    load_known_faces()  # Сначала загружаем лица в память
    # Затем запускаем веб-сервер, доступный из других контейнеров
    app.run(host='0.0.0.0', port=5001, debug=False)