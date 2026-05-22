"""
Сервис для работы с Google Gemini API.
Используется для парсинга текста тренировок и получения рекомендаций.
"""

import os
from typing import List, Optional, Union
from datetime import date

from google import genai
from pydantic import BaseModel, Field, field_validator


class Exercise(BaseModel):
    """Модель упражнения в тренировке."""

    name: str = Field(
        description="Название упражнения"
    )

    weight: float = Field(
        description="Вес снаряда в кг"
    )

    reps: List[int] = Field(
        description=(
            "СПИСОК повторений для КАЖДОГО подхода.\n"
            "Например:\n"
            "[20,20,20,20,20]\n"
            "или:\n"
            "[20,20,20,30]"
        )
    )

    @field_validator('name')
    @classmethod
    def normalize_exercise_name(cls, v: str) -> str:
        return (
            v.strip()
            .lower()
            .replace("ё", "е")
        )


class WorkoutSession(BaseModel):
    """Модель одной тренировочной сессии (один день)."""

    date: str = Field(description="Дата тренировки в формате YYYY-MM-DD")
    exercises: List[Exercise] = Field(description="Список выполненных упражнений в этот день")
    wellness_notes: Optional[str] = Field(default=None, description="Заметки по самочувствию пользователя")
    recommendation: Optional[str] = Field(default=None, description="Краткая рекомендация от AI тренера для этой сессии")


class WorkoutParseResult(BaseModel):
    """Результат парсинга текста тренировок через Gemini."""

    sessions: List[WorkoutSession] = Field(description="Список тренировочных сессий (по одной на каждый день)")


class AnalyticsIntent(BaseModel):
    """Модель намерения пользователя для аналитики."""

    exercise_name: str = Field(description="Название упражнения для анализа")
    period_days: int = Field(default=30, description="Количество дней для анализа")
    start_date: Optional[str] = Field(default=None, description="Начальная дата периода в формате YYYY-MM-DD (если указана)")
    end_date: Optional[str] = Field(default=None, description="Конечная дата периода в формате YYYY-MM-DD (если указана)")

    @field_validator('exercise_name')
    @classmethod
    def normalize_exercise_name(cls, v: str) -> str:
        """Приводит название упражнения к нижнему регистру для единообразия поиска в БД."""
        return v.strip().lower()


class UserIntent(BaseModel):
    """Модель для определения общего намерения пользователя."""

    intent_type: str = Field(description="Тип намерения: 'workout' (запись тренировки), 'analytics' (аналитика/прогресс), 'other' (другое)")
    workout_data: Optional[WorkoutParseResult] = Field(default=None, description="Данные тренировки, если intent_type='workout'")
    analytics_data: Optional[AnalyticsIntent] = Field(default=None, description="Данные аналитики, если intent_type='analytics'")


# Инициализация клиента Gemini
_gemini_client: Optional[genai.Client] = None


def get_gemini_client() -> genai.Client:
    """Получает клиент Gemini API, используя ключ из переменных окружения."""
    global _gemini_client

    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "Переменная окружения GEMINI_API_KEY не установлена. "
                "Проверьте файл .env или настройки окружения."
            )
        _gemini_client = genai.Client(api_key=api_key)

    return _gemini_client


