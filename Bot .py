import telebot
from telebot import types
import sqlite3
from datetime import datetime
import os
import re
import requests

# =========================================================
# SUV ONLAYN 2.0 — OCR
# Bitta Bot.py fayl
# Hisoblagich rasmini avtomatik o'qish + tasdiqlash
# =========================================================

BOT_TOKEN = "8848180909:AAHqVnZUjxBsmWq8DzI_WMyPV-LhjgBbz3I"
ADMIN_ID = 8786347772
OCR_API_KEY = "helloworld"

DB_NAME = "suv_onlayn.db"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Vaqtinchalik holatlar
user_states = {}
temp_data = {}


# =========================================================
# DATABASE
# =========================================================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            full_name TEXT,
            phone TEXT,
            address TEXT,
            meter_number TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            photo_id TEXT,
            reading TEXT,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            message TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =========================================================
# MENU
# =========================================================

def main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    markup.add(
        types.KeyboardButton("👤 Mening ma'lumotlarim"),
        types.KeyboardButton("📸 Ko‘rsatkich yuborish")
    )
    markup.add(
        types.KeyboardButton("📊 Ko‘rsatkichlar tarixi"),
        types.KeyboardButton("⚠️ Muammo haqida xabar")
    )
    markup.add(
        types.KeyboardButton("📞 Suv xizmatiga murojaat"),
        types.KeyboardButton("ℹ️ Loyiha haqida")
    )

    return markup


# =========================================================
# START
# =========================================================

@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id = ?", (user_id,))
    user = cur.fetchone()
    conn.close()

    if user:
        bot.send_message(
            message.chat.id,
            "💧 <b>SUV ONLAYN</b>\n\n"
            "Assalomu alaykum!\n"
            "Sizning ma'lumotlaringiz tizimda mavjud.\n\n"
            "Kerakli xizmatni tanlang:",
            reply_markup=main_menu()
        )
        return

    user_states[user_id] = "full_name"

    bot.send_message(
        message.chat.id,
        "💧 <b>SUV ONLAYN</b>\n\n"
        "Assalomu alaykum!\n\n"
        "🎯 <b>Maqsad:</b> suv hisoblagich ko‘rsatkichlarini "
        "telefon orqali qulay yuborish va raqamli nazorat qilish.\n\n"
        "📌 <b>Vazifalar:</b>\n"
        "• 📸 Hisoblagich rasmini qabul qilish\n"
        "• 🤖 Rasmda ko‘rsatkichni avtomatik o‘qish\n"
        "• ✅ O‘qilgan raqamni tasdiqlatish\n"
        "• 📊 Ko‘rsatkichlar tarixini saqlash\n"
        "• ⚠️ Muammolar va murojaatlarni qabul qilish\n\n"
        "Avval ro‘yxatdan o‘tamiz."
    )

    bot.send_message(
        message.chat.id,
        "👤 Ism-familiyangizni yozing:"
    )


# =========================================================
# TEXT HANDLER — BARCHA MATN SHU YERDA
# =========================================================

