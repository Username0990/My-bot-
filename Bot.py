import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command
import json
import os

TOKEN = "7520071050:AAHh-HgTGESpL6aOhwi7QJDF92gId9pavys"
ALLOWED_CHAT_ID = -2550160088  # ID нужного чата

bot = Bot(token=TOKEN)
dp = Dispatcher()

TRIGGERS_FILE = "triggers.json"

# Загрузка триггеров
def load_triggers():
    if os.path.exists(TRIGGERS_FILE):
        with open(TRIGGERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# Сохранение
def save_triggers(data):
    with open(TRIGGERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

triggers = load_triggers()

# Команда добавления триггера
@dp.message(Command("addtrigger"))
async def add_trigger(message: Message):
    if message.chat.id != ALLOWED_CHAT_ID:
        return

    try:
        text = message.text.replace("/addtrigger ", "")
        trigger, response = text.split("|", 1)
        trigger = trigger.strip().lower()
        response = response.strip()

        triggers[trigger] = response
        save_triggers(triggers)

        await message.answer("✅ Триггер добавлен!")
    except:
        await message.answer("Используй формат:\n/addtrigger слово | ответ")

# Автоответ
@dp.message(F.text)
async def auto_reply(message: Message):
    if message.chat.id != ALLOWED_CHAT_ID:
        return

    text = message.text.lower()
    if text in triggers:
        await message.answer(triggers[text])

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())