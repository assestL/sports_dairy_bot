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
    try:
        user = (
            db.query(User)
            .filter(User.telegram_id == telegram_id)
            .first()
        )
        if user is None:
            user = User(
                telegram_id=int(telegram_id),
                username=username,
                created_at=datetime.utcnow()
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"[DB] Пользователь успешно создан: telegram_id={telegram_id}")
        else:
            logger.info(f"[DB] Пользователь уже существует: {user}")
        return user
    except Exception as e:
        logger.error(f"[DB ERROR] Ошибка при работе с пользователем: {e}", exc_info=True)
        db.rollback()
        raise e
    finally:
        db.close()


def save_workout(
    telegram_id: int,
    parsed_data: WorkoutParseResult
) -> WorkoutSession:
    db = get_session_sync()
    try:
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
                workout_date = date.fromisoformat(workout_date)

            workout_session = WorkoutSession(
                telegram_id=telegram_id,
                session_date=workout_date,
                user_notes=session_data.wellness_notes,
                created_at=datetime.utcnow()
            )
            db.add(workout_session)
            db.flush()

            for exercise in session_data.exercises:
                sets_count = len(exercise.reps)
                reps_count = max(exercise.reps) if exercise.reps else 0
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
    from sqlalchemy import select
    from database.models import WorkoutSession

    db = get_session_sync()
    try:
        query = (
            select(WorkoutSession)
            .where(WorkoutSession.telegram_id == telegram_id)
            .order_by(WorkoutSession.session_date.desc(), WorkoutSession.session_id.desc())
        )
        sessions = db.execute(query).scalars().all()
        return list(sessions)
    finally:
        db.close()


async def delete_workout_session(session_id: int):
    db = get_session_sync()
    try:
        session_obj = db.query(WorkoutSession).filter(WorkoutSession.session_id == session_id).first()
        if session_obj:
            db.delete(session_obj)
            db.commit()
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


async def update_workout_session(session_id: int, exercises: list, notes: str = None):
    db = get_session_sync()
    try:
        session_obj = db.query(WorkoutSession).filter(WorkoutSession.session_id == session_id).first()
        if not session_obj:
            raise ValueError("Сессия не найдена")

        session_obj.user_notes = notes

        db.query(WorkoutDetail).filter(WorkoutDetail.session_id == session_id).delete()
        db.query(AIRecommendation).filter(AIRecommendation.session_id == session_id).delete()

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


async def save_ai_recommendation(
    telegram_id: int,
    advice_text: str,
    context_info: str = None,
    session_id: int = None
) -> AIRecommendation:
    """Сохраняет рекомендацию в БД и возвращает объект с ID."""
    db = get_session_sync()
    try:
        rec = AIRecommendation(
            session_id=session_id,
            advice_text=advice_text,
            is_read=False,
            context_info=context_info
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec
    finally:
        db.close()


async def update_recommendation_status(recommendation_id: int, is_accepted: bool):
    """Обновляет статус рекомендации (Принято/Отказано)."""
    db = get_session_sync()
    try:
        rec = db.query(AIRecommendation).filter(AIRecommendation.recommendation_id == recommendation_id).first()
        if rec:
            rec.is_read = is_accepted
            db.commit()
    finally:
        db.close()