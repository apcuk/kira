# logger.py

import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    
    # Создаём папку logs если её нет
    os.makedirs('logs', exist_ok=True)
    
    # Формат логов
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # SYSTEM.LOG - логи нашего скрипта (core, system)
    system_log = logging.getLogger('system')
    system_log.setLevel(logging.INFO)
    system_handler = RotatingFileHandler(
        'logs/system.log', 
        maxBytes=500*1024,  # 500 KB
        backupCount=2,
        encoding='utf-8'
    )
    system_handler.setFormatter(formatter)
    system_log.addHandler(system_handler)
    
    # TELEGRAM.LOG - события телеграма
    telegram_log = logging.getLogger('telegram')
    telegram_log.setLevel(logging.INFO)
    telegram_handler = RotatingFileHandler(
        'logs/telegram.log',
        maxBytes=1024*1024,  # 1 MB
        backupCount=1,
        encoding='utf-8'
    )
    telegram_handler.setFormatter(formatter)
    telegram_log.addHandler(telegram_handler)
    
    # CHAT.LOG - история диалогов
    chat_log = logging.getLogger('chat')
    chat_log.setLevel(logging.INFO)
    chat_handler = RotatingFileHandler(
        'logs/chat.log',
        maxBytes=2*1024*1024,  # 2 MB
        backupCount=3,
        encoding='utf-8'
    )
    chat_handler.setFormatter(formatter)
    chat_log.addHandler(chat_handler)

    # OPENAI.LOG - запросы и ответы к OpenAI
    openai_log = logging.getLogger('openai')
    openai_log.setLevel(logging.INFO)
    openai_handler = RotatingFileHandler(
        'logs/openai.log',
        maxBytes=1*1024*1024,  # 1 MB
        backupCount=2,
        encoding='utf-8'
    )
    openai_handler.setFormatter(formatter)
    openai_log.addHandler(openai_handler)

    # DEEPSEEK.LOG - запросы и ответы к DeepSeek
    deepseek_log = logging.getLogger('deepseek')
    deepseek_log.setLevel(logging.INFO)
    deepseek_handler = RotatingFileHandler(
        'logs/deepseek.log',
        maxBytes=1*1024*1024,  # 1 MB
        backupCount=2,
        encoding='utf-8'
    )
    deepseek_handler.setFormatter(formatter)
    deepseek_log.addHandler(deepseek_handler)

    # Подавляем лишние логи от библиотек
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)

# Создаём глобальные объекты логов
system_logger = logging.getLogger('system')
telegram_logger = logging.getLogger('telegram') 
chat_logger = logging.getLogger('chat')
openai_logger = logging.getLogger('openai')
deepseek_logger = logging.getLogger('deepseek')

def log_message(source: str, author: str, message: str):
    """Логирует сообщение в соответствующие лог-файлы"""
    log_entry = f"[{source}.{author}] {message}"
    
    # В system.log — только сообщения и ошибки
    if author in ["message", "error"]:
        system_logger.info(log_entry)
    
    # В telegram.log — только ТЕХНИЧЕСКИЕ события телеграма (запуск/ошибки)
    if source == "telegram" and author in ["system", "error"]:
        telegram_logger.info(log_entry)
    
    # В chat.log — диалоги (пользователь, ИИ)
    if author not in ["system", "error", "debug", "message"]:
        chat_logger.info(log_entry)
    
    # В openai.log / deepseek.log — логи соответствующих провайдеров
    # (если author или source указывает на провайдера)
    # if author == "openai" or source == "openai":
    #     openai_logger.info(log_entry)
    # if author == "deepseek" or source == "deepseek":
    #     deepseek_logger.info(log_entry)