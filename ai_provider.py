# ai_provider.py

import os

from typing import List, Dict, Any
from openai import OpenAI

from logger import log_system, log_chat
from database import db_get_recent_messages
from config_loader import config_get  # <--- НОВЫЙ ИМПОРТ

# ЗАГРУЗКА .env
from dotenv import load_dotenv
load_dotenv('conf/.env')

# ============ ФОРМИРОВАНИЕ СООБЩЕНИЙ ============

def ai_build_messages(user_message: str, persona: str = None, 
                      include_history: bool = True,
                      additional_context: list = None) -> List[Dict]:
    """
    Формирует список сообщений для OpenAI API.
    Включает историю диалога из БД если include_history=True.
    additional_context: список дополнительных сообщений в формате {"role": "...", "content": "..."}
    """
    messages = []
    system_count = 0
    history_count = 0
    additional_count = 0
    
    # 1. Системные промпты (персона)
    if persona:
        persona_file = f"conf/{persona}.md"
        if os.path.exists(persona_file):
            with open(persona_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            # Разбиваем на блоки по ##
            blocks = []
            current_block = []
            
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('## '):
                    if current_block:
                        blocks.append('\n'.join(current_block))
                        current_block = []
                if line:
                    current_block.append(line)
            
            if current_block:
                blocks.append('\n'.join(current_block))
            
            # Обрабатываем каждый блок
            for block_idx, block in enumerate(blocks, 1):
                # Извлекаем заголовок блока (первая строка, начинающаяся с ##)
                header = None
                for line in block.split('\n'):
                    if line.strip().startswith('## '):
                        header = line.strip()[3:].strip()  # убираем ## и пробелы
                        break
                
                # Убираем все строки, начинающиеся с ##
                clean_lines = [line for line in block.split('\n') 
                              if not line.strip().startswith('##')]
                clean_content = '\n'.join(clean_lines).strip()
                
                if clean_content:
                    # ЛОГИРУЕМ КАЖДОЕ СИСТЕМНОЕ СООБЩЕНИЕ
                    log_system("debug", f"Системное сообщение [{system_count + 1}] '{header or 'без заголовка'}': {clean_content.replace('\n', ' ')}")
                    
                    messages.append({"role": "system", "content": clean_content})
                    system_count += 1
                
        else:
            fallback_content = f"Ты — {persona}. Отвечай как друг."
            log_system("debug", f"Системное сообщение [{system_count + 1}]: {fallback_content.replace('\n', ' ')}")
            
            messages.append({"role": "system", "content": fallback_content})
            system_count += 1
    else:
        fallback_content = "Ты — полезный ассистент."
        log_system("debug", f"Системное сообщение [{system_count + 1}]: {fallback_content.replace('\n', ' ')}")
        
        messages.append({"role": "system", "content": fallback_content})
        system_count += 1
    
    # 1.1. Промпт памяти (НОВЫЙ)
    try:
        memory_prompt_file = config_get('memory.memory_prompt_file')
        if memory_prompt_file and os.path.exists(memory_prompt_file):
            with open(memory_prompt_file, 'r', encoding='utf-8') as f:
                memory_content_raw = f.read().strip()
            
            if memory_content_raw:
                # Извлекаем заголовок (первую строку с ##)
                header = None
                for line in memory_content_raw.split('\n'):
                    if line.strip().startswith('## '):
                        header = line.strip()[3:].strip()  # убираем ## и пробелы
                        break
                
                # Удаляем строки, начинающиеся с ## (как в обработке персонажа)
                clean_lines = [line for line in memory_content_raw.split('\n') 
                              if not line.strip().startswith('##')]
                memory_content = '\n'.join(clean_lines).strip()
                
                if memory_content:
                    # ЛОГИРУЕМ ПРОМПТ ПАМЯТИ С ЗАГОЛОВКОМ
                    log_system("debug", f"Системное сообщение [{system_count + 1}] '{header or 'Промпт памяти'}': {memory_content.replace('\n', ' ')}")
                    
                    messages.append({"role": "system", "content": memory_content})
                    system_count += 1
        else:
            log_system("error", f"Файл промпта алгоритма работы с памятью не найден или не указан: {memory_prompt_file}")
    except Exception as e:
        log_system("error", f"Ошибка загрузки промпта алгоритма работы с памятью: {e}")

    # 2. История диалога из БД (если нужно)
    if include_history:
        history_limit = config_get('ai.context_messages_limit', 10)
        history_messages = db_get_recent_messages(limit=max(1, history_limit))
        history_count = len(history_messages)
        
        # Форматируем историю
        for msg in reversed(history_messages):
            author = msg['author']
            role = "assistant" if author == "kira" else "user"
            msg_content = msg['message']
            # tag_topics = msg.get('tag_topics', [])  # можно оставить на будущее, но не используем
    
            # Пропускаем, если это сообщение от пользователя и совпадает с текущим user_message
            if role == "user" and msg_content == user_message:
                history_count -= 1
                continue
    
            messages.append({"role": role, "content": msg_content})
    
    # 2.1. Дополнительный контекст (например, результаты поиска)
    if additional_context:
        for ctx in additional_context:
            messages.append(ctx)  # предполагается, что ctx уже в формате {"role": "...", "content": "..."}
        additional_count = len(additional_context)
    
    # 3. Текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})
    
    # Финальное логирование структуры
    log_system("info", f"Сформирован промпт из {len(messages)} сообщений. Системных: {system_count}, история: {history_count}, доп. контекст: {additional_count}, текущее: 1)")
    
    # Дополнительно: логируем всю структуру на DEBUG уровне
    log_system("debug", "=== ПОЛНАЯ СТРУКТУРА ПРОМПТА ===")
    for i, msg in enumerate(messages):
        role = msg["role"]
        content_preview = msg["content"][:150].replace("\n", " ") + ("..." if len(msg["content"]) > 150 else "")
        log_system("debug", f"Сообщение {i+1}: [{role}] {content_preview}")
    
    return messages


# ============ ПРОВАЙДЕРЫ API ============

def ai_deepseek_request(messages: List[Dict], model: str = None) -> str:
    """Запрос к DeepSeek API (синхронный)"""
    api_key = os.getenv('API_KEY_DEEPSEEK')
    if not api_key:
        raise ValueError("API_KEY_DEEPSEEK не задан в .env")
    
    if model is None:
        model = config_get('ai.deepseek.model', 'deepseek-chat')
    
    client = OpenAI(
        api_key=api_key,
        base_url=config_get('ai.deepseek.base_url', 'https://api.deepseek.com')
    )
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=config_get('ai.deepseek.temperature', 0.99),
            max_tokens=config_get('ai.deepseek.max_tokens', 1024)
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log_system("error", f"Ошибка DeepSeek: {e}")
        raise

def ai_openai_request(messages: List[Dict], model: str = None) -> str:
    """Запрос к OpenAI API (синхронный)"""
    api_key = os.getenv('API_KEY_OPENAI')
    if not api_key:
        raise ValueError("API_KEY_OPENAI не задан в .env")
    
    if model is None:
        model = config_get('ai.openai.model', 'gpt-4o-mini')
    
    client = OpenAI(api_key=api_key)
    
    try:
        # Проверяем, поддерживает ли модель старый chat.completions API
        if model.startswith('gpt-4') or model.startswith('gpt-3'):
            # Старый API
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config_get('ai.openai.temperature', 0.99),
                max_tokens=config_get('ai.openai.max_tokens', 1024)
            )
            return response.choices[0].message.content.strip()
        else:
            # Новый /responses API для GPT-5+
            response = client.responses.create(
                model=model,
                input=messages,
                max_output_tokens=config_get('ai.openai.max_tokens', 1024)
            )
            return response.output_text.strip()
    except Exception as e:
        log_system("error", f"Ошибка OpenAI (модель {model}): {e}")
        if hasattr(e, 'response') and e.response:
           log_system("error", f"Тело ответа ошибки OpenAI: {e.response.text}")
        raise

