import asyncio
import sqlite3
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# 🛠 Твой токен и ID
BOT_TOKEN = "8903498656:AAFff-jLT18-YoOtAj4-qHApu5TvVJoPyzY"
ADMIN_CHAT_ID = 8116778370  

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Глобальная переменная для интервала проверки в секундах (по умолчанию 5 минут)
CHECK_INTERVAL = 300

class MonitorState(StatesGroup):
    typing_interval = State()      
    typing_broadcast_text = State() # Шаг ввода текста рассылки (теперь без пароля!)

# === БАЗА ДАННЫХ ===
def init_monitor_db():
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS sent_tasks (task_url TEXT PRIMARY KEY)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT,
            username TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_user(user_id, full_name, username):
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, full_name, username) VALUES (?, ?, ?)", (user_id, full_name, username))
    conn.commit()
    conn.close()

def is_task_new(url):
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sent_tasks WHERE task_url = ?", (url,))
    result = cursor.fetchone()
    conn.close()
    return result is None

def save_task(url):
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO sent_tasks (task_url) VALUES (?)", (url,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("monitor.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()] # Исправили извлечение ID из кортежа БД!
    conn.close()
    return users

# === МЕНЮ ===
def get_monitor_menu():
    kb = [
        [KeyboardButton(text="проверить! 🔍")],
        [KeyboardButton(text="поставить время чека"), KeyboardButton(text="Информация ℹ️")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_bio_text():
    return (
        "🚀 **Салам, майнер заказов!**\n\n"
        "Привет, я Илья! Python Developer / AI-Driven Engineer. 🐍\n"
        "Специализируюсь на создании Telegram-ботов, автоматизации рутинных процессов и парсинге данных.\n\n"
        "🔗 **Моё портфолио GitHub:** https://github.com\n"
        "💼 **Я на бирже Kwork:** https://kwork.ru"
    )

# === УМНАЯ ФУНКЦИЯ ПАРСИНГА ===
async def check_freelance_orders(manual_message: Message = None):
    url = "https://habr.com"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, timeout=10))
        
        if response.status_code != 200:
            if manual_message:
                await manual_message.answer("❌ Ошибка подключения к Хабру.")
            return

        soup = BeautifulSoup(response.text, "html.parser")
        tasks = soup.find_all("li", class_="content-list__item")
        found_new = False

        for task in tasks:
            title_element = task.find("div", class_="task__title").find("a")
            title = title_element.text.strip()
            link = "https://habr.com" + title_element["href"]
            
            price_element = task.find("div", class_="task__price")
            price_text = price_element.text.strip() if price_element else "Договорная"

            is_high_price = any(f"{i}0 000" in price_text.replace(" ", "") for i in range(1, 9))
            keywords = ["python", "telegram", "бот", "bot", "скрипт", "парсер", "автоматизац"]
            is_target_task = any(word in title.lower() for word in keywords)

            if is_target_task and not is_high_price and is_task_new(link):
                message_text = (
                    f"🔔 **Найден новый заказ!**\n\n"
                    f"📌 **Название:** {title}\n"
                    f"💰 **Цена:** {price_text}\n"
                    f"🔗 **Ссылка:** {link}"
                )
                await bot.send_message(chat_id=ADMIN_CHAT_ID, text=message_text, parse_mode="Markdown")
                save_task(link)
                found_new = True
                await asyncio.sleep(0.5)

        if manual_message and not found_new:
            await manual_message.answer("📭 Свежих заказов по твоим тегам пока нет. Ждем-с!", reply_markup=get_monitor_menu())

    except Exception as e:
        print(f"Ошибка при парсинге: {e}")
        if manual_message:
            await manual_message.answer("❌ Произошла ошибка при сканировании.")

# === ОБРАБОТКА КОМАНД И КНОПОК ===

@dp.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=get_monitor_menu())

@dp.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    
    # Заносим пользователя в базу (если это админ, он тоже должен быть в БД для получения рассылок)
    username = f"@{message.from_user.username}" if message.from_user.username else "Нет юзернейма"
    save_user(message.from_user.id, message.from_user.full_name, username)
    
    # Меню показываем только тебе! Обычный юзер получит просто био
    if message.from_user.id == ADMIN_CHAT_ID:
        await message.answer(
            text=get_bio_text(),
            reply_markup=get_monitor_menu(),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
    else:
        await message.answer(
            text=get_bio_text(),
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

# Ручная кнопка "проверить! 🔍"
@dp.message(F.text == "проверить! 🔍")
async def manual_check(message: Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await message.answer("⏳ Сканирую Хабр Фриланс прямо сейчас...")
    await check_freelance_orders(manual_message=message)

# Кнопка: Информация ℹ️
@dp.message(F.text == "Информация ℹ️")
async def show_info_message(message: Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await message.answer("🔥 **Проект py-ilya-dev v2.0**\nВсе системы мониторинга запущены и работают стабильно!", parse_mode="Markdown")

# Кнопка: поставить время чека
@dp.message(F.text == "поставить время чека")
async def set_time_message(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    await state.set_state(MonitorState.typing_interval)
    await message.answer(
        "⏳ **Настройка таймера.**\nУкажи время проверки в минутах (например, отправь в чат число 5 или 10):",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(MonitorState.typing_interval)
async def process_new_interval(message: Message, state: FSMContext):
    global CHECK_INTERVAL
    if message.text.isdigit():
        minutes = int(message.text)
        if minutes < 1:
            await message.answer("❌ Время не может быть меньше 1 минуты.")
            return
        CHECK_INTERVAL = minutes * 60
        await state.clear()
        await message.answer(f"✅ Успешно! Автоматический радар проверяет Хабр каждые **{minutes} мин.**", reply_markup=get_monitor_menu())
    else:
        await message.answer("Пожалуйста, отправь только число (минуты) или нажми кнопку '❌ Отмена'.")

# --- ОБНОВЛЕННАЯ РАССЫЛКА (ПРОВЕРКА ID И ОТКАЗ ДЛЯ ЮЗЕРОВ) ---
@dp.message(F.text == "/send")
async def start_broadcast_direct(message: Message, state: FSMContext):
    # Если пишет обычный юзер — бот жестко его отшивает!
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.answer("❌ **Ошибка доступа!**\nДанная команда доступна только администратору бота.")
        return
        
    # Если пишет админ (ты) — сразу пускаем к вводу текста без всяких паролей!
    await state.set_state(MonitorState.typing_broadcast_text)
    await message.answer(
        "📢 **Режим рассылки активирован.**\nВведите текст сообщения, которое получат ВСЕ пользователи бота:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)
    )

@dp.message(MonitorState.typing_broadcast_text)
async def do_broadcast(message: Message, state: FSMContext):
    text_to_send = message.text
    await state.clear()
    
    user_ids = get_all_users()
    await message.answer(f"⏳ Запускаю шифрованную рассылку для {len(user_ids)} пользователей...", reply_markup=get_monitor_menu())
    
    success_count = 0
    for u_id in user_ids:
        try:
            await bot.send_message(chat_id=u_id, text=text_to_send)
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            print(f"Не удалось отправить пользователю {u_id}: {e}")
            
    await message.answer(f"✅ Рассылка завершена!\nУспешно доставлено: {success_count} из {len(user_ids)}.")

# Фоновый планировщик
async def scheduler():
    while True:
        await check_freelance_orders(manual_message=None)
        await asyncio.sleep(CHECK_INTERVAL)

async def main():
    init_monitor_db()
    print("🚀 Перезапущен идеальный текстовый радар с проверкой прав доступа!")
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
