# main.py

# v.3.11 - добавлен маркер времени на начало сессии.
# v.3.10 - полностью реализована работа с памятьюв рамках чат-лога. приведено в порядок логирование. полностью рабочая версия на DEEPSEEK. под CHATGPT нужно оптимизировать промпты.
# v.3.09 - реализовано чанкование и векторизация сообщений чат-лога.
# v.3.08 - memory_manager.py - модуль менеджера памяти. реализовано тегирование сообщений в БД.
# v.3.07 - database.py + config_loader.py. сохранение чат-лога в БД. вынос работы с конфигами во внешний модуль.
# v.3.06 - отказ от асинхронной архитектуры.
# v.3.05 - ai_provider.py - подключены AI-провайдеры.
# v.3.04 - router.py - система маршрутизации сообщений (забыл закомитить и запушить эту версию).
# v.3.03 - front_telegram.py - базовый обработчик ТГ. доработана система логирования.
# v.3.02 - security.py - whitelist система.
# v.3.01 - logger.py - система логгирования.
# v.3.00 - Heloo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt.


import os
import sys

from dotenv import load_dotenv

from logger import setup_logging, log_system
from front_telegram import tg_run_bot
from database import db_init_tables

# Добавляем текущую директорию в путь Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    # Загружаем .env ПЕРВЫМ делом
    load_dotenv('conf/.env')
    setup_logging()
    
    VERSION = "v.3.11"
    log_system("info", f"Kira Copilot {VERSION} запущена")

    # ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
    try:
        db_init_tables()
        log_system("info", "База данных инициализирована")
    except Exception as e:
        log_system("error", f"Ошибка инициализации БД: {e}")
        log_system("error", "Kira Copilot не может работать без БД. Завершение.")
        return  # Выходим, не запускаем бота

    # Запускаем Telegram бота
    tg_run_bot()
    
if __name__ == "__main__":
    main()