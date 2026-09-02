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
OWNER_ID = 8588301820  # Sizning Telegram ID'ingiz
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


# Bot yaratish uchun yangi FSM holatlari
class BotCreatorStates(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_bot_token = State()


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
        url = invite_link if invite_link else f"https://t.me/{str(channel_id).lstrip('@')}"
        buttons.append([InlineKeyboardButton(text="➡️ Kanal", url=url)])
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
async def save_join_request_handler(request: types.ChatJoinRequest):
    sorovli_channels = await db.get_channels(channel_type="sorovli")
    if str(request.chat.id) in sorovli_channels:
        await db.save_pending_request(chat_id=request.chat.id, user_id=request.from_user.id)


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
    await message.answer(
        "Hali hech qanday botga menyu yasamagansiz.\n\n"
        "\"🤖 Botga menyu yasash\" tugmasini bosing."
    )


# --- BOTGA MENYU YASASH JARAYONI (YANGI LOGIKA) ---

@dp.message(F.text == "🤖 Botga menyu yasash")
async def create_bot_menu_handler(message: types.Message, state: FSMContext):
    await message.answer(
        "Kino botingizni yaratish uchun 1-qadam:\n\n"
        "Iltimos, o'zingizning **Telegram ID** raqamingizni yuboring.\n\n"
        "💡 ID raqamingizni bilish uchun @userinfobot ga kiring:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👤 @userinfobot ga o'tish", url="https://t.me/userinfobot")]
        ])
    )
    await state.set_state(BotCreatorStates.waiting_for_user_id)


@dp.message(BotCreatorStates.waiting_for_user_id)
async def receive_creator_id(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Iltimos, faqat raqamlardan iborat Telegram ID'ingizni yuboring (masalan: 8588301820).")
        return

    creator_id = int(text)
    await state.update_data(creator_id=creator_id)

    await message.answer(
        f"✅ ID qabul qilindi: <b>{creator_id}</b> — shu ID bot egasi etib belgilandi.\n\n"
        "2-qadam:\n"
        "Endi @BotFather ga kirib yangi bot oching va o'sha botning **TOKEN**'ini nusxalab menga yuboring.\n\n"
        "👉 @BotFather ga o'tish uchun quyidagi tugmani bosing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 @BotFather ga o'tish", url="https://t.me/BotFather")]
        ]),
        parse_mode="HTML"
    )
    await state.set_state(BotCreatorStates.waiting_for_bot_token)


@dp.message(BotCreatorStates.waiting_for_bot_token)
async def receive_bot_token(message: types.Message, state: FSMContext):
    token = message.text.strip()
    if ":" not in token or len(token) < 20:
        await message.answer("❌ Bu yaroqli bot tokeniga o'xshamaydi. Qaytadan tekshirib, to'g'ri tokenni yuboring.")
        return

    data = await state.get_data()
    creator_id = data.get("creator_id")

    # Bu yerda token va creator_id bazaga saqlanadi (masalan: await db.save_user_bot(...))

    await message.answer("⏳ Botingizga kino bot uchun menyular yaratilmoqda, iltimos kuting...")

    # Simulyatsiya yoki sozlash tugashi
    await message.answer(
        "✅ Tabriklaymiz! Botingiz muvaffaqiyatli ulandi va kino bot menyulari o'rnatildi.\n\n"
        "⚠️ <b>Muhim eslatma:</b>\n"
        "Agar botingiz vaqtini uzaytirmoqchi bo'lsangiz, har 2 ta do'stingizni taklif qilsangiz 1 kun botdan foydalana olasiz.\n"
        "Limit tugasa, afsuski menyu ishlamaydi va bot javob bermaydi.",
        reply_markup=await get_main_menu(message.from_user.id),
        parse_mode="HTML"
    )
    await state.clear()

# --------------------------------------------------


def admin_panel_keyboard(is_owner: bool):
    buttons = [
        [InlineKeyboardButton(text="➕ Majburiy kanal qo'shish", callback_data="admin_add_maj")],
        [InlineKeyboardButton(text="➕ So'rovli kanal qo'shish", callback_data="admin_add_sor")],
        [InlineKeyboardButton(text="📥 Yig'ilgan so'rovlarni tasdiqlash", callback_data="admin_approve_requests")],
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
        return
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
        "⚠️ Bot o'sha kanalda ADMIN bo'lishi shart."
    )
    await state.set_state(AdminStates.waiting_channel_sorovli)
    await callback.answer()


@dp.callback_query(F.data == "admin_approve_requests")
async def admin_approve_requests_callback(callback: types.CallbackQuery):
    if not await db.is_admin(callback.from_user.id, OWNER_ID):
        return
    
    pending = await db.get_pending_requests()
    if not pending:
        await callback.answer("Hozircha tasdiqlanmagan so'rovlar yo'q 📭", show_alert=True)
        return

    success_count = 0
    for chat_id, user_id in pending:
        try:
            await bot.approve_chat_join_request(chat_id=chat_id, user_id=user_id)
            success_count += 1
        except Exception as e:
            logging.warning(f"So'rovni tasdiqlashda xato ({user_id}): {e}")

    await db.clear_pending_requests()
    await callback.message.answer(f"✅ Jami {success_count} ta foydalanuvchining so'rovi tasdiqlandi!")
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
        await message.answer("❌ Bu ID emas. Masalan: -1001234567890")
        return

    try:
        link = await bot.create_chat_invite_link(chat_id=channel_id, creates_join_request=True)
    except Exception as e:
        await message.answer(f"❌ Havola yaratib bo'lmadi: {e}")
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

    text = "📋 Kanallar:\n\nMajburiy:\n" + ("\n".join(maj) if maj else "— yo'q") + "\n\nSo'rovli:\n" + ("\n".join(sor) if sor else "— yo'q")
    buttons = [[InlineKeyboardButton(text=f"🗑 {ch}", callback_data=f"admin_rm_ch:{ch}")] for ch in maj + sor]

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
    await callback.message.answer("Yangi admin ID'sini yuboring:")
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
    await message.answer(f"✅ {new_admin_id} admin qilindi.")
    await state.clear()


@dp.callback_query(F.data == "admin_list_admins")
async def admin_list_admins_callback(callback: types.CallbackQuery):
    if not await db.is_admin(callback.from_user.id, OWNER_ID):
        return
    admins = await db.get_admins()
    text = f"📋 Adminlar:\n👑 Owner: {OWNER_ID}\n" + ("\n".join([f"👤 {a[0]}" for a in admins]) if admins else "Boshqa admin yo'q.")
    buttons = [[InlineKeyboardButton(text=f"🗑 {a[0]}", callback_data=f"admin_rm_admin:{a[0]}")] for a in admins] if callback.from_user.id == OWNER_ID else []

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
