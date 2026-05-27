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
    "отжимания", "подтягивания", "пресс", "брусья",
    "скручивания", "приседания", "выпады", "планка"
}

CASE_NORMALIZATION = {
    "приседаний": "приседания", "приседаниям": "приседания",
    "приседаниями": "приседания", "приседаниях": "приседания",
    "приседание": "приседания", "приседанием": "приседания",
    "отжиманий": "отжимания", "отжиманиям": "отжимания",
    "отжиманиями": "отжимания", "отжиманиях": "отжимания",
    "отжимание": "отжимания", "отжиманием": "отжимания",
    "подтягиваний": "подтягивания", "подтягиваниям": "подтягивания",
    "подтягиваниями": "подтягивания", "подтягиваниях": "подтягивания",
    "подтягивание": "подтягивания", "подтягиванием": "подтягивания",
    "жиме": "жим", "жимом": "жим", "жима": "жим", "жиму": "жим",
    "тяге": "тяга", "тягой": "тяга", "тяги": "тяга", "тягу": "тяга", "тягах": "тяга",
    "становой тяге": "становая тяга", "становой тягой": "становая тяга",
    "брусьях": "брусья", "брусьями": "брусья", "брусьев": "брусья",
    "прессе": "пресс", "прессом": "пресс", "пресса": "пресс",
}


def normalize_exercise_name(name: str) -> str:
    name = name.lower().strip().replace("ё", "е")
    if name in CASE_NORMALIZATION:
        return CASE_NORMALIZATION[name]
    for ending in ["ий", "ей", "ям", "ях", "ами", "ем", "ом", "ах", "ам"]:
        if name.endswith(ending) and len(name) > len(ending) + 1:
            base = name[:-len(ending)]
            for suffix in ["а", "я", "ы", "и", ""]:
                variant = base + suffix
                if variant in BODYWEIGHT_EXERCISES or variant in CASE_NORMALIZATION.values():
                    return variant
    return name


def get_workout_history(
    telegram_id: int,
    exercise_name: str,
    days: int,
    start_date: datetime = None,
    end_date: datetime = None
):
    session = get_session_sync()
    try:
        if not exercise_name:
            return []

        normalized = normalize_exercise_name(exercise_name)

        if start_date is None and end_date is None:
            min_max_query = (
                select(
                    func.min(WorkoutSession.session_date).label('min_date'),
                    func.max(WorkoutSession.session_date).label('max_date')
                )
                .join(WorkoutDetail, WorkoutDetail.session_id == WorkoutSession.session_id)
                .where(
                    and_(
                        WorkoutSession.telegram_id == telegram_id,
                        WorkoutDetail.exercise_name.ilike(f"%{normalized}%")
                    )
                )
            )
            min_max_result = session.execute(min_max_query).first()

            if min_max_result and min_max_result.min_date and min_max_result.max_date:
                query_start = min_max_result.min_date
                query_end = min_max_result.max_date
            else:
                return []
        elif start_date is not None and end_date is not None:
            query_start = start_date
            query_end = end_date
        else:
            query_end = datetime.now().date()
            query_start = query_end - timedelta(days=days)

        rows = session.execute(
            select(
                WorkoutSession.session_date,
                WorkoutDetail.weight,
                WorkoutDetail.sets_count,
                WorkoutDetail.reps_count
            )
            .join(WorkoutDetail, WorkoutDetail.session_id == WorkoutSession.session_id)
            .where(
                and_(
                    WorkoutSession.telegram_id == telegram_id,
                    WorkoutDetail.exercise_name.ilike(f"%{normalized}%"),
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

            if normalized in BODYWEIGHT_EXERCISES or float(row.weight) == 0:
                total = row.sets_count * row.reps_count
            else:
                total = float(row.weight) * row.reps_count * row.sets_count
            grouped[date_key] += total

        history = sorted(grouped.items())
        return history
    finally:
        session.close()


def render_exercise_chart(
    history_data: List[Tuple[datetime, float]],
    exercise_name: str
):
    """
    Рисует график ТОЛЬКО по дням тренировок (без пропусков календарных дней).
    """
    fig, ax = plt.subplots(figsize=(10, 5))

    # Преобразуем даты в строки для категориальной оси X
    dates_str = [x[0].strftime('%d.%m') for x in history_data]
    values = [x[1] for x in history_data]

    if values:
        min_val = min(values)
        max_val = max(values)
        y_min = max(0, min_val - 10)
        y_max = max_val + 5
        ax.set_ylim(y_min, y_max)

    # Используем range(len) для X, чтобы не было "пустых" дней между тренировками
    ax.plot(range(len(dates_str)), values, marker="o", linewidth=3, color="#2E86AB")

    # Настраиваем метки X только по дням тренировок
    ax.set_xticks(range(len(dates_str)))
    ax.set_xticklabels(dates_str, rotation=45, ha='right')

    normalized = normalize_exercise_name(exercise_name)
    ylabel = "Количество повторений" if normalized in BODYWEIGHT_EXERCISES else "Тренировочный объем"

    ax.set_title(f"Прогресс: {exercise_name}", fontsize=14, fontweight='bold')
    ax.set_xlabel("Дата тренировки")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    buffer.seek(0)
    plt.close()

    return BufferedInputFile(file=buffer.read(), filename="progress.png")