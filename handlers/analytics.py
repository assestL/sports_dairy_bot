"""
Обработчики для аналитики тренировок.
Содержит команды для просмотра прогресса и списка упражнений.
"""

from aiogram import Router, types, F
from aiogram.filters import Command
from sqlalchemy import distinct, select

from database.connection import get_session_sync
from database.models import WorkoutDetail, WorkoutSession
from services.chart_service import get_workout_history, render_exercise_chart
from services.gemini_service import extract_analytics_intent

router = Router()


@router.message(Command("exercises"))
async def cmd_exercises(message: types.Message):
    """
    Обработчик команды /exercises.
    Выводит список всех уникальных упражнений, которые пользователь когда-либо записывал.
    """
    telegram_id = message.from_user.id
    
    session = get_session_sync()
    try:
        # Запрос DISTINCT exercise_name с JOIN между таблицами
        query = (
            select(distinct(WorkoutDetail.exercise_name))
            .select_from(WorkoutSession)
            .join(WorkoutDetail, WorkoutDetail.session_id == WorkoutSession.session_id)
            .where(WorkoutSession.telegram_id == telegram_id)
            .order_by(WorkoutDetail.exercise_name)
        )
        
        result = session.execute(query).all()
        exercises = [row[0] for row in result]
        
        if not exercises:
            await message.answer(
                "У вас пока нет записанных упражнений.\n"
                "Начните вести дневник тренировок, отправляя описание тренировки боту."
            )
            return
        
        exercises_list = "\n".join(f"• {ex}" for ex in exercises)
        await message.answer(
            f"Ваши упражнения:\n\n{exercises_list}",
            parse_mode="HTML"
        )
    finally:
        session.close()


@router.message(F.text.regexp(r"^(Покажи|Прогресс|Как там|График|Статистика)"))
async def handle_analytics_request(message: types.Message):
    """
    Обработчик текстовых запросов аналитики.
    
    Бот вызывает extract_analytics_intent для извлечения намерения,
    затем ищет данные в БД и строит график прогресса.
    """
    telegram_id = message.from_user.id
    text = message.text
    
    # Извлекаем намерение через Gemini API
    try:
        intent = await extract_analytics_intent(text)
    except Exception as e:
        await message.answer(
            "Не удалось распознать ваш запрос. Попробуйте сформулировать иначе, например:\n"
            "«Покажи мой прогресс в жиме лежа за 2 месяца»"
        )
        return
    
    exercise_name = intent.exercise_name
    period_days = intent.period_days
    
    # Получаем историю тренировок из БД
    history_data = get_workout_history(telegram_id, exercise_name, period_days)
    
    # Проверяем количество точек данных
    if len(history_data) < 2:
        await message.answer(
            "Недостаточно данных для построения графика по этому упражнению.\n"
            f"Найдено записей: {len(history_data)}\n"
            "Продолжайте вести дневник тренировок!"
        )
        return
    
    # Строим график
    chart_file = render_exercise_chart(history_data, exercise_name)
    
    # Отправляем график пользователю
    await message.answer_photo(
        photo=chart_file,
        caption=f"Ваш прогресс в упражнении: {exercise_name}"
    )