import asyncio
import json
import logging
import os
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.enums import ChatMemberStatus
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ['BOT_TOKEN']

# ID админов бота (по умолчанию — ваши два). Можно переопределить через ADMIN_IDS в окружении.
DEFAULT_ADMIN_IDS = "5228482650,8847824933"
ADMIN_IDS = {
    int(x.strip())
    for x in os.environ.get('ADMIN_IDS', DEFAULT_ADMIN_IDS).split(',')
    if x.strip().lstrip('-').isdigit()
}

GAME_URL = os.environ.get(
    'GAME_URL',
    'https://mihalich09.github.io/autoempiremiksss.githab.io/?v=3'
)

CHANNEL_LINK = 'https://t.me/+CyFuSUhjoHo0YzUy'
CHANNEL_ID = -1003965970211

IMAGE_STOP = 'https://i.postimg.cc/Kcn976rM/photo-2026-10-27-19-27-28.jpg'
IMAGE_SUCCESS = 'https://i.postimg.cc/DwtsMZ7X/photo-2026-10-27-19-41-48.jpg'

USERS_FILE = Path(os.environ.get('USERS_FILE', 'users.json'))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
broadcast_lock = asyncio.Lock()


# --- ХРАНИЛИЩЕ ПОЛЬЗОВАТЕЛЕЙ ---
def load_users() -> set[int]:
    if not USERS_FILE.exists():
        return set()
    try:
        data = json.loads(USERS_FILE.read_text(encoding='utf-8'))
        return {int(uid) for uid in data}
    except Exception as e:
        logging.error(f"Ошибка чтения {USERS_FILE}: {e}")
        return set()


def save_users(users: set[int]) -> None:
    try:
        USERS_FILE.write_text(json.dumps(sorted(users)), encoding='utf-8')
    except Exception as e:
        logging.error(f"Ошибка записи {USERS_FILE}: {e}")


def add_user(user_id: int) -> None:
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        save_users(users)


# --- ПРОВЕРКА ПОДПИСКИ ---
async def check_sub(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in [
            ChatMemberStatus.CREATOR,
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.MEMBER,
        ]:
            return True
        if member.status == ChatMemberStatus.RESTRICTED and member.is_member:
            return True
        return False
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False


@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    add_user(message.from_user.id)
    if await check_sub(message.from_user.id):
        await send_success(message)
    else:
        await send_sub_prompt(message)


@dp.callback_query(F.data == "check_sub")
async def check_cb(callback: types.CallbackQuery):
    add_user(callback.from_user.id)
    if await check_sub(callback.from_user.id):
        await callback.message.delete()
        await send_success(callback.message)
    else:
        await callback.answer("❌ Вы еще не подписались на канал!", show_alert=True)


async def send_sub_prompt(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 ПОДПИШИСЬ", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Я подписался, проверить", callback_data="check_sub")],
    ])
    await message.answer_photo(
        photo=IMAGE_STOP,
        caption=f"Для начала игры подпишись на наш канал с новостями:\n\n– {CHANNEL_LINK}",
        reply_markup=kb,
    )


async def send_success(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 Играть", web_app=WebAppInfo(url=GAME_URL))]
    ])
    await message.answer_photo(
        photo=IMAGE_SUCCESS,
        caption="🔥 <b>Спасибо за подписку!</b>\nТеперь ты можешь начинать играть! Удачи в развитии!",
        reply_markup=kb,
        parse_mode="HTML",
    )


# --- РАССЫЛКА /all ---
class Broadcast(StatesGroup):
    waiting_text = State()


@dp.message(Command("all"))
async def cmd_all(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1 and parts[1].strip():
        await broadcast(message, parts[1].strip())
        return

    await state.set_state(Broadcast.waiting_text)
    await message.answer(
        "📝 Отправьте текст, который бот разошлёт всем пользователям.\n\n"
        "Отмена — /cancel"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: types.Message, state: FSMContext):
    if await state.get_state() is None:
        return
    await state.clear()
    await message.answer("❌ Действие отменено.")


@dp.message(Broadcast.waiting_text)
async def do_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await broadcast(message, message.text or "")


async def broadcast(message: types.Message, text: str):
    text = text.strip()
    if not text:
        await message.answer("Пустой текст — рассылка отменена.")
        return

    users = load_users()
    if not users:
        await message.answer("Список пользователей пуст. Пользователи появятся после /start.")
        return

    if broadcast_lock.locked():
        await message.answer("⏳ Рассылка уже выполняется, подождите.")
        return

    async with broadcast_lock:
        status = await message.answer(f"⏳ Рассылка: 0/{len(users)}")
        sent = failed = blocked = 0
        to_remove: set[int] = set()

        for i, uid in enumerate(users, 1):
            try:
                await bot.send_message(uid, text)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
                to_remove.add(uid)
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await bot.send_message(uid, text)
                    sent += 1
                except Exception:
                    failed += 1
            except Exception as e:
                failed += 1
                logging.error(f"Ошибка отправки {uid}: {e}")

            await asyncio.sleep(0.05)  # антифлуд ~20 сообщений/сек

            if i % 25 == 0:
                try:
                    await status.edit_text(
                        f"📤 {i}/{len(users)}\n"
                        f"✅ {sent}  🚫 {blocked}  ❌ {failed}"
                    )
                except Exception:
                    pass

        if to_remove:
            save_users(users - to_remove)

        await status.edit_text(
            f"✅ <b>Рассылка завершена</b>\n\n"
            f"Всего получателей: {len(users)}\n"
            f"Отправлено: <b>{sent}</b>\n"
            f"Заблокировали бота: <b>{blocked}</b>\n"
            f"Ошибок: <b>{failed}</b>",
            parse_mode="HTML",
        )


# --- WEB SERVER ---
async def handle(request):
    return web.Response(text="Bot is running!")


async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()


async def main():
    logging.basicConfig(level=logging.INFO)
    await bot.delete_webhook(drop_pending_updates=True)

    print(f"Админы бота: {ADMIN_IDS}")
    print("Бот запущен и готов к работе!")

    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server(),
    )


if __name__ == "__main__":
    asyncio.run(main())