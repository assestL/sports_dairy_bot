"""
Обработчики тренировок.
"""

from datetime import date, timezone, timedelta
from typing import Union

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.crud import (
    save_workout,
    get_or_create_user
)

from services.gemini_service import (
    parse_workout_text,
    WorkoutParseResult,
    determine_user_intent,
    AnalyticsIntent
)

from utils.states import WorkoutStates
from handlers.analytics import create_main_menu_keyboard
from services.chart_service import (
    get_workout_history,
    render_exercise_chart
)

router = Router()

MSK = timezone(timedelta(hours=3))


def create_confirmation_keyboard():

    builder = InlineKeyboardBuilder()

    builder.button(
        text="✅ Сохранить",
        callback_data="workout_confirm"
    )

    builder.button(
        text="✏️ Редактировать",
        callback_data="workout_edit"
    )

    builder.button(
        text="❌ Отмена",
        callback_data="workout_cancel"
    )

    builder.adjust(1)

    return builder.as_markup()


def format_workout_result(
    parsed_data: WorkoutParseResult
) -> str:

    if not parsed_data.sessions:
        return "Не удалось распознать тренировку."

    result = ""

    for session in parsed_data.sessions:

        result += (
            f"📅 <b>{session.date}</b>\n\n"
        )

        for exercise in session.exercises:

            sets_count = len(exercise.reps)

            reps_text = " / ".join(
                map(str, exercise.reps)
            )

            result += (
                f"🏋️ <b>{exercise.name}</b>\n"
                f"Вес: {exercise.weight} кг\n"
                f"Подходов: {sets_count}\n"
                f"Повторения: {reps_text}\n\n"
            )

        if session.wellness_notes:

            result += (
                f"💬 {session.wellness_notes}\n\n"
            )

    return result


async def process_parsed_workout(
    message: Union[types.Message, types.CallbackQuery],
    parsed_data: WorkoutParseResult,
    state: FSMContext
):

    result_text = format_workout_result(
        parsed_data
    )

    await state.update_data(
        workout_data=parsed_data.model_dump()
    )

    if isinstance(message, types.CallbackQuery):

        send_method = message.message.edit_text

    else:

        send_method = message.answer

    await send_method(
        result_text,
        parse_mode="HTML",
        reply_markup=create_confirmation_keyboard()
    )


@router.message(F.text)
async def handle_user_message(
    message: types.Message,
    state: FSMContext
):

    # ГЛАВНОЕ ИСПРАВЛЕНИЕ
    # ВСЕГДА создаём пользователя

    get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )

    msg_date = message.date

    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(
            tzinfo=timezone.utc
        )

    msk_date = msg_date.astimezone(
        MSK
    ).date()

    telegram_date_str = msk_date.isoformat()

    processing_message = await message.answer(
        "⏳ Анализирую..."
    )

    try:

        intent = await determine_user_intent(
            message.text,
            telegram_date_str
        )

        try:
            await processing_message.delete()
        except:
            pass

        if intent.intent_type == "workout":

            await process_parsed_workout(
                message,
                intent.workout_data,
                state
            )

        elif intent.intent_type == "analytics":

            await handle_analytics_intent(
                message,
                intent.analytics_data
            )

        else:

            await message.answer(
                "Не понял запрос.",
                reply_markup=create_main_menu_keyboard()
            )

    except Exception as e:

        try:
            await processing_message.delete()
        except:
            pass

        await message.answer(
            f"Ошибка:\n{str(e)}",
            reply_markup=create_main_menu_keyboard()
        )


async def handle_analytics_intent(
    message: types.Message,
    intent: AnalyticsIntent
):
    from datetime import datetime as dt

    # Если указаны конкретные даты, используем их
    start_date_obj = None
    end_date_obj = None
    
    if intent.start_date and intent.end_date:
        try:
            start_date_obj = dt.strptime(intent.start_date, "%Y-%m-%d")
            end_date_obj = dt.strptime(intent.end_date, "%Y-%m-%d")
        except ValueError:
            pass

    history_data = get_workout_history(
        telegram_id=message.from_user.id,
        exercise_name=intent.exercise_name,
        days=intent.period_days,
        start_date=start_date_obj,
        end_date=end_date_obj
    )

    if len(history_data) < 1:

        await message.answer(
            "Недостаточно данных.",
            reply_markup=create_main_menu_keyboard()
        )

        return

    chart = render_exercise_chart(
        history_data,
        intent.exercise_name
    )

    await message.answer_photo(
        photo=chart,
        caption=f"Прогресс: {intent.exercise_name}",
        reply_markup=create_main_menu_keyboard()
    )


