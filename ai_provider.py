# ai_provider.py

import os
import yaml
from typing import List, Dict, Any
from openai import OpenAI  # Синхронный клиент
from logger import log_system, log_chat

# ЗАГРУЗКА .env
from dotenv import load_dotenv
load_dotenv('conf/.env')

# ============ КОНФИГУРАЦИЯ ============

def _load_config() -> Dict[str, Any]:
    """Загружает AI-конфиг из YAML и .env"""
    try:
        # YAML
        config_path = 'conf/config.yaml'
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Файл конфигурации не найден: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        if not config or 'ai' not in config:
            raise ValueError("Файл конфигурации не содержит секции 'ai'")
        
        # API-ключи из .env
        openai_key = os.getenv('API_KEY_OPENAI', '')
        deepseek_key = os.getenv('API_KEY_DEEPSEEK', '')
        
        config['ai']['openai']['api_key'] = openai_key
        config['ai']['deepseek']['api_key'] = deepseek_key
        
        # Логируем загрузку
        log_system("info", f"Конфигурация AI-провайдера загружена. Провайдер по умолчанию: {config['ai'].get('default_provider', 'deepseek')}")
        log_system("info", f"API ключи: OpenAI={'есть' if openai_key else 'нет'}, DeepSeek={'есть' if deepseek_key else 'нет'}")
        
        return config['ai']
        
    except Exception as e:
        log_system("error", f"Ошибка загрузки конфигурации AI: {e}")
        # Возвращаем дефолтный конфиг, чтобы приложение не падало
        return {
            'default_provider': 'deepseek',
            'persona': 'default',
            'openai': {'api_key': '', 'model': 'gpt-4o-mini', 'temperature': 0.99, 'max_tokens': 1024},
            'deepseek': {'api_key': '', 'model': 'deepseek-chat', 'temperature': 0.99, 'max_tokens': 1024, 'base_url': 'https://api.deepseek.com'}
        }


AI_CONFIG = _load_config()


# ============ ФОРМИРОВАНИЕ СООБЩЕНИЙ ============

def ai_build_messages(user_message: str, persona: str = None) -> List[Dict]:
    """
    Формирует список сообщений для OpenAI API.
    Загружает промпт из файла, разбивает на блоки по ##, убирает строки с ##.
    """
    messages = []
    
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
                
        else:
            messages.append({"role": "system", "content": f"Ты — {persona}. Отвечай как друг."})
    else:
        messages.append({"role": "system", "content": "Ты — полезный ассистент."})
    
    messages.append({"role": "user", "content": user_message})
    
    log_system("info", f"Сформирован промпт из {len(messages)} сообщений")
    return messages

# ============ ПРОВАЙДЕРЫ API ============

def ai_deepseek_request(messages: List[Dict], config: Dict) -> str:
    """Запрос к DeepSeek API (синхронный)"""
    api_key = config['deepseek']['api_key']
    if not api_key:
        raise ValueError("API_KEY_DEEPSEEK не задан в .env")
    
    client = OpenAI(
        api_key=api_key,
        base_url=config['deepseek']['base_url']
    )
    
    try:
        response = client.chat.completions.create(
            model=config['deepseek']['model'],
            messages=messages,
            temperature=config['deepseek']['temperature'],
            max_tokens=config['deepseek']['max_tokens']
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log_system("error", f"Ошибка DeepSeek: {e}")
        raise

def ai_openai_request(messages: List[Dict], config: Dict) -> str:
    """Запрос к OpenAI API (синхронный)"""
    api_key = config['openai']['api_key']
    model = config['openai']['model']
    
    client = OpenAI(api_key=api_key)
    
    try:
        # Проверяем, поддерживает ли модель старый chat.completions API
        if model.startswith('gpt-4') or model.startswith('gpt-3'):
            # Старый API
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=config['openai']['temperature'],
                max_tokens=config['openai']['max_tokens']
            )
            return response.choices[0].message.content.strip()
        else:
            # Новый /responses API для GPT-5+
            response = client.responses.create(
                model=model,
                input=messages,
                max_output_tokens=config['openai']['max_tokens']
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
    
    Параметры:
        user_message: текст сообщения пользователя
        provider_name: "deepseek" или "openai" (если None — из конфига)
        persona: имя персонажа (если None — из конфига)
    
    Возвращает: (текст_ответа, имя_провайдера)
    """
    # Определяем провайдера
    if provider_name is None:
        provider_name = AI_CONFIG['default_provider']
    
    # Определяем персону
    if persona is None:
        persona = AI_CONFIG.get('persona')
    
    # Формируем сообщения
    messages = ai_build_messages(user_message, persona)

    # Логируем промпт (безопасно)
    if messages and messages[0]['role'] == 'system':
        log_system("debug", f"Отправлено сообщение AI-моделе {provider_name}: {messages[0]['content'][:50]} ... ... ...")
    
    # Вызываем провайдера
    try:
        if provider_name == "deepseek":
            response_text = ai_deepseek_request(messages, AI_CONFIG)
        elif provider_name == "openai":
            response_text = ai_openai_request(messages, AI_CONFIG)
        else:
            raise ValueError(f"Неизвестный провайдер: {provider_name}")
        
        log_system("info", f"Получен ответ от AI-модели {provider_name} длиной {len(response_text)} символа")
        return response_text, provider_name.upper()
        
    except Exception as e:
        log_system("error", f"Ошибка AI провайдера {provider_name}: {e}")
        # TODO: fallback на резервный провайдер
        raise