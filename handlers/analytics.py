"""
Обработчики для аналитики, команд и главного меню.
"""
from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Union, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy import distinct, select, desc
from database.connection import get_session_sync
from database.models import WorkoutDetail, WorkoutSession
from database.crud import update_recommendation_status
from utils.states import WorkoutStates

router = Router()


def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📊 Мои упражнения"), KeyboardButton(text="📈 Показать прогресс")],
        [KeyboardButton(text="📝 Записать тренировку"), KeyboardButton(text="📖 Дневник тренировок")],
        [KeyboardButton(text="🔍 Запросить аналитику"), KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def create_recommendation_keyboard(rec_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Воспользуюсь советом", callback_data=f"rec_accept_{rec_id}")
    builder.button(text="❌ Откажусь от совета", callback_data=f"rec_reject_{rec_id}")
    builder.adjust(1)
    return builder.as_markup()


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Добро пожаловать в AI Дневник Тренировок!</b>\n"
        "Я помогу вам вести учет тренировок и анализировать прогресс.\n\n"
        "<b>Что я умею:</b>\n"
        "• 📝 Записывать тренировки — просто отправьте текст\n"
        "• 📊 Показывать список упражнений\n"
        "• 📈 Строить графики прогресса\n"
        "• 🔍 Давать аналитику и советы от AI-тренера\n\n"
        "Используйте кнопки ниже или команды:\n"
        "/exercises — список упражнений\n"
        "/progress — график прогресса\n"
        "/help — справка",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📖 <b>Справка по использованию бота</b>\n\n"
        "<b>📝 Как записать тренировку:</b>\n"
        "Просто отправьте описание в свободной форме.\n"
        "Примеры:\n"
        "• <i>\"Жим лежа 80кг 3х10, приседания 100кг 4х8\"</i>\n"
        "• <i>\"Вчера сделал 200 отжиманий, чувствовал себя бодро\"</i>\n"
        "• <i>\"3 подхода по 15 на бицепс 15кг\"</i>\n\n"
        "<b>📊 Как посмотреть упражнения:</b>\n"
        "Кнопка «📊 Мои упражнения» или /exercises\n\n"
        "<b>📈 Как посмотреть прогресс:</b>\n"
        "Кнопка «📈 Показать прогресс» или напишите:\n"
        "• <i>«Покажи прогресс в жиме лежа за 2 месяца»</i>\n"
        "• <i>«График приседаний»</i>\n\n"
        "<b>🔍 Как запросить аналитику:</b>\n"
        "Кнопка «🔍 Запросить аналитику» или напишите:\n"
        "• <i>«Проанализируй мои отжимания за месяц»</i>\n"
        "• <i>«Дай совет по приседаниям»</i>\n"
        "• <i>«Статистика становой тяги с 1 по 15 мая»</i>\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/exercises — список упражнений\n"
        "/progress — график прогресса\n"
        "/help — эта справка",
        parse_mode="HTML"
    )


@router.message(Command("progress"))
async def cmd_progress_request(message: types.Message, state: FSMContext):
    await state.set_state(WorkoutStates.waiting_for_chart)
    await message.answer(
        "📈 <b>Режим построения графика прогресса</b>\n\n"
        "Напишите название упражнения и период (если нужен).\n"
        "Чтобы выйти из режима, нажмите любую кнопку меню.\n\n"
        "<b>Примеры запросов:</b>\n"
        "• <i>«Жим лежа»</i> (весь период)\n"
        "• <i>«Прогресс приседаний за 3 месяца»</i>\n"
        "• <i>«Становая тяга с 1 по 30 мая»</i>\n"
        "• <i>«Отжимания за последнюю неделю»</i>",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(Command("exercises"))
async def cmd_exercises(message: types.Message, state: FSMContext):
    await state.clear()
    telegram_id = message.from_user.id
    session = get_session_sync()
    try:
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
                "Начните вести дневник тренировок.",
                reply_markup=create_main_menu_keyboard()
            )
            return
        exercises_list = "\n".join(f"• {ex}" for ex in exercises)
        await message.answer(
            f"Ваши упражнения:\n{exercises_list}",
            reply_markup=create_main_menu_keyboard(),
            parse_mode="HTML"
        )
    finally:
        session.close()


@router.message(F.text == "📊 Мои упражнения")
async def btn_exercises(message: types.Message, state: FSMContext):
    await state.clear()
    await cmd_exercises(message, state)


@router.message(F.text == "📈 Показать прогресс")
async def btn_progress_request(message: types.Message, state: FSMContext):
    await state.set_state(WorkoutStates.waiting_for_chart)
    await message.answer(
        "📈 <b>Режим построения графика прогресса</b>\n\n"
        "Напишите название упражнения и период (если нужен).\n"
        "Чтобы выйти из режима, нажмите любую кнопку меню.\n\n"
        "<b>Примеры запросов:</b>\n"
        "• <i>«Жим лежа»</i> (весь период)\n"
        "• <i>«Прогресс приседаний за 3 месяца»</i>\n"
        "• <i>«Становая тяга с 1 по 30 мая»</i>\n"
        "• <i>«Отжимания за последнюю неделю»</i>",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "📝 Записать тренировку")
async def btn_workout_request(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📝 <b>Запись тренировки</b>\n"
        "Просто отправьте описание вашей тренировки.\n\n"
        "<b>Примеры:</b>\n"
        "• <i>«Жим лежа 80кг 3 подхода по 10 повторений»</i>\n"
        "• <i>«Приседания 100кг 4х8, тяга становая 120кг 3х5»</i>\n"
        "• <i>«Вчера сделал 200 отжиманий, чувствовал себя отлично»</i>\n"
        "• <i>«Сегодня ноги: присед 100кг 3х10, выпады 20кг 3х15»</i>\n\n"
        "Я автоматически распознаю все параметры!",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text == "❓ Помощь")
async def btn_help(message: types.Message, state: FSMContext):
    await state.clear()
    await cmd_help(message, state)


@router.message(F.text == "📖 Дневник тренировок")
async def btn_workout_diary(message: types.Message, state: FSMContext):
    await state.clear()
    await show_workout_diary_page(message, page=0)


@router.message(F.text == "🔍 Запросить аналитику")
async def btn_analytics_request(message: types.Message, state: FSMContext):
    await state.set_state(WorkoutStates.waiting_for_advice)
    await message.answer(
        "🔍 <b>Режим запроса аналитики и совета AI-тренера</b>\n\n"
        "Напишите упражнение и период для анализа.\n"
        "Чтобы выйти из режима, нажмите любую кнопку меню.\n\n"
        "<b>Примеры запросов:</b>\n"
        "• <i>«Проанализируй мои отжимания за месяц»</i>\n"
        "• <i>«Как там мои приседания?»</i>\n"
        "• <i>«Дай совет по жиму лежа за последние 2 недели»</i>\n"
        "• <i>«Статистика становой тяги с 1 по 15 мая»</i>",
        reply_markup=create_main_menu_keyboard(),
        parse_mode="HTML"
    )


async def show_workout_diary_page(message: Union[types.Message, types.CallbackQuery], page: int):
    if isinstance(message, types.CallbackQuery):
        telegram_id = message.from_user.id
        original_message = message.message
    else:
        telegram_id = message.from_user.id
        original_message = None

    session = get_session_sync()
    try:
        query = (
            select(WorkoutSession)
            .where(WorkoutSession.telegram_id == telegram_id)
            .order_by(desc(WorkoutSession.session_date), desc(WorkoutSession.session_id))
        )
        sessions = session.execute(query).scalars().all()

        if not sessions:
            await message.answer(
                "У вас пока нет записанных тренировок.",
                reply_markup=create_main_menu_keyboard()
            )
            return

        ITEMS_PER_PAGE = 10
        total_pages = (len(sessions) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        if page < 0: page = 0
        if page >= total_pages: page = total_pages - 1 if total_pages > 0 else 0

        start_idx = page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(sessions))
        page_sessions = sessions[start_idx:end_idx]

        result_text = f"📖 <b>Дневник тренировок</b>\nСтраница {page + 1} из {total_pages}\n\n"
        for idx, workout_session in enumerate(page_sessions, start=start_idx + 1):
            result_text += f"{idx}. 📅 {workout_session.session_date.strftime('%d.%m.%Y')}\n"
            details_query = select(WorkoutDetail).where(WorkoutDetail.session_id == workout_session.session_id)
            details = session.execute(details_query).scalars().all()
            for detail in details:
                if detail.weight > 0:
                    result_text += f"   {detail.exercise_name}: {detail.sets_count}x{detail.reps_count} ({detail.weight} кг)\n"
                else:
                    result_text += f"   {detail.exercise_name}: {detail.sets_count}x{detail.reps_count}\n"
            if workout_session.user_notes:
                result_text += f"   💬 {workout_session.user_notes}\n"
            result_text += "\n"

        builder = InlineKeyboardBuilder()
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"diary_page_{page - 1}"))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"diary_page_{page + 1}"))

        edit_buttons = []
        for idx, _ in enumerate(page_sessions, start=start_idx + 1):
            edit_buttons.append(InlineKeyboardButton(text=str(idx), callback_data=f"diary_edit_{idx}"))

        if nav_buttons: builder.row(*nav_buttons)
        if edit_buttons:
            builder.row(*edit_buttons[:5])
            if len(edit_buttons) > 5:
                builder.row(*edit_buttons[5:])
        builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="diary_cancel"))
        keyboard = builder.as_markup()

        if isinstance(message, types.CallbackQuery):
            if original_message:
                await original_message.edit_text(result_text, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.message.answer(result_text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(result_text, parse_mode="HTML", reply_markup=keyboard)
    finally:
        session.close()


@router.callback_query(F.data.startswith("diary_page_"))
async def handle_diary_navigation(callback: CallbackQuery):
    page = int(callback.data.split("_")[-1])
    await show_workout_diary_page(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("diary_edit_"))
async def handle_diary_edit(callback: CallbackQuery, state: FSMContext):
    from database.crud import get_user_workout_sessions
    workout_number = int(callback.data.split("_")[-1])
    await state.update_data(edit_workout_number=workout_number)
    await state.set_state(WorkoutStates.waiting_for_edit)

    user_id = callback.from_user.id
    sessions = await get_user_workout_sessions(user_id)
    current_workout_info = ""

    if workout_number <= len(sessions):
        session = sessions[workout_number - 1]
        current_workout_info = f"\n📋 <b>Текущая информация:</b>\n"
        current_workout_info += f"📅 {session.session_date.strftime('%d.%m.%Y')}\n"

        db_session = get_session_sync()
        try:
            details_query = select(WorkoutDetail).where(WorkoutDetail.session_id == session.session_id)
            details = db_session.execute(details_query).scalars().all()
            for detail in details:
                if detail.weight > 0:
                    current_workout_info += f"   {detail.exercise_name}: {detail.sets_count}x{detail.reps_count} ({detail.weight} кг)\n"
                else:
                    current_workout_info += f"   {detail.exercise_name}: {detail.sets_count}x{detail.reps_count}\n"
        finally:
            db_session.close()

    builder = InlineKeyboardBuilder()
    builder.button(text=f"🗑 Удалить тренировку #{workout_number}", callback_data=f"diary_delete_{workout_number}")
    builder.button(text="❌ Отменить", callback_data="diary_cancel")
    builder.adjust(1)
    keyboard = builder.as_markup()

    await callback.message.edit_text(
        f"✏️ <b>Редактирование тренировки #{workout_number}</b>\n"
        f"Отправьте новое описание тренировки.\n"
        f"Или используйте кнопки ниже:\n"
        f"• 🗑 Удалить тренировку\n"
        f"• ❌ Отменить\n"
        f"{current_workout_info}",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "diary_cancel")
async def handle_diary_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ Действие отменено.\nВыберите команду из меню:",
        reply_markup=None
    )
    await callback.answer()


@router.callback_query(F.data.startswith("diary_delete_"))
async def handle_diary_delete(callback: CallbackQuery, state: FSMContext):
    from database.crud import get_user_workout_sessions, delete_workout_session
    workout_number = int(callback.data.split("_")[-1])
    try:
        user_id = callback.from_user.id
        sessions = await get_user_workout_sessions(user_id)
        if workout_number > len(sessions):
            await callback.answer(f"❌ Тренировка #{workout_number} не найдена.", show_alert=True)
            await state.clear()
            return

        session_to_delete = sessions[workout_number - 1]
        await delete_workout_session(session_to_delete.session_id)
        await state.clear()

        await callback.message.edit_text(
            f"✅ Тренировка #{workout_number} от {session_to_delete.session_date.strftime('%d.%m.%Y')} удалена!",
            reply_markup=create_main_menu_keyboard()
        )
        await callback.answer("Тренировка удалена!")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("rec_accept_"))
async def accept_recommendation(callback: CallbackQuery):
    rec_id = int(callback.data.split("_")[-1])
    await update_recommendation_status(rec_id, is_accepted=True)
    await callback.answer("✅ Совет принят!")
    await callback.message.edit_reply_markup(reply_markup=None)


@router.callback_query(F.data.startswith("rec_reject_"))
async def reject_recommendation(callback: CallbackQuery):
    rec_id = int(callback.data.split("_")[-1])
    await update_recommendation_status(rec_id, is_accepted=False)
    await callback.answer("❌ Совет отклонён.")
    await callback.message.edit_reply_markup(reply_markup=None)