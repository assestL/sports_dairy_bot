"""
CRUD операции.
Полностью совместимы с вашей PostgreSQL БД.
"""

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


def get_or_create_user(
    telegram_id: int,
    username: Optional[str] = None
) -> User:

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

            print(
                f"[DB] CREATED USER {telegram_id}"
            )

        return user

    except Exception as e:

        db.rollback()

        print(
            f"[DB ERROR] {str(e)}"
        )

        raise e

    finally:

        db.close()


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