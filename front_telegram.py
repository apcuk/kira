# front_telegram.py

import os
import asyncio

from telegram.ext import Application, MessageHandler, filters

from logger import setup_logging, log_system
from security import security

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
    Проверяет whitelist, логирует, отправляет ответ.
    """
    user = update.message.from_user
    user_id = user.id
    user_text = update.message.text
    
    # 1. Проверка whitelist
    if not security.is_allowed(user_id):
        # log_system("warning", f"Доступ запрещён для user_id={user_id}")
        denied_msg = security.get_access_denied_message()
        await update.message.reply_text(denied_msg)
        return
    
    # 2. Пользователь разрешён — логируем сообщение
    user_display_name = user.username or user.first_name or f"user_{user_id}"
    log_system("debug", f"Получено сообщение от пользователя {user_display_name} (TG ID: {user_id}): {user_text[:50]} ... ... ...")
    
    # 3. Отправляем действие "печатает..."
    await update.message.chat.send_action(action="typing")
    
    # 4. ПРОСТОЙ ОТВЕТ (пока без AI)
    response_text = f"Привет, {user_display_name}! Я Kira. Твоё сообщение: '{user_text}'"
    
    # 5. Логируем и отправляем ответ
    log_system("debug", f"Отправлено ответное сообщение пользователю {user_display_name} (TG ID: {user_id}): {response_text[:50]} ... ... ...")
    
    await update.message.reply_text(response_text)

async def tg_error_handler(update, context):
    """Обработчик ошибок"""
    error_msg = str(context.error)
    log_system("error", f"Ошибка: {error_msg}")
    
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

def tg_run_bot():
    """Запускает Telegram бота"""
    
    log_system("info", "Запуск Telegram бота...")
    
    try:
        # Инициализация
        app = tg_init_bot()
        
        # Добавляем обработчики
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, tg_handle_message))
        app.add_error_handler(tg_error_handler)
        
        # Запускаем polling
        log_system("info", "Telegram бот запущен")
        # print("Telegram бот запущен. Нажмите Ctrl+C для остановки.")
        
        app.run_polling()
        
    except Exception as e:
        log_system("error", f"Критическая ошибка бота: {e}")
        raise

# Для запуска напрямую
if __name__ == "__main__":
    setup_logging()
    tg_run_bot()