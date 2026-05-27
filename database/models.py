"""
Модели SQLAlchemy для базы данных спортивного дневника.
Полностью совместимы с вашей текущей PostgreSQL схемой.
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
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False
    )
    username: Mapped[Optional[str]] = mapped_column(
        String,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    workout_sessions: Mapped[List["WorkoutSession"]] = relationship(
        "WorkoutSession",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User telegram_id={self.telegram_id}>"


class WorkoutSession(Base):
    __tablename__ = "workout_sessions"

    session_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )
    telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id"),
        nullable=False
    )
    session_date: Mapped[date] = mapped_column(
        Date,
        nullable=False
    )
    user_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="workout_sessions"
    )
    workout_details: Mapped[List["WorkoutDetail"]] = relationship(
        "WorkoutDetail",
        back_populates="session",
        cascade="all, delete-orphan"
    )
    ai_recommendations: Mapped[List["AIRecommendation"]] = relationship(
        "AIRecommendation",
        back_populates="session",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<WorkoutSession session_id={self.session_id}>"


class WorkoutDetail(Base):
    __tablename__ = "workout_details"

    detail_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workout_sessions.session_id"),
        nullable=False
    )
    exercise_name: Mapped[str] = mapped_column(
        String,
        nullable=False
    )
    weight: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=0
    )
    sets_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )
    reps_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False
    )

    session: Mapped["WorkoutSession"] = relationship(
        "WorkoutSession",
        back_populates="workout_details"
    )

    def __repr__(self) -> str:
        return (
            f"<WorkoutDetail "
            f"exercise={self.exercise_name} "
            f"sets={self.sets_count} "
            f"reps={self.reps_count}>"
        )


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    recommendation_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True
    )
    session_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("workout_sessions.session_id"),
        nullable=True  # NULL для рекомендаций за период
    )
    advice_text: Mapped[str] = mapped_column(
        Text,
        nullable=False
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False
    )
    context_info: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True
    )

    session: Mapped[Optional["WorkoutSession"]] = relationship(
        "WorkoutSession",
        back_populates="ai_recommendations"
    )

    def __repr__(self) -> str:
        return f"<AIRecommendation id={self.recommendation_id}>"