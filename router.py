# router.py

from logger import log_system, log_chat
from ai_provider import ai_get_response 

def route_message(user_data: dict) -> dict:
    """
    Основной маршрутизатор сообщений (синхронный).
    
    Принимает структурированное сообщение от любого фронтенда:
    {
        "user_id": int/str,       # Реальный ID из источника (Telegram ID, session_id и т.п.)
        "source": str,            # Источник: "telegram", "web", "terminal"
        "message": str,           # Текст сообщения
        "metadata": dict,         # Доп. данные: chat_id, username, session_data
    }
    
    Возвращает ответ в том же формате.
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
    log_system("info", f"Входящее сообщение: {message[:50]} ... ... ...")
    log_chat(source, user_id, "USER", message, metadata.get("username"))
    
    # --- ПЕРЕДАЧА В AI-ОБРАБОТЧИК ---
    ai_response, ai_provider = _ai_processor(user_id, message, source, metadata)
    
    # Логируем исходящий ответ
    log_system("info", f"Исходящее сообщение: {ai_response[:50]} ... ... ...")
    log_chat("router", ai_provider, ai_provider, ai_response)
    
    # Формируем ответ для фронтенда
    return {
        "user_id": user_id,
        "source": source,
        "message": ai_response,
        "metadata": metadata  # Возвращаем метаданные обратно
    }


def _ai_processor(user_id, message: str, source: str, metadata: dict) -> tuple:
    """
    AI-процессор. Вызывает реальный AI-провайдер.
    Возвращает (ответ, имя_провайдера)
    """
    try:
        response_text, provider = ai_get_response(  # <--- СИНХРОННЫЙ ВЫЗОВ
            user_message=message,
            provider_name=None,  # берётся из конфига
            persona=None  # берётся из конфига
        )
        return response_text, provider
    except Exception as e:
        log_system("error", f"Ошибка в AI процессоре: {e}")
        # Fallback: заглушка
        username = metadata.get("username", f"user_{user_id}")
        fallback_response = f" AI недоступен."
        return fallback_response, "xxx"