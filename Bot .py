import telebot
from telebot import types
import sqlite3
from datetime import datetime

# =========================================================
# SUV ONLAYN 1.0
# Bitta Bot.py fayl
# =========================================================

BOT_TOKEN = "8848180909:AAHqVnZUjxBsmWq8DzI_WMyPV-LhjgBbz3I"
ADMIN_ID = 8786347772

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
        "💧 <b>SUV ONLAYN</b>\n"
        "📱 <b>Suv hisoblagichlarini raqamli boshqarish tizimi</b>\n\n"
        "🎯 <b>BOTNING MAQSADI</b>\n"
        "Fuqarolarga suv hisoblagichi va suv xizmatlari bilan "
        "bog‘liq jarayonlarni qulay, tezkor va shaffof tarzda "
        "raqamlashtirish imkonini yaratish.\n\n"
        "📌 <b>ASOSIY VAZIFALARI</b>\n"
        "1️⃣ 📸 Hisoblagich ko‘rsatkichini foto va raqam bilan qabul qilish\n"
        "2️⃣ 📊 Ko‘rsatkichlar tarixini saqlash va ko‘rsatish\n"
        "3️⃣ 👤 Fuqaro va hisoblagich ma’lumotlarini saqlash\n"
        "4️⃣ ⚠️ Hisoblagich yoki suv ta’minotidagi muammolar haqida xabar qabul qilish\n"
        "5️⃣ 📞 Suv xizmatiga elektron murojaat yuborish\n"
        "6️⃣ 📨 Murojaatlarni mas’ul xodimga tezkor yetkazish\n\n"
        "🚀 <b>Loyiha maqsadi:</b> suv xizmatlarini zamonaviy, "
        "qulay va shaffof qilish.\n\n"
        "✍️ <b>Loyiha muallifi:</b> Xusanboy Mirzakosimov\n"
        "📍 <b>Pilot hudud:</b> Andijon viloyati\n\n"
        "🔹 <i>Loyiha hozirda pilot bosqichida.</i>\n\n"
        "Ro‘yxatdan o‘tishni boshlaymiz."
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

    if isinstance(state, dict) and state.get("type") == "reading":
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

    user_states[user_id] = {
        "type": "reading",
        "photo_id": photo_id
    }

    bot.send_message(
        message.chat.id,
        "✅ Rasm qabul qilindi.\n\n"
        "Endi hisoblagichdagi ko‘rsatkichni raqam bilan yozing.\n\n"
        "Masalan: <b>132</b>"
    )


# =========================================================
# SAVE READING
# =========================================================

def save_reading(message, reading):
    user_id = message.from_user.id
    state = user_states.get(user_id)

    if not isinstance(state, dict):
        return

    photo_id = state.get("photo_id")

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
