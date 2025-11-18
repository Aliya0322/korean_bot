import asyncio
import random
from aiogram import Dispatcher, F, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from mistralai import Mistral
from datetime import datetime
from db import Database
import logging
logging.basicConfig(level=logging.INFO)

import sqlite3

from scheduler import schedule_daily_word, schedule_daily_quiz



from configuration import BOT_TOKEN, API_KEY, MODEL_NAME, MAX_REQUESTS_PER_DAY, user_requests, ADMIN_ID



# Функция для взаимодействия с Mistral AI
async def get_ai_response(content, prompt):
    try:
        client = Mistral(api_key=API_KEY)

        response = await client.chat.stream_async(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
        )
        result = ""
        async for chunk in response:
            delta_content = chunk.data.choices[0].delta.content
            if delta_content:
                result += delta_content
        return result or "Ошибка: Пустой ответ от модели."
    except Exception as e:
        return f"Произошла ошибка: {e}"

# Создаем экземпляры бота и диспетчера ,session=session
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()
db = Database('korean_bot.db')



# Проверка лимита запросов
def check_request_limit(user_id):
    today = datetime.now().date()

    if user_id not in user_requests:
        user_requests[user_id] = {"count": 0, "date": today}

    # Если дата изменилась, сбрасываем счётчик запросов
    if user_requests[user_id]["date"] != today:
        user_requests[user_id] = {"count": 0, "date": today}

    remaining_requests = MAX_REQUESTS_PER_DAY - user_requests[user_id]["count"]

    if remaining_requests <= 0:
        return "Лимит запросов на сегодня исчерпан.\n\n Попробуйте снова завтра. 👋🏻", False
    return (
        f"Вы можете сделать ещё <b>{remaining_requests} запросов</b> сегодня.\n\n"
        f"<b>Выберите нужный пункт меню, чтобы продолжить 👇🏻</b>",
        True,
    )


# Обновление счётчика запросов
def update_request_count(user_id):
    if user_id in user_requests:
        user_requests[user_id]["count"] += 1


# Создаем главное меню
def create_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Проверка орфографии 🖍"),
                KeyboardButton(text="Подготовка TOPIK"),
            ],
            [
                KeyboardButton(text="Подписаться на наш канал ✅"),
            ],
            [
                KeyboardButton(text="Моя статистика 📊"),
                KeyboardButton(text="Обратная связь 🧡"),
            ],
        ],
        resize_keyboard=True,
    )


# Определяем состояния для FSM
class EssayStates(StatesGroup):
    waiting_for_essay_topic = State()


class SpellCheckStates(StatesGroup):
    waiting_for_text_to_check = State()

class FeedbackStates(StatesGroup):
    waiting_for_user_message = State()

class AdminReplyState(StatesGroup):
    waiting_for_reply = State()


# Команда /start
@dp.message(CommandStart())
async def start_command(message: Message):
    if message.chat.type == 'private':
        if not db.user_exists(message.from_user.id):
            db.add_user(message.from_user.id)
        await message.answer(
        "안녕하세요!\n\nМеня зовут <b>Lingvo</b>, и я ваш помощник в изучении корейского языка.\n\n"
        "Я помогу вам:\n"
        "• Проверить орфографию корейских текстов\n"
        "• Изучать новые слова каждый день (рассылка в 9:00 по МСК)\n"
        "• Проходить квизы для закрепления знаний (рассылка в 19:00 по МСК)\n"
        "• Готовиться к экзамену TOPIK\n\n"
        "Рассылка происходит каждый день автоматически.\n\n"
        "<b>Выберите нужный пункт меню, чтобы начать:</b>",
        reply_markup=create_reply_menu(),
    )


# Обработчик команды "Проверка орфографии 🖍"
@dp.message(F.text == "Проверка орфографии 🖍")
async def spell_checker(message: Message, state: FSMContext):
    await state.set_state(SpellCheckStates.waiting_for_text_to_check)
    await message.answer(
        "Рад помочь!\n\nПожалуйста, отправьте текст <b>на корейском языке</b>, который вы хотите проверить на орфографию.\n\n"
        " Я исправлю ошибки и объясню изменения 👇🏻",
        reply_markup=create_reply_menu(),
    )


