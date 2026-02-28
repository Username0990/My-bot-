import os
import json
import requests
from flask import Flask, request

# Получаем токен из переменной окружения (Scalingo)
TOKEN = os.environ.get("BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{TOKEN}/"

# Хранилище триггеров
if os.path.exists("triggers.json"):
    with open("triggers.json", "r") as f:
        triggers = json.load(f)
else:
    triggers = {}

app = Flask(__name__)

def save_triggers():
    with open("triggers.json", "w") as f:
        json.dump(triggers, f)

def send_message(chat_id, text):
    requests.post(f"{API_URL}sendMessage", data={"chat_id": chat_id, "text": text})

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")

        # Добавление триггера через ЛС бота
        if text.startswith("/addtrigger"):
            try:
                _, payload = text.split(" ", 1)
                trigger, response = payload.split("|", 1)
                triggers[trigger.strip()] = response.strip()
                save_triggers()
                send_message(chat_id, f"✅ Триггер добавлен:\n{trigger.strip()} → {response.strip()}")
            except ValueError:
                send_message(chat_id, "❌ Используй: /addtrigger триггер | ответ")
            return "ok"

        # Автоответ
        for trig, resp in triggers.items():
            if trig.lower() in text.lower():
                send_message(chat_id, resp)
                break

    return "ok"

@app.route("/")
def index():
    return "Bot is running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
