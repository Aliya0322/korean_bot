import random
import sqlite3
import os
from aiogram import Dispatcher, Bot
from aiogram.types import FSInputFile
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from mistralai import Mistral
from configuration import BOT_TOKEN, API_KEY, MODEL_NAME, TEXT_STYLE, IMAGE_STYLE
from image_generator import ImageGenerator


bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()
image_generator = ImageGenerator()

# Функция для подключения к базе данных
def get_db_connection():
    return sqlite3.connect("korean_bot.db")

# Загружаем список слов из TXT-файла
def load_words():
    """
    Загружает слова из текстового файла korean_english_pairs.txt.
    Формат файла: каждая строка содержит "номер слово - английский_перевод"
    Пример:
        1 그리고 - And
        3 그래서 - So/therefore
        4 막혀요 - Traffic jam
    """
    words = []
    try:
        with open("korean_english_pairs.txt", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):  # Пропускаем пустые строки и комментарии
                    continue
                
                # Парсим строку: номер слово - английский_перевод
                if " - " not in line:
                    continue
                
                parts = line.split(" - ", 1)
                if len(parts) != 2:
                    continue
                
                # Извлекаем слово (убираем номер в начале, если есть)
                word_part = parts[0].strip()
                english_translation = parts[1].strip()
                
                # Убираем номер в начале (если есть)
                word_part_parts = word_part.split(None, 1)
                if len(word_part_parts) > 1 and word_part_parts[0].isdigit():
                    word = word_part_parts[1].strip()
                else:
                    word = word_part
                
                if word and english_translation:
                    # Сохраняем слово и английский перевод (будет переведен позже)
                    words.append({"word": word, "english_translation": english_translation})
    except FileNotFoundError:
        print("Ошибка: файл korean_english_pairs.txt не найден!")
        return []
    except Exception as e:
        print(f"Ошибка при чтении korean_english_pairs.txt: {e}")
        return []
    
    return words

# Функция для перевода с английского на русский через LLM
async def translate_to_russian(english_text: str) -> str:
    """
    Переводит английский текст на русский язык используя LLM.
    
    Args:
        english_text: Английский текст для перевода
        
    Returns:
        str: Русский перевод
    """
    # Если есть несколько вариантов через "/", переводим каждый
    if "/" in english_text:
        variants = [v.strip() for v in english_text.split("/")]
        translated_variants = []
        for variant in variants:
            if variant:
                translated = await translate_single_text(variant)
                translated_variants.append(translated)
        return "/".join(translated_variants) if translated_variants else english_text
    else:
        return await translate_single_text(english_text)

async def translate_single_text(english_text: str) -> str:
    """
    Переводит один английский текст на русский.
    """
    prompt = (
        f"Переведи следующее английское слово или фразу на русский язык. "
        f"Ответь только переводом, без дополнительных пояснений. "
        f"Если это фраза, сохрани структуру.\n\n"
        f"Английский текст: {english_text}"
    )
    
    try:
        client = Mistral(api_key=API_KEY)
        response = await client.chat.stream_async(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Переведи: {english_text}"},
            ],
        )
        result = ""
        async for chunk in response:
            delta_content = chunk.data.choices[0].delta.content
            if delta_content:
                result += delta_content
        
        return result.strip() if result.strip() else english_text
    except Exception as e:
        print(f"Ошибка при переводе '{english_text}': {e}")
        return english_text  # Возвращаем оригинал при ошибке

# Функция для получения примера от LLM
async def get_word_example(word: str, translation: str) -> str:
    """
    Получает пример использования слова от LLM.
    
    Args:
        word: Корейское слово
        translation: Перевод слова на русский
        
    Returns:
        str: Пример использования слова на корейском языке (без перевода)
    """
    prompt = (
        f"Ты помощник для изучения корейского языка. Используй {TEXT_STYLE}. "
        f"Для корейского слова '{word}' (перевод: '{translation}') предоставь:\n"
        f"Один простой пример использования на корейском языке.\n\n"
        f"Формат ответа: только корейский текст, без перевода и дополнительных пояснений.\n"
        f"Пример должен быть естественным для носителя корейского языка и понятным для начального уровня изучения корейского языка.\n"
        f"Ответ должен начинаться сразу с примера, без слова 'Пример:' или других префиксов."
    )
    
    try:
        client = Mistral(api_key=API_KEY)
        response = await client.chat.stream_async(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Слово: {word}"},
            ],
        )
        result = ""
        async for chunk in response:
            delta_content = chunk.data.choices[0].delta.content
            if delta_content:
                result += delta_content
        
        if not result or "Ошибка" in result:
            return f"{word} 예시"
        
        # Очищаем результат от лишних префиксов
        result = result.strip()
        if "Пример:" in result:
            result = result.split("Пример:", 1)[-1].strip()
        if "пример:" in result.lower():
            result = result.split(":", 1)[-1].strip()
        
        # Убираем перевод в скобках, если есть
        if "(" in result and ")" in result:
            # Удаляем всё что в скобках (переводы)
            import re
            result = re.sub(r'\([^)]*\)', '', result).strip()
        
        # Убираем перевод после дефиса, если есть (например: "사랑해요 - I love you")
        if " - " in result:
            result = result.split(" - ")[0].strip()
        
        return result if result else f"{word} 예시"
    except Exception as e:
        print(f"Ошибка при получении примера от LLM: {e}")
        return f"{word} 예시"

