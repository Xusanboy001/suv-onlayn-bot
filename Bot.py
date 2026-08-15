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

# 1 m³ suv narxini shu yerga yozing. 0 bo‘lsa bot narxni hisoblamaydi.
# Masalan: TARIFF_PER_M3 = 2500
TARIFF_PER_M3 = 0

# Katta sarfni ko‘rsatish uchun chegara (m³). Faqat ma’lumot sifatida chiqariladi.
HIGH_USAGE_THRESHOLD = 10.0

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
          types.KeyboardButton("📈 Sarf va to‘lov"))
    m.add(types.KeyboardButton("⚠️ Muammo haqida xabar"))
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
    """OCR uchun faqat bir nechta yengil variant tayyorlaymiz.
    Oldingi kodda o'nlab so'rov yuborilardi va bot uzoq kutib qolardi.
    """
    w, h = img.size

    # Hisoblagich raqamlari odatda markaz/yuqori qismda bo'ladi.
    crops = [
        img,
        img.crop((int(w * .18), int(h * .20), int(w * .92), int(h * .72))),
    ]

    out = []
    for c in crops:
        c = c.resize((min(c.width * 2, 1800), min(c.height * 2, 1800)))
        g = ImageOps.grayscale(c)
        g = ImageEnhance.Contrast(g).enhance(2.0)
        g = ImageEnhance.Sharpness(g).enhance(1.8)
        out.append(g)

    return out


def ocr_space(image):
    """Bitta rasmga bitta OCR so'rovi. 8 soniyadan ortiq kutmaydi."""
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=88)
    data_bytes = buf.getvalue()

    try:
        r = requests.post(
            "https://api.ocr.space/parse/image",
            files={"filename": ("meter.jpg", data_bytes, "image/jpeg")},
            data={
                "apikey": OCR_SPACE_API_KEY,
                "language": "eng",
                "OCREngine": "2",
                "scale": "true",
                "isOverlayRequired": "false",
                "detectOrientation": "true",
            },
            timeout=(5, 8)
        )

        if r.status_code != 200:
            print("OCR HTTP:", r.status_code)
            return ""

        j = r.json()

        if j.get("IsErroredOnProcessing"):
            print("OCR API:", j.get("ErrorMessage"))
            return ""

        parsed = j.get("ParsedResults") or []
        raw_text = " ".join(x.get("ParsedText", "") for x in parsed)

        # Matn ichidan raqamli ketma-ketliklarni ajratamiz.
        sequences = re.findall(r"\d[\d\s.,]{3,15}\d", raw_text)
        candidates = []

        for s in sequences:
            d = normalize_digits(s)
            if 4 <= len(d) <= 16:
                candidates.append(d)

        # Agar OCR oddiy matn qaytarsa, undan ham raqamlarni olamiz.
        if not candidates:
            d = normalize_digits(raw_text)
            if 4 <= len(d) <= 16:
                candidates.append(d)

        if not candidates:
            return ""

        # Suv hisoblagich uchun uzunroq raqamli satrni afzal ko'ramiz.
        candidates.sort(key=lambda x: len(x), reverse=True)
        return candidates[0]

    except requests.exceptions.Timeout:
        print("OCR timeout")
        return ""
    except Exception as e:
        print("OCR xatosi:", e)
        return ""


def read_meter_value(photo_bytes):
    """Maksimal 3 ta OCR urinish.
    Ishlamasa bot qotib qolmaydi — qo'lda kiritishni taklif qiladi.
    """
    original = Image.open(io.BytesIO(photo_bytes)).convert("RGB")

    candidates = []

    # Odatdagi holat
    for variant in make_variants(original):
        d = ocr_space(variant)
        if 4 <= len(d) <= 16:
            candidates.append(d)

    # Surat yonboshlab tushirilgan bo'lsa, yana birgina urinish.
    if not candidates:
        rotated = original.rotate(90, expand=True)
        d = ocr_space(rotated)
        if 4 <= len(d) <= 16:
            candidates.append(d)

    if not candidates:
        return None

    # Eng ko'p takrorlangan / mantiqan uzun raqamni tanlash.
    counts = {}
    for c in candidates:
        counts[c] = counts.get(c, 0) + 1

    ranked = sorted(
        counts.items(),
        key=lambda x: (-x[1], -len(x[0]))
    )
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

    if text == "📈 Sarf va to‘lov":
        show_usage(message); return

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
            "• Oldingi ko‘rsatkich bilan solishtirish\n"
            "• Sarflangan suv miqdorini hisoblash\n"
            "• Tarif kiritilganda to‘lovni hisoblash\n"
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
            "Hisoblagich raqamlarini aniqlayapman. Bu odatda bir necha soniya oladi.")

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


def parse_m3(value):
    """2.502, 2,502 yoki 2502 kabi qiymatlarni m³ soniga aylantiradi."""
    if value is None:
        return None

    s = str(value).strip().replace(",", ".")
    s = re.sub(r"[^0-9.]", "", s)

    if not s:
        return None

    try:
        # OCR/pilot holatida 2502 => 2.502
        if "." not in s and len(s) >= 4 and PILOT_LAST_4_DIGITS:
            s = s[:-3] + "." + s[-3:]
        return float(s)
    except ValueError:
        return None


