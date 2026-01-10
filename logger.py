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
    """Форматтер для файлов: полная дата [уровень.модуль.функция] сообщение"""
    
    def format(self, record):
        time_str = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        level = record.levelname.lower()
        name = record.name
        
        return f"{time_str} [{level}.{name}] {record.getMessage()}"

class ConsoleFormatter(logging.Formatter):
    """Форматтер для консоли с цветами (только текст сообщения)"""
    
    # ANSI коды цветов
    COLORS = {
        'debug': '\033[90m',      # серый
        'info': '\033[0m',        # обычный
        'warning': '\033[33m',    # желтый
        'error': '\033[31m',      # красный
        'critical': '\033[41m',   # красный фон
        'blue': '\033[94m',       # синий (для поисковых запросов)
        'reset': '\033[0m'        # сброс
    }
    
class ConsoleFormatter(logging.Formatter):
    """Форматтер для консоли с цветами (только текст сообщения)"""
    
    # ANSI коды цветов
    COLORS = {
        'debug': '\033[90m',      # серый
        'info': '\033[0m',        # обычный
        'warning': '\033[33m',    # желтый
        'error': '\033[31m',      # красный
        'critical': '\033[41m',   # красный фон
        'blue': '\033[94m',       # синий (для поисковых запросов и сессий)
        'reset': '\033[0m'        # сброс
    }
    
    def format(self, record):
        time_str = datetime.fromtimestamp(record.created).strftime('%d/%m %H:%M:%S')
        level = record.levelname.lower()
        name = record.name
        message = record.getMessage()
        
        # Базовая строка без цвета (дата и уровень)
        base_str = f"{time_str} [{level}.{name}] "
        
        # Определяем цвет для текста сообщения
        message_color = self.COLORS['info']  # по умолчанию
        
        # Подсвечиваем СИНИМ поисковые запросы и события памяти
        search_triggers = [
            'Обнаружен поисковый запрос',
            'поисковый запрос',
            '<SEARCH>',
            'Найдено чанков',
            'ID чанков',
            'векторизован поисковый запрос',
            'поиск по запросу'
        ]
        
        if any(trigger.lower() in message.lower() for trigger in search_triggers):
            message_color = self.COLORS['blue']  # СИНИЙ для поиска
        
        # Подсвечиваем СИНИМ сообщения о сессиях
        session_triggers = [
            'Начата новая сессия',
            'Продолжена текущая сессия'
        ]
        
        if any(trigger.lower() in message.lower() for trigger in session_triggers):
            message_color = self.COLORS['blue']  # СИНИЙ для сессий
        
        # Ошибки - красный текст
        if level == 'error':
            message_color = self.COLORS['error']
        
        # Предупреждения - желтый текст
        if level == 'warning':
            message_color = self.COLORS['warning']
        
        # Формируем: обычная дата+уровень + цветной текст сообщения
        formatted = f"{base_str}{message_color}{message}{self.COLORS['reset']}"
        return formatted

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
    
    # 3. Консоль с короткой датой и цветами (только INFO и выше)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(ConsoleFormatter())
    
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


def log_chat(source: str, name: str, message: str):
    """
    Логирует сообщение чата в формате: [источник.имя] текст
    """
    time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    safe_message = message.replace('\n', '\\n')
    log_line = f"{time_str} [{source}.{name}] {safe_message}"
    
    chat_logger = logging.getLogger("chat")
    chat_logger.info(log_line)


# Автоинициализация отключена — вызывать setup_logging() вручную