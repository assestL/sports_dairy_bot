"""
Обработчики для аналитики тренировок и команд.
"""
from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Union, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton
from sqlalchemy import distinct, select, desc
from database.connection import get_session_sync
from database.models import WorkoutDetail, WorkoutSession
from services.chart_service import get_workout_history, render_exercise_chart
from utils.states import WorkoutStates

router = Router()

def create_main_menu_keyboard() -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="📊 Мои упражнения"), KeyboardButton(text="📈 Показать прогресс")],
        [KeyboardButton(text="📝 Записать тренировку"), KeyboardButton(text="📖 Дневник тренировок")],
        [KeyboardButton(text="❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 <b>Добро пожаловать в AI Дневник Тренировок!</b>\n"
        "Я помогу вам вести учет тренировок и анализировать прогресс.\n"
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
async def cmd_help(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📖 <b>Справка по использованию бота</b>\n"
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
async def cmd_progress_request(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📈 <b>Построение графика прогресса</b>\n"
        "Напишите название упражнения, например:\n"
        "<i>«Покажи прогресс в жиме лежа»</i>\n"
        "Можно указать период: <i>«Прогресс приседаний за 3 месяца»</i>",
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
            await message.answer("У вас пока нет записанных упражнений.\nНачните вести дневник тренировок, отправляя описание тренировки боту.", reply_markup=create_main_menu_keyboard())
            return
        exercises_list = "\n".join(f"• {ex}" for ex in exercises)
        await message.answer(f"Ваши упражнения:\n{exercises_list}", reply_markup=create_main_menu_keyboard(), parse_mode="HTML")
    finally:
        session.close()

# Обработчики кнопок меню (везде добавлен state.clear(), чтобы прерывать режим редактирования)
@router.message(F.text == "📊 Мои упражнения")
async def btn_exercises(message: types.Message, state: FSMContext):
    await state.clear()
    await cmd_exercises(message, state)

@router.message(F.text == "📈 Показать прогресс")
async def btn_progress_request(message: types.Message, state: FSMContext):
    await state.clear()
    await cmd_progress_request(message, state)

@router.message(F.text == "📝 Записать тренировку")
async def btn_workout_request(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📝 <b>Запись тренировки</b>\n"
        "Просто отправьте сообщение с описанием вашей тренировки.\n"
        "Примеры:\n"
        "• <i>«Жим лежа 80кг 3 подхода по 10 повторений»</i>\n"
        "• <i>«Приседания 100кг 4х8, тяга становая 120кг 3х5»</i>\n"
        "• <i>«Сегодня делал грудь: жим на наклонной 70кг 3х12, разводка 25кг 3х15»</i>\n\n"
        "Я автоматически распознаю все упражнения и параметры!",
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

async def show_workout_diary_page(
    message: Union[types.Message, types.CallbackQuery],
    page: int
):
    if isinstance(message, types.CallbackQuery):
        telegram_id = message.from_user.id
        original_message = message.message
    else:
        telegram_id = message.from_user.id
        original_message = None

    session = get_session_sync()
    try:
        # Добавлена сортировка по session_id для стабильности
        query = (
            select(WorkoutSession)
            .where(WorkoutSession.telegram_id == telegram_id)
            .order_by(desc(WorkoutSession.session_date), desc(WorkoutSession.session_id))
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
        f"Отправьте новое описание тренировки для обновления.\n"
        f"Или используйте кнопки ниже:\n"
        f"• 🗑 Удалить тренировку — удалит эту тренировку из дневника\n"
        f"• ❌ Отменить — выйдет из режима редактирования\n"
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
            f"✅ Тренировка #{workout_number} от {session_to_delete.session_date.strftime('%d.%m.%Y')} успешно удалена!",
            reply_markup=create_main_menu_keyboard()
        )
        # ОБЯЗАТЕЛЬНО отвечаем на callback, чтобы убрать "часики" на кнопке в Telegram
        await callback.answer("Тренировка удалена!")
    except Exception as e:
        await callback.answer(f"❌ Ошибка при удалении: {str(e)}", show_alert=True)