"""
Обработчики для аналитики тренировок и команд.
Содержит команды для просмотра прогресса, списка упражнений и главное меню.
"""

from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from sqlalchemy import distinct, select

from database.connection import get_session_sync
from database.models import WorkoutDetail, WorkoutSession
from services.chart_service import get_workout_history, render_exercise_chart
from services.gemini_service import extract_analytics_intent

router = Router()


def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру главного меню с основными командами.
    
    Returns:
        ReplyKeyboardMarkup с кнопками команд
    """
    kb = [
        [KeyboardButton(text="📊 Мои упражнения"), KeyboardButton(text="📈 Показать прогресс")],
        [KeyboardButton(text="📝 Записать тренировку"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    """
    Обработчик команды /start.
    Выводит приветственное сообщение и главное меню.
    """
    await message.answer(
        "👋 <b>Добро пожаловать в AI Дневник Тренировок!</b>\n\n"
        "Я помогу вам вести учет тренировок и анализировать прогресс.\n\n"
        "<b>Что я умею:</b>\n"
        "• 📝 Записывать тренировки — просто отправьте текст с описанием\n"
        "• 📊 Показывать список ваших упражнений\n"
        "• 📈 Строить графики прогресса по упражнениям\n"
        "• 🤖 Давать рекомендации от AI-тренера\n\n"
        "Используйте кнопки ниже или команды:\n"
        "/exercises — список всех упражнений\n"
        "/progress — показать прогресс (спросит упражнение)\n"
        "/help — справка по использованию",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message):
    """
    Обработчик команды /help.
    Выводит справку по использованию бота.
    """
    await message.answer(
        "📖 <b>Справка по использованию бота</b>\n\n"
        "<b>Как записать тренировку:</b>\n"
        "Просто отправьте сообщение с описанием тренировки в свободной форме.\n"
        "Пример: <i>\"Жим лежа 80кг 3х10, приседания 100кг 4х8\"</i>\n\n"
        "<b>Как посмотреть упражнения:</b>\n"
        "Нажмите кнопку «📊 Мои упражнения» или используйте команду /exercises\n\n"
        "<b>Как посмотреть прогресс:</b>\n"
        "Нажмите кнопку «📈 Показать прогресс» или напишите:\n"
        "<i>«Покажи прогресс в жиме лежа за 2 месяца»</i>\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/exercises — список упражнений\n"
        "/progress — запросить график прогресса\n"
        "/help — эта справка",
        parse_mode="HTML"
    )


@router.message(Command("progress"))
async def cmd_progress_request(message: types.Message):
    """
    Обработчик команды /progress.
    Запрашивает у пользователя название упражнения для построения графика.
    """
    await message.answer(
        "📈 <b>Построение графика прогресса</b>\n\n"
        "Напишите название упражнения, например:\n"
        "<i>«Покажи прогресс в жиме лежа»</i>\n\n"
        "Можно указать период: <i>«Прогресс приседаний за 3 месяца»</i>",
        parse_mode="HTML"
    )


@router.message(F.text == "📊 Мои упражнения")
async def btn_exercises(message: types.Message):
    """
    Обработчик кнопки «📊 Мои упражнения».
    Выводит список всех уникальных упражнений пользователя.
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
                "Начните вести дневник тренировок, отправляя описание тренировки боту.",
                reply_markup=create_main_menu_keyboard()
            )
            return
        
        exercises_list = "\n".join(f"• {ex}" for ex in exercises)
        await message.answer(
            f"Ваши упражнения:\n\n{exercises_list}",
            reply_markup=create_main_menu_keyboard(),
            parse_mode="HTML"
        )
    finally:
        session.close()


@router.message(F.text == "📈 Показать прогресс")
async def btn_progress_request(message: types.Message):
    """
    Обработчик кнопки «📈 Показать прогресс».
    Запрашивает у пользователя название упражнения.
    """
    await message.answer(
        "📈 <b>Построение графика прогресса</b>\n\n"
        "Напишите название упражнения, например:\n"
        "<i>«Покажи прогресс в жиме лежа»</i>\n\n"
        "Можно указать период: <i>«Прогресс приседаний за 3 месяца»</i>",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "📝 Записать тренировку")
async def btn_workout_request(message: types.Message):
    """
    Обработчик кнопки «📝 Записать тренировку».
    Подсказывает пользователю, как записать тренировку.
    """
    await message.answer(
        "📝 <b>Запись тренировки</b>\n\n"
        "Просто отправьте сообщение с описанием вашей тренировки.\n\n"
        "Примеры:\n"
        "• <i>«Жим лежа 80кг 3 подхода по 10 повторений»</i>\n"
        "• <i>«Приседания 100кг 4х8, тяга становая 120кг 3х5»</i>\n"
        "• <i>«Сегодня делал грудь: жим на наклонной 70кг 3х12, разводка 25кг 3х15»</i>\n\n"
        "Я автоматически распознаю все упражнения и параметры!",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "❓ Помощь")
async def btn_help(message: types.Message):
    """
    Обработчик кнопки «❓ Помощь».
    Выводит справку по использованию бота.
    """
    await cmd_help(message)


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
                "Начните вести дневник тренировок, отправляя описание тренировки боту.",
                reply_markup=create_main_menu_keyboard()
            )
            return
        
        exercises_list = "\n".join(f"• {ex}" for ex in exercises)
        await message.answer(
            f"Ваши упражнения:\n\n{exercises_list}",
            reply_markup=create_main_menu_keyboard(),
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
            "«Покажи мой прогресс в жиме лежа за 2 месяца»",
            reply_markup=create_main_menu_keyboard()
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
            "Продолжайте вести дневник тренировок!",
            reply_markup=create_main_menu_keyboard()
        )
        return
    
    # Строим график
    chart_file = render_exercise_chart(history_data, exercise_name)
    
    # Отправляем график пользователю
    await message.answer_photo(
        photo=chart_file,
        caption=f"Ваш прогресс в упражнении: {exercise_name}",
        reply_markup=create_main_menu_keyboard()
    )