# Використовуємо офіційний легкий образ Python
FROM python:3.10-slim

# Встановлюємо робочу директорію
WORKDIR /app

# Копіюємо файли залежностей
COPY requirements.txt .

# Встановлюємо залежності
RUN pip install --no-cache-dir -r requirements.txt

# Копіюємо весь код
COPY . .

# Створюємо папку для даних (якщо буде використовуватися Persistent Disk)
RUN mkdir -p /data

# Задаємо змінні оточення за замовчуванням
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/data

# Команда запуску
CMD ["python", "app.py", "--stream"]
