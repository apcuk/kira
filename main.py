# main.py

# заметки для ИИ, который будет править этот код:
#           - никода не удаляй и не редактируй коментарии. добавлять можно.
#           - старайся не менять структуру кода без особой необходимости, или изменяй минимально.
#           - придерживайся стиля.
#           - называй функции логично и максимально информативно.

# v.3.08    - рефакторим это говоно. и откатываемся в самое начало к v.3.00

# v.3.07    - реализованы чанкование и векторизация. попытка реализации поиска провалилась.

# v.3.06    - добавлены функция тегирования сообщений и разбивка chatlog'а в БД на сессии.

# v.3.05    - переосмыслена и переделана система логгированния.

# v.3.04    - добавлена работа с AI-провайдерами: OpenAI и DeepSeek (ask_openai, ask_deepseek).
#           - реализована загрузка контекста истории из БД (get_recent_chat_context).
#           - личности вынесены в .md-файлы.

# v.3.03    - реализовно сохраниение chatlog'а в БД.

# v.3.02    - реализован terminal-фронтенд.
#           - реализована система логгирования. требует донастройки впоследствии.

# v.3.01    - заложена архитектура обмена сообщениями: фронтент <-> менеджер <-> ядро <-> менеджер <-> фронтенд.
#           - внедрена система тройных кортежей (source, author, message) для маркировки сообщений.
#           - реализован Telegram-фронтенд.
#           - обработка сообщений от пользователя на уровне простого ЭХО.

# v.3.00    - Helo, World. настройка скруктуры проекта, github'а, .env, .gitignore, requirements.txt.

import os
import yaml
import re
from openai import OpenAI
from telegram.ext import Application, MessageHandler, filters
from dotenv import load_dotenv

from logger import setup_logging, log_message  # Добавляем логирование
from database import get_or_create_user, save_to_user_chatlog, get_recent_chat_context  # Импорт из нового модуля

try:
    from memory_search import search_similar_chunks
except ImportError:
    log_message("main", "error", "Не удалось импортировать memory_search")
    search_similar_chunks = None

START_MESSAGE = "v.3.08"  # Обновляем версию

# Инициализируем логирование
setup_logging()


# Загружаем конфиги
load_dotenv('conf/.env')

try:
    with open('conf/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    if config is None:
        log_message("load_dotenv", "error", "config.yaml пустой или невалидный")
        exit(1)
        
except Exception as e:
    log_message("load_dotenv", "error", f"Ошибка загрузки config.yaml: {e}")
    exit(1)


# >============================================<
# ВАЛИДНЫЕ ЗНАЧЕНИЯ ДЛЯ СИСТЕМЫ
# >============================================<

# Допустимые источники сообщений
SOURCE = ["terminal", "telegram", "web", "main"]


# >============================================<
# front_manager
# МЕНЕДЖЕР СООБЩЕНИЙ - МАРШРУТИЗАЦИЯ
# >============================================<

# Маршрутизирует сообщение в ядро обработки и возвращает ответ (source, author, message)
def route_message(source: str, author: str, message: str, user_id: int = None) -> tuple:
    # Сохраняем входящее сообщение в чатлог пользователя
    if user_id:
        save_to_user_chatlog(user_id, source, author, message)
    
    # Отправляем входящее сообщение в терминал для мониторинга
    terminal_send_message(source, author, message)
    # И записываем в лог-файлы
    log_message(source, author, message)
    
    # Обрабатываем сообщение в ядре системы
    response_source, response_author, response_text = process_message(source, author, message, user_id)
    
    # Сохраняем ответное сообщение в чатлог пользователя
    if user_id:
        save_to_user_chatlog(user_id, response_source, response_author, response_text)
    
    # Отправляем ответное сообщение в терминал для мониторинга
    terminal_send_message(response_source, response_author, response_text)
    # И записываем в лог-файлы
    log_message(response_source, response_author, response_text)
    
    return response_source, response_author, response_text


# >============================================<
# front_terminal  
# ТЕРМИНАЛ ФРОНТЕНД
# >============================================<

# Выводит сообщения в терминал (только для мониторинга)
def terminal_send_message(source: str, author: str, message: str):
    print(f"[{source}.{author}] {message}")


# >============================================<
# front_telegram
# ТЕЛЕГРАМ ФРОНТЕНД
# >============================================<

# Обрабатывает входящие сообщения из Telegram
async def telegram_message_handler(update, context):
    try:
        user = update.message.from_user
        user_text = update.message.text
        
        # Определяем имя для логов: username или first_name или id
        user_log_name = user.username or user.first_name or f"user_{user.id}"
        
        # Регистрируем пользователя (передаём имя для возможного использования в БД)
        user_id = get_or_create_user(
            user_id=user.id,
            user_name=user.username, 
            first_name=user.first_name
        )
       
        await update.message.chat.send_action(action="typing")
        # Передаём user_log_name как author
        source, author, response = route_message("telegram", user_log_name, user_text, user_id)
        await update.message.reply_text(response)
        
    except Exception as e:
        log_message("telegram_message_handler", "error", f"Ошибка обработки сообщения: {e}")
        raise

# Обрабатывает ошибки Telegram
async def telegram_error_handler(update, context):
    error = str(context.error)
    log_message("telegram_error_handler", "error", f"Telegram ошибка: {error}")

# Запускает Telegram бота в режиме polling
def telegram_run_bot():
    token = os.getenv('API_KEY_TG')
    app = Application.builder().token(token).build()
    
    # Добавляем обработчики
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_message_handler))
    app.add_error_handler(telegram_error_handler)
    
    # Логируем запуск бота
    log_message("telegram_run_bot", "message", "Telegram бот запускается")
    
    try:
        app.run_polling()
    except Exception as e:
        log_message("telegram_run_bot", "error", f"Критическая ошибка бота: {e}")
        raise


