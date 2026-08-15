import telebot
from telebot import types
import sqlite3
from datetime import datetime
import io, re, requests
from PIL import Image, ImageEnhance, ImageOps

# =========================================================
# SUV ONLAYN — hisoblagich rasmini OCR orqali o'qish
# =========================================================

BOT_TOKEN = "8848180909:AAHqVnZUjxBsmWq8DzI_WMyPV-LhjgBbz3I"
ADMIN_ID = 8786347772
DB_NAME = "suv_onlayn.db"

# OCR.space kaliti. Ishlamasa, o'zingizning API kalitingizni kiriting.
OCR_SPACE_API_KEY = "helloworld"

# SIZNING PILOT HISOBLAGICHINGIZ UCHUN:
# OCR topgan uzun raqamlar ichidan oxirgi 4 raqam olinadi.
# Masalan: 0100102502 -> 2502 -> 2.502 m³
PILOT_LAST_4_DIGITS = True

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_states = {}
temp_data = {}


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY, full_name TEXT, phone TEXT,
        address TEXT, meter_number TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER,
        photo_id TEXT, reading TEXT, created_at TEXT)""")
    cur.execute("""CREATE TABLE IF NOT EXISTS complaints (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER,
        message TEXT, created_at TEXT)""")
    conn.commit()
    conn.close()


init_db()


def main_menu():
    m = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(types.KeyboardButton("👤 Mening ma'lumotlarim"),
          types.KeyboardButton("📸 Ko‘rsatkich yuborish"))
    m.add(types.KeyboardButton("📊 Ko‘rsatkichlar tarixi"),
          types.KeyboardButton("⚠️ Muammo haqida xabar"))
    m.add(types.KeyboardButton("📞 Suv xizmatiga murojaat"),
          types.KeyboardButton("ℹ️ Loyiha haqida"))
    return m


def normalize_digits(text):
    if not text:
        return ""
    for a, b in {"O":"0","o":"0","Q":"0","I":"1","l":"1","|":"1",
                 "Z":"2","z":"2","S":"5","s":"5","G":"6","g":"6",
                 "B":"8"}.items():
        text = text.replace(a, b)
    return re.sub(r"\D", "", text)


def make_variants(img):
    w, h = img.size
    crops = [
        img,
        img.crop((int(w*.20), int(h*.25), int(w*.90), int(h*.80))),
        img.crop((int(w*.25), int(h*.35), int(w*.85), int(h*.75))),
        img.crop((int(w*.15), int(h*.35), int(w*.95), int(h*.70)))
    ]
    out = []
    for c in crops:
        c = c.resize((c.width*2, c.height*2))
        g = ImageOps.grayscale(c)
        g = ImageEnhance.Contrast(g).enhance(2.2)
        g = ImageEnhance.Sharpness(g).enhance(2.0)
        out += [g,
                g.point(lambda p: 255 if p > 145 else 0),
                g.point(lambda p: 255 if p > 175 else 0)]
    return out


def ocr_space(image):
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data_bytes = buf.getvalue()
    best = ""

    for psm in ("6", "7", "11"):
        try:
            r = requests.post(
                "https://api.ocr.space/parse/image",
                files={"filename": ("meter.png", data_bytes, "image/png")},
                data={
                    "apikey": OCR_SPACE_API_KEY,
                    "language": "eng",
                    "OCREngine": "2",
                    "scale": "true",
                    "isOverlayRequired": "false",
                    "detectOrientation": "true"
                },
                timeout=25
            )
            if r.status_code != 200:
                continue
            j = r.json()
            parsed = j.get("ParsedResults") or []
            text = " ".join(x.get("ParsedText", "") for x in parsed)
            digits = normalize_digits(text)
            if len(digits) > len(best) and len(digits) <= 16:
                best = digits
        except Exception as e:
            print("OCR xatosi:", e)
    return best


def read_meter_value(photo_bytes):
    original = Image.open(io.BytesIO(photo_bytes)).convert("RGB")
    candidates = []

    for angle in (0, 90, 270):
        img = original.rotate(angle, expand=True)
        for variant in make_variants(img):
            d = ocr_space(variant)
            if 4 <= len(d) <= 16:
                candidates.append(d)

    if not candidates:
        return None

    counts = {}
    for c in candidates:
        counts[c] = counts.get(c, 0) + 1

    ranked = sorted(counts.items(), key=lambda x: (-x[1], abs(len(x[0])-8)))
    return ranked[0][0]


def format_meter_reading(raw):
    raw = normalize_digits(raw)
    if not raw:
        return None

    # Pilot hisoblagich: 2502 => 2.502 m³
    if PILOT_LAST_4_DIGITS and len(raw) >= 4:
        raw = raw[-4:]

    raw = raw.lstrip("0") or "0"

    if len(raw) >= 4:
        return f"{int(raw[:-3])}.{raw[-3:]}"
    return raw


@bot.message_handler(commands=["start"])
def start(message):
    uid = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id=?", (uid,))
    user = cur.fetchone()
    conn.close()

    if user:
        bot.send_message(message.chat.id,
            "💧 <b>SUV ONLAYN</b>\n\n"
            "Assalomu alaykum!\nKerakli xizmatni tanlang:",
            reply_markup=main_menu())
        return

    user_states[uid] = "full_name"
    bot.send_message(message.chat.id,
        "💧 <b>SUV ONLAYN</b>\n\n"
        "Maqsad: suv hisoblagich ko‘rsatkichlarini "
        "raqamlashtirish va yuborishni osonlashtirish.\n\n"
        "Avval ro‘yxatdan o‘tamiz.")
    bot.send_message(message.chat.id, "👤 Ism-familiyangizni yozing:")


@bot.message_handler(content_types=["text"])
def text_handler(message):
    uid = message.from_user.id
    text = message.text.strip()
    state = user_states.get(uid)

    if isinstance(state, dict) and state.get("type") == "reading":
        save_reading(message, text)
        return

    if text == "👤 Mening ma'lumotlarim":
        show_profile(message); return

    if text == "📸 Ko‘rsatkich yuborish":
        user_states[uid] = "waiting_photo"
        bot.send_message(message.chat.id,
            "📸 <b>Hisoblagich ko‘rsatkichini yuborish</b>\n\n"
            "Hisoblagichni yaqinroq va raqamlar aniq ko‘rinadigan "
            "qilib suratga oling.")
        return

    if text == "📊 Ko‘rsatkichlar tarixi":
        show_history(message); return

    if text in ("⚠️ Muammo haqida xabar", "📞 Suv xizmatiga murojaat"):
        user_states[uid] = "complaint"
        bot.send_message(message.chat.id, "📝 Murojaatingizni yozing:")
        return

    if text == "ℹ️ Loyiha haqida":
        bot.send_message(message.chat.id,
            "💧 <b>SUV ONLAYN</b>\n\n"
            "🎯 <b>Maqsad:</b> suv hisoblagich ko‘rsatkichlarini "
            "raqamlashtirish.\n\n"
            "📌 <b>Vazifalar:</b>\n"
            "• Hisoblagich rasmini qabul qilish\n"
            "• Raqamlarni avtomatik o‘qish\n"
            "• Natijani foydalanuvchiga tasdiqlatish\n"
            "• Ko‘rsatkichlar tarixini saqlash\n"
            "• Murojaatlarni qabul qilish")
        return

    if state == "full_name":
        save_temp(uid, "full_name", text)
        user_states[uid] = "phone"
        bot.send_message(message.chat.id, "📱 Telefon raqamingiz:")
        return
    if state == "phone":
        save_temp(uid, "phone", text)
        user_states[uid] = "address"
        bot.send_message(message.chat.id, "🏠 Yashash manzilingiz:")
        return
    if state == "address":
        save_temp(uid, "address", text)
        user_states[uid] = "meter_number"
        bot.send_message(message.chat.id, "🔢 Hisoblagich raqami:")
        return
    if state == "meter_number":
        save_temp(uid, "meter_number", text)
        finish_registration(message)
        return
    if state == "complaint":
        save_complaint(uid, text)
        bot.send_message(message.chat.id,
            "✅ <b>Murojaatingiz qabul qilindi.</b>",
            reply_markup=main_menu())
        try:
            bot.send_message(ADMIN_ID,
                f"⚠️ <b>YANGI MUROJAAT</b>\n\n"
                f"👤 Telegram ID: <code>{uid}</code>\n📝 {text}")
        except Exception as e:
            print(e)
        user_states.pop(uid, None)
        return

    bot.send_message(message.chat.id,
        "Iltimos, menyudagi bo‘limlardan birini tanlang.",
        reply_markup=main_menu())


@bot.message_handler(content_types=["photo"])
def photo_handler(message):
    uid = message.from_user.id

    if user_states.get(uid) != "waiting_photo":
        bot.send_message(message.chat.id,
            "Avval 📸 <b>Ko‘rsatkich yuborish</b> bo‘limini tanlang.")
        return

    photo_id = message.photo[-1].file_id

    try:
        file_info = bot.get_file(photo_id)
        photo_bytes = bot.download_file(file_info.file_path)

        bot.send_message(message.chat.id,
            "🔍 <b>Rasm tahlil qilinmoqda...</b>\n\n"
            "Hisoblagich raqamlarini aniqlayapman.")

        raw = read_meter_value(photo_bytes)

        if not raw:
            user_states[uid] = {"type":"reading", "photo_id":photo_id}
            bot.send_message(message.chat.id,
                "❌ Raqamlarni aniq o‘qiy olmadim.\n\n"
                "Iltimos, raqamni qo‘lda yozing. Masalan: <b>2.502</b>")
            return

        value = format_meter_reading(raw)
        user_states[uid] = {
            "type":"ocr_confirm", "photo_id":photo_id,
            "reading":value, "raw":raw
        }

        kb = types.InlineKeyboardMarkup()
        kb.add(
            types.InlineKeyboardButton("✅ To‘g‘ri", callback_data="ocr_yes"),
            types.InlineKeyboardButton("✏️ Qayta kiritish", callback_data="ocr_no")
        )

        bot.send_message(message.chat.id,
            "🤖 <b>Hisoblagich o‘qildi</b>\n\n"
            f"📊 Ko‘rsatkich: <b>{value} m³</b>\n\n"
            "Rasm bilan solishtirib ko‘ring:",
            reply_markup=kb)

    except Exception as e:
        print("OCR xatosi:", e)
        bot.send_message(message.chat.id,
            "❌ Rasmni tahlil qilishda xatolik bo‘ldi. Qayta urinib ko‘ring.")


@bot.callback_query_handler(func=lambda c: c.data in ("ocr_yes","ocr_no"))
def ocr_confirmation(call):
    uid = call.from_user.id
    state = user_states.get(uid)

    if not isinstance(state, dict) or state.get("type") != "ocr_confirm":
        bot.answer_callback_query(call.id, "Natija topilmadi.")
        return

    if call.data == "ocr_yes":
        save_reading_value(uid, call.message.chat.id,
                           state["reading"], state["photo_id"])
        bot.answer_callback_query(call.id, "Saqlandi!")
        bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id, reply_markup=None)
    else:
        user_states[uid] = {
            "type":"reading", "photo_id":state["photo_id"]
        }
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            "✏️ Ko‘rsatkichni qo‘lda kiriting.\nMasalan: <b>2.502</b>")


def save_reading(message, reading):
    uid = message.from_user.id
    state = user_states.get(uid)
    save_reading_value(uid, message.chat.id, reading, state.get("photo_id"))


def save_reading_value(uid, chat_id, reading, photo_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""INSERT INTO readings
        (telegram_id, photo_id, reading, created_at)
        VALUES (?,?,?,?)""",
        (uid, photo_id, reading, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    bot.send_message(chat_id,
        "✅ <b>Ko‘rsatkich saqlandi!</b>\n\n"
        f"📊 Ko‘rsatkich: <b>{reading} m³</b>\n"
        f"📅 Sana: {now}",
        reply_markup=main_menu())

    try:
        bot.send_photo(ADMIN_ID, photo_id,
            caption=(f"💧 <b>YANGI HISOBLAGICH KO‘RSATKICHI</b>\n\n"
                     f"👤 Telegram ID: <code>{uid}</code>\n"
                     f"📊 Ko‘rsatkich: <b>{reading} m³</b>\n"
                     f"📅 Sana: {now}"))
    except Exception as e:
        print(e)

    user_states.pop(uid, None)


def save_temp(uid, field, value):
    temp_data.setdefault(uid, {})[field] = value


def finish_registration(message):
    uid = message.from_user.id
    d = temp_data.get(uid, {})
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""INSERT OR REPLACE INTO users
        (telegram_id,full_name,phone,address,meter_number,created_at)
        VALUES (?,?,?,?,?,?)""",
        (uid,d.get("full_name",""),d.get("phone",""),d.get("address",""),
         d.get("meter_number",""),datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    temp_data.pop(uid,None)
    user_states.pop(uid,None)
    bot.send_message(message.chat.id,
        "🎉 <b>Ro‘yxatdan o‘tish yakunlandi!</b>\n\n"
        "Endi hisoblagich rasmini yuborishingiz mumkin.",
        reply_markup=main_menu())


def show_profile(message):
    uid = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE telegram_id=?", (uid,))
    u = cur.fetchone()
    conn.close()
    if not u:
        bot.send_message(message.chat.id, "Siz hali ro‘yxatdan o‘tmagansiz.")
        return
    bot.send_message(message.chat.id,
        "👤 <b>SIZNING MA'LUMOTLARINGIZ</b>\n\n"
        f"👤 F.I.Sh: {u[1]}\n📱 Telefon: {u[2]}\n"
        f"🏠 Manzil: {u[3]}\n🔢 Hisoblagich: {u[4]}")


def show_history(message):
    uid = message.from_user.id
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""SELECT reading,created_at FROM readings
                   WHERE telegram_id=? ORDER BY id DESC LIMIT 10""",(uid,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        bot.send_message(message.chat.id, "📊 Hozircha tarix mavjud emas.")
        return
    text = "📊 <b>KO‘RSATKICHLAR TARIXI</b>\n\n"
    for i,(reading,date) in enumerate(rows,1):
        text += f"{i}. 📊 {reading} m³\n   📅 {date}\n\n"
    bot.send_message(message.chat.id, text)


def save_complaint(uid, text):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""INSERT INTO complaints
        (telegram_id,message,created_at) VALUES (?,?,?)""",
        (uid,text,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


print("💧 SUV ONLAYN BOT ISHLAYAPTI...")
bot.infinity_polling(skip_pending=True)