async def parse_workout_text(text: str, telegram_date: str = None, is_edit: bool = False, existing_date: str = None) -> WorkoutParseResult:
    """
    Отправляет текст пользователя в Gemini API для парсинга структуры тренировок.

    Использует структурированный вывод (Response Schema) для гарантированного
    возврата валидного JSON согласно Pydantic схеме.

    Поддерживает описание нескольких тренировок в одном сообщении.
    ИИ автоматически распознает даты и создаст отдельные сессии для каждой тренировки.

    Args:
        text: Текст описания тренировки(ок) от пользователя
        telegram_date: Дата сообщения Telegram в формате YYYY-MM-DD (используется по умолчанию, если в тексте не указана дата)
        is_edit: Если True, то это редактирование существующей тренировки (не создавать новую дату)
        existing_date: Дата редактируемой тренировки в формате YYYY-MM-DD (обязательна при is_edit=True)

    Returns:
        WorkoutParseResult: Список тренировочных сессий, сгруппированных по датам
    """
    client = get_gemini_client()

    # Формируем промпт для модели
    if is_edit and existing_date:
        prompt = f"""
        Ты редактируешь существующую тренировку пользователя от {existing_date}.
        
        Пользователь отправил новое описание для ОБНОВЛЕНИЯ этой тренировки.
        
        ВАЖНО:
        1. НЕ создавай новую тренировку.
        2. НЕ меняй дату — используй ТОЛЬКО {existing_date}.
        3. Распарси новый текст и верни данные для обновления тренировки от {existing_date}.
        4. Создай ОДНУ сессию с датой {existing_date}.
        
        Верни JSON строго по схеме.
        
        Для КАЖДОГО подхода нужно создать отдельное значение в массиве reps.
        
        ПРИМЕРЫ:
        
        Пользователь:
        "5 подходов по 20 отжиманий"
        
        Правильно:
        
        "reps": [20,20,20,20,20]
        
        НЕПРАВИЛЬНО:
        
        "reps": [20]
        
        ----------------------------------------
        
        Пользователь:
        "3 подхода по 20 и 1 подход 30"
        
        Правильно:
        
        "reps": [20,20,20,30]
        
        ----------------------------------------
        
        Пользователь:
        "жим лежа 4x10 80кг"
        
        Правильно:
        
        "reps": [10,10,10,10]
        
        weight: 80
        
        ----------------------------------------
        
        Каждый подход ОБЯЗАТЕЛЬНО должен быть отдельным элементом массива reps.
        
        НЕ сокращай подходы.
        
        НЕ используй:
        - sets
        - sets_count
        
        Только массив reps.
        
        Отвечай ТОЛЬКО JSON.
        
        Дата редактируемой тренировки:
        {existing_date}
        
        Новое описание пользователя:
        {text}
""".format(text=text, existing_date=existing_date)
    else:
        prompt = f"""
        Проанализируй текст тренировки пользователя.

        Верни JSON строго по схеме.

        ВАЖНО:

        1. Создавай отдельную тренировочную сессию для каждой даты.

        2. Никогда не создавай даты в будущем.

        3. Все даты должны быть <= telegram_date.

        4. Если пользователь пишет:
        - вчера
        - позавчера
        - в прошлый понедельник
        - на прошлой неделе

        то вычисляй дату относительно telegram_date.

        5. Для КАЖДОГО подхода нужно создать отдельное значение в массиве reps.

        ПРИМЕРЫ:

        Пользователь:
        "5 подходов по 20 отжиманий"

        Правильно:

        "reps": [20,20,20,20,20]

        НЕПРАВИЛЬНО:

        "reps": [20]

        ----------------------------------------

        Пользователь:
        "3 подхода по 20 и 1 подход 30"

        Правильно:

        "reps": [20,20,20,30]

        ----------------------------------------

        Пользователь:
        "жим лежа 4x10 80кг"

        Правильно:

        "reps": [10,10,10,10]

        weight: 80

        ----------------------------------------

        Каждый подход ОБЯЗАТЕЛЬНО должен быть отдельным элементом массива reps.

        НЕ сокращай подходы.

        НЕ используй:
        - sets
        - sets_count

        Только массив reps.

        Отвечай ТОЛЬКО JSON.

        Дата сообщения Telegram:
        {telegram_date}

        Текст пользователя:
        {text}
""".format(text=text, telegram_date=telegram_date or "сегодня")

    # Используем генерацию с Response Schema для строгой валидации
    response = client.models.generate_content(
        model="gemini-2.5-flash",  # Современная быстрая модель
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": WorkoutParseResult,
        },
    )

    # Парсим ответ через Pydantic модель для дополнительной валидации
    result = WorkoutParseResult.model_validate_json(response.text)

    return result