# Обработчик текста для проверки орфографии
@dp.message(SpellCheckStates.waiting_for_text_to_check)
async def handle_spell_check(message: Message, state: FSMContext):
    processing_message = await message.answer("Ваш запрос обрабатывается... Пожалуйста, подождите 🕒")
    prompt = ("Ты помощник для проверки орфографии на корейском языке."
              "Исправь ошибки в тексте пользователя придерживаясь стиля и коротко объясни изменения."
              "Ответ отправляй в формате: <b>Исправленный текст:</b>, <b>Ошибки:</b>"
              "Объясняй ошибки на русском языке только если они есть."
              "Ты умеешь исправлять ошибки только на корейском языке.")

    await state.clear()
    await handle_request(message, prompt)
    await processing_message.delete()


# Общий обработчик запросов
async def handle_request(message: Message, prompt):
    user_id = message.from_user.id
    limit_message, within_limit = check_request_limit(user_id)

    if not within_limit:
        await message.answer(limit_message)
        return

    if len(message.text) > 200:
        await message.answer("Ваше сообщение слишком длинное! Пожалуйста, сократите текст до 200 символов.")
        return

    # Обновляем счётчик перед отправкой запроса к модели
    update_request_count(user_id)

    response = await get_ai_response(message.text, prompt)
    await message.answer(response, reply_markup=create_reply_menu())

    # После ответа больше не обновляем счётчик
    limit_message, _ = check_request_limit(user_id)
    await message.answer(limit_message, reply_markup=create_reply_menu())


@dp.message(F.text == "Подготовка TOPIK")
async def essay_plan(message: Message):
    subscription_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отписаться", callback_data="unsubscribe_topik")],
        [InlineKeyboardButton(text="Остаться", callback_data="stay_subscribed")]
    ])
    await message.answer(
        "Данный бот рассылает каждый день полезные слова для сдачи экзамена по TOPIK I.\n\n"
        "Если вы хотите отписаться, нажмите на кнопку ниже.",
        reply_markup=subscription_keyboard
    )

async def update_subscription_status(user_id, action):
    try:
        if action == "unsubscribe":
            db.delete_user(user_id)
        elif action == "resubscribe":
            db.add_user(user_id)
        return True
    except sqlite3.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
        return False

@dp.callback_query(F.data == "unsubscribe_topik")
async def unsubscribe_topik(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await update_subscription_status(user_id, "unsubscribe"):
        resubscribe_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Подписаться снова", callback_data="resubscribe_topik")]
        ])
        await callback.message.answer(
            "Вы отменили подписку на ежедневную рассылку полезных слов.\n\n"
            "Если передумаете, вы всегда можете подписаться снова.",
            reply_markup=resubscribe_keyboard
        )
    else:
        await callback.message.answer("Произошла ошибка при отписке. Пожалуйста, попробуйте позже.")
    await callback.answer()

@dp.callback_query(F.data == "stay_subscribed")
async def stay_subscribed(callback: CallbackQuery):
    await callback.message.answer("Вы остались подписанным на ежедневную рассылку полезных слов.")
    await callback.answer()

@dp.callback_query(F.data == "resubscribe_topik")
async def resubscribe_topik(callback: CallbackQuery):
    user_id = callback.from_user.id

    if await update_subscription_status(user_id, "resubscribe"):
        await callback.message.answer("Вы снова подписались на ежедневную рассылку полезных слов!")
    else:
        await callback.message.answer("Произошла ошибка при подписке. Пожалуйста, попробуйте позже.")
    await callback.answer()

