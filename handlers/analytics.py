"""
Обработчики для аналитики тренировок и команд.
Содержит команды для просмотра прогресса, списка упражнений и главное меню.
"""

from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Union, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import distinct, select

from database.connection import get_session_sync
from database.models import WorkoutDetail, WorkoutSession
from services.chart_service import get_workout_history, render_exercise_chart
from services.gemini_service import extract_analytics_intent
from utils.states import WorkoutStates

router = Router()


def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру главного меню с основными командами.

    Returns:
        ReplyKeyboardMarkup с кнопками команд
    """
    kb = [
        [KeyboardButton(text="📊 Мои упражнения"), KeyboardButton(text="📈 Показать прогресс")],
        [KeyboardButton(text="📝 Записать тренировку"), KeyboardButton(text="📖 Дневник тренировок")],
        [KeyboardButton(text="❓ Помощь")]
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


@router.message(F.text == "📖 Дневник тренировок")
async def btn_workout_diary(message: types.Message):
    """
    Обработчик кнопки «📖 Дневник тренировок».
    Отправляет первую страницу дневника тренировок.
    """
    await show_workout_diary_page(message, page=0)


async def show_workout_diary_page(
    message: Union[types.Message, types.CallbackQuery],
    page: int
):
    """
    Показывает страницу дневника тренировок с пагинацией.

    Args:
        message: Сообщение или callback query
        page: Номер страницы (0-based)
    """
    from sqlalchemy import select, desc
    from aiogram.types import InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    # Получаем telegram_id в зависимости от типа объекта
    if isinstance(message, types.CallbackQuery):
        telegram_id = message.from_user.id
        original_message = message.message
    else:
        telegram_id = message.from_user.id
        original_message = None

    session = get_session_sync()
    try:
        # Получаем все тренировки пользователя, отсортированные от новых к старым
        query = (
            select(WorkoutSession)
            .where(WorkoutSession.telegram_id == telegram_id)
            .order_by(desc(WorkoutSession.session_date))
        )

        sessions = session.execute(query).scalars().all()

        if not sessions:
            await message.answer(
                "У вас пока нет записанных тренировок.\n"
                "Начните вести дневник тренировок, отправляя описание тренировки боту.",
                reply_markup=create_main_menu_keyboard()
            )
            return

        ITEMS_PER_PAGE = 10
        total_pages = (len(sessions) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

        # Ограничиваем номер страницы допустимыми значениями
        if page < 0:
            page = 0
        if page >= total_pages:
            page = total_pages - 1 if total_pages > 0 else 0

        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(sessions))
        page_sessions = sessions[start_idx:end_idx]

        # Формируем текст страницы
        result_text = f"📖 <b>Дневник тренировок</b>\nСтраница {page + 1} из {total_pages}\n\n"

        for idx, workout_session in enumerate(page_sessions, start=start_idx + 1):
            result_text += f"{idx}. 📅 {workout_session.session_date.strftime('%d.%m.%Y')}\n"

            # Получаем детали тренировки
            details_query = (
                select(WorkoutDetail)
                .where(WorkoutDetail.session_id == workout_session.session_id)
            )
            details = session.execute(details_query).scalars().all()

            for detail in details:
                if detail.weight > 0:
                    result_text += f"   {detail.exercise_name}: {detail.sets_count}x{detail.reps_count} ({detail.weight} кг)\n"
                else:
                    result_text += f"   {detail.exercise_name}: {detail.sets_count}x{detail.reps_count}\n"

            if workout_session.user_notes:
                result_text += f"   💬 {workout_session.user_notes}\n"

            result_text += "\n"

        # Создаем клавиатуру навигации и управления тренировками
        builder = InlineKeyboardBuilder()

        # Кнопки навигации по страницам
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"diary_page_{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"diary_page_{page + 1}"))

        # Кнопки управления для текущей страницы
        edit_buttons = []
        for idx, _ in enumerate(page_sessions, start=start_idx + 1):
            edit_buttons.append(InlineKeyboardButton(text=str(idx), callback_data=f"diary_edit_{idx}"))

        # Добавляем кнопки навигации
        if nav_buttons:
            builder.row(*nav_buttons)

        # Добавляем кнопки выбора тренировки для редактирования
        if edit_buttons:
            builder.row(*edit_buttons[:5])  # Первая строка кнопок (до 5)
            if len(edit_buttons) > 5:
                builder.row(*edit_buttons[5:])  # Вторая строка кнопок (остальные)

        # Кнопка отмены
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="diary_cancel"))

        keyboard = builder.as_markup()

        if isinstance(message, types.CallbackQuery):
            if original_message:
                await original_message.edit_text(
                    result_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                await message.message.answer(
                    result_text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
        else:
            await message.answer(
                result_text,
                parse_mode="HTML",
                reply_markup=keyboard
            )

    finally:
        session.close()


@router.callback_query(F.data.startswith("diary_page_"))
async def handle_diary_navigation(callback: CallbackQuery):
    """
    Обработчик навигации по страницам дневника тренировок.
    """
    page = int(callback.data.split("_")[-1])
    await show_workout_diary_page(callback, page)


@router.callback_query(F.data.startswith("diary_edit_"))
async def handle_diary_edit(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик выбора тренировки для редактирования/удаления.
    """
    workout_number = int(callback.data.split("_")[-1])

    # Сохраняем номер тренировки и текущую страницу в состоянии
    await state.update_data(edit_workout_number=workout_number)
    await state.set_state(WorkoutStates.waiting_for_edit)

    # Создаём клавиатуру с кнопками удаления и отмены
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text=f"🗑 Удалить тренировку #{workout_number}",
        callback_data=f"diary_delete_{workout_number}"
    )
    
    builder.button(
        text="❌ Отменить",
        callback_data="diary_cancel"
    )
    
    builder.adjust(1)
    keyboard = builder.as_markup()

    await callback.message.edit_text(
        f"✏️ <b>Редактирование тренировки #{workout_number}</b>\n\n"
        f"Отправьте новое описание тренировки для обновления.\n\n"
        f"Пример описания:\n"
        f"\"Отжимания 4 подхода по 20 раз с весом 10 кг\"",
        parse_mode="HTML",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "diary_cancel")
