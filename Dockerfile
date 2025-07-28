FROM python:3.11-slim

# 1. Устанавливаем системные зависимости для Chromium
RUN apt-get update && apt-get install -y wget gnupg curl ca-certificates fonts-liberation libasound2 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 \
    libdrm2 libexpat1 libfontconfig1 libgbm1 libgcc1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 \
    libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 \
    libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 lsb-release xdg-utils

# 2. Обновляем pip и ставим Python-зависимости
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# 3. Устанавливаем Playwright и браузеры внутри контейнера
RUN pip install playwright && playwright install chromium

# 4. Копируем код приложения
COPY . .

EXPOSE 8080

# 5. Запускаем uvicorn на правильном порту (Railway сам подставляет $PORT)
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