# Обработчик ответов на квиз
@dp.callback_query(F.data.startswith("quiz_"))
async def handle_quiz_answer(callback: CallbackQuery):
    # Формат callback_data: quiz_{user_id}_{correct_index}_{selected_index}_{correct_word}
    parts = callback.data.split("_")
    if len(parts) != 5:
        await callback.answer("Ошибка обработки ответа")
        return
    
    user_id = int(parts[1])
    correct_index = int(parts[2])
    selected_index = int(parts[3])
    correct_word = parts[4]
    
    # Получаем original_sentence из базы данных
    active_quiz = db.get_active_quiz(user_id)
    if active_quiz and active_quiz['correct_word'] == correct_word:
        original_sentence = active_quiz['original_sentence']
    else:
        original_sentence = ""  # Fallback если не найдено
    
    # Проверяем, что ответил правильный пользователь
    if callback.from_user.id != user_id:
        await callback.answer("Это не ваш квиз!", show_alert=True)
        return
    
    # Проверяем правильность ответа
    is_correct = (selected_index == correct_index)
    
    # Сохраняем статистику в базу данных
    db.record_quiz_answer(user_id, is_correct, correct_word)
    
    # Удаляем активный квиз после ответа
    db.delete_active_quiz(user_id)
    
    if is_correct:
        # Правильный ответ
        response_text = (
            f"✅ <b>Правильно!</b>\n\n"
            f"Ответ: <b>\"{correct_word}\"</b>\n\n"
            f"\"{original_sentence}\"\n\n"
            f"Отличная работа! Продолжайте в том же духе! 🚀"
        )
        await callback.message.edit_text(
            response_text,
            parse_mode="HTML"
        )
        await callback.answer("Верно! 🎉")
    else:
        # Неправильный ответ
        # Получаем правильный вариант из кнопок
        correct_option = callback.message.reply_markup.inline_keyboard[correct_index][0].text
        
        # Одобряющие фразы при неправильном ответе
        encouraging_phrases = [
            "Не расстраивайтесь! Продолжайте учиться! 💪",
            "Это нормально ошибаться! Вы на правильном пути! 🌟",
            "Каждая ошибка - это шаг к успеху! Продолжайте! 🚀",
            "Вы стараетесь, и это главное! Не сдавайтесь! 💫",
            "Ошибки помогают учиться! Вы молодец! ✨"
        ]
        encouraging_phrase = random.choice(encouraging_phrases)
        
        response_text = (
            callback.message.text + 
            f"\n\n❌ <b>Неправильно.</b>\n\n"
            f"Правильный ответ: <b>{correct_option}</b>\n\n"
             f"\"{original_sentence}\"\n\n"
            f"{encouraging_phrase}"
        )
        await callback.message.edit_text(
            response_text,
            parse_mode="HTML"
        )
        await callback.answer("Неправильно 😔", show_alert=True)


# Обработчики для кнопки "Обратная связь 🧡"
@dp.message(F.text == "Обратная связь 🧡")
async def feedback_menu(message: Message):
    feedback_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Написать нам 📩", callback_data="write_us")],
        [InlineKeyboardButton(text="Рассказать другу ⭐️", callback_data="tell_friend")],
        [InlineKeyboardButton(text="Наши проекты ✅", callback_data="our_projects")]
    ])
    await message.answer(
        "Пожалуйста, выберите вариант обратной связи:\n\n",
        reply_markup=feedback_keyboard
    )

@dp.callback_query(F.data == "write_us")
async def write_us(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Напишите свое сообщение ниже, и мы обязательно ответим.")
    await state.set_state(FeedbackStates.waiting_for_user_message)
    await callback.answer()

@dp.message(FeedbackStates.waiting_for_user_message)
async def forward_to_admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        user_id = message.from_user.id
        user_name = message.from_user.full_name
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Ответить", callback_data=f"reply_{user_id}")]
            ]
        )
        logging.info(f"Создаю кнопку 'Ответить' для сообщения от {user_name} ({user_id})")
        await bot.send_message(
            ADMIN_ID,
            f"Новое сообщение от:\n{user_name}\n\n<b>{message.text}</b>",
            reply_markup=keyboard
        )
        await message.answer("✅ Ваше сообщение отправлено администратору.\n\nОжидайте ответа!")
        await state.clear()