def get_previous_reading(uid):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""SELECT reading, created_at FROM readings
                   WHERE telegram_id=? ORDER BY id DESC LIMIT 1""", (uid,))
    row = cur.fetchone()
    conn.close()
    return row


def save_reading_value(uid, chat_id, reading, photo_id):
    previous = get_previous_reading(uid)
    current_m3 = parse_m3(reading)

    # Hozirgi ko‘rsatkich oldingisidan kichik bo‘lsa, hisobni manfiy qilmaymiz.
    consumption = None
    if previous and current_m3 is not None:
        prev_m3 = parse_m3(previous[0])
        if prev_m3 is not None and current_m3 >= prev_m3:
            consumption = current_m3 - prev_m3

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""INSERT INTO readings
        (telegram_id, photo_id, reading, created_at)
        VALUES (?,?,?,?)""",
        (uid, photo_id, reading, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    msg = (
        "✅ <b>Ko‘rsatkich saqlandi!</b>\n\n"
        f"📊 Ko‘rsatkich: <b>{reading} m³</b>\n"
        f"📅 Sana: {now}\n"
    )

    if previous:
        msg += f"\n🔙 Oldingi: <b>{previous[0]} m³</b>"
        if consumption is not None:
            msg += f"\n💧 Sarflangan: <b>{consumption:.3f} m³</b>"

            if consumption >= HIGH_USAGE_THRESHOLD:
                msg += "\n\n⚠️ <b>Eslatma:</b> sarf odatdagidan yuqori bo‘lishi mumkin."

            if TARIFF_PER_M3 > 0:
                payment = consumption * TARIFF_PER_M3
                msg += f"\n💰 Taxminiy to‘lov: <b>{payment:,.0f} so‘m</b>"
            else:
                msg += "\n💰 To‘lov: tarif kiritilgach hisoblanadi."
    else:
        msg += "\n\nℹ️ Bu birinchi ko‘rsatkich. Keyingi ko‘rsatkichda sarf avtomatik hisoblanadi."

    bot.send_message(chat_id, msg, reply_markup=main_menu())

    try:
        admin_caption = (
            f"💧 <b>YANGI HISOBLAGICH KO‘RSATKICHI</b>\n\n"
            f"👤 Telegram ID: <code>{uid}</code>\n"
            f"📊 Ko‘rsatkich: <b>{reading} m³</b>\n"
            f"📅 Sana: {now}"
        )
        if consumption is not None:
            admin_caption += f"\n💧 Sarf: <b>{consumption:.3f} m³</b>"
        bot.send_photo(ADMIN_ID, photo_id, caption=admin_caption)
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


def show_usage(message):
    uid = message.from_user.id

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute("""SELECT reading, created_at FROM readings
                   WHERE telegram_id=? ORDER BY id DESC LIMIT 2""", (uid,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        bot.send_message(message.chat.id,
            "📈 Hozircha sarfni hisoblash uchun ko‘rsatkich yo‘q.",
            reply_markup=main_menu())
        return

    current = parse_m3(rows[0][0])

    if len(rows) < 2:
        bot.send_message(message.chat.id,
            "📈 <b>SARF VA TO‘LOV</b>\n\n"
            f"📊 Joriy ko‘rsatkich: <b>{rows[0][0]} m³</b>\n\n"
            "ℹ️ Kamida 2 ta ko‘rsatkich kerak. Keyingi ko‘rsatkich yuborilganda "
            "sarflangan suv avtomatik chiqadi.",
            reply_markup=main_menu())
        return

    previous = parse_m3(rows[1][0])

    if current is None or previous is None or current < previous:
        bot.send_message(message.chat.id,
            "⚠️ Ko‘rsatkichlarni solishtirib bo‘lmadi.\n\n"
            "Joriy ko‘rsatkich oldingisidan kichik yoki noto‘g‘ri kiritilgan.",
            reply_markup=main_menu())
        return

    consumption = current - previous
    msg = (
        "📈 <b>SARF VA TO‘LOV</b>\n\n"
        f"🔙 Oldingi: <b>{rows[1][0]} m³</b>\n"
        f"📊 Joriy: <b>{rows[0][0]} m³</b>\n"
        f"💧 Sarflangan: <b>{consumption:.3f} m³</b>\n"
    )

    if TARIFF_PER_M3 > 0:
        payment = consumption * TARIFF_PER_M3
        msg += f"💰 Taxminiy to‘lov: <b>{payment:,.0f} so‘m</b>\n"
        msg += f"🧾 Tarif: <b>{TARIFF_PER_M3:,.0f} so‘m/m³</b>"
    else:
        msg += "\n💰 Tarif hali sozlanmagan."

    if consumption >= HIGH_USAGE_THRESHOLD:
        msg += "\n\n⚠️ <b>Ogohlantirish:</b> sarf yuqori."

    bot.send_message(message.chat.id, msg, reply_markup=main_menu())


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