@bot.message_handler(content_types=["text"])
def text_handler(message):
    user_id = message.from_user.id
    text = message.text.strip()

    # -----------------------------------------------------
    # Agar ko'rsatkich rasmi yuborilgandan keyin raqam
    # kutilayotgan bo'lsa
    # -----------------------------------------------------

    state = user_states.get(user_id)

    if isinstance(state, dict) and state.get("type") in ("reading", "reading_manual"):
        save_reading(message, text)
        return

    # -----------------------------------------------------
    # MENU
    # -----------------------------------------------------

    if text == "👤 Mening ma'lumotlarim":
        show_profile(message)
        return

    if text == "📸 Ko‘rsatkich yuborish":
        user_states[user_id] = "waiting_photo"

        bot.send_message(
            message.chat.id,
            "📸 <b>Hisoblagich ko‘rsatkichini yuborish</b>\n\n"
            "Hisoblagich raqamlari aniq ko‘rinadigan "
            "rasmni yuboring.",
            reply_markup=main_menu()
        )
        return

    if text == "📊 Ko‘rsatkichlar tarixi":
        show_history(message)
        return

    if text == "⚠️ Muammo haqida xabar":
        user_states[user_id] = "complaint"

        bot.send_message(
            message.chat.id,
            "⚠️ Muammoingizni batafsil yozing.\n\n"
            "Masalan:\n"
            "«Hisoblagichim o‘rnatilgan, lekin bazaga "
            "kiritilmagan.»"
        )
        return

    if text == "📞 Suv xizmatiga murojaat":
        user_states[user_id] = "complaint"

        bot.send_message(
            message.chat.id,
            "📞 <b>Suv xizmatiga murojaat</b>\n\n"
            "Murojaatingizni yozing:"
        )
        return

    if text == "ℹ️ Loyiha haqida":
        bot.send_message(
            message.chat.id,
            "💧 <b>SUV ONLAYN</b>\n\n"
            "Maqsad — fuqarolarga suv hisoblagichi "
            "va suv xizmatlari bilan bog‘liq ma'lumotlarni "
            "telefon orqali qulay boshqarish imkonini yaratish.\n\n"
            "📸 Ko‘rsatkich yuborish\n"
            "📊 Ko‘rsatkichlar tarixi\n"
            "⚠️ Muammo haqida xabar\n"
            "📞 Suv xizmatiga murojaat\n\n"
            "🚀 Loyiha hozirda pilot bosqichida."
        )
        return

    # -----------------------------------------------------
    # REGISTRATION
    # -----------------------------------------------------

    if state == "full_name":
        save_temp(user_id, "full_name", text)
        user_states[user_id] = "phone"

        bot.send_message(
            message.chat.id,
            "📱 Telefon raqamingizni yozing:\n"
            "Masalan: +998901234567"
        )
        return

    if state == "phone":
        save_temp(user_id, "phone", text)
        user_states[user_id] = "address"

        bot.send_message(
            message.chat.id,
            "🏠 Yashash manzilingizni yozing:"
        )
        return

    if state == "address":
        save_temp(user_id, "address", text)
        user_states[user_id] = "meter_number"

        bot.send_message(
            message.chat.id,
            "🔢 Suv hisoblagich raqamini yozing.\n\n"
            "Agar bilmasangiz, <b>bilmayman</b> deb yozing."
        )
        return

    if state == "meter_number":
        save_temp(user_id, "meter_number", text)
        finish_registration(message)
        return

    # -----------------------------------------------------
    # COMPLAINT
    # -----------------------------------------------------

    if state == "complaint":
        save_complaint(user_id, text)

        bot.send_message(
            message.chat.id,
            "✅ <b>Murojaatingiz qabul qilindi.</b>\n\n"
            "Mas'ul xodimga yuborildi.",
            reply_markup=main_menu()
        )

        try:
            bot.send_message(
                ADMIN_ID,
                "⚠️ <b>YANGI MUROJAAT</b>\n\n"
                f"👤 Telegram ID: <code>{user_id}</code>\n"
                f"📝 Murojaat:\n{text}"
            )
        except Exception as e:
            print("Admin xabari yuborilmadi:", e)

        user_states.pop(user_id, None)
        return

    # -----------------------------------------------------
    # DEFAULT
    # -----------------------------------------------------

    bot.send_message(
        message.chat.id,
        "Iltimos, menyudagi kerakli bo‘limlardan birini tanlang.",
        reply_markup=main_menu()
    )


# =========================================================
# PHOTO HANDLER
# =========================================================

@bot.message_handler(content_types=["photo"])
def photo_handler(message):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if state != "waiting_photo":
        bot.send_message(
            message.chat.id,
            "Avval 📸 <b>Ko‘rsatkich yuborish</b> "
            "bo‘limini tanlang."
        )
        return

    photo_id = message.photo[-1].file_id

    bot.send_message(
        message.chat.id,
        "🔎 <b>Rasm tekshirilmoqda...</b>\n\n"
        "Hisoblagichdagi raqamni avtomatik o‘qishga harakat qilaman."
    )

    try:
        file_info = bot.get_file(photo_id)
        image_bytes = bot.download_file(file_info.file_path)
        detected_text = ocr_image(image_bytes)
        detected_reading = extract_reading(detected_text)
    except Exception as e:
        print("OCR xatosi:", e)
        detected_text = ""
        detected_reading = None

    if detected_reading:
        user_states[user_id] = {
            "type": "reading_ocr",
            "photo_id": photo_id,
            "reading": detected_reading
        }

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ To‘g‘ri", callback_data="ocr_yes"),
            types.InlineKeyboardButton("✏️ Qayta kiritish", callback_data="ocr_no")
        )

        bot.send_message(
            message.chat.id,
            "🤖 <b>Ko‘rsatkich avtomatik aniqlandi:</b>\n\n"
            f"📊 <b>{detected_reading} m³</b>\n\n"
            "⚠️ Iltimos, rasmga qarab tekshiring.\n"
            "Raqam to‘g‘ri bo‘lsa tasdiqlang.",
            reply_markup=markup
        )
    else:
        user_states[user_id] = {
            "type": "reading_manual",
            "photo_id": photo_id
        }
        bot.send_message(
            message.chat.id,
            "⚠️ Raqamni avtomatik aniq o‘qiy olmadim.\n\n"
            "Iltimos, hisoblagichdagi ko‘rsatkichni raqam bilan yozing.\n"
            "Masalan: <b>132</b>"
        )