@dp.callback_query(F.data.startswith("reply_"))
async def ask_admin_reply(callback: CallbackQuery, state: FSMContext):
    user_id = int(callback.data.split("_")[1])
    user_name = callback.message.text.split("\n")[1]
    await state.update_data(user_id=user_id)
    await state.set_state(AdminReplyState.waiting_for_reply)
    logging.info(f"Администратор нажал 'Ответить' для {user_id}.")
    await callback.message.answer(f"Введите ответ для пользователя `{user_name}` (id: `{user_id}`):")
    await callback.answer()

# Обработчик команды "Моя статистика 📊"
@dp.message(F.text == "Моя статистика 📊")
async def show_stats(message: Message):
    user_id = message.from_user.id
    today_stats = db.get_user_stats(user_id)
    all_time_stats = db.get_user_all_time_stats(user_id)
    
    stats_text = (
        f"<b>За все время:</b>\n"
        f"✅ Правильных: {all_time_stats['correct']}\n"
        f"📝 Всего ответов: {all_time_stats['total']}\n"
        f"🎯 Точность: {all_time_stats['accuracy']}%"
    )
    
    await message.answer(stats_text, reply_markup=create_reply_menu(), parse_mode="HTML")

@dp.message(AdminReplyState.waiting_for_reply)
async def send_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get("user_id")
    if not user_id:
        await message.answer("❌ Ошибка: не найден ID пользователя для ответа.")
        return
    try:
        await bot.send_message(user_id, f"📢 Ответ от администратора:\n\n{message.text}")
        await message.answer(f"✅ Ответ успешно отправлен пользователю c id `{user_id}`.")
        logging.info(f"✅ Ответ администратора отправлен пользователю {user_id}.")
    except Exception as e:
        logging.error(f"❌ Ошибка отправки ответа пользователю {user_id}: {e}")
        await message.answer(f"❌ Ошибка при отправке сообщения пользователю: {str(e)}")
    await state.clear()

@dp.callback_query(F.data == "tell_friend")
async def tell_friend(callback: CallbackQuery):
    await callback.message.answer(
        "Пригласите друга по этой ссылке: https://t.me/KoreanLangBot  🌟"
    )
    await callback.answer()

@dp.callback_query(F.data == "our_projects")
async def our_projects(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Бот для изучающих английский язык", url="https://t.me/myligvoacademy_bot")
        ],
        [
            InlineKeyboardButton(text="Бот-мотиватор для уютных чатов", url="https://t.me/Motivate_Chat_Bot")
        ]
    ])

    await callback.message.answer(
        "Вот наши проекты, которые могут быть вам полезны:",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.message(F.text == "Подписаться на наш канал ✅")
async def subscribe_channel(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Перейти в канал 🇰🇷", url="https://t.me/korea_secrets_aliya")]
    ])

    await message.answer(
        "Присоединяйтесь к нашему каналу с полезными материалами по корейскому языку и не только!\n\n",
        reply_markup=keyboard,
        disable_web_page_preview=True
    )

# Обработчик для сообщений вне меню
@dp.message()
async def handle_unknown_message(message: Message):
    await message.answer("Не понял вас.\n\n Пожалуйста, выберите пункт в меню ниже 👇🏻",
                         reply_markup=create_reply_menu())



async def main():
    print("Бот запущен!")
    # Создаем один планировщик для всех задач
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    scheduler = AsyncIOScheduler()
    
    # Планируем отправку слова дня в 9:00
    schedule_daily_word(scheduler=scheduler, hour=9, minute=0)
    
    # Планируем отправку квиза в 19:00 (значение по умолчанию)
    schedule_daily_quiz(scheduler=scheduler, test_mode=False)
    
    # Запускаем планировщик
    scheduler.start()
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

