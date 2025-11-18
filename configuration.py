import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем конфигурацию из переменных окружения
API_KEY = os.getenv("API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "codestral-latest")
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
MAX_REQUESTS_PER_DAY = int(os.getenv("MAX_REQUESTS_PER_DAY", "10"))
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Стили для генерации контента
TEXT_STYLE = "Дружелюбный и информативный тон"

# Другие настройки
user_requests = {}
