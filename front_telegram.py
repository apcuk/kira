# front_telegram.py

import os
import asyncio

from telegram.ext import Application, MessageHandler, filters

import router
from logger import setup_logging, log_system
from security import security
# from config_loader import config_get_aliases

# alias_user, alias_ai = config_get_aliases()

def tg_init_bot():
    """Инициализирует и возвращает Telegram бота"""
    
    # Загружаем токен из .env
    token = os.getenv('API_KEY_TG')
    if not token:
        log_system("error", "API_KEY_TG не задан в .env")
        raise ValueError("API_KEY_TG не задан в .env")
    
    log_system("info", f"Telegram бот инициализирован, токен: {token[:11]}...")
    return Application.builder().token(token).build()

async def tg_handle_message(update, context):
    """
    Обработчик входящих сообщений Telegram.
    Проверяет whitelist, логирует, передаёт в роутер.
    """
    user = update.message.from_user
    user_id = user.id
    user_text = update.message.text
    
    # 1. Проверка whitelist
    if not security.is_allowed(user_id):
        denied_msg = security.get_access_denied_message()
        await update.message.reply_text(denied_msg)
        return
    
    # 2. Пользователь разрешён — логируем сообщение
    user_display_name = user.username or user.first_name or f"user_{user_id}"
    log_system("info", f"Получено сообщение от пользователя {user_display_name} (TG ID: {user_id})")
    # log_system("debug", f"{alias_user}: {user_text}")     # логировать полное сообщение будем в роутере, не тут
    
    # 3. Отправляем действие "печатает..."
    await update.message.chat.send_action(action="typing")
    
    # 4. СОБИРАЕМ ДАННЫЕ ДЛЯ РОУТЕРА
    user_data = {
        "user_id": user_id,  # реальный Telegram ID
        "source": "telegram",
        "message": user_text,
        "metadata": {
            "chat_id": update.message.chat_id,
            "username": user_display_name,
            "message_id": update.message.message_id,
            "full_name": user.full_name if user.full_name else None
        }
    }
    
    # 5. ПЕРЕДАЁМ В РОУТЕР И ПОЛУЧАЕМ ОТВЕТ (синхронный вызов в отдельном потоке)
    try:
        # Запускаем синхронный router в отдельном потоке, чтобы не блокировать event loop
        result = await asyncio.to_thread(router.route_message, user_data)
        response_text = result["message"]
    except Exception as e:
        log_system("error", f"Ошибка в роутере: {e}")
        response_text = "Ошибка обработки сообщения. Попробуйте позже."
    
    # 6. Логируем и отправляем ответ
    log_system("info", f"Отправлено ответное сообщение пользователю {user_display_name} (TG ID: {user_id})")
    # log_system("debug", f"{alias_ai}: {response_text}")     # логировать полное сообщение будем в роутере, не тут
    
    await update.message.reply_text(response_text)

async def tg_error_handler(update, context):
    """Обработчик ошибок"""
    error_msg = str(context.error)
    log_system("error", f"Ошибка: {error_msg}")
    
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

def tg_run_bot():
    """Запускает Telegram бота"""
    
    log_system("info", "Запуск Telegram бота")
    
    try:
        # Инициализация
        app = tg_init_bot()
        
        # Добавляем обработчики
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tg_handle_message))
        app.add_error_handler(tg_error_handler)
        
        # Запускаем polling
        log_system("info", "Telegram бот запущен")
        app.run_polling()
        
    except Exception as e:
        log_system("error", f"Критическая ошибка бота: {e}")
        raise

# Для запуска напрямую
if __name__ == "__main__":
    setup_logging()
    tg_run_bot()