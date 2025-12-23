# router.py

import re
import threading

from logger import log_system, log_chat
from ai_provider import ai_get_response
from database import db_save_message, db_count_untagged_messages, db_count_unchunked_messages
from config_loader import config_get_aliases, config_get
from memory_manager import mm_create_tags, mm_create_chunks, mm_create_vectors
from memory_search import ms_process_search_request

alias_user, alias_ai = config_get_aliases()


def _extract_first_search_query(ai_response: str):
    """
    Извлекает ПЕРВЫЙ поисковый запрос из ответа AI.
    Возвращает (query, response_without_tags)
    Если тега нет - возвращает (None, исходный_текст)
    """
    pattern = r'<SEARCH>(.*?)</SEARCH>'
    match = re.search(pattern, ai_response, re.DOTALL)
    if not match:
        return None, ai_response
    
    query = match.group(1).strip()
    # Удаляем ВСЕ теги из ответа для отправки пользователю
    response_without_tags = re.sub(r'<SEARCH>.*?</SEARCH>', '', ai_response, flags=re.DOTALL).strip()
    return query, response_without_tags


def route_message(user_data: dict) -> dict:
    """
    Основной маршрутизатор сообщений (синхронный).
    Поддерживает рекурсивные поисковые запросы с ограничением глубины.
    Обрабатывает ответы AI, содержащие текст + тег <SEARCH> в одном сообщении.
    """
    
    # Извлекаем данные
    user_id = user_data.get("user_id")
    source = user_data.get("source")
    message = user_data.get("message", "")
    metadata = user_data.get("metadata", {})
    
    # Валидация
    if user_id is None or not source or not message:
        log_system("error", f"В роутер переданы некорректные данные: {user_data}")
        return {
            "user_id": user_id,
            "source": source or "unknown",
            "message": "Ошибка: некорректный формат сообщения",
            "metadata": metadata
        }
    
    # Логируем входящее сообщение
    log_system("info", f"Получено входящее сообщение в роутер")
    log_system("debug", f"{alias_user}: {message.replace('\n', ' ')}")
    log_chat(source, alias_user, message.replace('\n', ' '))

    # Сохраняем входящее сообщение в БД
    db_save_message(source=source, author=alias_user, message=message)

    # --- РЕКУРСИВНАЯ ОБРАБОТКА С ГЛУБИНОЙ ---
    max_recursion_depth = config_get('memory.max_recursion_depth', 3)
    current_depth = 0
    final_ai_response = ""
    ai_provider_used = ""
    
    # Сообщения для отправки пользователю (текст без тегов)
    messages_to_send = []
    
    while current_depth <= max_recursion_depth:
        # Вызов AI (всегда загружает историю из БД через include_history=True)
        log_system("info", f"Цикл AI, глубина {current_depth}")
        ai_response, ai_provider = _ai_processor(user_id, message, source, metadata)
        ai_provider_used = ai_provider
        
        # Извлекаем поисковый запрос и очищаем ответ от тегов
        search_query, clean_response = _extract_first_search_query(ai_response)
        
        # Если есть текст помимо тега - сохраняем его и готовим к отправке
        if clean_response:
            log_system("debug", f"Текст ответа AI без тегов: '{clean_response.replace('\n', ' ')}...'")
            messages_to_send.append(clean_response)  # Запоминаем для отправки пользователю
            
            # Сохраняем очищенный ответ в БД (но только если это не дубликат)
            # Проверяем, не было ли уже такого сообщения в этой сессии
            if not messages_to_send or clean_response != messages_to_send[-1]:
                db_save_message(source=ai_provider, author=alias_ai, message=clean_response)
        
        # Проверяем, есть ли поисковый запрос
        if search_query:
            log_system("info", f"Обнаружен поисковый запрос в ответе AI: '{search_query}'")
            
            # Достигнут лимит глубины?
            if current_depth >= max_recursion_depth:
                # Сохраняем запрос AI (несмотря на лимит)
                db_save_message(source=ai_provider, author=alias_ai, 
                               message=f"<SEARCH>{search_query}</SEARCH>",
                               tag_weight=0, tag_topics=["#_поиск_запрос_лимит"])
                # Выходим из цикла, финальный ответ - последний clean_response
                final_ai_response = clean_response if clean_response else ai_response
                break
            
            # Нормальная обработка поискового запроса
            # 1. Сохраняем поисковый запрос (от AI) в БД
            db_save_message(source=ai_provider, author=alias_ai, 
                           message=f"<SEARCH>{search_query}</SEARCH>",
                           tag_weight=0, tag_topics=["#_поиск_запрос"])
            
            # 2. Выполняем поиск
            search_results = ms_process_search_request(f"<SEARCH>{search_query}</SEARCH>")
            
            # 3. Сохраняем результаты поиска (от системы) в БД
            if search_results:
                db_save_message(source="memory_search", author=alias_user, 
                               message=search_results,
                               tag_weight=0, tag_topics=["#_поиск_результаты"])
            
            # 4. Увеличиваем глубину и продолжаем цикл
            current_depth += 1
            log_system("info", f"Глубина увеличена до {current_depth}")
            continue  # Цикл начнётся заново, AI загрузит из БД свежие сообщения
            
        else:
            # Поискового запроса нет - это финальный ответ
            final_ai_response = clean_response if clean_response else ai_response
            break
    
    # Если вышли по лимиту глубины (все ответы содержали поисковые запросы)
    if not final_ai_response and current_depth > max_recursion_depth:
        # Делаем финальный вызов AI (он загрузит всю историю из БД, включая последний запрос)
        log_system("info", "Финальный вызов AI после достижения лимита глубины")
        final_ai_response, ai_provider_used = _ai_processor(user_id, message, source, metadata)
        
        # Очищаем от тегов на случай, если в финальном ответе тоже есть тег
        _, final_ai_response = _extract_first_search_query(final_ai_response)
    
    # Отправляем пользователю ВСЕ накопленные сообщения (текст без тегов)
    for msg in messages_to_send:
        log_system("debug", f"Промежуточное сообщение для отправки: '{msg.replace('\n', ' ')}...'")
        # Здесь нужно отправить msg в ТГ, если твоя архитектура это поддерживает
        # Пока просто логируем
    
    # Логируем исходящий ответ (финальный)
    log_system("info", f"Сформировано исходящее сообщение из роутера")
    log_system("debug", f"{alias_ai}: {final_ai_response.replace('\n', ' ')}")
    log_chat(ai_provider_used, alias_ai, final_ai_response.replace('\n', ' '))

    # Сохраняем исходящее сообщение в БД (финальный ответ)
    db_save_message(source=ai_provider_used, author=alias_ai, message=final_ai_response)

    # Инициализация процессов памяти
    untagged_count = db_count_untagged_messages()
    unchunked_count = db_count_unchunked_messages()

    tagging_batch_size = config_get('memory.tagging_batch_size', 10)
    chunk_size = config_get('memory.chunk_size', 10)

    log_system("info", f"Нетэгированных сообщений {untagged_count}, незачанкованных сообщений {unchunked_count}")

    if unchunked_count >= chunk_size:
        log_system("info", f"Запуск чанкования для {unchunked_count} сообщений")
        mm_create_chunks()

    mm_create_vectors()
    
    # Формируем ответ для фронтенда
    # Объединяем все промежуточные сообщения и финальный ответ
    all_messages = []
    
    # Добавляем промежуточные сообщения (текст без тегов)
    for msg in messages_to_send:
        if msg and msg.strip():
            all_messages.append(msg.strip())
    
    # Добавляем финальный ответ, если он отличается от последнего промежуточного
    if final_ai_response and final_ai_response.strip():
        if not all_messages or all_messages[-1] != final_ai_response.strip():
            all_messages.append(final_ai_response.strip())
    
    # Объединяем все сообщения двойными переносами строк
    if all_messages:
        full_response = "\n\n".join(all_messages)
    else:
        full_response = final_ai_response if final_ai_response else ""
    
    return {
        "user_id": user_id,
        "source": source,
        "message": full_response,
        "metadata": metadata
    }


def _ai_processor(user_id, message: str, source: str, metadata: dict) -> tuple:
    """
    AI-процессор. Вызывает реальный AI-провайдер.
    Вся история загружается из БД через ai_get_response.
    """
    try:
        response_text, provider = ai_get_response(
            user_message=message,
            provider_name=None,
            persona=None
            # additional_context не передаём - всё уже в БД
        )
        return response_text, provider
    except Exception as e:
        log_system("error", f"Ошибка в AI процессоре: {e}")
        username = metadata.get("username", f"user_{user_id}")
        fallback_response = f" AI недоступен."
        return fallback_response, "xxx"