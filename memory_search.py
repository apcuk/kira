# memory_search.py
import os
import logging
import psycopg2
import yaml
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv('conf/.env')

try:
    with open('conf/config.yaml', 'r') as f:
        config = yaml.safe_load(f)
except Exception as e:
    logging.error("memory_search", "error", f"Ошибка загрузки config.yaml: {e}")
    config = {}

logger = logging.getLogger('system')

def get_db_connection():
    db_url = os.getenv('DB_URL')
    return psycopg2.connect(db_url)

def search_similar_chunks(user_id: int, query_text: str, limit: int = None):
    logger.info("search_similar_chunks", "info", f"Заглушка: user_id={user_id}, query='{query_text}'")
    return [
        {
            "id": -1,
            "text": "Поиск во внешней памяти временно отключён.",
            "score": 1.0
        }
    ]