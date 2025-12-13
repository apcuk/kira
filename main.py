# main.py

# заметки для ИИ, который будет править этот код:
#           - никода не удаляй и не редактируй коментарии. добавлять можно.
#           - старайся не менять структуру кода без особой необходимости, или изменяй минимально.
#           - придерживайся стиля.
#           - называй функции логично и максимально информативно.

# v.3.06    - добавлены функция тегирования сообщений и разбивка chatlog'а в БД на сессии.

# v.3.05    - переосмыслена и переделана система логгированния.

# v.3.04    - добавлена работа с AI-провайдерами: OpenAI и DeepSeek (ask_openai, ask_deepseek).
#           - реализована загрузка контекста истории из БД (get_recent_chat_context).
#           - личности вынесены в .md-файлы.

# v.3.03    - реализовно сохраниение chatlog'а в БД.

# v.3.02    - реализован terminal-фронтенд.
#           - реализована система логгирования. требует донастройки впоследствии.

# v.3.01    - заложена архитектура обмена сообщениями: фронтент <-> менеджер <-> ядро <-> менеджер <-> фронтенд.
#           - внедрена система тройных кортежей (source, author, message) для маркировки сообщений.
#           - реализован Telegram-фронтенд.
#           - обработка сообщений от пользователя на уровне простого ЭХО.

# v.3.00    - Helo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt.

import os
import yaml
import psycopg2
import threading
from openai import OpenAI
from telegram.ext import Application, MessageHandler, filters
from datetime import datetime, timezone
from dotenv import load_dotenv
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from logger import setup_logging, log_message  # Добавляем логирование
from memory_organizer import tag_untagged_messages

START_MESSAGE = "v.3.06"  # Обновляем версию

# Инициализируем логирование
setup_logging()


# Загружаем конфиги
load_dotenv('conf/.env')

try:
    with open('conf/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    if config is None:
        log_message("load_dotenv", "error", "config.yaml пустой или невалидный")
        exit(1)
        
except Exception as e:
    log_message("load_dotenv", "error", f"Ошибка загрузки config.yaml: {e}")
    exit(1)


# >============================================<
# ВАЛИДНЫЕ ЗНАЧЕНИЯ ДЛЯ СИСТЕМЫ
# >============================================<

# Допустимые источники сообщений
SOURCE = ["terminal", "telegram", "web", "main"]

# Кеш зарегистрированных пользователей (чтобы не проверять БД каждый раз)
_registered_users = set()


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
    response_source, response_author, response_text = process_message(source, author, message, user_id)
    
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
        
        # Определяем имя для логов: username или first_name или id
        user_log_name = user.username or user.first_name or f"user_{user.id}"
        
        # Регистрируем пользователя (передаём имя для возможного использования в БД)
        user_id = get_or_create_user(
            user_id=user.id,
            user_name=user.username, 
            first_name=user.first_name
        )
       
        await update.message.chat.send_action(action="typing")
        # Передаём user_log_name как author
        source, author, response = route_message("telegram", user_log_name, user_text, user_id)
        await update.message.reply_text(response)
        
    except Exception as e:
        log_message("telegram_message_handler", "error", f"Ошибка обработки сообщения: {e}")
        raise

# Обрабатывает ошибки Telegram
async def telegram_error_handler(update, context):
    error = str(context.error)
    log_message("telegram_error_handler", "error", f"Telegram ошибка: {error}")

# Запускает Telegram бота в режиме polling
def telegram_run_bot():
    token = os.getenv('API_KEY_TG')
    app = Application.builder().token(token).build()
    
    # Добавляем обработчики
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_message_handler))
    app.add_error_handler(telegram_error_handler)
    
    # Логируем запуск бота
    log_message("telegram_run_bot", "message", "Telegram бот запускается")
    
    try:
        app.run_polling()
    except Exception as e:
        log_message("telegram_run_bot", "error", f"Критическая ошибка бота: {e}")
        raise


# >============================================<
# back_database
# БАЗА ДАННЫХ
# >============================================<

