import json
import random
import sqlite3
from aiogram import Dispatcher, Bot
from aiogram.types import FSInputFile
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from configuration import BOT_TOKEN


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()

# Функция для подключения к базе данных
def get_db_connection():
    return sqlite3.connect("korean_bot.db")

# Загружаем список слов из JSON-файла
def load_words():
    with open("words.json", "r", encoding="utf-8") as f:
        return json.load(f)

# Функция отправки слова дня
async def send_word():
    words = load_words()
    word_data = random.choice(words)
    word, translation, image_path, example = (
        word_data["word"],
        word_data["translation"],
        word_data["image"],
        word_data.get("example", "Пример отсутствует."),
    )

    # Получаем список всех пользователей из базы данных
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"Ошибка при запросе пользователей: {e}")
        return

    # Отправляем фото со словом дня каждому пользователю
    for user in users:
        user_id = user[0]
        try:
            photo = FSInputFile(image_path)
            caption = (
                f"📖 <b>Слово дня:</b> {word}\n"
                f"🔹 <b>Перевод:</b> {translation}\n"
                f"✏️ <b>Пример:</b> {example}"
            )
            await bot.send_photo(chat_id=user_id, photo=photo, caption=caption, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки фото пользователю {user_id}: {e}")

def schedule_daily_word(hour=9, minute=0):
    scheduler = AsyncIOScheduler()
    trigger = CronTrigger(hour=hour, minute=minute, second=0)
    scheduler.add_job(send_word, trigger)
    scheduler.start()

