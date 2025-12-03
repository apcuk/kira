# main.py
# заметки для ИИ, который будет править этот код:
#           - никода не удаляй и не редактируй коментарии. добавлять можно.
#           - старайся не менять структуру кода без особой необходимости, или изменяй минимально.
#           - придерживайся стиля.
#           - называй функции логично и максимально информативно.

# v.3.03    - БУДЕМ ПОДКЛЮЧАТЬ БД.

# v.3.02    - реализован terminal-фронтенд.
#           - реализована система логгирования. требует донастройки впоследствии.

# v.3.01    - заложена архитектура обмена сообщениями: фронтент <-> менеджер <-> ядро <-> менеджер <-> фронтенд.
#           - внедрена система тройных кортежей (source, author, message) для маркировки сообщений.
#           - реализован Telegram-фронтенд.
#           - обработка сообщений от пользователя на уровне простого ЭХО.

# v.3.00    - Helo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt.

import os
import yaml
from telegram.ext import Application, MessageHandler, filters
from dotenv import load_dotenv
from logger import setup_logging, log_message  # Добавляем логирование
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

START_MESSAGE = "v.3.03"  # Обновляем версию

# Инициализируем логирование
setup_logging()


# Загружаем конфиги
load_dotenv('conf/.env')

try:
    with open('conf/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    if config is None:
        log_message("main", "error", "config.yaml пустой или невалидный")
        exit(1)
        
    DB_NAME = config['database']['name']
    
except Exception as e:
    log_message("main", "error", f"Ошибка загрузки config.yaml: {e}")
    exit(1)


# Объявляем константы
DB_NAME = config['database']['name']


# >============================================<
# ВАЛИДНЫЕ ЗНАЧЕНИЯ ДЛЯ СИСТЕМЫ
# >============================================<

# Допустимые источники сообщений
SOURCE = ["terminal", "telegram", "web", "main"]

# Допустимые авторы сообщений  
AUTHOR = ["user", "ai_model", "system", "error"]


# >============================================<
# front_manager
# МЕНЕДЖЕР СООБЩЕНИЙ - МАРШРУТИЗАЦИЯ
# >============================================<

# Маршрутизирует сообщение в ядро обработки и возвращает ответ (source, author, message)
def route_message(source: str, author: str, message: str, user_id: int = None) -> tuple:
    # Сохраняем входящее сообщение в чатлог пользователя
    if user_id:
        save_to_user_chatlog(user_id, source, author, message)
    
    # Отправляем входящее сообщение в терминал для мониторинга
    terminal_send_message(source, author, message)
    # И записываем в лог-файлы
    log_message(source, author, message)
    
    # Обрабатываем сообщение в ядре системы
    response_source, response_author, response_text = process_message(source, author, message)
    
    # Сохраняем ответное сообщение в чатлог пользователя
    if user_id:
        save_to_user_chatlog(user_id, response_source, response_author, response_text)
    
    # Отправляем ответное сообщение в терминал для мониторинга
    terminal_send_message(response_source, response_author, response_text)
    # И записываем в лог-файлы
    log_message(response_source, response_author, response_text)
    
    return response_source, response_author, response_text


# >============================================<
# front_terminal  
# ТЕРМИНАЛ ФРОНТЕНД
# >============================================<

# Выводит сообщения в терминал (только для мониторинга)
def terminal_send_message(source: str, author: str, message: str):
    print(f"[{source}.{author}] {message}")


# >============================================<
# front_telegram
# ТЕЛЕГРАМ ФРОНТЕНД
# >============================================<

# Обрабатывает входящие сообщения из Telegram
async def telegram_message_handler(update, context):
    try:
        user = update.message.from_user
        user_text = update.message.text
        
        # Регистрируем пользователя при первом сообщении
        user_id = get_or_create_user(
            user_id=user.id,
            user_name=user.username, 
            first_name=user.first_name
        )
       
        await update.message.chat.send_action(action="typing")
        source, author, response = route_message("telegram", "user", user_text, user_id)
        await update.message.reply_text(response)
        
    except Exception as e:
        log_message("telegram", "error", f"Ошибка обработки сообщения: {e}")
        raise

# Обрабатывает ошибки Telegram
async def telegram_error_handler(update, context):
    error = str(context.error)
    log_message("telegram", "error", f"Telegram ошибка: {error}")

# Запускает Telegram бота в режиме polling
def telegram_run_bot():
    token = os.getenv('API_KEY_TG')
    app = Application.builder().token(token).build()
    
    # Добавляем обработчики
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_message_handler))
    app.add_error_handler(telegram_error_handler)
    
    # Логируем запуск бота
    log_message("telegram", "system", "Telegram бот запускается")
    
    try:
        app.run_polling()
    except Exception as e:
        log_message("main", "error", f"Критическая ошибка бота: {e}")
        raise


