"""
Модели SQLAlchemy для базы данных спортивного дневника.
Используется современный стиль SQLAlchemy 2.0 с Mapped и mapped_column.
"""

from datetime import datetime, date
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


class User(Base):
    """Модель пользователя Telegram."""
    
    __tablename__ = "users"
    
    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Связь с тренировками (один ко многим)
    workout_sessions: Mapped[List["WorkoutSession"]] = relationship(
        "WorkoutSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<User(telegram_id={self.telegram_id}, username={self.username})>"


class WorkoutSession(Base):
    """Модель сессии тренировки."""
    
    __tablename__ = "workout_sessions"
    
    session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id"), nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    user_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    
    # Связь с пользователем (многие к одному)
    user: Mapped["User"] = relationship("User", back_populates="workout_sessions")
    
    # Связи с деталями тренировки и рекомендациями (один ко многим)
    workout_details: Mapped[List["WorkoutDetail"]] = relationship(
        "WorkoutDetail",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    
    ai_recommendations: Mapped[List["AIRecommendation"]] = relationship(
        "AIRecommendation",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<WorkoutSession(session_id={self.session_id}, date={self.session_date})>"


class WorkoutDetail(Base):
    """Модель деталей упражнения в тренировке."""
    
    __tablename__ = "workout_details"
    
    detail_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_sessions.session_id"), nullable=False)
    exercise_name: Mapped[str] = mapped_column(String, nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    sets_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reps_count: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Связь с сессией тренировки (многие к одному)
    session: Mapped["WorkoutSession"] = relationship("WorkoutSession", back_populates="workout_details")
    
    def __repr__(self) -> str:
        return f"<WorkoutDetail(exercise={self.exercise_name}, weight={self.weight})>"


class AIRecommendation(Base):
    """Модель AI-рекомендации для тренировки."""
    
    __tablename__ = "ai_recommendations"
    
    recommendation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("workout_sessions.session_id"), nullable=False)
    advice_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Связь с сессией тренировки (многие к одному)
    session: Mapped["WorkoutSession"] = relationship("WorkoutSession", back_populates="ai_recommendations")
    
    def __repr__(self) -> str:
        return f"<AIRecommendation(id={self.recommendation_id}, is_read={self.is_read})>"