# Функция для генерации промпта для изображения на основе английского перевода
async def generate_image_prompt(word: str, english_translation: str, russian_translation: str, example: str) -> str:
    """
    Генерирует промпт для изображения на основе английского перевода слова.
    Использует английский перевод, так как модели генерации изображений лучше работают с английским языком.
    
    Args:
        word: Корейское слово
        english_translation: Перевод слова на английский
        russian_translation: Перевод слова на русский (для контекста)
        example: Пример использования слова на корейском языке
        
    Returns:
        str: Промпт для генерации изображения на английском языке
    """
    prompt = (
        f"Describe the image for the word '{english_translation}'"
        f"The image should be realistic and safe to view."
    )
    
    try:
        client = Mistral(api_key=API_KEY)
        response = await client.chat.stream_async(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Korean word: '{word}'\nEnglish translation: '{english_translation}'\nRussian translation: '{russian_translation}'\nExample of usage (DO NOT describe image for example!): '{example}'\n\nDescribe the image for THE WORD ITSELF '{english_translation}' in English:"},
            ],
        )
        result = ""
        async for chunk in response:
            delta_content = chunk.data.choices[0].delta.content
            if delta_content:
                result += delta_content
        
        if result.strip():
            # Добавляем стиль к сгенерированному описанию и требования без людей и религиозных тем
            return f"{result.strip()}, no people, no faces, no human figures, no religious themes, no religious symbols, {IMAGE_STYLE}"
        else:
            # Если LLM не ответил, используем просто английский перевод с требованиями
            return f"{english_translation}, no people, no faces, no human figures, no religious themes, no religious symbols, {IMAGE_STYLE}"
    except Exception as e:
        print(f"Ошибка при генерации промпта для изображения: {e}")
        # При ошибке используем просто английский перевод с требованиями
        return f"{english_translation}, no people, no faces, no human figures, no religious themes, no religious symbols, {IMAGE_STYLE}"

# Функция отправки слова дня
async def send_word():
    words = load_words()
    if not words:
        print("Ошибка: список слов пуст!")
        return
        
    word_data = random.choice(words)
    word = word_data["word"]
    english_translation = word_data["english_translation"]
    
    # Переводим английский перевод на русский
    translation = await translate_to_russian(english_translation)
    
    # Получаем пример от LLM (без определения)
    example = await get_word_example(word, translation)
    
    # Генерируем промпт для изображения на основе английского перевода слова
    image_prompt = await generate_image_prompt(word, english_translation, translation, example)
    temp_image_path = f"temp_images/{word}_{random.randint(1000, 9999)}.png"
    
    try:
        # Создаем директорию для временных изображений
        os.makedirs("temp_images", exist_ok=True)
        
        # Генерируем изображение
        print(f"🎨 Генерация изображения для слова '{word}' ({translation})...")
        print(f"📝 Промпт: {image_prompt[:100]}...")
        image_generator.generate(image_prompt, temp_image_path)
        
        # Проверяем, что файл создан и не пустой
        if os.path.exists(temp_image_path) and os.path.getsize(temp_image_path) > 0:
            print(f"✅ Изображение успешно сгенерировано: {temp_image_path}")
        else:
            print(f"❌ Изображение не создано или пустое: {temp_image_path}")
            temp_image_path = None
    except Exception as e:
        print(f"❌ Ошибка при генерации изображения: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        temp_image_path = None

    # Получаем список всех пользователей из базы данных
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        conn.close()
    except sqlite3.Error as e:
        print(f"Ошибка при запросе пользователей: {e}")
        # Удаляем временное изображение при ошибке
        if temp_image_path and os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
            except:
                pass
        return

    # Отправляем слово дня каждому пользователю
    for user in users:
        user_id = user[0]
        try:
            caption = (
                f"📖 <b>Слово дня:</b> {word}\n"
                f"🔹 <b>Перевод:</b> {translation}\n\n"
                f"✏️ <b>Пример:</b> {example}"
            )
            
            if temp_image_path and os.path.exists(temp_image_path):
                photo = FSInputFile(temp_image_path)
                await bot.send_photo(chat_id=user_id, photo=photo, caption=caption, parse_mode="HTML")
            else:
                # Если изображение не сгенерировалось, отправляем только текст
                await bot.send_message(chat_id=user_id, text=caption, parse_mode="HTML")
        except Exception as e:
            print(f"Ошибка отправки фото пользователю {user_id}: {e}")

    # Удаляем временное изображение после отправки
    if temp_image_path and os.path.exists(temp_image_path):
        try:
            os.remove(temp_image_path)
        except Exception as e:
            print(f"Ошибка при удалении временного файла: {e}")

def schedule_daily_word(test_mode=False, hour=9, minute=0):
    """
    Планирует отправку слова дня.
    
    Args:
        test_mode: Если True, отправляет слово каждую минуту (для тестирования)
        hour: Час отправки (используется если test_mode=False)
        minute: Минута отправки (используется если test_mode=False)
    """
    scheduler = AsyncIOScheduler()
    if test_mode:
        # Для тестирования: отправка каждую минуту
        trigger = IntervalTrigger(minutes=1)
        print("⚠️ ТЕСТОВЫЙ РЕЖИМ: отправка слова каждую минуту")
    else:
        # Продакшн: отправка в указанное время каждый день
        trigger = CronTrigger(hour=hour, minute=minute, second=0)
        print(f"📅 Режим продакшн: отправка слова в {hour:02d}:{minute:02d} каждый день")
    scheduler.add_job(send_word, trigger)
    scheduler.start()
    return scheduler

