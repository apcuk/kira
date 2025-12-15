# security.py

import os
from typing import Set
from logger import setup_logging, log_system

def load_whitelist() -> Set[int]:
    """
    Загружает whitelist из переменной окружения WHITELIST_TG.
    Формат: "123456789" (один ID)
    """

    from dotenv import load_dotenv
    
    # ЗАГРУЗКА .env здесь
    load_dotenv('conf/.env')

    whitelist_str = os.getenv('WHITELIST_TG', '').strip()
    
    if not whitelist_str:
        log_system("error", "WHITELIST_TG не задан в .env")
        raise ValueError("WHITELIST_TG не задан в .env")
    
    whitelist = set()
    for id_str in whitelist_str.split(','):
        id_str = id_str.strip()
        if id_str.isdigit():
            whitelist.add(int(id_str))
        else:
            log_system("warning", f"Некорректный ID в whitelist: {id_str}")
    
    log_system("info", f"Загружен whitelist: {whitelist}")
    return whitelist

class Security:
    """Класс для управления доступом"""
    
    def __init__(self):
        self.whitelist = load_whitelist()
    
    def is_allowed(self, user_id: int) -> bool:
        """Проверяет, есть ли пользователь в whitelist."""
        allowed = user_id in self.whitelist
        
        if not allowed:
            log_system("warning", f"Доступ запрещён для пользователя {user_id}")
        
        return allowed
    
    def get_access_denied_message(self) -> str:
        """Возвращает сообщение об отказе в доступе"""
        return "⛔ Доступ запрещён. Этот бот приватный."

# Глобальный экземпляр
security = Security()