"""
=====================================================================
 TARONA BOT — aiogram 3.x asosida musiqa qidiruv boti
=====================================================================
Imkoniyatlari:
  1. Foydalanuvchi qo'shiq kodi yoki nomini yuboradi -> bot bazadan topib beradi
  2. Qo'shiqni tinglash/yuklab olish uchun Inline tugmalar
  3. Majburiy obuna: kanalga a'zo bo'lmagan foydalanuvchiga qo'shiq berilmaydi
  4. Admin audio yuborib, bazaga yangi qo'shiq qo'shishi mumkin

O'rnatish:
  pip install aiogram==3.* aiosqlite
=====================================================================
"""

import asyncio
import logging

import aiosqlite
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.client.default import DefaultBotProperties

# =====================================================================
# 1. SOZLAMALAR (CONFIG) — o'zingizning ma'lumotlaringizni kiriting
# =====================================================================

BOT_TOKEN = "8918745245:AAF95bqxarrU-rAopPa_w_A_BjJM_F5P8xw"  # @BotFather dan olingan token

# Majburiy obuna bo'lishi kerak bo'lgan kanal
CHANNEL_ID = -1003982672665        # Kanalning ID raqami (bot kanalda admin bo'lishi shart)
CHANNEL_USERNAME = "@kromiddinov_music"  # Kanal username (@ belgisisiz) — obuna tugmasi uchun

# Bazaga qo'shiq qo'shish huquqiga ega bo'lgan adminlar
ADMIN_IDS = [8430954002] # o'z Telegram ID raqamingizni kiriting

DB_NAME = "songs.db"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

# Obunani tasdiqlashni kutayotgan foydalanuvchilarning so'rovlarini vaqtincha saqlaymiz
# {user_id: "qidirilgan_matn"}
pending_requests: dict[int, str] = {}


# =====================================================================
# 2. MA'LUMOTLAR BAZASI (SQLite)
# =====================================================================

async def init_db():
    """Bot ishga tushganda jadval mavjud bo'lmasa, yaratib qo'yamiz."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE,      -- qo'shiqning qisqa kodi (masalan: 001)
                title TEXT,            -- qo'shiq nomi
                file_id TEXT NOT NULL  -- Telegramdagi audio fayl ID si
            )
        """)
        await db.commit()


async def add_song(code: str, title: str, file_id: str):
    """Bazaga yangi qo'shiq qo'shish (admin uchun)."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO songs (code, title, file_id) VALUES (?, ?, ?)",
            (code, title, file_id),
        )
        await db.commit()


async def find_song(query: str):
    """
    Qo'shiqni kod bo'yicha aniq, nomi bo'yicha esa qisman (LIKE) qidiradi.
    Topilsa (code, title, file_id) qaytaradi, topilmasa None.
    """
    async with aiosqlite.connect(DB_NAME) as db:
        # avval kod bo'yicha aniq moslikni tekshiramiz
        cursor = await db.execute(
            "SELECT code, title, file_id FROM songs WHERE code = ?", (query,)
        )
        row = await cursor.fetchone()
        if row:
            return row

        # keyin nomi bo'yicha qisman qidiruv
        cursor = await db.execute(
            "SELECT code, title, file_id FROM songs WHERE title LIKE ? LIMIT 1",
            (f"%{query}%",),
        )
        row = await cursor.fetchone()
        return row


# =====================================================================
# 3. MAJBURIY OBUNANI TEKSHIRISH
# =====================================================================

async def is_subscribed(user_id: int) -> bool:
    """Foydalanuvchi belgilangan kanalga a'zo yoki yo'qligini tekshiradi."""
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        # a'zo, admin yoki creator bo'lsa — obuna bor deb hisoblanadi
        return member.status in (
            ChatMemberStatus.MEMBER,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        )
    except Exception as e:
        logging.warning(f"Obunani tekshirishda xatolik: {e}")
        return False


def subscribe_keyboard() -> InlineKeyboardMarkup:
    """Obuna bo'lish va 'Tekshirish' tugmalari joylashgan klaviatura."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="📢 Kanalga o'tish",
                url=f"https://t.me/{CHANNEL_USERNAME}"
            )],
            [InlineKeyboardButton(
                text="✅ Obunani tekshirish",
                callback_data="check_sub"
            )],
        ]
    )


def song_keyboard(code: str) -> InlineKeyboardMarkup:
    """Qo'shiq bilan birga chiqadigan Inline tugmalar."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="🔁 Qayta yuborish",
                callback_data=f"resend:{code}"
            )],
            [InlineKeyboardButton(
                text="📢 Kanalimiz",
                url=f"https://t.me/{CHANNEL_USERNAME}"
            )],
        ]
    )


# =====================================================================
# 4. QO'SHIQNI FOYDALANUVCHIGA YUBORISH (yordamchi funksiya)
# =====================================================================

async def send_song_to_user(chat_id: int, code: str, title: str, file_id: str):
    """Topilgan qo'shiqni audio formatida, tugmalar bilan yuboradi."""
    await bot.send_audio(
        chat_id=chat_id,
        audio=file_id,
        caption=f"🎵 <b>{title}</b>\nKod: <code>{code}</code>",
        reply_markup=song_keyboard(code),
    )


# =====================================================================
# 5. HANDLERLAR (foydalanuvchi buyruqlari)
# =====================================================================

