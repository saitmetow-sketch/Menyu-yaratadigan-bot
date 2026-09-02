import os
import logging

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

import db

logging.basicConfig(level=logging.INFO)

TOKEN = os.environ.get("BOT_TOKEN")
OWNER_ID = 8588301820  # Sizning Telegram ID'ingiz (owner)
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get("PORT", 10000))

bot = Bot(token=TOKEN)
dp = Dispatcher()


async def check_subscription(user_id: int) -> bool:
    channels = await db.get_channels(channel_type="majburiy")
    for channel_id in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logging.warning(f"Kanal tekshirishda xato: {channel_id} — {e}")
            return False
    return True


def subscribe_keyboard(channels):
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(text=f"➡️ {ch}", url=f"https://t.me/{ch.lstrip('@')}")])
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🤖 Botga menyu yasash")],
        [KeyboardButton(text="📋 Botlarim menyusi")],
        [KeyboardButton(text="⏳ Vaqtni uzaytirish")],
    ],
    resize_keyboard=True
)


@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""

    referred_by = None
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            referred_by = ref_id

    await db.add_user_if_new(user_id, username, referred_by)

    channels = await db.get_channels(channel_type="majburiy")
    if channels:
        subscribed = await check_subscription(user_id)
        if not subscribed:
            await message.answer(
                "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, "
                "so'ng \"✅ Tekshirish\" tugmasini bosing:",
                reply_markup=subscribe_keyboard(channels)
            )
            return

    await message.answer("Assalomu alaykum! Xush kelibsiz 👇", reply_markup=main_menu)


@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    subscribed = await check_subscription(user_id)
    if subscribed:
        await callback.message.delete()
        await callback.message.answer("Rahmat! Endi botdan foydalanishingiz mumkin 👇", reply_markup=main_menu)
    else:
        await callback.answer("Siz hali barcha kanallarga obuna bo'lmagansiz ❌", show_alert=True)


@dp.message(F.text == "⏳ Vaqtni uzaytirish")
async def extend_time_handler(message: types.Message):
    user_id = message.from_user.id
    remaining = await db.get_remaining_days(user_id)
    me = await bot.me()
    ref_link = f"https://t.me/{me.username}?start={user_id}"
    await message.answer(
        f"⏳ Sizda {remaining} kun qoldi.\n\n"
        f"Har 2 ta do'stingizni taklif qilsangiz, +1 kun qo'shiladi!\n\n"
        f"🔗 Sizning taklif havolangiz:\n{ref_link}"
    )


@dp.message(F.text == "📋 Botlarim menyusi")
async def my_bots_handler(message: types.Message):
    # Bu qism keyingi bosqichda to'ldiriladi: foydalanuvchi yasagan botlar ro'yxati
    await message.answer(
        "Hali hech qanday botga menyu yasamagansiz.\n\n"
        "\"🤖 Botga menyu yasash\" tugmasini bosing."
    )


@dp.message(F.text == "🤖 Botga menyu yasash")
async def create_bot_menu_handler(message: types.Message):
    await message.answer(
        "Yangi bot yaratish uchun:\n\n"
        "1️⃣ @BotFather ga kiring\n"
        "2️⃣ /newbot deb yozing\n"
        "3️⃣ Botingizga nom bering\n"
        "4️⃣ Username bering (oxiri \"bot\" bilan tugashi kerak)\n"
        "5️⃣ Sizga TOKEN beriladi — o'sha tokenni shu yerga yuboring\n\n"
        "⚠️ Keyin o'zingizning Telegram ID'ingizni ham yuborishingiz kerak bo'ladi "
        "(bot egasi ekaningizni tasdiqlash uchun).\n\n"
        "(Token qabul qilish va botni ishga tushirish keyingi bosqichda qo'shiladi)"
    )


async def on_startup(app: web.Application):
    await db.init_db()
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook o'rnatildi: {WEBHOOK_URL}")


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()


async def health_check(request):
    return web.Response(text="Bot ishlayapti!")


def main():
    app = web.Application()
    app.router.add_get("/", health_check)
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
