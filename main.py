# main.py
# заметки для ИИ, который будет править этот код:
#           - никода не удаляй и не редактируй коментарии. добавлять можно.
#           - старайся не менять структуру кода без особой необходимости, или изменяй минимально.
#           - придерживайся стиля.
#           - называй функции логично и максимально информативно.

# v.3.02    - реализован terminal-фронтенд
#           - реализована система логгирования. требует донастройки впоследствии.

# v.3.01    - заложена архитектура обмена сообщениями: фронтент <-> менеджер <-> ядро <-> менеджер <-> фронтенд.
#           - внедрена система тройных кортежей (source, author, message) для маркировки сообщений.
#           - реализован Telegram-фронтенд.
#           - обработка сообщений от пользователя на уровне простого ЭХО.

# v.3.00    - Helo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt.

import os
from telegram.ext import Application, MessageHandler, filters
from dotenv import load_dotenv
from logger import setup_logging, log_message  # Добавляем логирование

load_dotenv('conf/.env')

START_MESSAGE = "v.3.02"  # Обновляем версию

# >============================================<
# ВАЛИДНЫЕ ЗНАЧЕНИЯ ДЛЯ СИСТЕМЫ
# >============================================<

# Допустимые источники сообщений
SOURCE = ["terminal", "telegram", "web", "main"]

# Допустимые авторы сообщений  
AUTHOR = ["user", "ai_model", "system", "error"]


# >============================================<
# front_manager
# МЕНЕДЖЕР СООБЩЕНИЙ - МАРШРУТИЗАЦИЯ
# >============================================<

# Маршрутизирует сообщение в ядро обработки и возвращает ответ (source, author, message)
def route_message(source: str, author: str, message: str) -> tuple:
    # Отправляем входящее сообщение в терминал для мониторинга
    terminal_send_message(source, author, message)
    # И записываем в лог-файлы
    log_message(source, author, message)
    
    # Обрабатываем сообщение в ядре системы
    response_source, response_author, response_text = process_message(source, author, message)
    
    # Отправляем ответное сообщение в терминал для мониторинга
    terminal_send_message(response_source, response_author, response_text)
    # И записываем в лог-файлы
    log_message(response_source, response_author, response_text)
    
    return response_source, response_author, response_text


# >============================================<
# front_terminal  
# ТЕРМИНАЛ ФРОНТЕНД - ВЫВОД СООБЩЕНИЙ В КОНСОЛЬ
# >============================================<

# Выводит сообщения в терминал (только для мониторинга)
def terminal_send_message(source: str, author: str, message: str):
    print(f"[{source}.{author}] {message}")


# >============================================<
# front_telegram
# ТЕЛЕГРАМ ФРОНТЕНД - ИНТЕРФЕЙС ПОЛЬЗОВАТЕЛЯ  
# >============================================<

# Обрабатывает входящие сообщения из Telegram
async def telegram_message_handler(update, context):
    try:
        user_text = update.message.text
        await update.message.chat.send_action(action="typing")  # Укашалочка "Печатает..."
        source, author, response = route_message("telegram", "user", user_text)
        await update.message.reply_text(response)  # Отправляем ответ в Telegram
    except Exception as e:
        # Логируем ошибки обработки
        log_message("telegram", "error", f"Ошибка обработки сообщения: {e}")
        raise

# Обрабатывает ошибки Telegram
async def telegram_error_handler(update, context):
    error = str(context.error)
    log_message("telegram", "error", f"Telegram ошибка: {error}")

# Запускает Telegram бота в режиме polling
def telegram_run_bot():
    token = os.getenv('API_KEY_TG')
    app = Application.builder().token(token).build()
    
    # Добавляем обработчики
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_message_handler))
    app.add_error_handler(telegram_error_handler)
    
    # Логируем запуск бота
    log_message("telegram", "system", "Telegram бот запускается")
    
    try:
        app.run_polling()
    except Exception as e:
        log_message("main", "error", f"Критическая ошибка бота: {e}")
        raise


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
    # Инициализируем систему логирования
    setup_logging()
    
    # Стартовое сообщение дублируем и в терминал, и в логи
    terminal_send_message("main", "system", START_MESSAGE)
    log_message("main", "system", START_MESSAGE)
    
    telegram_run_bot()

if __name__ == "__main__":
    main()