async def determine_user_intent(text: str, telegram_date: str = None) -> UserIntent:
    """
    Определяет общее намерение пользователя: запись тренировки, аналитика или другое.

    Эта функция анализирует текст и решает:
    - Это описание тренировки (workout)
    - Запрос аналитики/прогресса (analytics)
    - Что-то другое (other)

    Args:
        text: Текст сообщения от пользователя
        telegram_date: Дата сообщения Telegram в формате YYYY-MM-DD

    Returns:
        UserIntent: Структурированное намерение с данными тренировки или аналитики
    """
    client = get_gemini_client()

    prompt = """
Ты — помощник для определения намерений пользователя в спортивном дневнике.
Пользователь может отправить:
1. Описание тренировки (например: "Жим лежа 80кг 3х10, приседания 100кг 4х8")
2. Запрос аналитики (например: "Покажи прогресс в жиме лежа за 2 месяца", "Как там мои приседания?", "Отжимания с 14 по 17 мая 2026 года")
3. Что-то другое (приветствие, вопрос, команда)

Твоя задача:
1. Определить тип намерения:
   - 'workout' — если пользователь описывает свою тренировку (упражнения, веса, подходы, повторения)
   - 'analytics' — если пользователь запрашивает аналитику/прогресс по упражнениям
   - 'other' — всё остальное

2. Если intent_type='workout':
   - Извлечь дату(ы) тренировки. Если дата не указана, используй telegram_date ({telegram_date})
   - Распознать все упражнения с параметрами: название, вес, подходы, повторения
   - Выделить заметки о самочувствии
   - Сформулировать рекомендацию
ВАЖНО:
- Никогда не создавай даты в будущем
- Все даты должны быть <= telegram_date
- "вчера", "в прошлый понедельник" и подобные фразы
  вычисляй относительно telegram_date
- Если описаны тренировки за несколько дней —
  создай отдельную session для каждого дня
  
3. Если intent_type='analytics':
   - Определить название упражнения
   - Определить период анализа:
     * Если пользователь указал конкретные даты (например, "с 14 по 17 мая 2026 года" или "с 14 по 17 мая"),
       извлеки start_date и end_date в формате YYYY-MM-DD
     * Если указан относительный период ("за 2 месяца", "за неделю"), используй period_days
     * По умолчанию period_days = 30
   - ВАЖНО: Для дат вида "с 14 по 17 мая 2026 года" определи год:
     * Если месяц ещё не наступил в текущем году, используй текущий год
     * Если месяц уже прошёл, используй следующий год
     * Если год явно указан, используй его

4. Если intent_type='other':
   - Оставь workout_data и analytics_data пустыми (null)

Отвечай ТОЛЬКО в формате JSON согласно предоставленной схеме UserIntent.

Дата сообщения Telegram: {telegram_date}

Сообщение пользователя:
{text}
""".format(text=text, telegram_date=telegram_date or "сегодня")

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": UserIntent,
        },
    )

    result = UserIntent.model_validate_json(response.text)

    return result


async def extract_analytics_intent(text: str) -> AnalyticsIntent:
    """
    Извлекает намерение пользователя для аналитики из текстового запроса.

    Понимает запросы вроде:
    - "Покажи мой прогресс в жиме лежа за 2 месяца"
    - "Как там мои приседания?"
    - "Прогресс становой тяги за неделю"

    Args:
        text: Текстовый запрос пользователя

    Returns:
        AnalyticsIntent: Структурированное намерение с названием упражнения и периодом
    """
    client = get_gemini_client()

    prompt = """
Ты — помощник для извлечения намерений пользователя в спортивном дневнике.
Пользователь запрашивает аналитику по своим тренировкам.
Твоя задача:
1. Определить название упражнения, о котором спрашивает пользователь
2. Определить период анализа (если указан). Поддерживаются форматы: "за N дней/недель/месяцев"
   - Если период не указан, используй значение по умолчанию 30 дней
   - 1 неделя = 7 дней, 1 месяц = 30 дней
   
Отвечай ТОЛЬКО в формате JSON согласно предоставленной схеме. Не добавляй никаких пояснений вне JSON.

Запрос пользователя:
{text}
""".format(text=text)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": AnalyticsIntent,
        },
    )

    result = AnalyticsIntent.model_validate_json(response.text)

    return result