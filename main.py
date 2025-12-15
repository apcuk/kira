# main.py

# v.3.01 - logger.py - система логгирования

# v.3.00 - Heloo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt 

from logger import setup_logging, log_system, log_message

def main():
    
    # Явно инициализируем логирование
    setup_logging()
    
    VERSION = "v.3.01"
    
    log_system("info", f"Бот {VERSION} запущен")
    log_system("info", "Добро пожаловать")
    
if __name__ == "__main__":
    main()