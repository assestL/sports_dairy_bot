"""
Сервис для работы с Google Gemini API.
"""
import os
from typing import List, Optional
from google import genai
from pydantic import BaseModel, Field, field_validator


class Exercise(BaseModel):
    name: str = Field(description="Название упражнения")
    weight: float = Field(description="Вес снаряда в кг")
    reps: List[int] = Field(
        description=(
            "СПИСОК повторений для КАЖДОГО подхода.\n"
            "Например: [20,20,20,20,20] или [20,20,20,30]"
        )
    )

    @field_validator('name')
    @classmethod
    def normalize_exercise_name(cls, v: str) -> str:
        return v.strip().lower().replace("ё", "е")


class WorkoutSession(BaseModel):
    date: str = Field(description="Дата тренировки в формате YYYY-MM-DD")
    exercises: List[Exercise] = Field(description="Список выполненных упражнений")
    wellness_notes: Optional[str] = Field(default=None, description="Заметки по самочувствию")
    recommendation: Optional[str] = Field(default=None, description="Краткая рекомендация от AI")


class WorkoutParseResult(BaseModel):
    sessions: List[WorkoutSession] = Field(description="Список тренировочных сессий")


class AnalyticsIntent(BaseModel):
    exercise_name: str = Field(description="Название упражнения для анализа")
    period_days: int = Field(default=30, description="Количество дней для анализа")
    start_date: Optional[str] = Field(default=None, description="Начальная дата (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default=None, description="Конечная дата (YYYY-MM-DD)")
    analysis_type: str = Field(
        default="chart",
        description="Тип ответа: 'chart' (график) или 'advice' (текстовый анализ с советом)"
    )

    @field_validator('exercise_name')
    @classmethod
    def normalize_exercise_name(cls, v: str) -> str:
        return v.strip().lower()


class UserIntent(BaseModel):
    intent_type: str = Field(description="Тип: 'workout', 'analytics', 'other'")
    workout_data: Optional[WorkoutParseResult] = Field(default=None)
    analytics_data: Optional[AnalyticsIntent] = Field(default=None)


_gemini_client: Optional[genai.Client] = None


def get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY не установлена.")
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


async def parse_workout_text(text: str, telegram_date: str = None, is_edit: bool = False, existing_date: str = None) -> WorkoutParseResult:
    client = get_gemini_client()

    if is_edit and existing_date:
        prompt = f"""
Ты редактируешь существующую тренировку от {existing_date}.
НЕ создавай новую тренировку. Используй ТОЛЬКО дату {existing_date}.
Верни JSON строго по схеме.
Для КАЖДОГО подхода создай отдельное значение в reps.
Дата: {existing_date}
Текст: {text}
"""
    else:
        prompt = f"""
Проанализируй текст тренировки.
Верни JSON строго по схеме.
Все даты <= telegram_date.
"вчера", "позавчера" вычисляй относительно telegram_date.
Для КАЖДОГО подхода создай отдельное значение в reps.
Дата: {telegram_date or "сегодня"}
Текст: {text}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": WorkoutParseResult,
        },
    )
    return WorkoutParseResult.model_validate_json(response.text)


async def determine_user_intent(text: str, telegram_date: str = None) -> UserIntent:
    client = get_gemini_client()
    prompt = f"""
Ты — помощник для определения намерений в спортивном дневнике.

1️⃣ 'workout' — описание тренировки (упражнения, веса, подходы).
Примеры: "жим 80кг 3х10", "вчера 200 отжиманий", "присед 100кг 4х8".

2️⃣ 'analytics' — запрос аналитики/прогресса.
Определи analysis_type:
- "chart" — если просят график/визуализацию ("покажи прогресс", "график").
- "advice" — если просят анализ/совет/статистику ("проанализируй", "дай совет").
Примеры: "Покажи прогресс в жиме", "Проанализируй отжимания за месяц".

3️⃣ 'other' — всё остальное.

Отвечай ТОЛЬКО JSON по схеме UserIntent.
Дата: {telegram_date or "сегодня"}
Текст: {text}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": UserIntent,
        },
    )
    return UserIntent.model_validate_json(response.text)


async def extract_analytics_intent(text: str) -> AnalyticsIntent:
    client = get_gemini_client()
    prompt = f"""
Извлеки намерение для аналитики.
1. Название упражнения
2. Период (если нет — 30 дней)
3. analysis_type: "chart" если просят график, "advice" если просят анализ/совет.
Отвечай ТОЛЬКО JSON.
Текст: {text}
"""
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": AnalyticsIntent,
        },
    )
    return AnalyticsIntent.model_validate_json(response.text)


async def generate_session_advice(wellness_notes: str, exercises_summary: str) -> str:
    """Совет на основе самочувствия и упражнений."""
    client = get_gemini_client()
    prompt = f"""
Ты — AI-тренер. Пользователь записал тренировку.
Самочувствие: "{wellness_notes or 'Нет заметок'}"
Упражнения: {exercises_summary}

Дай короткий совет (1-2 предложения).
Если самочувствие хорошее — похвали.
Если плохое — посоветуй восстановление.
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text.strip()


async def generate_period_analytics(
    period_desc: str,
    stats_text: str,
    notes_summary: str,
    first_value: float,
    last_value: float,
    avg_change_percent: float,
    total_sessions: int
) -> str:
    """Аналитика и совет за период."""
    client = get_gemini_client()

    if last_value > first_value:
        change_desc = f"прирост +{last_value - first_value:.0f} ({((last_value / first_value - 1) * 100):.1f}%)"
    elif last_value < first_value:
        change_desc = f"снижение -{first_value - last_value:.0f} ({((1 - last_value / first_value) * 100):.1f}%)"
    else:
        change_desc = "без изменений (0%)"

    prompt = f"""
Ты — AI-тренер. Проанализируй тренировки за период: {period_desc}

📊 МЕТРИКИ:
• Первая: {first_value:.0f}, Последняя: {last_value:.0f}
• Изменение: {change_desc}
• Средний темп: {avg_change_percent:+.1f}% за сессию
• Всего тренировок: {total_sessions}

📈 ДИНАМИКА:
{stats_text}

💬 ЗАМЕТКИ: {notes_summary or "Нет"}

Сформируй 3 абзаца:
1️⃣ Результат с % изменения
2️⃣ Контекст (связь с самочувствием)
3️⃣ Конкретный совет

Используй эмодзи 📈📉✅⚠️.
"""
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    return response.text.strip()