async def handle_diary_cancel(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик отмены действия в дневнике тренировок.
    """
    await state.clear_state()
    
    await callback.message.edit_text(
        "❌ Действие отменено.\n\nВыберите команду из меню:",
        reply_markup=create_main_menu_keyboard()
    )
    
    await callback.answer()


@router.callback_query(F.data.startswith("diary_delete_"))
async def handle_diary_delete(callback: CallbackQuery, state: FSMContext):
    """
    Обработчик удаления тренировки из дневника.
    """
    from database.crud import get_user_workout_sessions, delete_workout_session
    
    workout_number = int(callback.data.split("_")[-1])
    
    try:
        # Получаем все сессии пользователя
        user_id = callback.from_user.id
        sessions = await get_user_workout_sessions(user_id)
        
        if workout_number > len(sessions):
            await callback.answer(
                f"❌ Тренировка #{workout_number} не найдена.",
                show_alert=True
            )
            await state.clear_state()
            return
        
        # Удаляем тренировку (сессии отсортированы от новых к старым)
        session_to_delete = sessions[workout_number - 1]
        await delete_workout_session(session_to_delete.session_id)
        
        await state.clear_state()
        
        await callback.message.edit_text(
            f"✅ Тренировка #{workout_number} от {session_to_delete.session_date.strftime('%d.%m.%Y')} успешно удалена!",
            reply_markup=create_main_menu_keyboard()
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка при удалении: {str(e)}", show_alert=True)


# Убираем regexp-хэндлер, так как теперь все запросы обрабатываются через determine_user_intent в workout.py
# Этот хэндлер больше не нужен, чтобы избежать дублирования обработки