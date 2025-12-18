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
                message_ids INTEGER[] DEFAULT '{}',
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
    conn = db_get_connection()
    try:
        cur = conn.cursor()
        
        # Получаем последнюю сессию из БД
        cur.execute('''
            SELECT session_id, created_at 
            FROM chatlog 
            ORDER BY created_at DESC 
            LIMIT 1
        ''')
        row = cur.fetchone()
        
        timeout_hours = config_get('memory.session_timeout_hours', 6)
        now = datetime.now()
        
        if row:
            last_session_id, last_created = row
            # Проверяем, не истекла ли сессия
            if (now - last_created) <= timedelta(hours=timeout_hours):
                log_system("debug", f"Продолжена сессия: {last_session_id}")
                return last_session_id
        
        # Новая сессия
        new_session_id = int(now.timestamp())
        log_system("info", f"Создана новая сессия: {new_session_id}")
        return new_session_id
        
    finally:
        conn.close()

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

def db_get_untagged_messages(conn, limit: int = 10):
    """
    Возвращает сообщения без тегов (tag_weight IS NULL)
    Возвращает список словарей с ключами: id, source, author, message
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('''
        SELECT id, source, author, message
        FROM chatlog
        WHERE tag_weight IS NULL
        ORDER BY created_at ASC
        LIMIT %s
    ''', (limit,))
    
    rows = cur.fetchall()
    # Преобразуем в список словарей для удобства
    return [dict(row) for row in rows]

def db_update_message_tags(conn, message_id: int, weight: int, topics: list):
    """
    Обновляет теги сообщения.
    topics: список строк, например ["#здоровье", "#планы"]
    """
    cur = conn.cursor()
    cur.execute('''
        UPDATE chatlog
        SET tag_weight = %s, tag_topics = %s
        WHERE id = %s
    ''', (weight, topics, message_id))
    
    # Проверяем, что обновили именно одну строку
    if cur.rowcount != 1:
        log_system("warning", f"Обновлено {cur.rowcount} строк вместо 1 для message_id={message_id}")

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

def db_count_untagged_messages():
    """Возвращает количество нетэгированных сообщений"""
    conn = db_get_connection()
    try:
        cur = conn.cursor()
        cur.execute('''
            SELECT COUNT(*) FROM chatlog 
            WHERE tag_weight IS NULL
        ''')
        return cur.fetchone()[0]
    finally:
        conn.close()

def db_count_unchunked_messages(min_weight: int = 2):
    """Возвращает количество сообщений, готовых для чанкования"""
    conn = db_get_connection()
    try:
        cur = conn.cursor()
        # Находим последний зачанкованный ID
        last_id = db_get_last_chunked_message_id(conn)
        
        cur.execute('''
            SELECT COUNT(*) 
            FROM chatlog 
            WHERE id > %s AND tag_weight >= %s
        ''', (last_id, min_weight))
        
        return cur.fetchone()[0]
    finally:
        conn.close()

def db_get_last_chunked_message_id(conn):
    """Возвращает максимальный ID сообщения из последнего чанка, или 0 если чанков нет"""
    cur = conn.cursor()
    cur.execute('''
        SELECT message_ids[array_length(message_ids, 1)]
        FROM chunks 
        ORDER BY created_at DESC 
        LIMIT 1
    ''')
    row = cur.fetchone()
    return row[0] if row and row[0] is not None else 0

def db_get_unchunked_messages(conn, limit: int, min_weight: int = 2):
    """
    Возвращает сообщения, которых нет в чанках и с tag_weight >= min_weight.
    Берёт начиная с последнего зачанкованного ID.
    """
    last_id = db_get_last_chunked_message_id(conn)
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('''
        SELECT id, author, message, tag_weight, tag_topics
        FROM chatlog
        WHERE id > %s 
          AND tag_weight >= %s
        ORDER BY id ASC
        LIMIT %s
    ''', (last_id, min_weight, limit))
    
    rows = cur.fetchall()
    return [dict(row) for row in rows]

def db_save_chunk(conn, chunk_text: str, message_ids: list):
    """Сохраняет новый чанк"""
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO chunks (chunk_text, message_ids, created_at)
        VALUES (%s, %s, NOW())
        RETURNING id
    ''', (chunk_text, message_ids))
    
    chunk_id = cur.fetchone()[0]
    log_system("info", f"Сохранён чанк {chunk_id} с {len(message_ids)} сообщениями")
    return chunk_id     

def db_get_chunks_without_embeddings(conn, limit: int = 10):
    """
    Возвращает чанки без эмбеддингов (embedding IS NULL)
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('''
        SELECT id, chunk_text, message_ids
        FROM chunks
        WHERE embedding IS NULL
        ORDER BY created_at ASC
        LIMIT %s
    ''', (limit,))
    
    rows = cur.fetchall()
    return [dict(row) for row in rows]

def db_update_chunk_embedding(conn, chunk_id: int, embedding: list):
    """
    Обновляет эмбеддинг чанка.
    embedding: список из 1536 float
    """
    cur = conn.cursor()
    # Преобразуем список в PostgreSQL vector
    cur.execute('''
        UPDATE chunks
        SET embedding = %s
        WHERE id = %s
    ''', (embedding, chunk_id))
    
    if cur.rowcount != 1:
        log_system("warning", f"Обновлено {cur.rowcount} строк вместо 1 для chunk_id={chunk_id}")       