import json
import random
import sqlite3
from aiogram import Dispatcher, Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
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

# Загружаем квизы из JSON-файла
def load_quiz_data():
    try:
        with open("quiz_data.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("quiz_questions", [])
    except FileNotFoundError:
        print("❌ Файл quiz_data.json не найден")
        return []
    except json.JSONDecodeError:
        print("❌ Ошибка чтения quiz_data.json")
        return []

# Функция для создания квиза
async def create_quiz_question():
    quiz_data = load_quiz_data()
    words = load_words()
    
    if not quiz_data:
        # Fallback: создаем простой квиз из слов
        return await create_fallback_quiz(words)
    
    # Выбираем случайный квиз из подготовленных данных
    quiz_item = random.choice(quiz_data)
    
    # Создаем список вариантов и перемешиваем
    options = [quiz_item["word"]] + quiz_item["wrong_options"]
    random.shuffle(options)
    
    # Находим индекс правильного ответа
    correct_index = options.index(quiz_item["word"])
    
    return {
        "sentence": quiz_item["sentence"],
        "original_sentence": quiz_item["original_sentence"],
        "options": options,
        "correct_index": correct_index,
        "correct_word": quiz_item["word"],
        "translation": quiz_item["translation"]
    }

# Функция-запасной вариант если нет файла с квизами
async def create_fallback_quiz(words):
    correct_word_data = random.choice(words)
    correct_word = correct_word_data["word"]
    translation = correct_word_data["translation"]
    
    # Простое предложение-заготовка
    sentence = f"나는 ______을(를) 좋아해요."
    original_sentence = f"나는 {correct_word}을(를) 좋아해요."
    
    # Выбираем 3 неправильных варианта
    wrong_words = []
    while len(wrong_words) < 3:
        wrong_word_data = random.choice(words)
        if wrong_word_data["word"] != correct_word and wrong_word_data["word"] not in wrong_words:
            wrong_words.append(wrong_word_data["word"])
    
    # Создаем список вариантов и перемешиваем
    options = [correct_word] + wrong_words
    random.shuffle(options)
    correct_index = options.index(correct_word)
    
    return {
        "sentence": sentence,
        "original_sentence": original_sentence,
        "options": options,
        "correct_index": correct_index,
        "correct_word": correct_word,
        "translation": translation
    }

# Функция отправки квиза (остается без изменений)
async def send_quiz():
    print("🔄 Начало отправки квиза...")
    
    quiz = await create_quiz_question()
    
    # Получаем список всех пользователей из базы данных
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
        print(f"👥 Найдено пользователей: {len(users)}")
    except sqlite3.Error as e:
        print(f"❌ Ошибка при запросе пользователей: {e}")
        return

    # Отправляем квиз каждому пользователю
    successful_sends = 0
    for user in users:
        user_id = user[0]
        try:
            # Создаем инлайн-кнопки с вариантами ответов
            # Используем короткий формат callback_data без original_sentence
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text=option, 
                    callback_data=f"quiz_{user_id}_{quiz['correct_index']}_{i}_{quiz['correct_word']}"
                )]
                for i, option in enumerate(quiz["options"])
            ])
            
            message_text = (
                f"<b>Ежедневный квиз</b>\n\n"
                f"📝 <b>Заполните пропуск:</b>\n\n"
                f"{quiz['sentence']}\n"
                f"<i>({quiz['translation']})</i>"
            )
            
            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
            # Сохраняем original_sentence в базу данных
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO active_quizzes (user_id, correct_word, original_sentence)
                    VALUES (?, ?, ?)
                """, (user_id, quiz['correct_word'], quiz['original_sentence']))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"⚠️ Ошибка сохранения квиза в БД для {user_id}: {e}")
            
            successful_sends += 1
            print(f"✅ Квиз отправлен пользователю {user_id}")
        except Exception as e:
            print(f"❌ Ошибка отправки квиза пользователю {user_id}: {e}")

    print(f"📊 Итог: успешно отправлено {successful_sends}/{len(users)} пользователям")

# Остальные функции остаются без изменений
async def send_word():
    words = load_words()
    word_data = random.choice(words)
    word, translation, image_path, example = (
        word_data["word"],
        word_data["translation"],
        word_data["image"],
        word_data.get("example", "Пример отсутствует."),
    )

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"Ошибка при запросе пользователей: {e}")
        return

    for user in users:
        user_id = user[0]
        try:
            photo = FSInputFile(image_path)
            caption = (
                f"<b>Слово дня:</b> {word}\n"
                f"<b>Перевод:</b> {translation}\n"
                f"✏️ <b>Пример:</b> {example}"
            )
            await bot.send_photo(chat_id=user_id, photo=photo, caption=caption, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки фото пользователю {user_id}: {e}")

def schedule_daily_word(scheduler=None, hour=9, minute=0):
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    trigger = CronTrigger(hour=hour, minute=minute, second=0)
    scheduler.add_job(send_word, trigger)
    print(f"📅 Отправка слова дня в {hour:02d}:{minute:02d} каждый день")
    return scheduler

def schedule_daily_quiz(scheduler=None, test_mode=False, hour=19, minute=0):
    if scheduler is None:
        scheduler = AsyncIOScheduler()
    if test_mode:
        trigger = IntervalTrigger(minutes=1)
        print("⚠️ ТЕСТОВЫЙ РЕЖИМ: отправка квиза каждую минуту")
    else:
        trigger = CronTrigger(hour=hour, minute=minute, second=0)
        print(f"📅 Отправка квиза в {hour:02d}:{minute:02d} каждый день")
    
    scheduler.add_job(send_quiz, trigger)
    return scheduler