# >============================================<
# back_database
# БАЗА ДАННЫХ
# >============================================<

# Регистрация пользователя по старой схеме
def get_or_create_user(user_id, user_name, first_name):
    db_url = os.getenv('DB_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Создаем таблицу если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                user_name TEXT,
                user_firstname TEXT, 
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Логируем что проверяем пользователя
        log_message("database", "system", f"Проверяем пользователя {user_id}")
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = %s', (user_id,))
        existing_user = cursor.fetchone()
        
        if not existing_user:
            # Логируем создание
            log_message("database", "system", f"Создаем пользователя: {user_name}")
            cursor.execute(
                'INSERT INTO users (user_id, user_name, user_firstname) VALUES (%s, %s, %s)',
                (user_id, user_name, first_name)
            )
            conn.commit()
            log_message("database", "system", f"УСПЕШНО создан пользователь: {user_name}")
        else:
            log_message("database", "system", f"Пользователь {user_id} уже существует")
        
        # Создаем таблицу для логов чата пользователя
        create_user_chatlog_table(user_id)
        
        cursor.close()
        conn.close()
        return user_id
        
    except Exception as e:
        log_message("database", "error", f"Ошибка регистрации пользователя: {e}")
        return None

# Создает таблицу для логов чата конкретного пользователя
def create_user_chatlog_table(user_id: int):
    db_url = os.getenv('DB_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        table_name = f"user_{user_id}_chatlog"
        
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                source VARCHAR(50) NOT NULL,
                author VARCHAR(50) NOT NULL,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        log_message("database", "system", f"Создана/проверена таблица {table_name}")
        
    except Exception as e:
        log_message("database", "error", f"Ошибка создания таблицы чата: {e}")

# Сохраняет сообщение в таблицу пользователя
def save_to_user_chatlog(user_id: int, source: str, author: str, message: str):
    db_url = os.getenv('DB_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        table_name = f"user_{user_id}_chatlog"
        
        cursor.execute(
            f'INSERT INTO {table_name} (source, author, message) VALUES (%s, %s, %s)',
            (source, author, message)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        log_message("database", "system", f"Сохранено сообщение в {table_name}")
        
    except Exception as e:
        log_message("database", "error", f"Ошибка сохранения в чатлог: {e}")


# >============================================<
# ЯДРО СИСТЕМЫ - ОБРАБОТКА СООБЩЕНИЙ
# >============================================<

# Обрабатывает сообщение и генерирует ответ (source, author, message)
def process_message(source: str, author: str, message: str) -> tuple:
    return "core", "system", f"Эхо: {message}"


# >============================================<
# ОСНОВНОЙ ЦИКЛ ПРОГРАММЫ
# >============================================<

# Основная функция запуска приложения
def main():
    # Стартовое сообщение дублируем и в терминал, и в логи
    terminal_send_message("main", "system", START_MESSAGE)
    log_message("main", "system", START_MESSAGE)
    
    telegram_run_bot()

if __name__ == "__main__":
    main()