# logger.py

import inspect
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
MAX_FILE_SIZE = 1 * 1024 * 1024
BACKUP_COUNT = 5

class SimpleFormatter(logging.Formatter):
    """Форматтер: время [уровень.модуль.функция] сообщение"""
    
    def format(self, record):
        time_str = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname.lower()
        name = record.name
        
        return f"{time_str} [{level}.{name}] {record.getMessage()}"

def setup_logging():
    """Настраивает логирование: файл + консоль"""
    
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)
    
    # 1. Файл system.log
    system_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "system.log"),
        maxBytes=MAX_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    system_handler.setLevel(logging.DEBUG)
    system_handler.setFormatter(SimpleFormatter())
    
    # 2. Файл chat.log (НОВЫЙ)
    chat_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "chat.log"),
        maxBytes=MAX_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    chat_handler.setLevel(logging.INFO)  # Все сообщения чата идут как INFO
    chat_handler.setFormatter(logging.Formatter('%(message)s'))  # Только само сообщение
    
    # 3. Консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('[%(levelname)s.%(name)s] %(message)s'))
    
    # 4. Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(system_handler)
    root_logger.addHandler(console_handler)
    
    # 5. Создаём отдельный логгер для чата
    chat_logger = logging.getLogger("chat")
    chat_logger.setLevel(logging.INFO)
    chat_logger.handlers.clear()
    chat_logger.addHandler(chat_handler)
    chat_logger.propagate = False  # Чтобы сообщения чата не дублировались в root
    
    # 6. Уменьшаем шум библиотек
    for lib in ['telegram', 'httpx', 'httpcore', 'asyncio', 'aiosignal', 'openai']:
        logging.getLogger(lib).setLevel(logging.WARNING)

def log_system(level: str, message: str, module: str = None, func: str = None):
    """
    Логирует сообщение.
    Пример: log_system("info", "Бот запущен")
    """
    import inspect
    import os
    
    if module is None:
        stack = inspect.stack()
        for frame_info in stack:
            if frame_info.function == 'log_system':
                continue
            
            frame = frame_info.frame
            if 'logger.py' not in frame.f_globals.get('__file__', ''):
                module = frame.f_globals.get('__name__', 'unknown')
                if module == '__main__':
                    module = 'main'
                
                if func is None:
                    func = frame_info.function
                    if func == '<module>':
                        func = None
                break
        
        if module is None:
            module = 'unknown'
    
    name = f"{module}.{func}" if func and func != '<module>' else module
    logger = logging.getLogger(name)
    getattr(logger, level.lower())(message)


def log_chat(source: str, user_id, role: str, message: str, display_name: str = None):
    """
    Логирует сообщение чата через выделенный логгер chat.
    display_name: username или first_name (если есть)
    """
    # Форматируем user идентификатор
    if display_name and display_name != f"user_{user_id}":
        user_ident = display_name  # Только имя, без ID
    else:
        user_ident = str(user_id)
    
    # Форматируем запись
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    safe_message = message.replace('\n', '\\n')
    log_line = f"{time_str} [{source}.{user_ident}] {role}: {safe_message}"
    
    # Используем выделенный логгер
    chat_logger = logging.getLogger("chat")
    chat_logger.info(log_line)


# Автоинициализация отключена — вызывать setup_logging() вручную