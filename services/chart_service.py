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

# Упражнения с собственным весом (weight=0 в БД)
BODYWEIGHT_EXERCISES = {
    "отжимания", "подтягивания", "пресс", "брусья",
    "скручивания", "приседания", "выпады", "планка"
}

# Маппинг падежных форм для популярных упражнений
CASE_NORMALIZATION = {
    # Приседания
    "приседаний": "приседания", "приседаниям": "приседания",
    "приседаниями": "приседания", "приседаниях": "приседания",
    "приседание": "приседания", "приседанием": "приседания",
    # Отжимания
    "отжиманий": "отжимания", "отжиманиям": "отжимания",
    "отжиманиями": "отжимания", "отжиманиях": "отжимания",
    "отжимание": "отжимания", "отжиманием": "отжимания",
    # Подтягивания
    "подтягиваний": "подтягивания", "подтягиваниям": "подтягивания",
    "подтягиваниями": "подтягивания", "подтягиваниях": "подтягивания",
    "подтягивание": "подтягивания", "подтягиванием": "подтягивания",
    # Жим
    "жиме": "жим", "жимом": "жим", "жима": "жим", "жиму": "жим", "жимом": "жим",
    # Тяга
    "тяге": "тяга", "тягой": "тяга", "тяги": "тяга", "тягу": "тяга", "тягах": "тяга",
    # Становая тяга
    "становой тяге": "становая тяга", "становой тягой": "становая тяга",
    # Брусья
    "брусьях": "брусья", "брусьями": "брусья", "брусьев": "брусья",
    # Пресс
    "прессе": "пресс", "прессом": "пресс", "пресса": "пресс",
}

def normalize_exercise_name(name: str) -> str:
    """Нормализует название упражнения: убирает падежи, приводит к нижнему регистру."""
    name = name.lower().strip().replace("ё", "е")

    # Сначала пробуем точное совпадение в маппинге падежей
    if name in CASE_NORMALIZATION:
        return CASE_NORMALIZATION[name]

    # Пробуем убрать окончания -ий, -ей, -ям, -ях, -ами, -ем, -ом
    for ending in ["ий", "ей", "ям", "ях", "ами", "ем", "ом", "ах", "ам"]:
        if name.endswith(ending) and len(name) > len(ending) + 1:
            base = name[:-len(ending)]
            # Пробуем добавить "а" или "я" для множественного числа
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

        # Если даты не указаны явно, берём первую и последнюю запись этого упражнения из БД
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
                # Данных нет
                return []
        elif start_date is not None and end_date is not None:
            query_start = start_date
            query_end = end_date
        else:
            # Если указана только одна дата, используем fallback
            query_end = datetime.now().date()
            query_start = query_end - timedelta(days=days)

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

            # Если вес = 0 или упражнение в списке bodyweight, считаем повторения
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
    fig, ax = plt.subplots(figsize=(10, 5))
    dates = [x[0] for x in history_data]
    values = [x[1] for x in history_data]

    if values:
        min_val = min(values)
        max_val = max(values)
        y_min = max(0, min_val - 10)
        y_max = max_val + 5
        ax.set_ylim(y_min, y_max)

    ax.plot(dates, values, marker="o", linewidth=3)

    normalized = normalize_exercise_name(exercise_name)
    ylabel = "Количество повторений" if normalized in BODYWEIGHT_EXERCISES else "Тренировочный объем"

    ax.set_title(f"Прогресс: {exercise_name}")
    ax.set_xlabel("Дата")
    ax.set_ylabel(ylabel)
    ax.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png", dpi=150)
    buffer.seek(0)
    plt.close()

    return BufferedInputFile(file=buffer.read(), filename="progress.png")