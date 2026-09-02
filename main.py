import os
import logging

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
dp = Dispatcher(storage=MemoryStorage())


class AdminStates(StatesGroup):
    waiting_channel_majburiy = State()
    waiting_channel_sorovli = State()
    waiting_admin_id = State()


async def check_subscription(user_id: int) -> bool:
    channels = await db.get_channels(channel_type="majburiy") + await db.get_channels(channel_type="sorovli")
    for channel_id in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status in ("left", "kicked"):
                return False
        except Exception as e:
            logging.warning(f"Kanal tekshirishda xato: {channel_id} — {e}")
            return False
    return True


async def get_all_channels_full():
    maj = await db.get_channels_full("majburiy")
    sor = await db.get_channels_full("sorovli")
    return maj + sor


def subscribe_keyboard(channels_full):
    buttons = []
    for channel_id, invite_link in channels_full:
        if invite_link:
            url = invite_link
        else:
            url = f"https://t.me/{str(channel_id).lstrip('@')}"
        buttons.append([InlineKeyboardButton(text=f"➡️ Kanal", url=url)])
    buttons.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_main_menu(user_id: int):
    keyboard = [
        [KeyboardButton(text="🤖 Botga menyu yasash")],
        [KeyboardButton(text="📋 Botlarim menyusi")],
        [KeyboardButton(text="⏳ Vaqtni uzaytirish")],
    ]
    if await db.is_admin(user_id, OWNER_ID):
        keyboard.append([KeyboardButton(text="🔧 Admin panel")])
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


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

    channels_full = await get_all_channels_full()
    if channels_full:
        subscribed = await check_subscription(user_id)
        if not subscribed:
            await message.answer(
                "Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling, "
                "so'ng \"✅ Tekshirish\" tugmasini bosing:",
                reply_markup=subscribe_keyboard(channels_full)
            )
            return

    await message.answer("Assalomu alaykum! Xush kelibsiz 👇", reply_markup=await get_main_menu(user_id))


@dp.chat_join_request()
async def auto_approve_join_request(request: types.ChatJoinRequest):
    sorovli_channels = await db.get_channels(channel_type="sorovli")
    if str(request.chat.id) in sorovli_channels:
        try:
            await bot.approve_chat_join_request(chat_id=request.chat.id, user_id=request.from_user.id)
        except Exception as e:
            logging.warning(f"So'rovni tasdiqlashda xato: {e}")


@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    subscribed = await check_subscription(user_id)
    if subscribed:
        await callback.message.delete()
        await callback.message.answer("Rahmat! Endi botdan foydalanishingiz mumkin 👇", reply_markup=await get_main_menu(user_id))
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


