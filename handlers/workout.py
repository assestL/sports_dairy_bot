"""
Модуль обработчиков для записи тренировок.
Содержит хэндлеры для обработки текстовых сообщений и кнопок подтверждения.
"""

from datetime import date, timezone, timedelta
from typing import Union

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.crud import save_workout
from services.gemini_service import parse_workout_text, WorkoutParseResult, determine_user_intent, AnalyticsIntent
from utils.states import WorkoutStates
from handlers.analytics import create_main_menu_keyboard
from services.chart_service import get_workout_history, render_exercise_chart

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
    Форматирует распарсенные данные тренировок в красивое сообщение.
    
    Args:
        parsed_data: Распарсенные данные тренировок (список сессий)
        
    Returns:
        Отформатированный текст для отправки пользователю
    """
    if not parsed_data.sessions:
        return "⚠️ Не удалось распознать ни одной тренировки.\nПожалуйста, опишите подробнее."
    
    result_text = ""
    
    # Обрабатываем каждую сессию отдельно
    for session_idx, session in enumerate(parsed_data.sessions, 1):
        # Преобразуем дату в читаемый формат
        workout_date = session.date
        if isinstance(workout_date, str):
            try:
                workout_date = date.fromisoformat(workout_date)
            except ValueError:
                pass
        
        # Добавляем разделитель между сессиями
        if session_idx > 1:
            result_text += "\n" + "─" * 30 + "\n\n"
        
        # Формируем заголовок с датой
        result_text += f"📅 <b>Тренировка за {workout_date}</b>\n\n"
        
        # Добавляем список упражнений
        result_text += "<b>Упражнения:</b>\n"
        for i, exercise in enumerate(session.exercises, 1):
            result_text += (
                f"{i}. <b>{exercise.name}</b> - "
                f"{exercise.weight}кг × {exercise.reps} ({exercise.sets} подхода)\n"
            )
        
        # Добавляем заметки о самочувствии, если они есть
        if session.wellness_notes:
            result_text += f"\n💭 <b>Заметки:</b>\n<i>{session.wellness_notes}</i>\n"
    
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
async def handle_user_message(message: types.Message, state: FSMContext) -> None:
    """
    Универсальный обработчик текстовых сообщений.
    
    Использует ИИ для определения намерения пользователя:
    - Запись тренировки (workout)
    - Запрос аналитики (analytics)
    - Другое (other)
    
    ВАЖНО: Этот хэндлер обрабатывает ТОЛЬКО обычные текстовые сообщения.
    Команды (начинающиеся с /) обрабатываются отдельно через Command фильтр.
    Кнопки меню обрабатываются отдельными хэндлерами через F.text == "..."
    """
    # Получаем дату сообщения в часовом поясе МСК
    # Telegram хранит дату в UTC, конвертируем в MSK (UTC+3)
    msg_date = message.date
    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=timezone.utc)
    
    # Конвертируем в московское время (UTC+3)
    msk_date = msg_date.astimezone(timezone.utc).date()
    
    # Формируем дату в формате ISO для передачи в Gemini
    telegram_date_str = msk_date.isoformat()
    
    text = message.text
    
    # Отправляем сообщение о начале анализа
    processing_message = await message.answer("⏳ Анализирую ваш запрос...")
    
    try:
        # Определяем намерение пользователя через Gemini API
        intent = await determine_user_intent(text, telegram_date_str)
        
        if intent.intent_type == 'workout':
            # Это запись тренировки
            await processing_message.delete()
            await process_parsed_workout(message, intent.workout_data, state)
            
        elif intent.intent_type == 'analytics':
            # Это запрос аналитики
            await processing_message.delete()
            await handle_analytics_intent(message, intent.analytics_data)
            
        else:
            # Неизвестное намерение - предлагаем записать тренировку или показать помощь
            await processing_message.delete()
            await message.answer(
                "🤔 Я не совсем понял ваш запрос.\n\n"
                "Вы можете:\n"
                "• 📝 Описать тренировку: <i>\"Жим лежа 80кг 3х10\"</i>\n"
                "• 📈 Узнать прогресс: <i>\"Покажи прогресс в приседаниях\"</i>\n"
                "• 📊 Посмотреть упражнения: нажмите кнопку «Мои упражнения»\n\n"
                "Или выберите действие в меню ниже.",
                reply_markup=create_main_menu_keyboard(),
                parse_mode="HTML"
            )
        
    except Exception as e:
        # Обрабатываем ошибки
        await processing_message.delete()
        await message.answer(
            f"❌ Произошла ошибка при анализе: {str(e)}\n\n"
            "Пожалуйста, попробуйте описать подробнее или используйте кнопки меню.",
            reply_markup=create_main_menu_keyboard()
        )


async def handle_analytics_intent(message: types.Message, intent: AnalyticsIntent):
    """
    Обрабатывает намерение аналитики - строит график прогресса.
    
    Args:
        message: Сообщение от пользователя
        intent: Извлеченное намерение аналитики
    """
    telegram_id = message.from_user.id
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


@router.callback_query(F.data == "workout_confirm")
async def confirm_workout(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Обработчик нажатия кнопки "Сохранить".
    
    Сохраняет ВСЕ тренировочные сессии в базу данных и показывает AI-рекомендацию.
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
        # Сохраняем все сессии в БД (функция сама обработает список sessions)
        saved_session = save_workout(
            telegram_id=callback.from_user.id,
            parsed_data=parsed_data
        )
        
        # Формируем сообщение с рекомендацией от ИИ (берем из всех сессий или объединяем)
        recommendations = [s.recommendation for s in parsed_data.sessions if s.recommendation]
        if recommendations:
            recommendation_text = "\n\n".join(recommendations)
        else:
            recommendation_text = "Отличная работа! Продолжайте в том же духе."
        
        final_message = (
            f"✅ <b>Сохранено тренировок: {len(parsed_data.sessions)}</b>\n\n"
            f"🤖 <b>Рекомендация AI-тренера:</b>\n"
            f"<i>{recommendation_text}</i>"
        )
        
        # Отправляем сообщение с рекомендацией
        await callback.message.answer(
            text=final_message,
            parse_mode="HTML"
        )
        
    except Exception as e:
        # Обрабатываем ошибки сохранения
        await callback.message.answer(
            f"❌ Ошибка при сохранении: {str(e)}\n\n"
            "Пожалуйста, попробуйте позже.",
            reply_markup=create_main_menu_keyboard()
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
        "Если хотите записать тренировку, просто отправьте текст с описанием.",
        reply_markup=create_main_menu_keyboard()
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
            "Пожалуйста, отправьте описание тренировки заново.",
            reply_markup=create_main_menu_keyboard()
        )
        await state.clear()
        return
    
    # Восстанавливаем оригинальные данные
    original_data = WorkoutParseResult(**workout_data)
    
    # Получаем дату сообщения для передачи в Gemini
    msg_date = message.date
    if msg_date.tzinfo is None:
        msg_date = msg_date.replace(tzinfo=timezone.utc)
    msk_date = msg_date.astimezone(timezone.utc).date()
    telegram_date_str = msk_date.isoformat()
    
    # Формируем объединенный текст: оригинал + исправление
    # Собираем информацию о всех сессиях
    sessions_info = []
    for session in original_data.sessions:
        session_date = session.date
        if isinstance(session_date, str):
            session_date = session_date
        exercises_str = ", ".join([f"{e.name} ({e.weight}кг {e.sets}x{e.reps})" for e in session.exercises])
        sessions_info.append(f"Дата: {session_date}, Упражнения: {exercises_str}")
    
    combined_text = (
        f"ИСХОДНЫЕ ДАННЫЕ:\n"
        f"{'; '.join(sessions_info)}\n"
        f"Заметки: {original_data.sessions[0].wellness_notes if original_data.sessions and original_data.sessions[0].wellness_notes else 'нет'}\n\n"
        f"ИСПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯ: {message.text}"
    )
    
    # Отправляем сообщение о начале анализа
    processing_message = await message.answer("⏳ Применяю исправления и анализирую...")
    
    try:
        # Повторно парсим объединенный текст с датой из Telegram
        parsed_data = await parse_workout_text(combined_text, telegram_date_str)
        
        # Обрабатываем и показываем новые результаты
        await process_parsed_workout(message, parsed_data, state, is_edit=True)
        
    except Exception as e:
        # Обрабатываем ошибки парсинга
        await message.answer(
            f"❌ Произошла ошибка при применении исправлений: {str(e)}\n\n"
            "Пожалуйста, попробуйте описать исправление подробнее.",
            reply_markup=create_main_menu_keyboard()
        )
    finally:
        # Удаляем сообщение "Применяю исправления..."
        try:
            await processing_message.delete()
        except Exception:
            pass
    
    # Очищаем состояние (будет установлено заново в process_parsed_workout)
    await state.clear()