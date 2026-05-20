"""
Модуль обработчиков для записи тренировок.
Содержит хэндлеры для обработки текстовых сообщений и кнопок подтверждения.
"""

from datetime import date
from typing import Union

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.crud import save_workout
from services.gemini_service import parse_workout_text, WorkoutParseResult
from utils.states import WorkoutStates

# Создаем роутер для регистрации хэндлеров
router = Router()


def create_confirmation_keyboard() -> types.InlineKeyboardMarkup:
    """
    Создает inline-клавиатуру с кнопками подтверждения тренировки.
    
    Returns:
        InlineKeyboardMarkup с кнопками: Сохранить, Редактировать, Отмена
    """
    builder = InlineKeyboardBuilder()
    
    # Кнопка "Сохранить" - callback_data для сохранения тренировки
    builder.button(text="✅ Сохранить", callback_data="workout_confirm")
    # Кнопка "Редактировать" - callback_data для редактирования
    builder.button(text="✏️ Редактировать", callback_data="workout_edit")
    # Кнопка "Отмена" - callback_data для отмены
    builder.button(text="❌ Отмена", callback_data="workout_cancel")
    
    # Располагаем кнопки в один ряд
    builder.adjust(1, 1, 1)
    
    return builder.as_markup()


def format_workout_result(parsed_data: WorkoutParseResult) -> str:
    """
    Форматирует распарсенные данные тренировки в красивое сообщение.
    
    Args:
        parsed_data: Распарсенные данные тренировки
        
    Returns:
        Отформатированный текст для отправки пользователю
    """
    # Преобразуем дату в читаемый формат
    workout_date = parsed_data.workout_date
    if isinstance(workout_date, str):
        try:
            workout_date = date.fromisoformat(workout_date)
        except ValueError:
            pass
    
    # Формируем заголовок с датой
    result_text = f"📅 <b>Тренировка за {workout_date}</b>\n\n"
    
    # Добавляем список упражнений
    result_text += "<b>Упражнения:</b>\n"
    for i, exercise in enumerate(parsed_data.exercises, 1):
        result_text += (
            f"{i}. <b>{exercise.name}</b> - "
            f"{exercise.weight}кг × {exercise.reps} ({exercise.sets} подхода)\n"
        )
    
    # Добавляем заметки о самочувствии, если они есть
    if parsed_data.wellness_notes:
        result_text += f"\n💭 <b>Заметки:</b>\n<i>{parsed_data.wellness_notes}</i>\n"
    
    return result_text


async def process_parsed_workout(
    message: Union[types.Message, types.CallbackQuery],
    parsed_data: WorkoutParseResult,
    state: FSMContext,
    is_edit: bool = False
) -> None:
    """
    Обрабатывает распарсенные данные тренировки и отправляет результат пользователю.
    
    Args:
        message: Сообщение или callback query для ответа
        parsed_data: Распарсенные данные тренировки
        state: Состояние FSM для хранения временных данных
        is_edit: Флаг, указывающий на редактирование (True) или новую запись (False)
    """
    # Форматируем результат
    result_text = format_workout_result(parsed_data)
    
    # Сохраняем распарсенные данные в FSM storage для последующего использования
    await state.update_data(workout_data=parsed_data.model_dump())
    
    # Определяем метод для отправки сообщения
    if isinstance(message, types.CallbackQuery):
        send_method = message.message.edit_text
    else:
        send_method = message.answer
    
    # Отправляем сообщение с результатами и кнопками подтверждения
    await send_method(
        text=result_text,
        reply_markup=create_confirmation_keyboard(),
        parse_mode="HTML"
    )


@router.message(F.text)
async def handle_workout_text(message: types.Message, state: FSMContext) -> None:
    """
    Обработчик текстовых сообщений для записи тренировки.
    
    Принимает текст тренировки, отправляет на парсинг в Gemini API
    и показывает результаты с кнопками подтверждения.
    """
    # Отправляем сообщение о начале анализа
    processing_message = await message.answer("⏳ Анализирую тренировку...")
    
    try:
        # Парсим текст тренировки через Gemini API
        parsed_data = await parse_workout_text(message.text)
        
        # Обрабатываем и показываем результаты
        await process_parsed_workout(message, parsed_data, state)
        
    except Exception as e:
        # Обрабатываем ошибки парсинга
        await message.answer(
            f"❌ Произошла ошибка при анализе тренировки: {str(e)}\n\n"
            "Пожалуйста, попробуйте описать тренировку подробнее."
        )
    finally:
        # Удаляем сообщение "Анализирую..."
        try:
            await processing_message.delete()
        except Exception:
            pass


