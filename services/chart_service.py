"""
Сервис для построения графиков прогресса упражнений.
Использует Seaborn и Matplotlib для визуализации данных.
"""

import io
from datetime import datetime, timedelta
from typing import List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from aiogram.types import BufferedInputFile
from sqlalchemy import and_, func, select

from database.connection import get_session_sync
from database.models import WorkoutDetail, WorkoutSession


def get_workout_history(telegram_id: int, exercise_name: str, days: int) -> List[Tuple[datetime, float]]:
    """
    Получает историю тренировок пользователя по указанному упражнению за период.
    
    Делает JOIN-запрос между таблицами WorkoutSession и WorkoutDetail,
    фильтрует по пользователю, упражнению и временному периоду.
    
    Args:
        telegram_id: Telegram ID пользователя
        exercise_name: Название упражнения для анализа
        days: Количество дней для анализа
        
    Returns:
        Список кортежей (дата, максимальный_вес) отсортированных по дате
    """
    session = get_session_sync()
    try:
        # Вычисляем дату начала периода
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Строим запрос с JOIN между WorkoutSession и WorkoutDetail
        # Используем subquery для получения максимального веса по каждой дате
        query = (
            select(
                WorkoutSession.session_date,
                func.max(WorkoutDetail.weight).label("max_weight")
            )
            .join(
                WorkoutDetail,
                WorkoutDetail.session_id == WorkoutSession.session_id
            )
            .where(
                and_(
                    WorkoutSession.telegram_id == telegram_id,
                    WorkoutDetail.exercise_name.ilike(f"%{exercise_name}%"),
                    WorkoutSession.session_date >= start_date,
                    WorkoutSession.session_date <= end_date
                )
            )
            .group_by(WorkoutSession.session_date)
            .order_by(WorkoutSession.session_date)
        )
        
        result = session.execute(query).all()
        
        # Преобразуем результат в список кортежей (datetime, float)
        history = [(row.session_date, float(row.max_weight)) for row in result]
        
        return history
    finally:
        session.close()


def render_exercise_chart(history_data: List[Tuple[datetime, float]], exercise_name: str) -> BufferedInputFile:
    """
    Создает график прогресса упражнения и возвращает его как BufferedInputFile.
    
    Использует Seaborn для современной визуализации с сеткой, точками и линией тренда.
    График сохраняется в памяти (BytesIO) без записи на диск.
    
    Args:
        history_data: Список кортежей (дата, вес) для отображения
        exercise_name: Название упражнения для заголовка графика
        
    Returns:
        BufferedInputFile: Готовый к отправке файл графика
    """
    # Настраиваем тему Seaborn
    sns.set_theme(style="darkgrid")
    
    # Создаем фигуру и оси
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Извлекаем данные для графика
    dates = [item[0] for item in history_data]
    weights = [item[1] for item in history_data]
    
    # Преобразуем даты в формат для matplotlib
    date_numbers = np.arange(len(dates))
    
    # Определяем цвет из палитры Seaborn
    palette = sns.color_palette("muted")
    primary_color = palette[0]
    trend_color = palette[1]
    
    # Рисуем точки с данными
    ax.scatter(date_numbers, weights, color=primary_color, s=80, zorder=3, label="Результаты")
    
    # Рисуем линию, соединяющую точки
    ax.plot(date_numbers, weights, color=primary_color, linewidth=2, zorder=2)
    
    # Добавляем линию тренда (полиномиальная аппроксимация)
    if len(dates) >= 2:
        # Вычисляем коэффициенты полинома первой степени (линейный тренд)
        z = np.polyfit(date_numbers, weights, 1)
        p = np.poly1d(z)
        
        # Рисуем линию тренда
        ax.plot(
            date_numbers,
            p(date_numbers),
            "--",
            color=trend_color,
            linewidth=2,
            alpha=0.7,
            label="Тренд"
        )
    
    # Настраиваем ось X с датами
    ax.set_xticks(date_numbers)
    # Форматируем даты для отображения (день.месяц)
    date_labels = [d.strftime("%d.%m") if hasattr(d, 'strftime') else str(d) for d in dates]
    ax.set_xticklabels(date_labels, rotation=45, ha='right')
    
    # Подписи осей и заголовок
    ax.set_xlabel("Дата тренировки", fontsize=12)
    ax.set_ylabel("Вес (кг)", fontsize=12)
    ax.set_title(f"Прогресс в упражнении: {exercise_name}", fontsize=14, fontweight='bold')
    
    # Добавляем легенду
    ax.legend(loc='upper left')
    
    # Убираем лишние отступы
    plt.tight_layout()
    
    # Сохраняем график в BytesIO (память)
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=150, bbox_inches='tight')
    buffer.seek(0)
    
    # Закрываем фигуру для освобождения памяти
    plt.close(fig)
    
    # Возвращаем как BufferedInputFile для aiogram
    return BufferedInputFile(
        file=buffer.read(),
        filename=f"progress_{exercise_name}.png"
    )