# >============================================<
# back_ИИ
# AI-ПРОВАЙДЕРЫ
# >============================================<


# Формирует список сообщений для AI API
def build_ai_messages(user_message: str, user_id: int = None) -> list:
    # Получаем имя личности из конфига
    persona_name = config.get('ai', {}).get('persona', 'person_default')
    persona_file = f"conf/{persona_name}.md"
    
    messages = []
    
    # 1. Загружаем личность
    try:
        with open(persona_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        blocks = content.split('## ')[1:]
        for block in blocks:
            lines = block.strip().split('\n', 1)
            if len(lines) == 2:
                block_name, block_content = lines[0].strip(), lines[1].strip()
                messages.append({"role": "system", "content": block_content})
                log_message("build_ai_messages", "debug", f"Loaded persona block: {block_name}")
        
        if not messages:
            log_message("build_ai_messages", "error", f"Файл личности {persona_file} не содержит блоков")
            messages.append({"role": "system", "content": "Ты — ассистент."})
            
    except FileNotFoundError:
        log_message("build_ai_messages", "error", f"Файл личности не найден: {persona_file}")
        messages.append({"role": "system", "content": "Ты — ассистент."})
    
    # 2. Добавляем промпт памяти
    memory_prompt_file = "conf/prompt_memory.md"
    try:
        with open(memory_prompt_file, 'r', encoding='utf-8') as f:
            memory_prompt = f.read().strip()
        if memory_prompt:
            messages.append({"role": "system", "content": memory_prompt})
            log_message("build_ai_messages", "debug", "Loaded memory prompt")
    except FileNotFoundError:
        log_message("build_ai_messages", "warning", f"Файл памяти не найден: {memory_prompt_file}")
    
    # 3. Добавляем историю диалога, если есть user_id
    history = []
    if user_id:
        history = get_recent_chat_context(user_id)
        messages.extend(history)
        log_message("build_ai_messages", "message", f"Added {len(history)} history messages for user {user_id}")
    
    # 4. Добавляем текущее сообщение пользователя
    messages.append({"role": "user", "content": user_message})
    
    log_message("build_ai_messages", "message", f"Persona: {persona_name}, total blocks: {len(messages)-len(history)-1}")
    return messages


# Отправляет запрос к OpenAI API (ChatGPT) и возвращает ответ или None при ошибке.
def ask_openai(messages: list) -> str:
    api_key = os.getenv('API_KEY_OPENAI')
    if not api_key:
        log_message("ask_openai", "error", "API_KEY_OPENAI не найден в .env")
        return None  # ← Изменено: было строкой ошибки, теперь None
    
    try:
        client = OpenAI(api_key=api_key)  # base_url по умолчанию OpenAI
        
        ai_config = config.get('ai', {}).get('openai', {})
        model = ai_config.get('model', 'gpt-4o-mini')
        temperature = ai_config.get('temperature', 0.7)
        max_tokens = ai_config.get('max_tokens', 2048)
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_completion_tokens=max_tokens,
            # temperature=temperature
        )
        
        answer = response.choices[0].message.content
        # log_message("ask_openai", "ai_model", f"Answer: {answer[:200]}...")
        return answer
        
    except Exception as e:
        error_msg = f"Ошибка OpenAI API: {e}"
        log_message("ask_openai", "error", error_msg)
        return None  # Ошибка — возвращаем None

