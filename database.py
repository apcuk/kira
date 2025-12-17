# database.py

import os
import psycopg2
import psycopg2.extras
import yaml

from datetime import datetime, timedelta

from logger import log_system
from config_loader import config_get

# ============ КОНФИГУРАЦИЯ ============
# DB_URL = os.getenv('DB_URL')

#def _load_memory_config():
#    """Загружает конфиг памяти из config.yaml"""
#    try:
#        with open('conf/config.yaml', 'r', encoding='utf-8') as f:
#            config = yaml.safe_load(f)
#        return config.get('memory', {})
#    except Exception as e:
#        log_system("error", f"Ошибка загрузки конфига памяти: {e}")
#        return {'session_timeout_hours': 6}  # fallback
#
#MEMORY_CONFIG = _load_memory_config()

# ============ СОСТОЯНИЕ СЕССИИ ============
_CURRENT_SESSION_ID = None
_LAST_MESSAGE_TIME = None

# ============ БАЗОВЫЕ ФУНКЦИИ БД ============
def db_get_connection():
    """Возвращает подключение к БД"""
    db_url = os.getenv('DB_URL')
    if not db_url:
        raise ValueError("DB_URL не задан в .env")
    return psycopg2.connect(db_url)

def db_init_tables():
    """Создаёт таблицы chatlog и chunks если их нет, добавляет индексы"""
    conn = db_get_connection()
    try:
        cur = conn.cursor()
        
        # chatlog
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chatlog (
                id SERIAL PRIMARY KEY,
                source VARCHAR(50) NOT NULL,
                author VARCHAR(50) NOT NULL,
                message TEXT NOT NULL,
                tag_weight INTEGER,
                tag_topics TEXT[],
                session_id BIGINT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        # Индекс для быстрого чанкования (сортировка по времени)
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_chatlog_created 
            ON chatlog (created_at DESC)
        ''')
        
        # chunks
        cur.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id SERIAL PRIMARY KEY,
                chunk_text TEXT NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                embedding vector(1536)
            )
        ''')
        
        # Векторный индекс для быстрого поиска (IVFFlat для pgvector)
        cur.execute('''
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
            ON chunks 
            USING ivfflat (embedding vector_cosine_ops)
        ''')
        
        conn.commit()
        log_system("info", "Таблицы и индексы инициализированы")
    finally:
        conn.close()

# ============ ЛОГИКА СЕССИЙ ============
def db_get_or_create_session_id():
    """Возвращает текущий session_id, создаёт новый если сессия истекла"""
    global _CURRENT_SESSION_ID, _LAST_MESSAGE_TIME
    
    now = datetime.now()
    timeout_hours = config_get('memory.session_timeout_hours', 6)
    
    # Если это первое сообщение или сессия истекла
    if (_CURRENT_SESSION_ID is None or 
        _LAST_MESSAGE_TIME is None or
        (now - _LAST_MESSAGE_TIME) > timedelta(hours=timeout_hours)):
        
        # Новая сессия: timestamp первого сообщения
        _CURRENT_SESSION_ID = int(now.timestamp())
        log_system("info", f"Создана новая сессия: {_CURRENT_SESSION_ID}")
    
    # Обновляем время последнего сообщения
    _LAST_MESSAGE_TIME = now
    return _CURRENT_SESSION_ID

def db_save_message(source: str, author: str, message: str):
    """Сохраняет сообщение, автоматически определяя session_id"""
    session_id = db_get_or_create_session_id()
    
    conn = db_get_connection()
    try:
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO chatlog (source, author, message, session_id)
            VALUES (%s, %s, %s, %s)
        ''', (source, author, message, session_id))
        
        conn.commit()
        log_system("info", f"Сообщение сохранено в БД (сессия {session_id}): {author[:20]}...")
    finally:
        conn.close()

def db_get_recent_messages(limit: int = 10):
    """Возвращает последние limit сообщений из chatlog"""
    conn = db_get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('''
            SELECT source, author, message, created_at
            FROM chatlog
            ORDER BY created_at DESC
            LIMIT %s
        ''', (limit,))
        rows = cur.fetchall()
        return rows
    finally:
        conn.close()