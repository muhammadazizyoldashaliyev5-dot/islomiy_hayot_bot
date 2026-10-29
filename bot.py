import asyncio
import logging
import os
import sqlite3
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = Path(__file__).with_name("islomiy_hayot.db")
TZ = ZoneInfo(os.getenv("TIMEZONE", "Asia/Tashkent"))
API_BASE = "https://api.aladhan.com/v1"

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

PRAYERS = [
    ("Fajr", "Bomdod"),
    ("Dhuhr", "Peshin"),
    ("Asr", "Asr"),
    ("Maghrib", "Shom"),
    ("Isha", "Xufton"),
]

DAILY_TASKS = [
    "Bomdod namozi",
    "Peshin namozi",
    "Asr namozi",
    "Shom namozi",
    "Xufton namozi",
    "Qur'ondan 5–10 daqiqa o‘qish",
    "Bugungi duo yoki zikr",
    "Bir yaxshi amal qilish",
]

def connect_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            city TEXT NOT NULL DEFAULT 'Tashkent',
            country TEXT NOT NULL DEFAULT 'Uzbekistan',
            reminders INTEGER NOT NULL DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            task_date TEXT NOT NULL,
            task_name TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, task_date, task_name)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sent_reminders (
            user_id INTEGER NOT NULL,
            prayer_date TEXT NOT NULL,
            prayer_name TEXT NOT NULL,
            PRIMARY KEY(user_id, prayer_date, prayer_name)
        )
    """)
    conn.commit()
    return conn

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕌 Namozni o‘rganish", callback_data="learn")],
        [InlineKeyboardButton(text="⏰ Bugungi namoz vaqtlari", callback_data="times")],
        [InlineKeyboardButton(text="📖 Qur'on va zikr", callback_data="quran")],
        [InlineKeyboardButton(text="✅ Kunlik reja", callback_data="daily")],
        [InlineKeyboardButton(text="📍 Shahar sozlamasi", callback_data="city")],
        [InlineKeyboardButton(text="🔔 Eslatmalarni yoqish/o‘chirish", callback_data="reminders")],
        [InlineKeyboardButton(text="ℹ️ Yordam", callback_data="help")],
    ])

def get_user(user_id):
    with connect_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    return row

def ensure_user(user_id, first_name=""):
    with connect_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users(user_id, first_name) VALUES(?, ?)",
            (user_id, first_name or "")
        )

def ensure_tasks(user_id):
    today = datetime.now(TZ).date().isoformat()
    with connect_db() as conn:
        for task in DAILY_TASKS:
            conn.execute(
                "INSERT OR IGNORE INTO tasks(user_id, task_date, task_name) VALUES(?,?,?)",
                (user_id, today, task)
            )

def daily_keyboard(user_id):
    ensure_tasks(user_id)
    today = datetime.now(TZ).date().isoformat()
    with connect_db() as conn:
        rows = conn.execute(
            "SELECT id, task_name, done FROM tasks WHERE user_id=? AND task_date=? ORDER BY id",
            (user_id, today)
        ).fetchall()
    buttons = [
        [InlineKeyboardButton(
            text=f"{'✅' if r['done'] else '⬜'} {r['task_name']}",
            callback_data=f"task:{r['id']}:{0 if r['done'] else 1}"
        )]
        for r in rows
    ]
    buttons.append([InlineKeyboardButton(text="🔄 Yangilash", callback_data="daily")])
    return InlineKeyboardMarkup(inline_keyboard=buttons), sum(r["done"] for r in rows), len(rows)

async def get_prayer_times(city, country):
    params = {"city": city, "country": country, "school": 1}
    timeout = aiohttp.ClientTimeout(total=12)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(f"{API_BASE}/timingsByCity", params=params) as response:
            response.raise_for_status()
            data = await response.json()
    if data.get("code") != 200 or not data.get("data", {}).get("timings"):
        raise ValueError("Namoz vaqtlari topilmadi")
    timings = data["data"]["timings"]
    return timings, data["data"].get("date", {}).get("readable", "")

def format_times(timings, readable, city):
    lines = [f"⏰ <b>{city} uchun namoz vaqtlari</b>", f"📅 {readable}", ""]
    for api_name, uz_name in PRAYERS:
        raw = timings.get(api_name, "--:--")
        # API time may include timezone annotations; display only HH:MM.
        clock = str(raw).split(" ")[0]
        lines.append(f"• {uz_name}: <b>{clock}</b>")
    lines += [
        "",
        "Hisoblash xizmati: AlAdhan API; Asr uchun Hanafiy (school=1) tanlangan.",
        "Mahalliy masjid jadvali bilan solishtirib tekshiring."
    ]
    return "\n".join(lines)

async def send_daily_prayer_times(bot: Bot):
    """Check every minute and send reminders for Uzbekistan local time."""
    while True:
        try:
            now = datetime.now(TZ)
            hhmm = now.strftime("%H:%M")
            today = now.date().isoformat()
            with connect_db() as conn:
                users = conn.execute(
                    "SELECT user_id, city, country FROM users WHERE reminders=1"
                ).fetchall()

            for user in users:
                try:
                    timings, _ = await get_prayer_times(user["city"], user["country"])
                    for api_name, uz_name in PRAYERS:
                        prayer_time = str(timings.get(api_name, "")).split(" ")[0]
                        if prayer_time != hhmm:
                            continue
                        with connect_db() as conn:
                            already = conn.execute(
                                "SELECT 1 FROM sent_reminders WHERE user_id=? AND prayer_date=? AND prayer_name=?",
                                (user["user_id"], today, api_name)
                            ).fetchone()
                            if not already:
                                conn.execute(
                                    "INSERT OR IGNORE INTO sent_reminders(user_id, prayer_date, prayer_name) VALUES(?,?,?)",
                                    (user["user_id"], today, api_name)
                                )
                                should_send = True
                            else:
                                should_send = False
                        if should_send:
                            await bot.send_message(
                                user["user_id"],
                                f"🕌 {uz_name} namozi vaqti bo‘ldi.\n"
                                "Alloh ibodatlaringizni qabul qilsin. Mahalliy masjid jadvalini ham tekshiring."
                            )
                except Exception:
                    logging.exception("Namoz eslatmasi xatosi user_id=%s", user["user_id"])
        except Exception:
            logging.exception("Eslatma tekshiruvida xato")
        await asyncio.sleep(60)

@dp.message(CommandStart())
async def start(message: Message):
    ensure_user(message.from_user.id, message.from_user.first_name)
    await message.answer(
        "Assalomu alaykum! 🕌\n\n"
        "Men Islomiy Hayot yordamchisiman. Namozni o‘rganish, namoz vaqtlarini ko‘rish, "
        "Qur'on va zikr bo‘limi hamda kunlik reja bilan yordam beraman.\n\n"
        "Boshlash uchun menyudan bo‘lim tanlang.",
        reply_markup=menu()
    )

@dp.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "/start — bosh menyu\n"
        "/times — bugungi namoz vaqtlari\n"
        "/daily — kunlik reja\n"
        "/prayer — namozni o‘rganish\n"
        "/quran — Qur'on va zikr\n"
        "/setcity Toshkent — shaharni sozlash\n"
        "/reminders_on — eslatmalarni yoqish\n"
        "/reminders_off — eslatmalarni o‘chirish",
        reply_markup=menu()
    )

@dp.message(Command("prayer"))
async def prayer_command(message: Message):
    await message.answer(
        "🕌 <b>NAMOZNI O‘RGANISH — boshlang‘ich reja</b>\n\n"
        "1. Tahoratni o‘rganing.\n"
        "2. Namozning shartlari va farzlarini ishonchli ustozdan o‘rganing.\n"
        "3. Fotiha va qisqa suralarni to‘g‘ri talaffuz bilan yodlang.\n"
        "4. Qiyom, ruku, sajda va qa'da tartibini amaliy o‘rganing.\n"
        "5. Hanafiy mazhabidagi amaliy tafsilotlarni ishonchli manba yoki imom bilan tekshiring.\n\n"
        "Bu qisqa yo‘l xaritasi to‘liq fiqh qo‘llanmasi o‘rnini bosmaydi.",
        parse_mode="HTML"
    )

@dp.message(Command("quran"))
async def quran_command(message: Message):
    await message.answer(
        "📖 <b>QUR'ON VA ZIKR</b>\n\n"
        "• Har kuni 5–10 daqiqa Qur'on o‘qishga vaqt ajrating.\n"
        "• Arabcha matnni ishonchli mushafdan o‘qing.\n"
        "• Ma'nosini ishonchli o‘zbekcha tarjimadan o‘rganing.\n"
        "• Zikr va duolarni ma'nosini tushunib o‘rganing.\n\n"
        "Eslatma: bot tekshirilmagan matnni oyat yoki hadis deb ko‘rsatmaydi.",
        parse_mode="HTML"
    )

@dp.message(Command("daily"))
async def daily_command(message: Message):
    ensure_user(message.from_user.id, message.from_user.first_name)
    keyboard, done, total = daily_keyboard(message.from_user.id)
    await message.answer(
        f"✅ <b>BUGUNGI REJA</b>\nBajarilgan: {done}/{total}\n\n"
        "Vazifani bosib belgilashingiz mumkin. Maqsad — asta-sekin yaxshi odatlarni shakllantirish.",
        reply_markup=keyboard, parse_mode="HTML"
    )

@dp.message(Command("times"))
async def times_command(message: Message):
    ensure_user(message.from_user.id, message.from_user.first_name)
    user = get_user(message.from_user.id)
    await message.answer("Namoz vaqtlari olinmoqda...")
    try:
        timings, readable = await get_prayer_times(user["city"], user["country"])
        await message.answer(format_times(timings, readable, user["city"]), parse_mode="HTML")
    except Exception:
        logging.exception("Namoz vaqtlari API xatosi")
        await message.answer(
            "Namoz vaqtlarini hozir olib bo‘lmadi. Internetni tekshiring yoki /setcity Toshkent deb qayta sozlang."
        )

@dp.message(Command("setcity"))
async def set_city(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Shahar nomini kiriting. Masalan: /setcity Toshkent")
        return
    city = parts[1].strip()[:80]
    ensure_user(message.from_user.id, message.from_user.first_name)
    with connect_db() as conn:
        conn.execute("UPDATE users SET city=?, country='Uzbekistan' WHERE user_id=?",
                     (city, message.from_user.id))
    await message.answer(f"📍 Shahar saqlandi: {city}, Uzbekistan\n/times orqali vaqtlarni tekshiring.")

@dp.message(Command("reminders_on"))
async def reminders_on(message: Message):
    ensure_user(message.from_user.id, message.from_user.first_name)
    with connect_db() as conn:
        conn.execute("UPDATE users SET reminders=1 WHERE user_id=?", (message.from_user.id,))
    await message.answer("🔔 Namoz eslatmalari yoqildi. Bot ishlayotgan paytda eslatma yuboradi.")

@dp.message(Command("reminders_off"))
async def reminders_off(message: Message):
    ensure_user(message.from_user.id, message.from_user.first_name)
    with connect_db() as conn:
        conn.execute("UPDATE users SET reminders=0 WHERE user_id=?", (message.from_user.id,))
    await message.answer("🔕 Namoz eslatmalari o‘chirildi.")

@dp.callback_query(F.data == "learn")
async def cb_learn(call: CallbackQuery):
    await call.message.answer("Namozni o‘rganish bo‘limi: /prayer")
    await call.answer()

@dp.callback_query(F.data == "quran")
async def cb_quran(call: CallbackQuery):
    await call.message.answer("Qur'on va zikr bo‘limi: /quran")
    await call.answer()

@dp.callback_query(F.data == "times")
async def cb_times(call: CallbackQuery):
    await call.answer()
    user = get_user(call.from_user.id)
    try:
        timings, readable = await get_prayer_times(user["city"], user["country"])
        await call.message.answer(format_times(timings, readable, user["city"]), parse_mode="HTML")
    except Exception:
        await call.message.answer("Namoz vaqtlari olinmadi. /setcity Toshkent buyrug‘ini tekshiring.")

@dp.callback_query(F.data == "daily")
async def cb_daily(call: CallbackQuery):
    ensure_user(call.from_user.id, call.from_user.first_name)
    keyboard, done, total = daily_keyboard(call.from_user.id)
    await call.message.answer(
        f"✅ <b>BUGUNGI REJA</b>\nBajarilgan: {done}/{total}",
        reply_markup=keyboard, parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("task:"))
async def cb_task(call: CallbackQuery):
    try:
        _, task_id, done = call.data.split(":")
        with connect_db() as conn:
            conn.execute("UPDATE tasks SET done=? WHERE id=? AND user_id=?",
                         (int(done), int(task_id), call.from_user.id))
        keyboard, completed, total = daily_keyboard(call.from_user.id)
        await call.message.edit_text(
            f"✅ <b>BUGUNGI REJA</b>\nBajarilgan: {completed}/{total}",
            reply_markup=keyboard, parse_mode="HTML"
        )
        await call.answer("Belgilandi.")
    except Exception:
        await call.answer("Vazifani yangilab bo‘lmadi.", show_alert=True)

@dp.callback_query(F.data == "city")
async def cb_city(call: CallbackQuery):
    await call.message.answer("Shaharni sozlash: /setcity Toshkent")
    await call.answer()

@dp.callback_query(F.data == "reminders")
async def cb_reminders(call: CallbackQuery):
    user = get_user(call.from_user.id)
    new_value = 0 if user and user["reminders"] else 1
    with connect_db() as conn:
        conn.execute("UPDATE users SET reminders=? WHERE user_id=?", (new_value, call.from_user.id))
    await call.message.answer("🔔 Eslatmalar yoqildi." if new_value else "🔕 Eslatmalar o‘chirildi.")
    await call.answer()

@dp.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await call.message.answer("/help buyrug‘i orqali barcha buyruqlarni ko‘ring.")
    await call.answer()

async def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. .env fayliga BotFather tokenini yozing.")
    connect_db().close()
    bot = Bot(token=TOKEN)
    reminder_task = asyncio.create_task(send_daily_prayer_times(bot))
    try:
        print("Islomiy Hayot bot ishga tushdi. Telegramda /start yuboring.")
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