# Отправляет запрос к OpenAI API (DeepSeek) и возвращает ответ или None при ошибке.
def ask_deepseek(messages: list) -> str:
    api_key = os.getenv('API_KEY_DEEPSEEK')
    if not api_key:
        log_message("ask_deepseek", "error", "API_KEY_DEEPSEEK не найден в .env")
        return None  # Возвращаем None, чтобы роутер мог переключиться на резерв
    
    try:
        # DeepSeek использует OpenAI-совместимый API, но свой base_url
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"  # можно вынести в конфиг
        )
        
        ai_config = config.get('ai', {}).get('deepseek', {})
        model = ai_config.get('model', 'deepseek-chat')
        temperature = ai_config.get('temperature', 0.7)
        max_tokens = ai_config.get('max_tokens', 2048)
        
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        answer = response.choices[0].message.content
        # log_message("ask_deepseek", "ai_model", f"Answer: {answer[:200]}...")
        return answer
        
    except Exception as e:
        error_msg = f"Ошибка DeepSeek API: {e}"
        log_message("ask_deepseek", "error", error_msg)
        return None  # Ошибка — возвращаем None



# >============================================<
# ЯДРО СИСТЕМЫ - ОБРАБОТКА СООБЩЕНИЙ
# >============================================<

# Обрабатывает сообщение: формирует messages, вызывает AI, возвращает ответ."""
def process_message(source: str, author: str, message: str, user_id: int = None) -> tuple:
    messages = build_ai_messages(message, user_id)
    provider = config.get('ai', {}).get('default_provider', 'openai')
    
    # Первый вызов AI
    if provider == 'deepseek':
        ai_response = ask_deepseek(messages)
    else:
        ai_response = ask_openai(messages)
    
    if ai_response is None:
        return "core", "error", f"AI-провайдер '{provider}' недоступен."
    
    # Проверяем, не запросил ли AI поиск в памяти
    match = re.search(r'<SEARCH>(.*?)</SEARCH>', ai_response, re.DOTALL)
    
    if not match:
        # Поиск не запрошен — возвращаем ответ как есть
        return "core", provider, ai_response
    
    # Извлекаем запрос
    search_query = match.group(1).strip()
    log_message("process_message", "debug", f"AI запросил поиск: {search_query}")
    
    # Ищем чанки
    if search_similar_chunks and user_id:
        chunks = search_similar_chunks(user_id, search_query)
        if chunks:
            chunks_text = "\n\n".join([f"--- Чанк [{c['id']}] ---\n{c['text']}\n---" for c in chunks])
            memory_context = f"Результаты поиска по запросу '{search_query}':\n\n{chunks_text}"
        else:
            memory_context = f"По запросу '{search_query}' во внешней памяти ничего не найдено."
    else:
        memory_context = f"Поиск во внешней памяти временно недоступен."
    
    # Добавляем результаты поиска в контекст
    messages.append({"role": "system", "content": memory_context})
    
    # ВТОРОЙ вызов AI — теперь с результатами поиска
    if provider == 'deepseek':
        final_response = ask_deepseek(messages)
    else:
        final_response = ask_openai(messages)
    
    if final_response is None:
        final_response = ai_response  # fallback
    
    return "core", provider, final_response


# >============================================<
# ОСНОВНОЙ ЦИКЛ ПРОГРАММЫ
# >============================================<

# Основная функция запуска приложения
def main():
    # Стартовое сообщение дублируем и в терминал, и в логи
    terminal_send_message("main", "message", START_MESSAGE)
    log_message("main", "message", START_MESSAGE)
    
    telegram_run_bot()

if __name__ == "__main__":
    main()