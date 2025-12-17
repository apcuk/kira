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

def ai_build_messages(user_message: str, persona: str = None, include_history: bool = True) -> List[Dict]:
    """
    Формирует список сообщений для OpenAI API.
    Включает историю диалога из БД если include_history=True.
    """
    messages = []
    system_count = 0
    history_count = 0
    
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
            for block in blocks:
                # Убираем все строки, начинающиеся с ##
                clean_lines = [line for line in block.split('\n') 
                              if not line.strip().startswith('##')]
                clean_content = '\n'.join(clean_lines).strip()
                
                if clean_content:
                    messages.append({"role": "system", "content": clean_content})
                    system_count += 1
                
        else:
            messages.append({"role": "system", "content": f"Ты — {persona}. Отвечай как друг."})
            system_count += 1
    else:
        messages.append({"role": "system", "content": "Ты — полезный ассистент."})
        system_count += 1
    
    # 2. История диалога из БД (если нужно)
    if include_history:
        history_limit = config_get('ai.context_messages_limit', 10)
        history_messages = db_get_recent_messages(limit=max(1, history_limit - 1))
        history_count = len(history_messages)
        
        # Форматируем историю
        for msg in reversed(history_messages):
            author = msg['author']
            role = "assistant" if author == "kira" else "user"
            messages.append({"role": role, "content": msg['message']})
    
    # 3. Текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})
    
    log_system("info", f"Сформирован промпт из {len(messages)} сообщений. Системных: {system_count}, история: {history_count}, текущее: 1)")
    return messages

# ============ ПРОВАЙДЕРЫ API ============

def ai_deepseek_request(messages: List[Dict]) -> str:
    """Запрос к DeepSeek API (синхронный)"""
    api_key = os.getenv('API_KEY_DEEPSEEK')
    if not api_key:
        raise ValueError("API_KEY_DEEPSEEK не задан в .env")
    
    client = OpenAI(
        api_key=api_key,
        base_url=config_get('ai.deepseek.base_url', 'https://api.deepseek.com')
    )
    
    try:
        response = client.chat.completions.create(
            model=config_get('ai.deepseek.model', 'deepseek-chat'),
            messages=messages,
            temperature=config_get('ai.deepseek.temperature', 0.99),
            max_tokens=config_get('ai.deepseek.max_tokens', 1024)
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log_system("error", f"Ошибка DeepSeek: {e}")
        raise

def ai_openai_request(messages: List[Dict]) -> str:
    """Запрос к OpenAI API (синхронный)"""
    api_key = os.getenv('API_KEY_OPENAI')
    if not api_key:
        raise ValueError("API_KEY_OPENAI не задан в .env")
    
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
        log_system("error", f"Ошибка OpenAI: {e}")
        raise

# ============ ОСНОВНОЙ ИНТЕРФЕЙС ============

def ai_get_response(
    user_message: str, 
    provider_name: str = None,
    persona: str = None
) -> tuple[str, str]:
    """
    Основная функция для получения ответа от AI (синхронная).
    """
    # Определяем провайдера
    if provider_name is None:
        provider_name = config_get('ai.default_provider', 'deepseek')
    
    # Определяем персону
    if persona is None:
        persona = config_get('ai.persona', 'default')
    
    # Формируем сообщения
    messages = ai_build_messages(user_message, persona)

    # Логируем промпт
    if messages and messages[0]['role'] == 'system':
        log_system("debug", f"Отправлено сообщение AI-моделе {provider_name}: {messages[0]['content'][:50]} ... ... ...")
    
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