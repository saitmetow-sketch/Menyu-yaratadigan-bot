import os
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

logging.basicConfig(level=logging.INFO)

# Token va manzillar Render'dagi "Environment Variables" bo'limidan olinadi
TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_HOST = os.environ.get("RENDER_EXTERNAL_URL")  # Render avtomatik beradi
WEBHOOK_PATH = f"/webhook/{TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

PORT = int(os.environ.get("PORT", 10000))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Asosiy menyu tugmalari
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📋 Xizmatlar"), KeyboardButton(text="💰 Narxlar")],
        [KeyboardButton(text="📞 Aloqa")]
    ],
    resize_keyboard=True
)


@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("Assalomu alaykum! Menyudan birini tanlang:", reply_markup=main_menu)


@dp.message(lambda m: m.text == "📋 Xizmatlar")
async def services_handler(message: types.Message):
    await message.answer("Bizning xizmatlar:\n- Xizmat 1\n- Xizmat 2\n- Xizmat 3")


@dp.message(lambda m: m.text == "💰 Narxlar")
async def prices_handler(message: types.Message):
    await message.answer("Narxlarimiz:\n- Boshlang'ich: 100 000 so'm\n- Standart: 250 000 so'm")


@dp.message(lambda m: m.text == "📞 Aloqa")
async def contact_handler(message: types.Message):
    await message.answer("Bog'lanish uchun: @sizning_username")


async def health_check(request):
    # Render'ning "hayotdami" tekshiruvi shu manzilga kiradi
    return web.Response(text="Bot ishlayapti!")


async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook o'rnatildi: {WEBHOOK_URL}")


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()


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