def ocr_image(image_bytes):
    """OCR.Space orqali rasm ichidagi matnni o‘qiydi."""
    response = requests.post(
        "https://api.ocr.space/parse/image",
        files={"file": ("meter.jpg", image_bytes, "image/jpeg")},
        data={
            "apikey": OCR_API_KEY,
            "language": "eng",
            "isOverlayRequired": "false",
            "OCREngine": "2",
            "scale": "true"
        },
        timeout=30
    )
    response.raise_for_status()
    data = response.json()

    if data.get("IsErroredOnProcessing"):
        raise RuntimeError(str(data.get("ErrorMessage", "OCR xatosi")))

    parts = []
    for parsed in data.get("ParsedResults", []):
        parts.append(parsed.get("ParsedText", ""))
    return "\n".join(parts)


def extract_reading(text):
    """OCR matnidan raqamli ko‘rsatkichni ajratishga urinadi."""
    if not text:
        return None

    # OCR ba’zan O/I/S kabi belgilarni raqam deb adashtiradi.
    normalized = (text.upper()
                  .replace("O", "0")
                  .replace("I", "1")
                  .replace("L", "1")
                  .replace("S", "5"))

    candidates = re.findall(r"\b\d{1,8}(?:[.,]\d{1,3})?\b", normalized)
    if not candidates:
        candidates = re.findall(r"\d{1,8}", normalized)

    # Juda uzun sana/telefon kabi sonlarni chetga chiqaramiz.
    clean = []
    for value in candidates:
        value = value.replace(",", ".")
        digits = re.sub(r"\D", "", value)
        if 1 <= len(digits) <= 6:
            clean.append(value)

    if not clean:
        return None

    # Eng uzun mos sonni tanlaymiz; foydalanuvchi baribir tasdiqlaydi.
    clean.sort(key=lambda x: len(re.sub(r"\D", "", x)), reverse=True)
    return clean[0]


@bot.callback_query_handler(func=lambda call: call.data in ["ocr_yes", "ocr_no"])
def ocr_confirmation(call):
    user_id = call.from_user.id
    state = user_states.get(user_id)

    if not isinstance(state, dict) or state.get("type") != "reading_ocr":
        bot.answer_callback_query(call.id, "Bu so‘rov eskirgan.")
        return

    if call.data == "ocr_no":
        user_states[user_id] = {
            "type": "reading_manual",
            "photo_id": state.get("photo_id")
        }
        bot.answer_callback_query(call.id)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(
            call.message.chat.id,
            "✏️ Mayli. Hisoblagichdagi ko‘rsatkichni raqam bilan yozing.\n\n"
            "Masalan: <b>132</b>"
        )
        return

    reading = state.get("reading")
    bot.answer_callback_query(call.id, "Tasdiqlandi ✅")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    save_reading_value(call.message, reading, state.get("photo_id"))


@bot.message_handler(content_types=["text"], func=lambda m: isinstance(user_states.get(m.from_user.id), dict) and user_states.get(m.from_user.id, {}).get("type") == "reading_manual")
def manual_reading_handler(message):
    reading = message.text.strip()
    if not re.fullmatch(r"\d{1,8}(?:[.,]\d{1,3})?", reading):
        bot.send_message(message.chat.id, "❗ Faqat hisoblagichdagi raqamni yozing. Masalan: <b>132</b>")
        return
    state = user_states.get(message.from_user.id, {})
    save_reading_value(message, reading, state.get("photo_id"))


