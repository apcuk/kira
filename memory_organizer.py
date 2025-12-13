# memory_organizer.py v.0.3
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
    Пытается распарсить ответ AI как массив объектов.
    Возвращает список словарей или None при ошибке.
    """
    if not ai_response:
        logger.error("[error.parse_tag_ai_response] Пустой ответ AI")
        return None
    
    # Логируем сырой ответ для отладки
    logger.info(f"[message.parse_tag_ai_response] Сырой ответ AI (первые 1000 символов): {ai_response[:1000]}")
    
    try:
        data = json.loads(ai_response)
    except json.JSONDecodeError as e:
        logger.error(f"[error.parse_tag_ai_response] Ошибка парсинга JSON: {e}")
        return None
    
    # Если ответ — словарь, возможно, массив внутри поля 'result' или 'tags'
    if isinstance(data, dict):
        logger.info(f"[message.parse_tag_ai_response] Ответ AI — словарь, ключи: {list(data.keys())}")
        # Ищем массив в возможных полях
        for key in ['result', 'tags', 'data', 'array']:
            if key in data and isinstance(data[key], list):
                data = data[key]
                break
    
    # Теперь data должен быть списком
    if not isinstance(data, list):
        logger.error(f"[error.parse_tag_ai_response] Ответ AI не является массивом. Тип: {type(data)}")
        return None
    
    if len(data) != expected_len:
        logger.warning(f"[warning.parse_tag_ai_response] Количество элементов в массиве ({len(data)}) не совпадает с ожидаемым ({expected_len})")
        # Можно продолжить, обрежем или дополним
        if len(data) > expected_len:
            data = data[:expected_len]
        else:
            # Дополним пустыми объектами
            while len(data) < expected_len:
                data.append({"topics": [], "trash": False})
    
    # Проверяем структуру каждого элемента
    validated_list = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            logger.warning(f"[warning.parse_tag_ai_response] Элемент {i} не является словарем: {item}")
            item = {"topics": [], "trash": False}
        
        topics = item.get("topics", [])
        if not isinstance(topics, list):
            topics = []
        
        trash = item.get("trash", False)
        if not isinstance(trash, bool):
            trash = False
        
        validated_list.append({"topics": topics, "trash": trash})
    
    return validated_list

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
    tags_list = parse_tag_ai_response(ai_response, len(ids))  # ← ИСПРАВЛЕНО ИМЯ ФУНКЦИИ
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