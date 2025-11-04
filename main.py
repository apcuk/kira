# main.py
# заметки для ИИ, который будет править этот код:
#           - никода не удаляй и не редактируй коментарии. добавлять можно.
#           - старайся не менять структуру кода без особой необходимости, или изменяй минимально.
#           - придерживайся стиля.
#           - называй функции логично и максимально информативно.

# v.3.01    - заложена архитектура обмена сообщениями: фронтент <-> менеджер <-> ядро <-> менеджер <-> фронтенд.
#           - внедрена система тройных кортежей (source, author, message) для маркировки сообщений.
#           - реализован Telegram-фронтенд.
#           - обработка сообщений от пользователя на уровне простого ЭХО.
# v.3.00    - Helo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt.

import os
from telegram.ext import Application, MessageHandler, filters
from dotenv import load_dotenv

load_dotenv('conf/.env')

START_MESSAGE = "v.3.01"

# >============================================<
# ВАЛИДНЫЕ ЗНАЧЕНИЯ ДЛЯ СИСТЕМЫ
# >============================================<

# Допустимые источники сообщений
SOURCE = ["terminal", "telegram", "web", "core"]

# Допустимые авторы сообщений  
AUTHOR = ["user", "system", "deepseek__model"]


# >============================================<
# front_manager
# МЕНЕДЖЕР СООБЩЕНИЙ - МАРШРУТИЗАЦИЯ
# >============================================<

# Маршрутизирует сообщение в ядро обработки и возвращает ответ (source, author, message)
def route_message(source: str, author: str, message: str) -> tuple:
    return process_message(source, author, message)


# >============================================<
# front_telegram
# ТЕЛЕГРАМ ФРОНТЕНД - ИНТЕРФЕЙС ПОЛЬЗОВАТЕЛЯ  
# >============================================<

# Обрабатывает входящие сообщения из Telegram
async def telegram_message_handler(update, context):
    user_text = update.message.text
    await update.message.chat.send_action(action="typing")  # Укашалочка "Печатает..."
    source, author, response = route_message("telegram", "user", user_text)
    await update.message.reply_text(response)

# Запускает Telegram бота в режиме polling"
def telegram_run_bot():
    token = os.getenv('API_KEY_TG')
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_message_handler))
    app.run_polling()


# >============================================<
# ЯДРО СИСТЕМЫ - ОБРАБОТКА СООБЩЕНИЙ
# >============================================<

# Обрабатывает сообщение и генерирует ответ (source, author, message)
def process_message(source: str, author: str, message: str) -> tuple:
    return "core", "system", f"Эхо: {message}"


# >============================================<
# ОСНОВНОЙ ЦИКЛ ПРОГРАММЫ
# >============================================<

# Основная функция запуска приложения
def main():
    print(START_MESSAGE)
    telegram_run_bot()

if __name__ == "__main__":
    main()