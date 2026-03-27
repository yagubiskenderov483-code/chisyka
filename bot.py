import asyncio
import logging
from telethon import TelegramClient
from telethon.tl.functions.messages import DeleteMessagesRequest, GetDialogsRequest
from telethon.tl.types import InputPeerEmpty
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========================
API_ID = 28687552
API_HASH = "1abf9a58d0c22f62437bec89bd6b27a3"
BOT_TOKEN = "8676951864:AAGYpllQTYN4s99VAkfsffU4XhJkafdeBYw"
ADMIN_ID = [174415647, 6250429823]
SESSION_NAME = "session"
# ========================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
tg_client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

is_deleting = False

class Auth(StatesGroup):
    phone = State()
    code = State()
    password = State()

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить все мои сообщения", callback_data="delete_all")],
    ])

def stop_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏹ Стоп", callback_data="stop_delete")],
    ])

@dp.message(Command("start"))
async def cmd_start(message: Message, state: 
    await state.clear()
if message.from_user.id not in ADMIN_IDS:
    return
    authorized = False
    try:
        if tg_client.is_connected():
            authorized = await tg_client.is_user_authorized()
    except Exception:
        pass

    if not authorized:
        await message.answer(
            "📱 Введи номер телефона: <code>+79001234567</code>",
            parse_mode="HTML"
        )
        await state.set_state(Auth.phone)
        return

    await message.answer("👇 Выбери действие:", reply_markup=main_kb())

@dp.message(Auth.phone)
async def auth_phone(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    phone = message.text.strip()
    try:
        if not tg_client.is_connected():
            await tg_client.connect()
        result = await tg_client.send_code_request(phone)
        await state.update_data(phone=phone, phone_code_hash=result.phone_code_hash)
        await state.set_state(Auth.code)
        await message.answer("📨 Введи код из Telegram:")
    except Exception as e:
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")
        await state.clear()

@dp.message(Auth.code)
async def auth_code(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    try:
        await tg_client.sign_in(phone=data["phone"], code=code, phone_code_hash=data["phone_code_hash"])
        me = await tg_client.get_me()
        await state.clear()
        await message.answer(f"✅ Авторизован как @{me.username or me.first_name}", reply_markup=main_kb())
    except SessionPasswordNeededError:
        await state.set_state(Auth.password)
        await message.answer("🔐 Введи пароль 2FA:")
    except Exception as e:
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")
        await state.clear()

@dp.message(Auth.password)
async def auth_password(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        await tg_client.sign_in(password=message.text.strip())
        me = await tg_client.get_me()
        await state.clear()
        await message.answer(f"✅ Авторизован как @{me.username or me.first_name}", reply_markup=main_kb())
    except Exception as e:
        await message.answer(f"❌ Ошибка: <code>{e}</code>", parse_mode="HTML")

@dp.callback_query(F.data == "delete_all")
async def cb_delete_all(callback: CallbackQuery):
    global is_deleting
    if is_deleting:
        await callback.answer("⏳ Уже идёт удаление!", show_alert=True)
        return

    is_deleting = True
    await callback.answer()

    status = await callback.message.answer(
        "🗑 Начинаю удаление...\n📊 Чатов обработано: 0\n✅ Удалено сообщений: 0",
        reply_markup=stop_kb()
    )

    me = await tg_client.get_me()
    total_deleted = 0
    chats_done = 0

    try:
        async for dialog in tg_client.iter_dialogs():
            if not is_deleting:
                break

            try:
                msg_ids = []
                async for msg in tg_client.iter_messages(dialog.id, from_user=me.id):
                    if not is_deleting:
                        break
                    msg_ids.append(msg.id)
                    if len(msg_ids) >= 100:
                        await tg_client(DeleteMessagesRequest(msg_ids, revoke=True))
                        total_deleted += len(msg_ids)
                        msg_ids = []

                if msg_ids:
                    await tg_client(DeleteMessagesRequest(msg_ids, revoke=True))
                    total_deleted += len(msg_ids)

                chats_done += 1

                try:
                    await status.edit_text(
                        f"🗑 Удаляю сообщения...\n"
                        f"📂 Чат: {dialog.name[:30]}\n"
                        f"📊 Чатов обработано: {chats_done}\n"
                        f"✅ Удалено сообщений: {total_deleted}",
                        reply_markup=stop_kb()
                    )
                except Exception:
                    pass

                await asyncio.sleep(0.5)

            except FloodWaitError as e:
                await asyncio.sleep(e.seconds + 1)
            except Exception as e:
                logger.error(f"Ошибка в чате {dialog.name}: {e}")
                continue

    finally:
        is_deleting = False

    await status.edit_text(
        f"✅ <b>Готово!</b>\n\n"
        f"📊 Чатов обработано: <b>{chats_done}</b>\n"
        f"🗑 Удалено сообщений: <b>{total_deleted}</b>",
        parse_mode="HTML",
        reply_markup=main_kb()
    )

@dp.callback_query(F.data == "stop_delete")
async def cb_stop(callback: CallbackQuery):
    global is_deleting
    is_deleting = False
    await callback.answer("⏹ Останавливаю...")

async def main():
    await tg_client.connect()
    try:
        await dp.start_polling(bot)
    finally:
        await tg_client.disconnect()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