@router.message(F.audio | F.document)
async def cmd_start(message: Message):
    """/start buyrug'i — botni tanishtirish."""
    await message.answer(
        "👋 Salom! Men <b>Tarona Bot</b>man.\n\n"
        "🔎 Qo'shiqni topish uchun uning <b>kodi</b> yoki <b>nomini</b> yozib yuboring.\n"
        "Masalan: <code>001</code> yoki <i>Sevgi qo'shig'i</i>"
    )


@router.message(Command("add"))
async def cmd_add_hint(message: Message):
    """Admin uchun qo'shiq qo'shish bo'yicha yo'riqnoma."""
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer(
        "🎶 Yangi qo'shiq qo'shish uchun audio faylni quyidagi formatdagi "
        "izoh (caption) bilan yuboring:\n\n"
        "<code>KOD | Qo'shiq nomi</code>\n\n"
        "Masalan: <code>001 | Sevgi qo'shig'i</code>"
    )


@router.message(F.audio | F.document)
async def handle_admin_audio(message: Message):
    """
    Admin audio fayl yuborsa (caption: 'kod | nomi' formatida),
    bot uni bazaga saqlaydi. Oddiy foydalanuvchilar bu funksiyadan
    foydalana olmaydi.
    """
    if message.from_user.id not in ADMIN_IDS:
        return  # admin bo'lmagan foydalanuvchini e'tiborsiz qoldiramiz

    caption = message.caption or ""
    if "|" not in caption:
        await message.answer(
            "⚠️ Iltimos, caption'ni to'g'ri formatda yozing:\n"
            "<code>KOD | Qo'shiq nomi</code>"
        )
        return

    code_part, title_part = caption.split("|", maxsplit=1)
    code = code_part.strip()
    title = title_part.strip()
   file_id = message.audio.file_id if message.audio else message.document.file_id

    await add_song(code=code, title=title, file_id=file_id)
    await message.answer(f"✅ Qo'shiq bazaga qo'shildi!\nKod: <code>{code}</code>\nNomi: {title}")


@router.message(F.text)
async def handle_search(message: Message):
    """
    Oddiy matnli xabarlarni qo'shiq qidiruvi sifatida qabul qilamiz.
    Avval bazadan qidiramiz, so'ng majburiy obunani tekshiramiz.
    """
    query = message.text.strip()
    user_id = message.from_user.id

    song = await find_song(query)
    if not song:
        await message.answer("❌ Bunday qo'shiq topilmadi. Kod yoki nomni tekshirib qayta urinib ko'ring.")
        return

    code, title, file_id = song

    # majburiy obunani tekshiramiz
    if await is_subscribed(user_id):
        await send_song_to_user(message.chat.id, code, title, file_id)
    else:
        # foydalanuvchining so'rovini eslab qolamiz, obunadan so'ng qo'shiqni yuboramiz
        pending_requests[user_id] = code
        await message.answer(
            "🚫 Qo'shiqni olish uchun avval quyidagi kanalga obuna bo'ling, "
            "so'ngra <b>«✅ Obunani tekshirish»</b> tugmasini bosing.",
            reply_markup=subscribe_keyboard(),
        )


# =====================================================================
# 6. CALLBACK (INLINE TUGMA) HANDLERLARI
# =====================================================================

@router.callback_query(F.data == "check_sub")
async def check_subscription_callback(callback: CallbackQuery):
    """'Obunani tekshirish' tugmasi bosilganda ishlaydi."""
    user_id = callback.from_user.id

    if not await is_subscribed(user_id):
        await callback.answer("❗ Siz hali kanalga obuna bo'lmagansiz!", show_alert=True)
        return

    # foydalanuvchi obuna bo'lgan — avvalgi so'rovini topib, qo'shiqni yuboramiz
    code = pending_requests.pop(user_id, None)
    if not code:
        await callback.answer("✅ Obuna tasdiqlandi! Endi qo'shiq kodi yoki nomini yuboring.", show_alert=True)
        return

    song = await find_song(code)
    if song:
        _, title, file_id = song
        await send_song_to_user(callback.message.chat.id, code, title, file_id)
        await callback.message.delete()  # obuna xabarini o'chiramiz
    await callback.answer("✅ Obuna tasdiqlandi!")


@router.callback_query(F.data.startswith("resend:"))
async def resend_song_callback(callback: CallbackQuery):
    """'Qayta yuborish' tugmasi bosilganda qo'shiqni qayta yuboradi."""
    code = callback.data.split(":", maxsplit=1)[1]
    user_id = callback.from_user.id

    if not await is_subscribed(user_id):
        await callback.answer("❗ Siz kanaldan chiqib ketgansiz. Qayta obuna bo'ling.", show_alert=True)
        await callback.message.answer(
            "🚫 Qo'shiqni olish uchun kanalga obuna bo'ling:",
            reply_markup=subscribe_keyboard(),
        )
        return

    song = await find_song(code)
    if song:
        _, title, file_id = song
        await send_song_to_user(callback.message.chat.id, code, title, file_id)
    await callback.answer()


# =====================================================================
# 7. BOTNI ISHGA TUSHIRISH
# =====================================================================

async def main():
    await init_db()
    logging.info("Tarona bot ishga tushdi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
