"""
Модуль состояний FSM (Finite State Machine) для бота.
Используется для управления состояниями пользователя при взаимодействии с ботом.
"""

from aiogram.fsm.state import State, StatesGroup


class WorkoutStates(StatesGroup):
    """
    Группа состояний для процесса записи тренировки.
    
    Состояния:
    - waiting_for_correction: ожидание текста с исправлениями от пользователя
    """
    
    # Состояние ожидания текста с исправлениями от пользователя
    waiting_for_correction = State()