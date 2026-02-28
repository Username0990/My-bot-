import os
import logging
import asyncpg
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена и URL базы данных из переменных окружения
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not TOKEN:
    raise ValueError("No TELEGRAM_BOT_TOKEN found in environment variables")
if not DATABASE_URL:
    raise ValueError("No DATABASE_URL found in environment variables")


# Функции для работы с БД
async def init_db():
    """Создаёт таблицу triggers, если её нет"""
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS triggers (
            id SERIAL PRIMARY KEY,
            keyword TEXT UNIQUE NOT NULL,
            response TEXT NOT NULL
        )
    """)
    await conn.close()


async def add_trigger_to_db(keyword: str, response: str) -> bool:
    """Добавляет триггер в БД. Возвращает True, если успешно, иначе False (дубликат)"""
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await conn.execute(
            "INSERT INTO triggers (keyword, response) VALUES ($1, $2)",
            keyword.lower(), response
        )
        return True
    except asyncpg.UniqueViolationError:
        return False
    finally:
        await conn.close()


async def remove_trigger_from_db(keyword: str) -> bool:
    """Удаляет триггер из БД. Возвращает True, если удалён, иначе False"""
    conn = await asyncpg.connect(DATABASE_URL)
    result = await conn.execute("DELETE FROM triggers WHERE keyword = $1", keyword.lower())
    await conn.close()
    return result != "DELETE 0"


async def get_all_triggers():
    """Возвращает все триггеры в виде списка кортежей (keyword, response)"""
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT keyword, response FROM triggers ORDER BY id")
    await conn.close()
    return [(row["keyword"], row["response"]) for row in rows]


async def get_response_for_keyword(word: str) -> str | None:
    """Ищет ответ по ключевому слову (регистронезависимо)"""
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("SELECT response FROM triggers WHERE keyword = $1", word.lower())
    await conn.close()
    return row["response"] if row else None


# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветственное сообщение и справка"""
    await update.message.reply_text(
        "Привет! Я бот-триггер.\n"
        "Команды (только в личных сообщениях):\n"
        "/addtrigger <слово> <ответ> – добавить триггер\n"
        "/removetrigger <слово> – удалить триггер\n"
        "/listtriggers – показать все триггеры\n\n"
        "После добавления я буду отвечать на указанное слово в любом чате, где нахожусь."
    )


async def add_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавляет новый триггер. Доступно только в ЛС."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("Эта команда работает только в личных сообщениях.")
        return

    # Разбираем аргументы: первое слово – ключ, остальное – ответ
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /addtrigger <слово> <ответ>")
        return

    keyword = args[0]
    response = " ".join(args[1:])

    success = await add_trigger_to_db(keyword, response)
    if success:
        await update.message.reply_text(f"Триггер '{keyword}' добавлен!")
    else:
        await update.message.reply_text(f"Триггер '{keyword}' уже существует.")


async def remove_trigger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет триггер. Доступно только в ЛС."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("Эта команда работает только в личных сообщениях.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /removetrigger <слово>")
        return

    keyword = context.args[0]
    removed = await remove_trigger_from_db(keyword)
    if removed:
        await update.message.reply_text(f"Триггер '{keyword}' удалён.")
    else:
        await update.message.reply_text(f"Триггер '{keyword}' не найден.")


async def list_triggers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает все сохранённые триггеры. Доступно только в ЛС."""
    if update.effective_chat.type != "private":
        await update.message.reply_text("Эта команда работает только в личных сообщениях.")
        return

    triggers = await get_all_triggers()
    if not triggers:
        await update.message.reply_text("Список триггеров пуст.")
        return

    lines = [f"{kw} → {resp}" for kw, resp in triggers]
    await update.message.reply_text("Текущие триггеры:\n" + "\n".join(lines))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает все текстовые сообщения и ищет триггеры."""
    # Игнорируем сообщения без текста (стикеры, фото и т.д.)
    if not update.message or not update.message.text:
        return

    text = update.message.text.lower()
    words = text.split()

    # Проверяем каждое слово сообщения на совпадение с ключевым словом
    for word in words:
        response = await get_response_for_keyword(word)
        if response:
            await update.message.reply_text(response)
            # Можно прервать после первого совпадения или отвечать на все.
            # Здесь прерываем, чтобы не флудить, если несколько ключей в одном сообщении.
            break


def main():
    """Запуск бота"""
    # Инициализация базы данных
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

    # Создание приложения
    application = Application.builder().token(TOKEN).build()

    # Регистрация обработчиков команд (работают везде, но мы ограничили логикой внутри)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addtrigger", add_trigger))
    application.add_handler(CommandHandler("removetrigger", remove_trigger))
    application.add_handler(CommandHandler("listtriggers", list_triggers))

    # Обработчик всех текстовых сообщений (для поиска триггеров)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запуск бота (polling)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
