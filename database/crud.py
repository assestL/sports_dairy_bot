"""
CRUD операции.
Полностью совместимы с вашей PostgreSQL БД.
"""

import logging
from datetime import datetime
from typing import Optional

from database.connection import get_session_sync
from database.models import (
    User,
    WorkoutSession,
    WorkoutDetail,
    AIRecommendation,
)

from services.gemini_service import WorkoutParseResult

logger = logging.getLogger(__name__)


def get_or_create_user(
    telegram_id: int,
    username: Optional[str] = None
) -> User:

    logger.info(f"[DB] Вызов get_or_create_user: telegram_id={telegram_id}, username={username}")
    
    db = get_session_sync()
    logger.info(f"[DB] Сессия успешно создана")

    try:
        logger.info(f"[DB] Поиск пользователя с telegram_id={telegram_id}")
        
        user = (
            db.query(User)
            .filter(User.telegram_id == telegram_id)
            .first()
        )

        if user is None:
            logger.info(f"[DB] Пользователь не найден, создаём нового")
            
            user = User(
                telegram_id=int(telegram_id),
                username=username,
                created_at=datetime.utcnow()
            )
            
            logger.info(f"[DB] Объект User создан: {user}")

            db.add(user)
            logger.info(f"[DB] Объект User добавлен в сессию")

            db.commit()
            logger.info(f"[DB] Транзакция закоммичена")

            db.refresh(user)
            logger.info(f"[DB] Объект User обновлён после коммита")

            print(
                f"[DB] CREATED USER {telegram_id}"
            )
            logger.info(f"[DB] Пользователь успешно создан: telegram_id={telegram_id}")

        else:
            logger.info(f"[DB] Пользователь уже существует: {user}")

        return user

    except Exception as e:
        logger.error(f"[DB ERROR] Ошибка при работе с пользователем: {e}", exc_info=True)
        
        db.rollback()
        logger.info(f"[DB] Выполнен rollback транзакции")

        print(
            f"[DB ERROR] {str(e)}"
        )

        raise e

    finally:
        db.close()
        logger.info(f"[DB] Сессия закрыта")


def save_workout(
    telegram_id: int,
    parsed_data: WorkoutParseResult
) -> WorkoutSession:

    db = get_session_sync()

    try:

        # ГАРАНТИЯ существования пользователя
        user = (
            db.query(User)
            .filter(User.telegram_id == telegram_id)
            .first()
        )

        if user is None:

            user = User(
                telegram_id=telegram_id,
                username=None,
                created_at=datetime.utcnow()
            )

            db.add(user)
            db.commit()
            db.refresh(user)

        last_session = None

        for session_data in parsed_data.sessions:

            workout_date = session_data.date

            if isinstance(workout_date, str):

                from datetime import date

                workout_date = date.fromisoformat(
                    workout_date
                )

            workout_session = WorkoutSession(
                telegram_id=telegram_id,
                session_date=workout_date,
                user_notes=session_data.wellness_notes,
                created_at=datetime.utcnow()
            )

            db.add(workout_session)

            db.flush()

            # СОХРАНЯЕМ ИМЕННО В ВАШУ СХЕМУ БД
            for exercise in session_data.exercises:

                sets_count = len(exercise.reps)

                # если reps = [10,10,10]
                # сохраняем:
                # sets_count = 3
                # reps_count = 10

                reps_count = max(exercise.reps)

                detail = WorkoutDetail(
                    session_id=workout_session.session_id,

                    exercise_name=(
                        exercise.name
                        .lower()
                        .strip()
                        .replace("ё", "е")
                    ),

                    weight=exercise.weight,

                    sets_count=sets_count,

                    reps_count=reps_count
                )

                db.add(detail)

            if session_data.recommendation:

                recommendation = AIRecommendation(
                    session_id=workout_session.session_id,
                    advice_text=session_data.recommendation,
                    is_read=False
                )

                db.add(recommendation)

            last_session = workout_session

        db.commit()

        if last_session:
            db.refresh(last_session)

        return last_session

    except Exception as e:

        db.rollback()
        raise e

    finally:
        db.close()


async def get_user_workout_sessions(telegram_id: int):
    """
    Получает все тренировки пользователя, отсортированные от новых к старым.
    """
    from sqlalchemy import select
    from database.connection import get_session_sync
    from database.models import WorkoutSession
    
    db = get_session_sync()
    try:
        query = (
            select(WorkoutSession)
            .where(WorkoutSession.telegram_id == telegram_id)
            .order_by(WorkoutSession.session_date.desc())
        )
        sessions = db.execute(query).scalars().all()
        return list(sessions)
    finally:
        db.close()


async def delete_workout_session(session_id: int):
    """
    Удаляет тренировку и все связанные детали.
    """
    from sqlalchemy import delete
    from database.connection import get_session_sync
    from database.models import WorkoutDetail, WorkoutSession, AIRecommendation
    
    db = get_session_sync()
    try:
        # Сначала удаляем детали тренировки
        db.execute(delete(WorkoutDetail).where(WorkoutDetail.session_id == session_id))
        # Удаляем рекомендации
        db.execute(delete(AIRecommendation).where(AIRecommendation.session_id == session_id))
        # Удаляем саму сессию
        db.execute(delete(WorkoutSession).where(WorkoutSession.session_id == session_id))
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


async def update_workout_session(session_id: int, exercises: list, notes: str = None):
    """
    Обновляет тренировку: удаляет старые детали и добавляет новые.
    """
    from sqlalchemy import delete
    from database.connection import get_session_sync
    from database.models import WorkoutDetail, WorkoutSession
    
    db = get_session_sync()
    try:
        # Обновляем заметки сессии
        if notes is not None:
            session_obj = db.query(WorkoutSession).filter(WorkoutSession.session_id == session_id).first()
            if session_obj:
                session_obj.user_notes = notes
        
        # Удаляем старые детали тренировки
        db.execute(delete(WorkoutDetail).where(WorkoutDetail.session_id == session_id))
        
        # Добавляем новые детали
        for exercise in exercises:
            sets_count = len(exercise.reps)
            reps_count = max(exercise.reps) if exercise.reps else 0
            
            detail = WorkoutDetail(
                session_id=session_id,
                exercise_name=exercise.name.lower().strip().replace("ё", "е"),
                weight=exercise.weight,
                sets_count=sets_count,
                reps_count=reps_count
            )
            db.add(detail)
        
        db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()