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