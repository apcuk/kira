# main.py

# v.3.06 - отказ от асинхронной архитектуры.
# v.3.05 - ai_provider.py - подключены AI-провайдеры
# v.3.04 - router.py - система маршрутизации сообщений (забыл закомитить и запушить эту версию)
# v.3.03 - front_telegram.py - базовый обработчик ТГ. доработана система логирования
# v.3.02 - security.py - whitelist система
# v.3.01 - logger.py - система логгирования
# v.3.00 - Heloo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt 


import os
import sys

# Добавляем текущую директорию в путь Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

from logger import setup_logging, log_system
from front_telegram import tg_run_bot

def main():

    # Загружаем .env ПЕРВЫМ делом
    load_dotenv('conf/.env')

    # Явно инициализируем логирование
    setup_logging()
    
    VERSION = "v.3.06"
    
    log_system("info", f"Kira Copilot {VERSION} запущена")

    # Запускаем Telegram бота
    tg_run_bot()
    
if __name__ == "__main__":
    main()