# logger.py

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
MAX_FILE_SIZE = 1 * 1024 * 1024  # 10 MB
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
    file_handler = RotatingFileHandler(
        filename=os.path.join(LOG_DIR, "system.log"),
        maxBytes=MAX_FILE_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(SimpleFormatter())
    
    # 2. Консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('[%(levelname)s.%(name)s] %(message)s'))
    
    # 3. Настройка корневого логгера
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 4. Уменьшаем шум библиотек
    for lib in ['telegram', 'httpx', 'httpcore', 'asyncio', 'aiosignal']:
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

# Автоинициализация отключена — вызывать setup_logging() вручную