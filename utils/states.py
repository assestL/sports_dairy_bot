"""
Модуль состояний FSM (Finite State Machine) для бота.
Используется для управления состояниями пользователя при взаимодействии с ботом.
"""
from aiogram.fsm.state import State, StatesGroup


class WorkoutStates(StatesGroup):
    """
    Группа состояний для процесса записи тренировки и аналитики.
    """
    waiting_for_correction = State()
    waiting_for_edit = State()
    waiting_for_chart = State()   # Режим ожидания построения графика
    waiting_for_advice = State()  # Режим ожидания текстовой аналитики с советом