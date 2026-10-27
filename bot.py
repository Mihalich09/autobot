import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ChatMemberStatus

# --- НАСТРОЙКИ ---
BOT_TOKEN = '8716212766:AAFaBk0dkVUzvODObE44P2ffWYrkm8XZkCI' 
GAME_URL = 'https://mihalich09.github.io/autoempiremiksss.github.io/' 
CHANNEL_LINK = 'https://t.me/+CyFuSUhjoHo0YzUy' 
CHANNEL_ID = -1003965970211 

IMAGE_STOP = 'https://i.postimg.cc/Kcn976rM/photo-2026-10-27-19-27-28.jpg' 
IMAGE_SUCCESS = 'https://i.postimg.cc/DwtsMZ7X/photo-2026-10-27-19-41-48.jpg'

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Функция проверки подписки
async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in [ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.MEMBER]:
            return True
        if member.status == ChatMemberStatus.RESTRICTED and member.is_member:
            return True
        return False
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False

@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    if await check_sub(message.from_user.id):
        await send_success(message)
    else:
        await send_sub_prompt(message)

@dp.callback_query(F.data == "check_sub")
async def check_cb(callback: types.CallbackQuery):
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await send_success(callback.message)
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)

async def send_sub_prompt(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 ПОДПИШИСЬ", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался, проверить", callback_data="check_sub")]
    ])
    await message.answer_photo(
        photo=IMAGE_STOP,
        caption=f"Для начала игры подпишись на наш канал с новостями:\n\n– {CHANNEL_LINK}",
        reply_markup=kb
    )

async def send_success(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Играть", web_app=WebAppInfo(url=GAME_URL))]
    ])
    await message.answer_photo(
        photo=IMAGE_SUCCESS,
        caption="🔥 <b>Спасибо за подписку!</b>\nТеперь ты можешь начинать играть! Удачи в развитии!",
        reply_markup=kb, parse_mode="HTML"
    )

# --- ЗАГЛУШКА ДЛЯ RENDER (чтобы сервис не засыпал) ---
async def handle(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render выдает порт автоматически
    port = int(os.environ.get('PORT', 8080)) 
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    logging.basicConfig(level=logging.INFO)
    # Удаляем вебхук на всякий случай
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен и готов к работе!")
    
    # Запускаем одновременно бота и веб-сервер
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())
    # restart