# Регистрация пользователя по старой схеме
def get_or_create_user(user_id, user_name, first_name):
    global _registered_users
    
    # Если пользователь уже в кеше — сразу возвращаем ID
    if user_id in _registered_users:
        return user_id
    
    db_url = os.getenv('DB_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Создаем таблицу users если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                user_name TEXT,
                user_firstname TEXT, 
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Логируем что проверяем пользователя
        log_message("get_or_create_user", "message", f"Проверяем пользователя {user_id}")
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = %s', (user_id,))
        existing_user = cursor.fetchone()
        
        if not existing_user:
            # Логируем создание
            log_message("get_or_create_user", "message", f"Создаем пользователя: {user_name}")
            cursor.execute(
                'INSERT INTO users (user_id, user_name, user_firstname) VALUES (%s, %s, %s)',
                (user_id, user_name, first_name)
            )
            conn.commit()
            log_message("get_or_create_user", "message", f"УСПЕШНО создан пользователь: {user_name}")
            
            # Создаем таблицу для логов чата пользователя (только для нового)
            create_user_chatlog_table(user_id)
        else:
            log_message("get_or_create_user", "message", f"Пользователь {user_id} уже существует")
        
        # Добавляем пользователя в кеш
        _registered_users.add(user_id)
        
        cursor.close()
        conn.close()
        return user_id
        
    except Exception as e:
        log_message("get_or_create_user", "error", f"Ошибка регистрации пользователя: {e}")
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
                tag_topics JSONB,
                tag_trash BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                session_id INTEGER
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        log_message("create_user_chatlog_table", "message", f"Создана/проверена таблица {table_name}")
        
    except Exception as e:
        log_message("create_user_chatlog_table", "error", f"Ошибка создания таблица чата: {e}")

# Сохраняет сообщение в таблицу пользователя
def save_to_user_chatlog(user_id: int, source: str, author: str, message: str):
    db_url = os.getenv('DB_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        table_name = f"user_{user_id}_chatlog"
        
        # 1. Определяем session_id
        cursor.execute(f'''
            SELECT created_at, session_id 
            FROM {table_name} 
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
        last_msg = cursor.fetchone()
        
        session_id = None
        if last_msg:
            last_time, last_session_id = last_msg
            # Приводим last_time к aware datetime (если он naive, считаем что UTC)
            if last_time.tzinfo is None:
                last_time = last_time.replace(tzinfo=timezone.utc)
            
            time_diff = datetime.now(timezone.utc) - last_time
            timeout_hours = config.get('memory', {}).get('session_timeout_hours', 6)
            
            if time_diff.total_seconds() > timeout_hours * 3600:
                # Новая сессия
                session_id = int(datetime.now(timezone.utc).timestamp())
                log_message("save_to_user_chatlog", "debug", 
                           f"Новая сессия для user_id={user_id}, перерыв: {time_diff}")
            else:
                # Продолжение сессии
                session_id = last_session_id
        else:
            # Первое сообщение пользователя
            session_id = int(datetime.now(timezone.utc).timestamp())
            log_message("save_to_user_chatlog", "debug", 
                       f"Первое сообщение, создана сессия {session_id} для user_id={user_id}")
        
        # 2. Сохраняем сообщение с session_id
        cursor.execute(
            f'INSERT INTO {table_name} (source, author, message, session_id) VALUES (%s, %s, %s, %s)',
            (source, author, message, session_id)
        )
        
        conn.commit()
        log_message("save_to_user_chatlog", "message", f"Сохранено сообщение в {table_name}, session_id={session_id}")
        
        # 3. Проверяем, нужно ли запускать тегирование
        cursor.execute(f'''
            SELECT COUNT(*) 
            FROM {table_name} 
            WHERE tag_topics IS NULL
        ''')
        untagged_count = cursor.fetchone()[0]
        
        tagging_threshold = config.get('memory', {}).get('tagging_batch_size', 10)
        
        if untagged_count >= tagging_threshold:
            log_message("save_to_user_chatlog", "message", 
                       f"Запуск фонового тегирования для user_id={user_id} (нетэгированных: {untagged_count})")
            # Запускаем в фоне
            thread = threading.Thread(
                target=tag_untagged_messages, 
                args=(user_id,),
                daemon=True
            )
            thread.start()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        log_message("save_to_user_chatlog", "error", f"Ошибка сохранения в чатлог: {e}")


# Возвращает последние limit сообщений из чатлога пользователя, исключая самое свежее (только что сохранённое).
def get_recent_chat_context(user_id: int, limit: int = None) -> list:
    db_url = os.getenv('DB_URL')
    context = []
    
    if limit is None:
        limit = config.get('ai', {}).get('context_messages_limit', 10)
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        table_name = f"user_{user_id}_chatlog"
        
        cursor.execute(f'''
            SELECT author, message 
            FROM {table_name} 
            ORDER BY created_at DESC 
            LIMIT %s 
            OFFSET 1
        ''', (limit,))
        
        rows = cursor.fetchall()
        
        # Авторы-ассистенты (AI провайдеры)
        ai_authors = ["openai", "deepseek"]
        
        for author, message in reversed(rows):
            role = "assistant" if author in ai_authors else "user"
            context.append({"role": role, "content": message})
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        log_message("get_recent_chat_context", "error", f"Ошибка загрузки контекста: {e}")
    
    log_message("get_recent_chat_context", "message", f"Loaded {len(context)} history messages for user {user_id}")
    return context


# >============================================<
# back_ИИ
# AI-ПРОВАЙДЕРЫ
# >============================================<


# Формирует список сообщений для AI API
def build_ai_messages(user_message: str, user_id: int = None) -> list:
    
    # Получаем имя личности из конфига
    persona_name = config.get('ai', {}).get('persona', 'person_default')
    persona_file = f"conf/{persona_name}.md"  # расширение .md
    
    messages = []
    
    try:
        with open(persona_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Разбиваем файл на блоки по ##
        blocks = content.split('## ')[1:]  # первый элемент — всё до первого заголовка, его пропускаем
        
        for block in blocks:
            # Первая строка — название блока, остальное — содержимое
            lines = block.strip().split('\n', 1)
            if len(lines) == 2:
                block_name, block_content = lines[0].strip(), lines[1].strip()
                # Каждый блок становится отдельным system-сообщением
                messages.append({"role": "system", "content": block_content})
                log_message("build_ai_messages", "debug", f"Loaded persona block: {block_name}")
        
        if not messages:
            log_message("build_ai_messages", "error", f"Файл личности {persona_file} не содержит блоков")
            messages.append({"role": "system", "content": "Ты — ассистент."})
            
    except FileNotFoundError:
        log_message("build_ai_messages", "error", f"Файл личности не найден: {persona_file}")
        messages.append({"role": "system", "content": "Ты — ассистент."})
    
    # Добавляем историю диалога, если есть user_id
    history = []  # Инициализируем пустым списком
    if user_id:
        history = get_recent_chat_context(user_id)
        messages.extend(history)
        log_message("build_ai_messages", "message", f"Added {len(history)} history messages for user {user_id}")
    
    # Добавляем текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})
    
    log_message("build_ai_messages", "message", f"Persona: {persona_name}, total blocks: {len(messages)-len(history)-1}")
    return messages


# Отправляет запрос к OpenAI API (ChatGPT) и возвращает ответ или None при ошибке.
def ask_openai(messages: list) -> str:
    api_key = os.getenv('API_KEY_OPENAI')
    if not api_key:
        log_message("ask_openai", "error", "API_KEY_OPENAI не найден в .env")
        return None  # ← Изменено: было строкой ошибки, теперь None
    
    try:
        client = OpenAI(api_key=api_key)  # base_url по умолчанию OpenAI
        
        ai_config = config.get('ai', {}).get('openai', {})
        model = ai_config.get('model', 'gpt-4o-mini')
        temperature = ai_config.get('temperature', 0.7)
        max_tokens = ai_config.get('max_tokens', 2048)
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,
            # temperature=temperature
        )
        
        answer = response.choices[0].message.content
        # log_message("ask_openai", "ai_model", f"Answer: {answer[:200]}...")
        return answer
        
    except Exception as e:
        error_msg = f"Ошибка OpenAI API: {e}"
        log_message("ask_openai", "error", error_msg)
        return None  # Ошибка — возвращаем None

# Отправляет запрос к OpenAI API (DeepSeek) и возвращает ответ или None при ошибке.
def ask_deepseek(messages: list) -> str:
    api_key = os.getenv('API_KEY_DEEPSEEK')
    if not api_key:
        log_message("ask_deepseek", "error", "API_KEY_DEEPSEEK не найден в .env")
        return None  # Возвращаем None, чтобы роутер мог переключиться на резерв
    
    try:
        # DeepSeek использует OpenAI-совместимый API, но свой base_url
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"  # можно вынести в конфиг
        )
        
        ai_config = config.get('ai', {}).get('deepseek', {})
        model = ai_config.get('model', 'deepseek-chat')
        temperature = ai_config.get('temperature', 0.7)
        max_tokens = ai_config.get('max_tokens', 2048)
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        answer = response.choices[0].message.content
        # log_message("ask_deepseek", "ai_model", f"Answer: {answer[:200]}...")
        return answer
        
    except Exception as e:
        error_msg = f"Ошибка DeepSeek API: {e}"
        log_message("ask_deepseek", "error", error_msg)
        return None  # Ошибка — возвращаем None



# >============================================<
# ЯДРО СИСТЕМЫ - ОБРАБОТКА СООБЩЕНИЙ
# >============================================<

# Обрабатывает сообщение: формирует messages, вызывает AI, возвращает ответ."""
def process_message(source: str, author: str, message: str, user_id: int = None) -> tuple:
    
    # Формируем список сообщений с историей
    messages = build_ai_messages(message, user_id)
    log_message("process_message", "message", f"Messages built with history: {len(messages)} total")
    
    # Выбираем провайдера из конфига
    provider = config.get('ai', {}).get('default_provider', 'openai')
    log_message("process_message", "message", f"Selected AI provider: {provider}")
    
    ai_response = None
    
    if provider == 'deepseek':
        ai_response = ask_deepseek(messages)
    else:  # openai
        ai_response = ask_openai(messages)
    
    # Если провайдер не ответил — возвращаем ошибку
    if ai_response is None:
        ai_response = f"Ошибка: AI-провайдер '{provider}' недоступен."
        log_message("process_message", "error", ai_response)
    
    # Возвращаем ответ от имени ai_model
    return "core", provider, ai_response


# >============================================<
# ОСНОВНОЙ ЦИКЛ ПРОГРАММЫ
# >============================================<

# Основная функция запуска приложения
def main():
    # Стартовое сообщение дублируем и в терминал, и в логи
    terminal_send_message("main", "message", START_MESSAGE)
    log_message("main", "message", START_MESSAGE)
    
    telegram_run_bot()

if __name__ == "__main__":
    main()