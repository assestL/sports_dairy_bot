"""
Модуль для подключения к базе данных и создания сессий SQLAlchemy.
Использует переменные окружения для конфигурации.
Поддерживает как синхронные (psycopg2), так и асинхронные (asyncpg) драйверы.
Для синхронного режима убедитесь, что DATABASE_URL использует postgresql:// или postgresql+psycopg2://
"""

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from database.models import Base


def get_database_url() -> str:
    """Получает URL базы данных из переменной окружения."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "Переменная окружения DATABASE_URL не установлена. "
            "Проверьте файл .env или настройки окружения."
        )
    return database_url


def get_sync_database_url() -> str:
    """
    Преобразует URL базы данных в синхронный формат.
    Если используется asyncpg, заменяет на psycopg2.
    """
    url = get_database_url()
    # Заменяем асинхронный драйвер на синхронный, если он указан
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif url.startswith("asyncpg://"):
        url = url.replace("asyncpg://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://"):
        # Явно указываем psycopg2 для ясности
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


# Создание синхронного движка SQLAlchemy
# Используем psycopg2 для синхронной работы
engine = create_engine(
    get_sync_database_url(),
    echo=False,  # Установите True для отладки SQL-запросов
    pool_pre_ping=True,  # Проверка соединения перед использованием
)


# Фабрика сессий
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """
    Инициализирует базу данных: создаёт все таблицы согласно моделям.
    Вызывается один раз при старте приложения.
    """
    Base.metadata.create_all(bind=engine)


def get_session() -> Generator[Session, None, None]:
    """
    Генератор сессий базы данных.
    Используется для зависимости в зависимостях (dependency injection).
    Гарантирует закрытие сессии после использования.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_session_sync() -> Session:
    """
    Возвращает новую сессию базы данных.
    Используйте в синхронном коде, где нельзя использовать генераторы.
    Не забудьте закрыть сессию после использования!
    """
    return SessionLocal()