@router.callback_query(F.data == "workout_confirm")
async def confirm_workout(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Обработчик нажатия кнопки "Сохранить".
    
    Сохраняет тренировку в базу данных и показывает AI-рекомендацию.
    """
    # Получаем сохраненные данные из FSM storage
    data = await state.get_data()
    workout_data = data.get("workout_data")
    
    if not workout_data:
        await callback.answer("❌ Данные тренировки не найдены. Попробуйте снова.", show_alert=True)
        return
    
    # Восстанавливаем объект WorkoutParseResult из словаря
    parsed_data = WorkoutParseResult(**workout_data)
    
    # Отправляем сообщение о сохранении
    await callback.message.edit_text(
        text=f"{callback.message.text}\n\n💾 Сохраняю в базу данных...",
        reply_markup=None,
        parse_mode="HTML"
    )
    
    try:
        # Сохраняем тренировку в БД
        session = save_workout(
            telegram_id=callback.from_user.id,
            parsed_data=parsed_data
        )
        
        # Формируем сообщение с рекомендацией от ИИ
        recommendation_text = (
            "✅ <b>Тренировка успешно сохранена!</b>\n\n"
            f"🤖 <b>Рекомендация AI-тренера:</b>\n"
            f"<i>{parsed_data.recommendation}</i>"
        )
        
        # Отправляем сообщение с рекомендацией
        await callback.message.answer(
            text=recommendation_text,
            parse_mode="HTML"
        )
        
    except Exception as e:
        # Обрабатываем ошибки сохранения
        await callback.message.answer(
            f"❌ Ошибка при сохранении: {str(e)}\n\n"
            "Пожалуйста, попробуйте позже."
        )
    finally:
        # Очищаем состояние FSM
        await state.clear()


@router.callback_query(F.data == "workout_edit")
async def edit_workout(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Обработчик нажатия кнопки "Редактировать".
    
    Переводит бота в состояние ожидания исправлений от пользователя.
    """
    # Переводим в состояние ожидания исправлений
    await state.set_state(WorkoutStates.waiting_for_correction)
    
    # Сохраняем оригинальный текст сообщения для последующего редактирования
    # (в реальном проекте можно хранить историю сообщений)
    await state.update_data(original_message_id=callback.message.message_id)
    
    # Отправляем инструкцию пользователю
    await callback.message.answer(
        "✏️ <b>Редактирование тренировки</b>\n\n"
        "Напишите, что нужно исправить в распознанной тренировке.\n"
        "Например: <i>\"Изменить вес в жиме лежа на 85кг\"</i>\n\n"
        "Я объединю ваше исправление с исходными данными и покажу новый результат.",
        parse_mode="HTML"
    )
    
    # Убираем клавиатуру из предыдущего сообщения
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Отвечаем на callback
    await callback.answer()


@router.callback_query(F.data == "workout_cancel")
async def cancel_workout(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Обработчик нажатия кнопки "Отмена".
    
    Отменяет запись тренировки и очищает состояние FSM.
    """
    # Очищаем состояние FSM
    await state.clear()
    
    # Отправляем сообщение об отмене
    await callback.message.answer(
        "🚫 Запись тренировки отменена.\n\n"
        "Если хотите записать тренировку, просто отправьте текст с описанием."
    )
    
    # Убираем клавиатуру из предыдущего сообщения
    await callback.message.edit_reply_markup(reply_markup=None)
    
    # Отвечаем на callback
    await callback.answer()


@router.message(WorkoutStates.waiting_for_correction)
async def handle_correction(message: types.Message, state: FSMContext) -> None:
    """
    Обработчик состояния ожидания исправлений.
    
    Получает текст исправления, объединяет с исходными данными
    и повторно запускает парсинг.
    """
    # Получаем сохраненные данные из FSM storage
    data = await state.get_data()
    workout_data = data.get("workout_data")
    
    if not workout_data:
        await message.answer(
            "❌ Данные тренировки не найдены.\n"
            "Пожалуйста, отправьте описание тренировки заново."
        )
        await state.clear()
        return
    
    # Восстанавливаем оригинальные данные
    original_data = WorkoutParseResult(**workout_data)
    
    # Формируем объединенный текст: оригинал + исправление
    # В реальном проекте можно использовать более умную логику объединения
    combined_text = (
        f"{original_data.workout_date}\n"
        f"Упражнения: {[e.name for e in original_data.exercises]}\n"
        f"Заметки: {original_data.wellness_notes or 'нет'}\n\n"
        f"ИСПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ: {message.text}"
    )
    
    # Отправляем сообщение о начале анализа
    processing_message = await message.answer("⏳ Применяю исправления и анализирую...")
    
    try:
        # Повторно парсим объединенный текст
        parsed_data = await parse_workout_text(combined_text)
        
        # Обрабатываем и показываем новые результаты
        await process_parsed_workout(message, parsed_data, state, is_edit=True)
        
    except Exception as e:
        # Обрабатываем ошибки парсинга
        await message.answer(
            f"❌ Произошла ошибка при применении исправлений: {str(e)}\n\n"
            "Пожалуйста, попробуйте описать исправление подробнее."
        )
    finally:
        # Удаляем сообщение "Применяю исправления..."
        try:
            await processing_message.delete()
        except Exception:
            pass
    
    # Очищаем состояние (будет установлено заново в process_parsed_workout)
    await state.clear()