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


async def parse_workout_text(text: str) -> WorkoutParseResult:
    """
    Отправляет текст пользователя в Gemini API для парсинга структуры тренировки.
    
    Использует структурированный вывод (Response Schema) для гарантированного
    возврата валидного JSON согласно Pydantic схеме.
    
    Args:
        text: Текст описания тренировки от пользователя
        
    Returns:
        WorkoutParseResult: Структурированные данные о тренировке
    """
    client = get_gemini_client()
    
    # Формируем промпт для модели
    prompt = """
Ты — помощник для анализа спортивных тренировок. 
Пользователь отправит тебе описание своей тренировки в свободной форме.
Твоя задача:
1. Извлечь дату тренировки (если не указана, используй текущую дату в формате YYYY-MM-DD)
2. Распознать все выполненные упражнения с параметрами: название, вес, подходы, повторения
3. Выделить заметки пользователя о самочувствии (если есть)
4. Сформулировать краткую рекомендацию для улучшения следующих тренировок

Отвечай ТОЛЬКО в формате JSON согласно предоставленной схеме. Не добавляй никаких пояснений вне JSON.

Текст тренировки пользователя:
{text}
""".format(text=text)
    
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