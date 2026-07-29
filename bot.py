import asyncio
import logging
import os
from datetime import datetime, timedelta
import sqlite3
import yt_dlp
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
import re

# تنظیمات از Environment Variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
FORCE_CHANNELS = os.getenv("FORCE_CHANNELS", "").split(",")
DAILY_INSTA = int(os.getenv("DAILY_INSTA", 2))
DAILY_YT = int(os.getenv("DAILY_YT", 1))
REFERRAL_NEEDED = int(os.getenv("REFERRAL_NEEDED", 5))
CARD_NUMBER = os.getenv("CARD_NUMBER", "شماره کارت")
CARD_HOLDER = os.getenv("CARD_HOLDER", "نام صاحب کارت")
SUB_PRICE = os.getenv("SUB_PRICE", "قیمت")
SUB_DAYS = int(os.getenv("SUB_DAYS", 30))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# دیتابیس
def init_db():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        insta_daily INTEGER DEFAULT 0,
        yt_daily INTEGER DEFAULT 0,
        referral_count INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT 0,
        sub_expire TEXT DEFAULT NULL,
        last_reset DATE DEFAULT CURRENT_DATE
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS referrals (
        referrer_id INTEGER,
        referred_id INTEGER UNIQUE,
        date TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    user = c.fetchone()
    if not user:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user = c.fetchone()
    conn.close()
    return user

def reset_daily_limits():
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("UPDATE users SET insta_daily=0, yt_daily=0, last_reset=DATE('now')")
    conn.commit()
    conn.close()

def check_referral_goal(user_id):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("SELECT referral_count FROM users WHERE user_id=?", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count >= REFERRAL_NEEDED

def add_referral(referrer_id, new_user_id):
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO referrals (referrer_id, referred_id) VALUES (?, ?)", (referrer_id, new_user_id))
    c.execute("UPDATE users SET referral_count = referral_count + 1 WHERE user_id=?", (referrer_id,))
    conn.commit()
    conn.close()

# چک کردن جوین کانال‌ها
async def check_force_join(user_id):
    if not FORCE_CHANNELS or FORCE_CHANNELS == [""]:
        return True
    for channel in FORCE_CHANNELS:
        if not channel.strip():
            continue
        try:
            member = await bot.get_chat_member(chat_id=channel.strip(), user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

@dp.message_handler(commands=["start"])
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    if not await check_force_join(user_id):
        keyboard = InlineKeyboardMarkup()
        for channel in FORCE_CHANNELS:
            if channel.strip():
                keyboard.add(InlineKeyboardButton("📢 جوین کانال", url=f"https://t.me/{channel.strip()}"))
        keyboard.add(InlineKeyboardButton("✅ عضو شدم", callback_data="check_join"))
        await message.answer("❗ لطفاً ابتدا در کانال‌های زیر عضو شوید:", reply_markup=keyboard)
        return
    await message.answer("🎬 سلام! لینک ویدیو از اینستاگرام یا یوتیوب رو بفرست تا دانلود کنم.")

@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_force_join(user_id):
        await callback.message.edit_text("✅ عضویت شما تأیید شد! حالا لینک ویدیو رو بفرست.")
    else:
        await callback.answer("❌ هنوز عضو نشدی!", show_alert=True)

@dp.message_handler(commands=["invite"])
async def invite_cmd(message: types.Message):
    user_id = message.from_user.id
    bot_username = (await bot.get_me()).username
    link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    await message.answer(f"🔗 لینک دعوت شما:\n{link}\n\nبا دعوت {REFERRAL_NEEDED} نفر، محدودیت دانلود برداشته میشه!")

@dp.message_handler(commands=["buy"])
async def buy_cmd(message: types.Message):
    text = f"💳 خرید اشتراک ویژه\n\n🏦 شماره کارت: {CARD_NUMBER}\n👤 صاحب حساب: {CARD_HOLDER}\n💰 قیمت: {SUB_PRICE}\n📅 مدت: {SUB_DAYS} روز\n\n📸 عکس رسید رو بفرست تا توسط ادمین تأیید بشه."
    await message.answer(text)

@dp.message_handler(content_types=["photo"])
async def handle_payment_photo(message: types.Message):
    if message.photo:
        user_id = message.from_user.id
        await message.forward(ADMIN_ID)
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton("✅ تأیید", callback_data=f"confirm_{user_id}"))
        keyboard.add(InlineKeyboardButton("❌ رد", callback_data=f"reject_{user_id}"))
        await bot.send_message(ADMIN_ID, f"🛒 رسید جدید از کاربر {user_id}", reply_markup=keyboard)
        await message.answer("✅ رسید شما برای ادمین ارسال شد. پس از تأیید، اشتراک فعال میشه.")

@dp.callback_query_handler(lambda c: c.data.startswith("confirm_"))
async def confirm_sub(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect("bot_data.db")
    c = conn.cursor()
    expire = (datetime.now() + timedelta(days=SUB_DAYS)).isoformat()
    c.execute("UPDATE users SET sub_expire=? WHERE user_id=?", (expire, user_id))
    conn.commit()
    conn.close()
    await callback.answer("✅ اشتراک فعال شد!")
    await bot.send_message(user_id, "🎉 اشتراک ویژه شما فعال شد! دانلود نامحدود دارید.")

@dp.callback_query_handler(lambda c: c.data.startswith("reject_"))
async def reject_sub(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    await callback.answer("❌ اشتراک رد شد.")
    await bot.send_message(user_id, "❌ متأسفانه رسید شما تأیید نشد. لطفاً دوباره تلاش کنید.")

if __name__ == "__main__":
    init_db()
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