# ============ ОСНОВНОЙ ИНТЕРФЕЙС ============

def ai_get_response(
    user_message: str, 
    provider_name: str = None,
    persona: str = None,
    additional_context: list = None  # <--- НОВЫЙ ПАРАМЕТР
) -> tuple[str, str]:
    """
    Основная функция для получения ответа от AI (синхронная).
    additional_context: список дополнительных сообщений в формате {"role": "...", "content": "..."}
    """
    # Определяем провайдера
    if provider_name is None:
        provider_name = config_get('ai.default_provider', 'deepseek')
    
    # Определяем персону
    if persona is None:
        persona = config_get('ai.persona', 'default')
    
    # Формируем сообщения
    messages = ai_build_messages(user_message, persona, 
                                 include_history=True, 
                                 additional_context=additional_context)

    # Логируем промпт
    if messages and messages[0]['role'] == 'system':
        log_system("info", f"Отправлено сообщение AI-моделе {provider_name}.")
    
    # Вызываем провайдера
    try:
        if provider_name == "deepseek":
            response_text = ai_deepseek_request(messages)
        elif provider_name == "openai":
            response_text = ai_openai_request(messages)
        else:
            raise ValueError(f"Неизвестный провайдер: {provider_name}")
        
        log_system("info", f"Получен ответ от AI-модели {provider_name} длиной {len(response_text)} символа")
        return response_text, provider_name
        
    except Exception as e:
        log_system("error", f"Ошибка AI провайдера {provider_name}: {e}")
        raise