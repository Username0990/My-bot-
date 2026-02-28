import os
import telebot
from telebot.types import Message, BusinessConnection
from flask import Flask, request
import psycopg2

TOKEN = os.environ['TELEGRAM_TOKEN']
ADMIN_ID = int(os.environ['ADMIN_ID'])
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

DATABASE_URL = os.getenv('DATABASE_URL') or os.getenv('SCALINGO_POSTGRESQL_URL')
triggers = {}  # lower_trigger: {'original': str, 'reply': str}

def init_db():
    if not DATABASE_URL:
        print("⚠️ Без Postgres — данные в памяти, потеряются при рестарте")
        return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS triggers (
            id SERIAL PRIMARY KEY,
            trigger_phrase TEXT NOT NULL,
            reply_text TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def load_triggers():
    global triggers
    triggers = {}
    if not DATABASE_URL:
        return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT trigger_phrase, reply_text FROM triggers")
    for tp, rt in cur.fetchall():
        triggers[tp.lower()] = {'original': tp, 'reply': rt}
    cur.close()
    conn.close()

def save_trigger(trigger_phrase: str, reply_text: str):
    lower = trigger_phrase.lower()
    triggers[lower] = {'original': trigger_phrase, 'reply': reply_text}
    if not DATABASE_URL:
        return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM triggers WHERE lower(trigger_phrase) = %s", (lower,))
    if cur.fetchone():
        cur.execute("UPDATE triggers SET trigger_phrase = %s, reply_text = %s WHERE lower(trigger_phrase) = %s",
                    (trigger_phrase, reply_text, lower))
    else:
        cur.execute("INSERT INTO triggers (trigger_phrase, reply_text) VALUES (%s, %s)",
                    (trigger_phrase, reply_text))
    conn.commit()
    cur.close()
    conn.close()

def remove_trigger(trigger_phrase: str):
    lower = trigger_phrase.lower()
    if lower in triggers:
        del triggers[lower]
    if not DATABASE_URL:
        return
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM triggers WHERE lower(trigger_phrase) = %s", (lower,))
    conn.commit()
    cur.close()
    conn.close()

# === Админ-команды (обычные сообщения) ===
@bot.message_handler(commands=['start', 'help'])
def welcome(message: Message):
    if message.chat.type != 'private':
        return
    bot.reply_to(message, "🤖 Бот для Telegram Business автоответов\n\n"
                          "/addtrigger триггер :: ответ\n"
                          "/removetrigger триггер\n"
                          "/listtriggers\n"
                          "/myid — показать твой ID")

@bot.message_handler(commands=['myid'])
def show_id(message: Message):
    bot.reply_to(message, f"Твой ID: `{message.from_user.id}`")

@bot.message_handler(commands=['addtrigger'])
def add_trigger_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace('/addtrigger', '', 1).strip()
    if ' :: ' not in text:
        bot.reply_to(message, "Формат: `/addtrigger привет :: Здравствуйте! Чем могу помочь?`")
        return
    trigger, reply = [x.strip() for x in text.split(' :: ', 1)]
    if not trigger or not reply:
        bot.reply_to(message, "Ошибка формата")
        return
    save_trigger(trigger, reply)
    bot.reply_to(message, f"✅ Добавлено:\n{trigger} → {reply}")

@bot.message_handler(commands=['removetrigger'])
def remove_trigger_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    trigger = message.text.replace('/removetrigger', '', 1).strip()
    if not trigger:
        bot.reply_to(message, "Укажи триггер")
        return
    remove_trigger(trigger)
    bot.reply_to(message, f"🗑 Удалено: {trigger}")

@bot.message_handler(commands=['listtriggers'])
def list_triggers_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not triggers:
        bot.reply_to(message, "📭 Нет триггеров")
        return
    txt = "\n".join([f"{info['original']} :: {info['reply']}" for info in triggers.values()])
    bot.reply_to(message, f"📋 Триггеры:\n{txt}")

# === Автоответы для бизнес-чатов ===
@bot.business_message_handler(func=lambda m: True)
def business_auto_reply(message: Message):
    if not message.text or not getattr(message, 'business_connection_id', None):
        return
    msg_text = message.text.strip().lower()
    # Ищем самый длинный совпадающий триггер
    for trig_lower in sorted(triggers.keys(), key=len, reverse=True):
        if trig_lower in msg_text:
            reply = triggers[trig_lower]['reply']
            try:
                bot.send_message(
                    chat_id=message.chat.id,
                    text=reply,
                    business_connection_id=message.business_connection_id
                )
            except Exception as e:
                print("Ошибка отправки:", e)
            return  # только один ответ

# === Business Connection (для логов) ===
@bot.business_connection_handler(func=lambda c: True)
def business_conn_handler(conn: BusinessConnection):
    print(f"🔗 Business connection: {conn.id} | enabled: {conn.is_enabled}")

# === Webhook для Scalingo ===
@app.route(f'/{TOKEN}', methods=['POST'])
def telegram_webhook():
    json_str = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/set_webhook')
def set_webhook():
    base = request.host_url.rstrip('/')
    url = f"{base}/{TOKEN}"
    bot.remove_webhook()
    success = bot.set_webhook(
        url=url,
        allowed_updates=['message', 'business_message', 'business_connection']
    )
    return f"✅ Webhook установлен на {url}<br>Success: {success}"

# Инициализация
init_db()
load_triggers()
print("🚀 Бот запущен")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
