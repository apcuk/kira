# memory_organizer.py v.0.5

import os
import json
import logging
from openai import OpenAI
from dotenv import load_dotenv
import psycopg2
import yaml

# Загружаем конфиги
load_dotenv('conf/.env')

try:
    with open('conf/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
except Exception as e:
    logging.error(f"[error.memory_organizer] Ошибка загрузки config.yaml: {e}")
    config = {}

# Логирование
logger = logging.getLogger('system')

def get_db_connection():
    """Возвращает подключение к БД."""
    db_url = os.getenv('DB_URL')
    return psycopg2.connect(db_url)

def load_prompt_tags_template() -> str:
    """Загружает шаблон промпта для тегирования из файла."""
    try:
        with open('conf/prompt_tags.md', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.error("[error.load_prompt_tags_template] Файл conf/prompt_tags.md не найден")
        return None

def build_tagging_prompt(messages: list) -> str:
    """Формирует промпт для тегирования пачки сообщений."""
    template = load_prompt_tags_template()
    if not template:
        return ""
    
    numbered_messages = "\n".join([f"{i+1}. {msg}" for i, msg in enumerate(messages)])
    return template.replace("{numbered_messages}", numbered_messages)

def call_deepseek_for_tagging(prompt: str) -> str:
    """Отправляет промпт в DeepSeek и возвращает ответ."""
    api_key = os.getenv('API_KEY_DEEPSEEK')
    if not api_key:
        logger.error("[error.call_deepseek_for_tagging] API_KEY_DEEPSEEK не найден")
        return None
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        logger.error(f"[error.call_deepseek_for_tagging] Ошибка DeepSeek API: {e}")
        return None

def parse_tag_ai_response(ai_response: str, expected_len: int):
    """
    Парсит ответ AI в формате:
    1. #тег1,#тег2 trash:yes/no
    2. #тег1 trash:yes/no
    Возвращает список словарей или None при ошибке.
    """
    if not ai_response:
        logger.error("[error.parse_tag_ai_response] Пустой ответ AI")
        return None
    
    logger.info(f"[message.parse_tag_ai_response] Ответ AI:\n{ai_response[:1000]}")
    
    lines = ai_response.strip().split('\n')
    tags_list = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Проверяем формат: "1. #тег1,#тег2 trash:yes"
        # Убираем номер с точкой в начале
        if '.' in line:
            line = line.split('.', 1)[1].strip()
        
        # Разделяем теги и trash-флаг
        if ' trash:' not in line:
            logger.warning(f"[warning.parse_tag_ai_response] Строка без trash: {line}")
            tags_list.append({"topics": [], "trash": False})
            continue
        
        tags_part, trash_part = line.split(' trash:', 1)
        tags_part = tags_part.strip()
        trash_part = trash_part.strip().lower()
        
        # Парсим теги
        topics = []
        if tags_part:
            # Разделяем запятыми, убираем пустые
            raw_tags = [tag.strip() for tag in tags_part.split(',') if tag.strip()]
            for tag in raw_tags:
                if tag.startswith('#'):
                    topics.append(tag)
                else:
                    # Если забыл # — добавляем
                    topics.append(f"#{tag}")
        
        # Парсим trash
        trash = trash_part == 'yes'
        
        tags_list.append({"topics": topics, "trash": trash})
    
    # Проверяем количество
    if len(tags_list) != expected_len:
        logger.warning(f"[warning.parse_tag_ai_response] Количество строк ({len(tags_list)}) не совпадает с ожидаемым ({expected_len})")
        # Дополняем или обрезаем
        if len(tags_list) > expected_len:
            tags_list = tags_list[:expected_len]
        else:
            while len(tags_list) < expected_len:
                tags_list.append({"topics": [], "trash": False})
    
    logger.info(f"[message.parse_tag_ai_response] Успешно распаршено {len(tags_list)} записей")
    return tags_list

def generate_embeddings_for_new_chunks(user_id: int):
    """Генерирует и сохраняет эмбеддинги для чанков без embedding."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    chunks_table = f"user_{user_id}_chunks"
    
    # Выбираем чанки без эмбеддингов
    cursor.execute(f"""
        SELECT id, chunk_text 
        FROM {chunks_table} 
        WHERE embedding IS NULL 
        ORDER BY id ASC
        LIMIT 50
    """)
    
    rows = cursor.fetchall()
    if not rows:
        logger.info(f"[embeddings] Нет новых чанков для векторизации, user_id={user_id}")
        cursor.close()
        conn.close()
        return
    
    # Готовим запрос к OpenAI Embeddings
    import openai
    api_key = os.getenv('API_KEY_OPENAI')
    if not api_key:
        logger.error("[embeddings] API_KEY_OPENAI не найден")
        cursor.close()
        conn.close()
        return
    
    client = openai.OpenAI(api_key=api_key)
    
    try:
        # Отправляем батч
        texts = [row[1] for row in rows]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
            encoding_format="float"
        )
        
        # Обновляем каждый чанк
        for (chunk_id, _), embedding_data in zip(rows, response.data):
            embedding_vector = embedding_data.embedding
            cursor.execute(
                f"UPDATE {chunks_table} SET embedding = %s WHERE id = %s",
                (embedding_vector, chunk_id)
            )
        
        conn.commit()
        logger.info(f"[embeddings] Векторизовано {len(rows)} чанков для user_id={user_id}")
        
    except Exception as e:
        logger.error(f"[embeddings] Ошибка OpenAI Embeddings: {e}")
        conn.rollback()
    
    cursor.close()
    conn.close()

def tag_untagged_messages(user_id: int, batch_size: int = None):
    """
    Находит нетэгированные сообщения пользователя, отправляет пачкой на тегирование 
    и обновляет записи в БД.
    """
    if batch_size is None:
        batch_size = config.get('memory', {}).get('tagging_batch_size', 10)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    table_name = f"user_{user_id}_chatlog"
    
    # Выбираем нетэгированные сообщения (старые сначала)
    cursor.execute(f"""
        SELECT id, message 
        FROM {table_name} 
        WHERE tag_topics IS NULL 
        ORDER BY created_at ASC 
        LIMIT %s
    """, (batch_size,))
    
    rows = cursor.fetchall()
    if not rows:
        logger.info(f"[message.tag_untagged_messages] Нет нетэгированных сообщений для user_id={user_id}")
        cursor.close()
        conn.close()
        return
    
    ids = [row[0] for row in rows]
    messages = [row[1] for row in rows]
    
    logger.info(f"[message.tag_untagged_messages] Начало тегирования {len(messages)} сообщений для user_id={user_id}")
    
    # Формируем промпт для батча
    prompt = build_tagging_prompt(messages)
    if not prompt:
        logger.error("[error.tag_untagged_messages] Не удалось создать промпт")
        cursor.close()
        conn.close()
        return
    
    # Отправляем в DeepSeek
    ai_response = call_deepseek_for_tagging(prompt)
    if not ai_response:
        logger.error(f"[error.tag_untagged_messages] Ошибка AI для user_id={user_id}")
        cursor.close()
        conn.close()
        return
    
    # Парсим ответ AI
    tags_list = parse_tag_ai_response(ai_response, len(ids))
    if not tags_list:
        logger.error(f"[error.tag_untagged_messages] Не удалось распарсить ответ AI для user_id={user_id}")
        cursor.close()
        conn.close()
        return
    
    # Обновляем записи в БД
    try:
        for msg_id, tags_data in zip(ids, tags_list):
            topics = tags_data["topics"]
            trash = tags_data["trash"]
            
            cursor.execute(f"""
                UPDATE {table_name} 
                SET tag_topics = %s, tag_trash = %s 
                WHERE id = %s
            """, (json.dumps(topics), trash, msg_id))
        
        conn.commit()
        logger.info(f"[message.tag_untagged_messages] Успешно тегировано {len(ids)} сообщений для user_id={user_id}")

    except Exception as e:
        logger.error(f"[error.tag_untagged_messages] Ошибка обновления БД: {e}")
        conn.rollback()
        cursor.close()
        conn.close()
        return  # Выходим, не запускаем чанкование
    
    # Чанкование ВНЕ блока try, чтобы его ошибки логировались отдельно
    logger.info(f"[tagging] Запуск чанкования после тегирования для user_id={user_id}")
    try:
        create_chunks(user_id)
    except Exception as e:
        logger.error(f"[error.create_chunks] Ошибка чанкования: {e}")
    
    cursor.close()
    conn.close()

def create_chunks(user_id: int):
    """
    Создаёт чанки из тегированных, не мусорных сообщений.
    Использует last_message_id_stop для определения точки старта и сохраняет перекрытие.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    chatlog_table = f"user_{user_id}_chatlog"
    chunks_table = f"user_{user_id}_chunks"
    
    # Получаем параметры чанкования
    chunk_size = config.get('memory', {}).get('chunk_size', 10)
    chunk_step = config.get('memory', {}).get('chunk_step_size', 6)
    overlap = chunk_size - chunk_step  # перекрытие
    
    # 1. Находим последний обработанный message_id_stop
    cursor.execute(f"SELECT MAX(message_id_stop) FROM {chunks_table}")
    last_stop_row = cursor.fetchone()
    last_stop = last_stop_row[0] if last_stop_row[0] is not None else 0
    
    # 2. Вычисляем raw-старт для следующего чанка
    if last_stop == 0:
        start_id = 1
    else:
        start_id = last_stop - overlap + 1
        if start_id < 1:
            start_id = 1
    
    logger.info(f"[chunking] user_id={user_id}, last_stop={last_stop}, start_id={start_id}, chunk_size={chunk_size}, step={chunk_step}")
    
    # 3. Выбираем все подходящие сообщения, начиная с start_id
    cursor.execute(f"""
        SELECT id, message, session_id, author
        FROM {chatlog_table}
        WHERE id >= %s 
          AND tag_topics IS NOT NULL 
          AND tag_trash = FALSE
        ORDER BY id ASC
    """, (start_id,))
    
    messages = cursor.fetchall()
    
    if not messages:
        logger.info(f"[chunking] Нет сообщений для чанкования, user_id={user_id}")
        cursor.close()
        conn.close()
        return
    
    # 4. Разбиваем на чанки скользящим окном
    chunks_created = 0
    total_messages = len(messages)
    
    i = 0
    while i < total_messages:
        # Берём chunk_size сообщений, начиная с i
        chunk_messages = messages[i:i + chunk_size]
        if len(chunk_messages) < chunk_size:
            break
        
        # Собираем данные чанка
        msg_ids = [msg[0] for msg in chunk_messages]
        session_ids = list(set(msg[2] for msg in chunk_messages))
        
        # Форматируем текст чанка: [Автор] сообщение
        messages_formatted = []
        for msg in chunk_messages:
            msg_id, msg_text, session_id, author = msg
            messages_formatted.append(f"[{author}] {msg_text}")
        
        chunk_text = "\n".join(messages_formatted)
        message_id_start = min(msg_ids)
        message_id_stop = max(msg_ids)
        session_id = session_ids[0] if len(session_ids) == 1 else 0
        
        # Вставляем чанк в БД (chunk_meta пока NULL)
        cursor.execute(f"""
            INSERT INTO {chunks_table} 
            (chunk_text, message_id_start, message_id_stop, session_id, chunk_meta)
            VALUES (%s, %s, %s, %s, NULL)
        """, (chunk_text, message_id_start, message_id_stop, session_id))
        
        chunks_created += 1
        i += chunk_step
    
    conn.commit()
    logger.info(f"[chunking] Создано {chunks_created} чанков для user_id={user_id}")
    
    cursor.close()
    conn.close()

    # Векторизуем новые чанки
    logger.info(f"[chunking] Запуск векторизации для user_id={user_id}")
    try:
        generate_embeddings_for_new_chunks(user_id)
    except Exception as e:
        logger.error(f"[error.embeddings] Ошибка векторизации: {e}")