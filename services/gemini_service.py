"""
Сервис для работы с Google Gemini API.
Используется для парсинга текста тренировок и получения рекомендаций.
"""

import os
from datetime import date
from typing import List, Optional

from google import genai
from pydantic import BaseModel, Field


class Exercise(BaseModel):
    """Модель упражнения в тренировке."""
    
    name: str = Field(description="Название упражнения")
    weight: float = Field(description="Вес снаряда в кг")
    sets: int = Field(description="Количество подходов")
    reps: int = Field(description="Количество повторений в подходе")


class WorkoutParseResult(BaseModel):
    """Результат парсинга текста тренировки через Gemini."""
    
    workout_date: str | date = Field(description="Дата тренировки (строка или дата)")
    exercises: List[Exercise] = Field(description="Список выполненных упражнений")
    wellness_notes: Optional[str] = Field(default=None, description="Заметки по самочувствию пользователя")
    recommendation: str = Field(description="Краткая рекомендация от AI тренера")


class AnalyticsIntent(BaseModel):
    """Модель намерения пользователя для аналитики."""
    
    exercise_name: str = Field(description="Название упражнения для анализа")
    period_days: int = Field(default=30, description="Количество дней для анализа")


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


async def parse_workout_text(text: str, telegram_date: str = None) -> WorkoutParseResult:
    """
    Отправляет текст пользователя в Gemini API для парсинга структуры тренировки.
    
    Использует структурированный вывод (Response Schema) для гарантированного
    возврата валидного JSON согласно Pydantic схеме.
    
    Поддерживает описание нескольких тренировок в одном сообщении.
    ИИ автоматически распознает даты и создаст отдельные записи для каждой тренировки.
    
    Args:
        text: Текст описания тренировки(ок) от пользователя
        telegram_date: Дата сообщения Telegram в формате YYYY-MM-DD (используется по умолчанию, если в тексте не указана дата)
        
    Returns:
        WorkoutParseResult: Структурированные данные о тренировке (если несколько тренировок - объединяет упражнения)
    """
    client = get_gemini_client()
    
    # Формируем промпт для модели
    prompt = """
Ты — помощник для анализа спортивных тренировок. 
Пользователь отправит тебе описание своих тренировок в свободной форме.
В одном сообщении может быть описание НЕСКОЛЬКИХ тренировок за разные дни.

Твоя задача:
1. Извлечь дату(ы) тренировки из текста. Если дата не указана для конкретной тренировки, ИСПОЛЬЗУЙ дату из параметра telegram_date ({telegram_date})
2. Распознать все выполненные упражнения с параметрами: название, вес, подходы, повторения
3. Выделить заметки пользователя о самочувствии (если есть)
4. Сформулировать краткую рекомендацию для улучшения следующих тренировок

ВАЖНО: Если в сообщении описаны тренировки за несколько разных дней, 
объедини ВСЕ упражнения из всех тренировок в один список exercises.
Для workout_date используй самую раннюю дату из найденных в тексте, или telegram_date если дат нет.

Отвечай ТОЛЬКО в формате JSON согласно предоставленной схеме. Не добавляй никаких пояснений вне JSON.

Дата сообщения Telegram (используй как дату тренировки по умолчанию): {telegram_date}

Текст тренировки пользователя:
{text}
""".format(text=text, telegram_date=telegram_date or "сегодня")
    
    # Используем генерацию с Response Schema для строгой валидации
    response = client.models.generate_content(
        model="gemini-2.0-flash",  # Современная быстрая модель
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
2. Запрос аналитики (например: "Покажи прогресс в жиме лежа за 2 месяца", "Как там мои приседания?")
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
   - ВАЖНО: Если описаны тренировки за несколько дней, объедини ВСЕ упражнения в один список

3. Если intent_type='analytics':
   - Определить название упражнения
   - Определить период анализа (по умолчанию 30 дней)

4. Если intent_type='other':
   - Оставь workout_data и analytics_data пустыми (null)

Отвечай ТОЛЬКО в формате JSON согласно предоставленной схеме UserIntent.

Дата сообщения Telegram: {telegram_date}

Сообщение пользователя:
{text}
""".format(text=text, telegram_date=telegram_date or "сегодня")
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
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
        model="gemini-2.0-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": AnalyticsIntent,
        },
    )
    
    result = AnalyticsIntent.model_validate_json(response.text)
    
    return result