# =========================================================
# SAVE READING
# =========================================================

def save_reading(message, reading):
    user_id = message.from_user.id
    state = user_states.get(user_id)
    if not isinstance(state, dict):
        return
    save_reading_value(message, reading, state.get("photo_id"))


def save_reading_value(message, reading, photo_id):
    user_id = message.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO readings
        (telegram_id, photo_id, reading, created_at)
        VALUES (?, ?, ?, ?)
    """, (
        user_id,
        photo_id,
        reading,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    bot.send_message(
        message.chat.id,
        "✅ <b>Ko‘rsatkich saqlandi!</b>\n\n"
        f"📊 Ko‘rsatkich: <b>{reading} m³</b>\n"
        f"📅 Sana: {now}\n\n"
        "Ma'lumotlaringiz tizimga saqlandi.",
        reply_markup=main_menu()
    )

    try:
        bot.send_photo(
            ADMIN_ID,
            photo_id,
            caption=(
                "💧 <b>YANGI HISOBLAGICH KO‘RSATKICHI</b>\n\n"
                f"👤 Telegram ID: <code>{user_id}</code>\n"
                f"📊 Ko‘rsatkich: <b>{reading} m³</b>\n"
                f"📅 Sana: {now}"
            )
        )
    except Exception as e:
        print("Admin uchun rasm yuborilmadi:", e)

    user_states.pop(user_id, None)


# =========================================================
# TEMP DATA
# =========================================================

def save_temp(user_id, field, value):
    if user_id not in temp_data:
        temp_data[user_id] = {}

    temp_data[user_id][field] = value


# =========================================================
# FINISH REGISTRATION
# =========================================================

def finish_registration(message):
    user_id = message.from_user.id
    data = temp_data.get(user_id, {})

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT OR REPLACE INTO users
        (telegram_id, full_name, phone, address, meter_number, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        data.get("full_name", ""),
        data.get("phone", ""),
        data.get("address", ""),
        data.get("meter_number", ""),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    temp_data.pop(user_id, None)
    user_states.pop(user_id, None)

    bot.send_message(
        message.chat.id,
        "🎉 <b>Ro‘yxatdan o‘tish yakunlandi!</b>\n\n"
        "Endi siz suv hisoblagichingiz bo‘yicha "
        "ma'lumot yuborishingiz mumkin.",
        reply_markup=main_menu()
    )


# =========================================================
# PROFILE
# =========================================================

def show_profile(message):
    user_id = message.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM users WHERE telegram_id = ?",
        (user_id,)
    )

    user = cur.fetchone()
    conn.close()

    if not user:
        bot.send_message(
            message.chat.id,
            "Siz hali ro‘yxatdan o‘tmagansiz.\n"
            "/start buyrug‘ini bosing."
        )
        return

    bot.send_message(
        message.chat.id,
        "👤 <b>SIZNING MA'LUMOTLARINGIZ</b>\n\n"
        f"👤 F.I.Sh: {user[1]}\n"
        f"📱 Telefon: {user[2]}\n"
        f"🏠 Manzil: {user[3]}\n"
        f"🔢 Hisoblagich: {user[4]}"
    )


# =========================================================
# HISTORY
# =========================================================

def show_history(message):
    user_id = message.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT reading, created_at
        FROM readings
        WHERE telegram_id = ?
        ORDER BY id DESC
        LIMIT 10
    """, (user_id,))

    rows = cur.fetchall()
    conn.close()

    if not rows:
        bot.send_message(
            message.chat.id,
            "📊 Hozircha ko‘rsatkichlar tarixi mavjud emas."
        )
        return

    text = "📊 <b>KO‘RSATKICHLAR TARIXI</b>\n\n"

    for i, row in enumerate(rows, start=1):
        text += (
            f"{i}. 📊 {row[0]} m³\n"
            f"   📅 {row[1]}\n\n"
        )

    bot.send_message(message.chat.id, text)


# =========================================================
# COMPLAINT
# =========================================================

def save_complaint(user_id, message_text):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO complaints
        (telegram_id, message, created_at)
        VALUES (?, ?, ?)
    """, (
        user_id,
        message_text,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


# =========================================================
# RUN
# =========================================================

print("💧 SUV ONLAYN BOT ISHLAYAPTI...")

bot.infinity_polling(skip_pending=True)
