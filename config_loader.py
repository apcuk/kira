# config_loader.py
import yaml
import os
from logger import log_system

_CONFIG = None

def config_load():
    """Загружает конфиг один раз и кэширует"""
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    
    try:
        with open('conf/config.yaml', 'r', encoding='utf-8') as f:
            _CONFIG = yaml.safe_load(f)
        log_system("info", "Конфигурация загружена")
        return _CONFIG
    except Exception as e:
        log_system("error", f"Ошибка загрузки конфига: {e}")
        return {}

def config_get(key=None, default=None):
    """
    Возвращает значение из конфига по ключу (например 'memory.session_timeout_hours').
    Если key=None — возвращает весь конфиг.
    Поддерживает вложенные ключи через точку.
    """
    config = config_load()
    if key is None:
        return config
    
    # Поддержка вложенных ключей через точку
    keys = key.split('.')
    value = config
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k, {})
        else:
            return default
    
    return value if value != {} else default

def config_get_aliases():
    """Возвращает алиасы пользователя и AI (обратная совместимость)"""
    aliases = config_get('aliases', {})
    return (
        aliases.get('alias_user', 'user'),
        aliases.get('alias_ai', 'kira')
    )