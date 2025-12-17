# memory_manager.py
import time
import threading
import json
import re
from typing import List, Dict, Any
from logger import log_system
from ai_provider import ai_deepseek_request, ai_openai_request
from config_loader import config_get
from database import (
    db_get_connection,
    db_get_untagged_messages,
    db_update_message_tags,
    db_get_recent_messages,
    # db_save_chunk,
    # db_get_chunks_without_embeddings,
    # db_update_chunk_embedding
)


# ============ ТЭГИРОВАНИЕ ============
def mm_ai_message_tagger(messages_batch):
    """Тэгирует пачку сообщений через AI"""
    batch_size = len(messages_batch)
    
    # 1. Загружаем промпт
    try:
        prompt_file = config_get('memory.tagger_prompt_file', 'conf/prompt_tags.md')
        with open(prompt_file, 'r', encoding='utf-8') as f:
            prompt_template = f.read().strip()
    except Exception as e:
        log_system("error", f"Ошибка загрузки промпта: {e}")
        return [{'weight': 2, 'topics': ["#_ошибка_тегирования"]} for _ in range(batch_size)]
    
    # 2. Подставляем сообщения с авторами
    messages_text = ""
    for item in messages_batch:
        messages_text += f"{item['author']}: {item['message']}\n"
    
    full_prompt = prompt_template.replace("[batchsize]", str(batch_size))
    full_prompt = full_prompt.replace("[message]", messages_text.strip())
    
    # 3. Вызываем AI
    provider = config_get('memory.tagger_provider', 'deepseek')
    model = config_get('memory.tagger_model', 'deepseek-chat')

    try:
        messages = [{"role": "user", "content": full_prompt}]
    
        if provider == "deepseek":
            response = ai_deepseek_request(messages, model=model)
        elif provider == "openai":
            response = ai_openai_request(messages, model=model)
        else:
            raise ValueError(f"Неизвестный провайдер: {provider}")
        
        log_system("debug", f"Ответ от {provider} ({model}): {response[:500]}")

        # 4. Парсим ответ
        lines = [line.strip() for line in response.split('\n') if line.strip()]
        
        # Проверяем количество строк
        if len(lines) != batch_size:
            log_system("warning", f"AI вернул {len(lines)} строк вместо {batch_size}")
            if len(lines) > batch_size:
                lines = lines[:batch_size]
            else:
                while len(lines) < batch_size:
                    lines.append("")
        
        results = []
        for line in lines:
            try:
                parts = line.split()
                if not parts:
                    raise ValueError("Пустая строка от AI")
                
                weight = int(parts[0])
                tags = [tag for tag in parts[1:] if tag.startswith('#')]
                
                if not 1 <= weight <= 3:
                    raise ValueError(f"Вес вне диапазона: {weight}")
                
                if weight == 1:
                    if "#_мусор" not in tags:
                        tags = ["#_мусор"]
                
                results.append({'weight': weight, 'topics': tags})
                
            except Exception as e:
                log_system("warning", f"Ошибка парсинга строки '{line}': {e}")
                results.append({'weight': 2, 'topics': ["#_ошибка_тегирования"]})
        
        return results
        
    except Exception as e:
        log_system("error", f"Ошибка AI тэгирования: {e}")
        log_system("debug", f"Промпт (первые 1000 символов): {full_prompt[:1000]}")
        if hasattr(e, 'response'):
            log_system("debug", f"Статус: {e.response.status_code}, Тело: {e.response.text}")
        return [{'weight': 2, 'topics': ["#_ошибка_тегирования"]} for _ in range(batch_size)]


def mm_create_tags(batch_size: int = None):
    """Тэгирует batch_size нетэгированных сообщений через AI"""
    if batch_size is None:
        batch_size = config_get('memory.tagging_batch_size', 10)
    
    conn = db_get_connection()
    try:
        untagged = db_get_untagged_messages(conn, limit=batch_size)
        if not untagged:
            log_system("debug", "Нет сообщений для тэгирования")
            return
        
        log_system("info", f"Начинаем тэгирование {len(untagged)} сообщений")
        
        messages_data = []
        for msg in untagged:
            messages_data.append({
                'author': msg['author'],
                'message': msg['message']
            })
        
        tags_results = mm_ai_message_tagger(messages_data)
        
        for i, msg in enumerate(untagged):
            if i < len(tags_results):
                tags = tags_results[i]
                db_update_message_tags(conn, msg['id'], tags['weight'], tags['topics'])
        
        conn.commit()
        log_system("info", f"Тэгирование завершено для {len(untagged)} сообщений")
        
    except Exception as e:
        log_system("error", f"Ошибка тэгирования: {e}")
        conn.rollback()
    finally:
        conn.close()


# ============ ЧАНКОВАНИЕ ============
def mm_create_chunks(chunk_size: int = None, overlap: int = None):
    """Создаёт чанки если накопилось достаточно сообщений"""
    if chunk_size is None:
        chunk_size = config_get('memory.chunk_size', 10)
    if overlap is None:
        overlap = config_get('memory.chunk_step_size', 3)
    
    pass


# ============ ВЕКТОРИЗАЦИЯ ============
def mm_create_vectors():
    """Векторизует чанки без эмбеддингов"""
    pass


# ============ ФОНОВАЯ ЗАДАЧА ============
def mm_background_worker(interval_sec: int = None):
    """Фоновая задача для обработки памяти"""
    if interval_sec is None:
        interval_sec = config_get('memory.background_interval_sec', 60)
    
    log_system("info", f"Фоновая задача памяти запущена (интервал {interval_sec}с)")
    
    while True:
        try:
            mm_create_tags()
            mm_create_chunks()
            mm_create_vectors()
        except Exception as e:
            log_system("error", f"Ошибка в фоновой задаче памяти: {e}")
        
        time.sleep(interval_sec)


# ============ ЗАПУСК ============
def mm_start_background():
    """Запускает фоновую задачу в отдельном потоке"""
    thread = threading.Thread(target=mm_background_worker, daemon=True)
    thread.start()
    log_system("info", "Фоновая задача памяти запущена в отдельном потоке")
    return thread