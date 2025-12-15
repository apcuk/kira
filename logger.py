# logger.py

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

# ==================== КОНФИГУРАЦИЯ ====================
LOG_DIR = "logs"
MAX_FILE_SIZE = 1 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 5

# ==================== ФОРМАТТЕРЫ ====================

class SystemFormatter(logging.Formatter):
    """Форматтер для system.log: [level.name] message"""
    
    def format(self, record):
        # Форматируем просто и понятно
        time_str = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level_name = record.levelname.lower()
        logger_name = record.name
        
        message = record.getMessage()
        
        return f"{time_str} [{level_name}.{logger_name}] {message}"

class ChatFormatter(logging.Formatter):
    """Форматтер для chat.log: время | автор | сообщение"""
    
    def format(self, record):
        record.asctime = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        return super().format(record)

class TelegramFormatter(logging.Formatter):
    """Форматтер для telegram.log: время | уровень | сообщение"""
    
    def format(self, record):
        record.asctime = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        return super().format(record)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================

def setup_logging():
    """Настраивает систему логирования с тремя файлами"""
    
    # Создаём папку для логов
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # ========== 1. system.log ==========
    system_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "system.log"),
        maxBytes=MAX_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    system_handler.setLevel(logging.DEBUG)
    system_handler.setFormatter(SystemFormatter())
    system_handler.addFilter(lambda record: record.name != 'chat' and record.name != 'telegram')
    
    # ========== 2. chat.log ==========
    chat_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "chat.log"),
        maxBytes=MAX_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    chat_handler.setLevel(logging.INFO)
    chat_handler.setFormatter(ChatFormatter('%(asctime)s | %(author)-15s | %(message)s'))
    chat_handler.addFilter(lambda record: record.name == 'chat')
    
    # ========== 3. telegram.log ==========
    telegram_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "telegram.log"),
        maxBytes=MAX_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    telegram_handler.setLevel(logging.DEBUG)  # ВСЁ от Telegram
    telegram_handler.setFormatter(TelegramFormatter('%(asctime)s | %(levelname)-8s | %(message)s'))
    telegram_handler.addFilter(lambda record: record.name == 'telegram')
    
    # ========== 4. Консоль ==========
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('[%(levelname)s.%(name)s] %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # ========== Настраиваем корневой логгер ==========
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Очищаем старые обработчики
    root_logger.handlers.clear()
    
    # Добавляем новые
    root_logger.addHandler(system_handler)
    root_logger.addHandler(chat_handler)
    root_logger.addHandler(telegram_handler)
    root_logger.addHandler(console_handler)
    
    # Логируем старт
    # log_system("info", "Логирование инициализировано", __name__, "setup_logging")

# ==================== ИНТЕРФЕЙС ДЛЯ ПРОГРАММЫ ====================

def log_message(source: str, author: str, message: str):
    """
    Логирует сообщение чата.
    Используется для сообщений пользователя и ответов системы.
    
    Args:
        source: Источник ('telegram', 'terminal', 'core', 'error')
        author: Автор ('user', 'openai', 'deepseek', 'system')
        message: Текст сообщения
    """
    chat_logger = logging.getLogger('chat')
    
    # Для сохранения author в LogRecord
    extra = {'author': author}
    
    if source == 'error':
        chat_logger.error(message, extra=extra)
    else:
        chat_logger.info(message, extra=extra)

def log_system(level: str, message: str, module: str = None, func: str = None):
    """
    Логирует системное сообщение.
    
    Args:
        level: Уровень ('debug', 'info', 'warning', 'error', 'critical')
        message: Текст сообщения
        module: Имя модуля (автоматически определяется если None)
        func: Имя функции (автоматически определяется если None)
    """
    import inspect
    import os
    
    # Определяем caller правильно
    if module is None:
        # Ищем первого caller'а который НЕ из logger.py
        stack = inspect.stack()
        for frame_info in stack:
            # Пропускаем текущую функцию и модуль logger
            if frame_info.function == 'log_system':
                continue
            
            frame = frame_info.frame
            module_path = frame.f_globals.get('__file__', '')
            
            # Если это не logger.py
            if 'logger.py' not in module_path:
                # Получаем имя модуля
                module_name = frame.f_globals.get('__name__', 'unknown')
                
                # Если это __main__, преобразуем в имя файла
                if module_name == '__main__':
                    filename = os.path.basename(frame.f_globals.get('__file__', 'main.py'))
                    module_name = filename.replace('.py', '')
                
                module = module_name
                
                # Определяем функцию если не указана
                if func is None:
                    func = frame_info.function
                    if func == '<module>':
                        func = None
                break
        
        # Если не нашли (все вызовы из logger.py)
        if module is None:
            module = 'unknown'
    
    # Формируем имя логгера
    if func and func != '<module>':
        logger_name = f"{module}.{func}"
    else:
        logger_name = module
    
    logger = logging.getLogger(logger_name)
    
    level_method = getattr(logger, level.lower(), logger.info)
    level_method(message)

def log_telegram(level: str, message: str):
    """
    Логирует сообщение от Telegram API.
    
    Args:
        level: Уровень ('debug', 'info', 'warning', 'error')
        message: Текст сообщения
    """
    telegram_logger = logging.getLogger('telegram')
    level_method = getattr(telegram_logger, level.lower(), telegram_logger.info)
    level_method(message)

# Создаём alias для обратной совместимости
log_telegram_error = lambda msg: log_telegram('error', msg)

# Автоматическая инициализация при первом импорте
# if not logging.getLogger().handlers:
#    setup_logging()