@router.callback_query(F.data == "workout_confirm")
async def confirm_workout(
    callback: CallbackQuery,
    state: FSMContext
):

    data = await state.get_data()

    workout_data = data.get(
        "workout_data"
    )

    if not workout_data:

        await callback.answer(
            "Нет данных тренировки.",
            show_alert=True
        )

        return

    parsed_data = WorkoutParseResult(
        **workout_data
    )

    try:

        # ЕЩЁ ОДНА ГАРАНТИЯ
        get_or_create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username
        )

        save_workout(
            telegram_id=callback.from_user.id,
            parsed_data=parsed_data
        )

        await callback.message.edit_reply_markup(
            reply_markup=None
        )

        await callback.message.answer(
            "✅ Тренировка сохранена.",
            reply_markup=create_main_menu_keyboard()
        )

    except Exception as e:

        await callback.message.answer(
            f"Ошибка сохранения:\n{str(e)}"
        )

    finally:

        await state.clear()


@router.callback_query(F.data == "workout_cancel")
async def cancel_workout(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await callback.message.edit_reply_markup(
        reply_markup=None
    )

    await callback.message.answer(
        "Тренировка отменена.",
        reply_markup=create_main_menu_keyboard()
    )

    await callback.answer()


@router.callback_query(F.data == "workout_edit")
async def edit_workout(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.set_state(
        WorkoutStates.waiting_for_correction
    )

    await callback.message.answer(
        "Напиши исправление."
    )

    await callback.answer()


@router.message(
    WorkoutStates.waiting_for_correction
)
async def handle_correction(
    message: types.Message,
    state: FSMContext
):

    data = await state.get_data()

    workout_data = data.get(
        "workout_data"
    )

    if not workout_data:

        await message.answer(
            "Нет данных тренировки."
        )

        return

    original = WorkoutParseResult(
        **workout_data
    )

    processing = await message.answer(
        "⏳ Исправляю..."
    )

    try:

        parsed = await parse_workout_text(
            message.text
        )

        try:
            await processing.delete()
        except:
            pass

        await process_parsed_workout(
            message,
            parsed,
            state
        )

    except Exception as e:

        try:
            await processing.delete()
        except:
            pass

        await message.answer(
            f"Ошибка:\n{str(e)}"
        )


@router.message(WorkoutStates.waiting_for_edit)
async def handle_workout_edit(message: types.Message, state: FSMContext):
    """
    Обработчик редактирования тренировки из дневника.
    Получает новое описание тренировки и использует ИИ для парсинга.
    """
    from database.crud import get_user_workout_sessions, update_workout_session
    
    data = await state.get_data()
    workout_number = data.get("edit_workout_number")
    
    if not workout_number:
        await message.answer(
            "❌ Ошибка: не найден номер тренировки для редактирования.\n"
            "Попробуйте снова выбрать тренировку из дневника.",
            reply_markup=create_main_menu_keyboard()
        )
        await state.clear()
        return
    
    # Парсим новое описание тренировки через ИИ
    processing = await message.answer("⏳ Обрабатываю новое описание тренировки...")
    
    try:
        parsed = await parse_workout_text(message.text)
        
        try:
            await processing.delete()
        except:
            pass
        
        # Получаем текущие сессии пользователя
        user_id = message.from_user.id
        sessions = await get_user_workout_sessions(user_id)
        
        if workout_number > len(sessions):
            await message.answer(
                f"❌ Тренировка #{workout_number} не найдена.",
                reply_markup=create_main_menu_keyboard()
            )
            await state.clear()
            return
        
        # Обновляем тренировку
        session_to_update = sessions[workout_number - 1]
        await update_workout_session(
            session_id=session_to_update.session_id,
            exercises=parsed.exercises,
            notes=parsed.notes
        )
        
        await message.answer(
            f"✅ Тренировка #{workout_number} от {session_to_update.session_date.strftime('%d.%m.%Y')} успешно обновлена!\n\n"
            f"{format_workout_result(parsed)}",
            reply_markup=create_main_menu_keyboard()
        )
        
    except Exception as e:
        try:
            await processing.delete()
        except:
            pass
        await message.answer(f"❌ Ошибка при обновлении: {str(e)}")
    
    await state.clear()