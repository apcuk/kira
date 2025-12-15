# database.py

import os
import psycopg2
import threading
from datetime import datetime, timezone
from logger import log_message


def get_or_create_user(tg_user_id, tg_user_name, tg_first_name):
    db_url = os.getenv('DB_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # Создаем таблицу users если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id SERIAL PRIMARY KEY,           -- внутренний ID (автоинкремент)
                tg_user_id BIGINT UNIQUE NOT NULL,    -- Telegram ID (уникальный)
                tg_user_name TEXT,                    -- Telegram username
                tg_user_firstname TEXT,               -- Telegram first name
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Логируем что проверяем пользователя
        log_message("database.get_or_create_user", "message", f"Проверяем пользователя {tg_user_id} / {tg_user_name} / {tg_user_firstname}")
        
        cursor.execute('SELECT tg_user_id FROM users WHERE tg_user_id = %s', (tg_user_id,))
        existing_user = cursor.fetchone()
        
        if not existing_user:
            # Логируем создание
            log_message("database.get_or_create_user", "message", f"Создаем пользователя: {tg_user_id} / {tg_user_name} / {tg_user_firstname}")
            cursor.execute(
                'INSERT INTO users (tg_user_id, tg_user_name, tg_user_firstname) VALUES (%s, %s, %s)',
                (tg_user_id, tg_user_name, tg_first_name)
            )
            conn.commit()
            log_message("database.get_or_create_user", "message", f"Успешно создан пользователь: {user_name} / {tg_user_id} / {tg_user_name} / {tg_user_firstname}")
            
            # Создаем таблицу для логов чата пользователя (только для нового)
            create_user_tables(user_id)
        else:
            log_message("database.get_or_create_user", "message", f"Пользователь {tg_user_id} / {tg_user_name} / {tg_user_firstname} уже существует")
        
        cursor.close()
        conn.close()
        return user_id
        
    except Exception as e:
        log_message("database.get_or_create_user", "error", f"Ошибка регистрации пользователя: {e}")
        return None


def create_user_tables(user_id: int):
    """
    Создаёт все необходимые таблицы для пользователя:
    - user_{id}_chatlog — для сообщений
    - user_{id}_chunks — для чанков
    Создаёт необходимые индексы.
    """
    db_url = os.getenv('DB_URL')
    
    try:
        conn = psycopg2.connect(db_url)
        cursor = conn.cursor()
        
        # 1. Таблица чатлога
        chatlog_table = f"user_{user_id}_chatlog"
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {chatlog_table} (
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
        
        # Индексы для чатлога
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{chatlog_table}_created_at ON {chatlog_table}(created_at)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{chatlog_table}_session ON {chatlog_table}(session_id)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{chatlog_table}_tag_trash ON {chatlog_table}(tag_trash)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{chatlog_table}_tag_topics ON {chatlog_table} USING GIN (tag_topics)')
        
        # 2. Таблица чанков с полем для векторов
        chunks_table = f"user_{user_id}_chunks"
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {chunks_table} (
                id SERIAL PRIMARY KEY,
                chunk_text TEXT NOT NULL,
                message_id_start INTEGER NOT NULL,
                message_id_stop INTEGER NOT NULL,
                session_id INTEGER NOT NULL,
                chunk_meta JSONB,
                embedding vector(1536),
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')

        # Индексы для чанков
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{chunks_table}_id_range ON {chunks_table}(message_id_start, message_id_stop)')
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{chunks_table}_session ON {chunks_table}(session_id)')
        # Индекс для векторов (IVFFlat для косинусной близости)
        cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{chunks_table}_embedding ON {chunks_table} USING ivfflat (embedding vector_cosine_ops)')
        
        conn.commit()
        cursor.close()
        conn.close()
        log_message("create_user_tables", "message", 
                   f"Созданы/проверены таблицы {chatlog_table} и {chunks_table} с индексами для user_id={user_id}")
        
    except Exception as e:
        log_message("create_user_tables", "error", f"Ошибка создания таблиц: {e}")


def save_to_user_chatlog(user_id: int, source: str, author: str, message: str):
    """
    Сохраняет сообщение в таблицу пользователя с определением сессии.
    Запускает фоновое тегирование при накоплении нетэгированных сообщений.
    """
    from memory_organizer import tag_untagged_messages  # Ленивый импорт
    import yaml
    from dotenv import load_dotenv
    
    load_dotenv('conf/.env')
    
    try:
        with open('conf/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        log_message("save_to_user_chatlog", "error", f"Ошибка загрузки config.yaml: {e}")
        return
    
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


def get_recent_chat_context(user_id: int, limit: int = None) -> list:
    """
    Возвращает последние limit сообщений из чатлога пользователя, 
    исключая самое свежее (только что сохранённое).
    """
    import yaml
    from dotenv import load_dotenv
    
    load_dotenv('conf/.env')
    
    try:
        with open('conf/config.yaml', 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        log_message("get_recent_chat_context", "error", f"Ошибка загрузки config.yaml: {e}")
        return []
    
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