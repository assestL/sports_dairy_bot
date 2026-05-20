"""
Модуль CRUD операций для работы с базой данных.
Содержит функции для создания, чтения, обновления и удаления записей.
Использует синхронные вызовы SQLAlchemy, завернутые в безопасные функции.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from database.connection import get_session_sync
from database.models import User, WorkoutSession, WorkoutDetail, AIRecommendation
from services.gemini_service import WorkoutParseResult


def get_or_create_user(telegram_id: int, username: Optional[str] = None) -> User:
    """
    Проверяет наличие пользователя в базе данных по telegram_id.
    Если пользователь не найден — создает нового.
    
    Args:
        telegram_id: Telegram ID пользователя
        username: Имя пользователя в Telegram (может быть None)
        
    Returns:
        Объект пользователя (существующий или newly created)
    """
    db = get_session_sync()
    try:
        # Пытаемся найти существующего пользователя
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        
        if user is None:
            # Создаем нового пользователя
            user = User(
                telegram_id=telegram_id,
                username=username,
                created_at=datetime.utcnow()
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        return user
    finally:
        db.close()


def save_workout(telegram_id: int, parsed_data: WorkoutParseResult) -> WorkoutSession:
    """
    Сохраняет тренировку в базу данных в рамках одной транзакции.
    Создает сессию тренировки, все упражнения и AI-рекомендацию.
    
    Args:
        telegram_id: Telegram ID пользователя
        parsed_data: Распарсенные данные тренировки из Gemini API
        
    Returns:
        Объект сохраненной сессии тренировки
    """
    db = get_session_sync()
    try:
        # Преобразуем дату тренировки в формат date, если она строка
        workout_date = parsed_data.workout_date
        if isinstance(workout_date, str):
            from datetime import date
            workout_date = date.fromisoformat(workout_date)
        
        # Создаем сессию тренировки
        session = WorkoutSession(
            telegram_id=telegram_id,
            session_date=workout_date,
            user_notes=parsed_data.wellness_notes,
            created_at=datetime.utcnow()
        )
        db.add(session)
        db.flush()  # Получаем session_id перед добавлением деталей
        
        # Добавляем детали упражнений
        for exercise in parsed_data.exercises:
            detail = WorkoutDetail(
                session_id=session.session_id,
                exercise_name=exercise.name,
                weight=exercise.weight,
                sets_count=exercise.sets,
                reps_count=exercise.reps
            )
            db.add(detail)
        
        # Добавляем AI-рекомендацию
        recommendation = AIRecommendation(
            session_id=session.session_id,
            advice_text=parsed_data.recommendation,
            is_read=False
        )
        db.add(recommendation)
        
        # Фиксируем все изменения в одной транзакции
        db.commit()
        db.refresh(session)
        
        return session
    except Exception as e:
        db.rollback()  # Откатываем транзакцию при ошибке
        raise e
    finally:
        db.close()
