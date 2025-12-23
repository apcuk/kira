# memory_search.py

"""
Модуль для поиска по векторной памяти.
Обрабатывает поисковые запросы AI (<SEARCH>...</SEARCH>).
"""

import os
import re
from typing import List, Dict, Any, Optional

import psycopg2
import psycopg2.extras
from openai import OpenAI

from logger import log_system
from config_loader import config_get
from database import db_get_connection


# ============ УТИЛИТЫ ============
def ms_extract_search_query(ai_response: str) -> Optional[str]:
    """
    Извлекает поисковый запрос из тегов <SEARCH> в ответе AI.
    Возвращает запрос или None, если тег не найден.
    """
    pattern = r'<SEARCH>(.*?)</SEARCH>'
    match = re.search(pattern, ai_response, re.DOTALL)
    if match:
        query = match.group(1).strip()
        if query:
            return query
    return None


def ms_query_embedding(query_text: str) -> Optional[List[float]]:
    """
    Векторизует текстовый запрос через OpenAI Embeddings API.
    Возвращает список из 1536 float или None при ошибке.
    """
    api_key = os.getenv('API_KEY_OPENAI')
    if not api_key:
        log_system("error", "API_KEY_OPENAI не задан")
        return None
    
    try:
        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=query_text,
            encoding_format="float"
        )
        embedding = response.data[0].embedding
        log_system("info", f"Векторизован поисковый запрос: '{query_text}...'")
        return embedding
    except Exception as e:
        log_system("error", f"Ошибка векторизации поискового запроса: {e}")
        return None


def ms_search_similar_chunks(query_embedding: List[float], limit: int = None) -> List[Dict[str, Any]]:
    """
    Ищет в БД чанки, наиболее близкие к вектору запроса (косинусное сходство).
    Возвращает список словарей с ключами: chunk_text, similarity (косинусная близость), chunk_id.
    Фильтрует по порогу сходства.
    """
    if limit is None:
        limit = config_get('memory.search_chunks_limit', 3)
    
    similarity_threshold = config_get('memory.search_similarity_threshold', 0.28)
    
    conn = db_get_connection()
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Косинусное сходство: embedding <=> query_embedding
        cur.execute('''
            SELECT 
                id,
                chunk_text,
                1 - (embedding <=> %s::vector) AS similarity
            FROM chunks
            WHERE embedding IS NOT NULL
            ORDER BY similarity DESC
            LIMIT %s
        ''', (query_embedding, limit))
        
        rows = cur.fetchall()
        results = []
        for row in rows:
            similarity = float(row['similarity'])
            if similarity >= similarity_threshold:
                results.append({
                    'chunk_id': row['id'],
                    'chunk_text': row['chunk_text'],
                    'similarity': similarity
                })
        
        # Логируем статистику с ID
        log_system("info", f"Найдено {len(results)} чанков после фильтрации по порогу {similarity_threshold}")
        
        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ КАЖДОГО ЧАНКА
        for i, chunk in enumerate(results, 1):
            chunk_id = chunk['chunk_id']
            similarity = chunk['similarity']
            text = chunk['chunk_text']
            
            # Пытаемся извлечь дату из чанка (первая строка)
            first_line = text.split('\n')[0] if '\n' in text else text[:100]
            
            log_system("info", f"Чанк {i} ID: #{chunk_id}, сходство: {similarity:.3f}")
            # Полный текст в DEBUG если нужно
            log_system("debug", f"Полное содержание чанка {chunk_id}: {text.replace('\n', ' ')}")
        
        # Или если чанков нет
        if not results:
            log_system("info", "Нет чанков, прошедших порог сходства.")
        
        return results
        
    except Exception as e:
        log_system("error", f"Ошибка поиска чанков: {e}")
        return []
    finally:
        conn.close()


def ms_format_search_results(query: str, chunks: List[Dict]) -> str:
    """
    Форматирует результаты поиска в текстовый блок для AI.
    """
    if not chunks:
        return "По вашему запросу ничего не найдено в памяти."
    
    lines = [f"Результаты поиска по запросу «{query}»:\n"]
    
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"--- Фрагмент {i} (ID: {chunk['chunk_id']}, сходство: {chunk['similarity']:.2f}) ---")
        lines.append(chunk['chunk_text'])
        lines.append("")  # пустая строка между чанками
    
    return "\n".join(lines).strip()


# ============ ОСНОВНОЙ ИНТЕРФЕЙС ============
def ms_process_search_request(ai_response: str) -> Optional[str]:
    """
    Основная функция: обрабатывает ответ AI, содержащий тег <SEARCH>.
    Возвращает отформатированные результаты поиска или None, если тег не найден.
    """
    # 1. Извлекаем запрос
    query = ms_extract_search_query(ai_response)
    if query is None:
        return None
    
    log_system("info", f"Обнаружен поисковый запрос: '{query}'")
    
    # 2. Векторизуем запрос
    query_embedding = ms_query_embedding(query)
    if query_embedding is None:
        return "Ошибка векторизации запроса. Поиск невозможен."
    
    # 3. Ищем чанки
    chunks = ms_search_similar_chunks(query_embedding)
    
    # 4. Форматируем результаты
    results_text = ms_format_search_results(query, chunks)
    
    # 5. Сохраняем запрос и результаты в БД (это будет делать router)
    # Здесь просто возвращаем текст для AI
    return results_text


# Для тестирования модуля
if __name__ == "__main__":
    # Тестовый запрос
    test_response = "<SEARCH>любимый офильм пользователя</SEARCH>"
    print(f"Тестовый ответ AI: {test_response}")
    
    results = ms_process_search_request(test_response)
    if results:
        print("\nРезультаты поиска:")
        print(results[:500] + "..." if len(results) > 500 else results)
    else:
        print("Тег <SEARCH> не найден.")