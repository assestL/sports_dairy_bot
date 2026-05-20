"""
Модуль конфигурации приложения.
Загружает переменные окружения из файла .env с использованием python-dotenv.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


# Определяем путь к корневой директории проекта
BASE_DIR = Path(__file__).resolve().parent.parent

# Загружаем переменные окружения из файла .env
# Ищем файл в корневой директории проекта
env_path = BASE_DIR / ".env"
load_dotenv(dotenv_path=env_path)


def get_bot_token() -> str:
    """
    Получает токен Telegram бота из переменных окружения.
    
    Returns:
        Токен бота
        
    Raises:
        ValueError: Если переменная BOT_TOKEN не установлена
    """
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError(
            "Переменная окружения BOT_TOKEN не установлена. "
            "Проверьте файл .env или настройки окружения."
        )
    return token


def get_gemini_api_key() -> str:
    """
    Получает API ключ для Google Gemini из переменных окружения.
    
    Returns:
        API ключ Gemini
        
    Raises:
        ValueError: Если переменная GEMINI_API_KEY не установлена
    """
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "Переменная окружения GEMINI_API_KEY не установлена. "
            "Проверьте файл .env или настройки окружения."
        )
    return key


def get_database_url() -> str:
    """
    Получает URL подключения к базе данных из переменных окружения.
    
    Returns:
        Database URL в формате postgresql://...
        
    Raises:
        ValueError: Если переменная DATABASE_URL не установлена
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError(
            "Переменная окружения DATABASE_URL не установлена. "
            "Проверьте файл .env или настройки окружения."
        )
    return url


# Экспортируем значения для удобного импорта в других модулях
BOT_TOKEN = get_bot_token()
GEMINI_API_KEY = get_gemini_api_key()
DATABASE_URL = get_database_url()