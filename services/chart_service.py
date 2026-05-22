"""
Сервис графиков прогресса.
"""

import io
from datetime import datetime, timedelta
from typing import List, Tuple

import matplotlib.pyplot as plt

from aiogram.types import BufferedInputFile

from sqlalchemy import and_, func, select

from database.connection import get_session_sync
from database.models import WorkoutDetail, WorkoutSession


BODYWEIGHT_EXERCISES = {
    "отжимания",
    "подтягивания",
    "пресс",
    "брусья",
    "скручивания"
}


ALIASES = {
    "отжиманиях": "отжимания",
    "отжимание": "отжимания",
    "подтягиваниях": "подтягивания",
    "подтягивание": "подтягивания",
}


def normalize_exercise_name(name: str) -> str:

    name = (
        name
        .lower()
        .strip()
        .replace("ё", "е")
    )

    return ALIASES.get(name, name)


def get_workout_history(
    telegram_id: int,
    exercise_name: str,
    days: int,
    start_date: datetime = None,
    end_date: datetime = None
):

    session = get_session_sync()

    try:
        # Если указаны конкретные даты, используем их
        if start_date is not None and end_date is not None:
            query_start = start_date
            query_end = end_date
        else:
            # Иначе используем период дней от текущей даты
            query_end = datetime.now().date()
            query_start = query_end - timedelta(days=days)

        normalized = normalize_exercise_name(exercise_name)

        rows = session.execute(
            select(
                WorkoutSession.session_date,
                WorkoutDetail.weight,
                WorkoutDetail.sets_count,
                WorkoutDetail.reps_count
            )
            .join(
                WorkoutDetail,
                WorkoutDetail.session_id == WorkoutSession.session_id
            )
            .where(
                and_(
                    WorkoutSession.telegram_id == telegram_id,

                    WorkoutDetail.exercise_name.ilike(
                        f"%{normalized}%"
                    ),

                    WorkoutSession.session_date >= query_start,
                    WorkoutSession.session_date <= query_end
                )
            )
            .order_by(WorkoutSession.session_date)
        ).all()

        grouped = {}

        for row in rows:

            date_key = row.session_date

            if date_key not in grouped:
                grouped[date_key] = 0

            # СОБСТВЕННЫЙ ВЕС
            if normalized in BODYWEIGHT_EXERCISES:

                total = row.sets_count * row.reps_count

            # ВЕСОВЫЕ
            else:

                total = (
                    float(row.weight)
                    * row.reps_count
                    * row.sets_count
                )

            grouped[date_key] += total

        history = sorted(grouped.items())

        return history

    finally:
        session.close()


def render_exercise_chart(
    history_data: List[Tuple[datetime, float]],
    exercise_name: str
):

    fig, ax = plt.subplots(figsize=(10, 5))

    dates = [x[0] for x in history_data]
    values = [x[1] for x in history_data]

    # Добавляем запас пустого места: снизу 10, сверху 5
    if values:
        min_val = min(values)
        max_val = max(values)
        y_min = max(0, min_val - 10)  # снизу запас 10, но не меньше 0
        y_max = max_val + 5  # сверху запас 5
        ax.set_ylim(y_min, y_max)

    ax.plot(
        dates,
        values,
        marker="o",
        linewidth=3
    )

    normalized = normalize_exercise_name(exercise_name)

    ylabel = (
        "Количество повторений"
        if normalized in BODYWEIGHT_EXERCISES
        else "Тренировочный объем"
    )

    ax.set_title(f"Прогресс: {exercise_name}")
    ax.set_xlabel("Дата")
    ax.set_ylabel(ylabel)

    ax.grid(True)

    plt.xticks(rotation=45)

    plt.tight_layout()

    buffer = io.BytesIO()

    plt.savefig(
        buffer,
        format="png",
        dpi=150
    )

    buffer.seek(0)

    plt.close()

    return BufferedInputFile(
        file=buffer.read(),
        filename="progress.png"
    )