def admin_panel_keyboard(is_owner: bool):
    buttons = [
        [InlineKeyboardButton(text="➕ Majburiy kanal qo'shish", callback_data="admin_add_maj")],
        [InlineKeyboardButton(text="➕ So'rovli kanal qo'shish", callback_data="admin_add_sor")],
        [InlineKeyboardButton(text="📋 Kanallar ro'yxati", callback_data="admin_list_channels")],
    ]
    if is_owner:
        buttons.append([InlineKeyboardButton(text="👤 Admin qo'shish", callback_data="admin_add_admin")])
    buttons.append([InlineKeyboardButton(text="📋 Adminlar ro'yxati", callback_data="admin_list_admins")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("admin"))
async def admin_panel_handler(message: types.Message):
    user_id = message.from_user.id
    if not await db.is_admin(user_id, OWNER_ID):
        return  # admin bo'lmagan odamga hech narsa ko'rsatilmaydi
    is_owner = user_id == OWNER_ID
    await message.answer("🔧 Admin panel:", reply_markup=admin_panel_keyboard(is_owner))


@dp.message(F.text == "🔧 Admin panel")
async def admin_panel_button_handler(message: types.Message):
    await admin_panel_handler(message)


@dp.callback_query(F.data == "admin_add_maj")
async def admin_add_maj_callback(callback: types.CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id, OWNER_ID):
        return
    await callback.message.answer("Majburiy kanal username'ini yuboring (masalan: @mening_kanalim):")
    await state.set_state(AdminStates.waiting_channel_majburiy)
    await callback.answer()


@dp.callback_query(F.data == "admin_add_sor")
async def admin_add_sor_callback(callback: types.CallbackQuery, state: FSMContext):
    if not await db.is_admin(callback.from_user.id, OWNER_ID):
        return
    await callback.message.answer(
        "So'rovli kanalning ID'sini yuboring (masalan: -1001234567890).\n\n"
        "⚠️ Bot o'sha kanalda ADMIN bo'lishi shart (invite link yaratish huquqi bilan)."
    )
    await state.set_state(AdminStates.waiting_channel_sorovli)
    await callback.answer()


@dp.message(AdminStates.waiting_channel_majburiy)
async def receive_channel_majburiy(message: types.Message, state: FSMContext):
    channel = message.text.strip()
    await db.add_channel(channel, "majburiy")
    await message.answer(f"✅ {channel} majburiy kanallar ro'yxatiga qo'shildi.")
    await state.clear()


@dp.message(AdminStates.waiting_channel_sorovli)
async def receive_channel_sorovli(message: types.Message, state: FSMContext):
    channel_id = message.text.strip()

    if not (channel_id.lstrip("-").isdigit()):
        await message.answer("❌ Bu ID emas. Kanal ID'si masalan shunday ko'rinishda bo'ladi: -1001234567890")
        return

    try:
        link = await bot.create_chat_invite_link(chat_id=channel_id, creates_join_request=True)
    except Exception as e:
        await message.answer(
            f"❌ Havola yaratib bo'lmadi: {e}\n\n"
            "Bot o'sha kanalda ADMIN ekanligiga va 'foydalanuvchilarni taklif qilish' huquqi borligiga ishonch hosil qiling."
        )
        await state.clear()
        return

    await db.add_channel(channel_id, "sorovli", invite_link=link.invite_link)
    await message.answer(f"✅ Kanal qo'shildi.\nHavola: {link.invite_link}")
    await state.clear()


@dp.callback_query(F.data == "admin_list_channels")
async def admin_list_channels_callback(callback: types.CallbackQuery):
    if not await db.is_admin(callback.from_user.id, OWNER_ID):
        return
    maj = await db.get_channels("majburiy")
    sor = await db.get_channels("sorovli")

    text = "📋 Kanallar:\n\n"
    text += "Majburiy:\n" + ("\n".join(maj) if maj else "— yo'q") + "\n\n"
    text += "So'rovli:\n" + ("\n".join(sor) if sor else "— yo'q")

    buttons = []
    for ch in maj + sor:
        buttons.append([InlineKeyboardButton(text=f"🗑 {ch}", callback_data=f"admin_rm_ch:{ch}")])

    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None)
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_rm_ch:"))
async def admin_remove_channel_callback(callback: types.CallbackQuery):
    if not await db.is_admin(callback.from_user.id, OWNER_ID):
        return
    channel = callback.data.split(":", 1)[1]
    await db.remove_channel(channel)
    await callback.message.answer(f"❌ {channel} o'chirildi.")
    await callback.answer()


@dp.callback_query(F.data == "admin_add_admin")
async def admin_add_admin_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Bu faqat owner uchun ⛔", show_alert=True)
        return
    await callback.message.answer("Yangi admin qilmoqchi bo'lgan odamning Telegram ID'sini yuboring:")
    await state.set_state(AdminStates.waiting_admin_id)
    await callback.answer()


@dp.message(AdminStates.waiting_admin_id)
async def receive_admin_id(message: types.Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        await state.clear()
        return
    if not message.text.strip().isdigit():
        await message.answer("❌ Faqat raqam (ID) yuboring.")
        return
    new_admin_id = int(message.text.strip())
    await db.add_admin(new_admin_id, added_by=message.from_user.id)
    await message.answer(f"✅ {new_admin_id} admin qilib qo'shildi.")
    await state.clear()


@dp.callback_query(F.data == "admin_list_admins")
async def admin_list_admins_callback(callback: types.CallbackQuery):
    if not await db.is_admin(callback.from_user.id, OWNER_ID):
        return
    is_owner = callback.from_user.id == OWNER_ID
    admins = await db.get_admins()

    text = "📋 Adminlar:\n\n"
    text += f"👑 Owner: {OWNER_ID}\n"
    if admins:
        for admin_id, added_by in admins:
            text += f"👤 {admin_id}\n"
    else:
        text += "Boshqa admin yo'q."

    buttons = []
    if is_owner:
        for admin_id, added_by in admins:
            buttons.append([InlineKeyboardButton(text=f"🗑 {admin_id}", callback_data=f"admin_rm_admin:{admin_id}")])

    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None)
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_rm_admin:"))
async def admin_remove_admin_callback(callback: types.CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Bu faqat owner uchun ⛔", show_alert=True)
        return
    admin_id = int(callback.data.split(":", 1)[1])
    await db.remove_admin(admin_id)
    await callback.message.answer(f"❌ {admin_id} adminlikdan olindi.")
    await callback.answer()


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
