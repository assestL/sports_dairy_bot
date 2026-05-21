from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database.crud import get_or_create_user

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Регистрирует пользователя и отправляет приветствие с инструкцией.
    """
    # Гарантируем наличие пользователя в БД
    await get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )

    await message.answer(
        "👋 Привет! Я твой персональный тренер-ассистент.\n\n"
        "Я помогу тебе вести учет тренировок и давать рекомендации.\n\n"
        "📝 <b>Как записать тренировку?</b>\n"
        "Просто напиши мне текст в свободной форме. Например:\n"
        "<i>'Сегодня делал жим лежа 60кг 3 по 10, присед 80кг 4 по 8. Чувствовал себя бодро.'</i>\n\n"
        "Я проанализирую текст, покажу результат и сохраню в дневник."
    )
"""
Модуль обработчиков команд и сообщений бота.
Содержит хэндлеры для общих команд (/start, /help и т.д.).
"""

from aiogram import Router, types
from aiogram.filters import Command

from database.crud import get_or_create_user

# Создаем роутер для регистрации хэндлеров
router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message) -> None:
    """
    Обработчик команды /start.
    
    Приветствует пользователя, регистрирует его в базе данных
    и объясняет, как записать тренировку.
    """
    # Получаем или создаем пользователя в БД
    user = get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username
    )
    
    # Формируем приветственное сообщение
    welcome_text = (
        f"👋 Привет, {message.from_user.full_name}!\n\n"
        "Я — твой персональный AI-тренер и дневник тренировок.\n\n"
        "📝 <b>Как записать тренировку:</b>\n"
        "Просто отправь мне текст описания своей тренировки в свободной форме.\n"
        "Например:\n"
        "<i>\"Сегодня сделал жим лежа 80кг 3х10, присед 100кг 4х8. "
        "Чувствовал себя отлично!\"</i>\n\n"
        "Я проанализирую твою тренировку, покажу результаты и сохраню в дневник."
    )
    
    # Отправляем сообщение пользователю
    await message.answer(
        text=welcome_text,
        parse_mode="HTML"
    )


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    """
    Обработчик команды /help.
    
    Показывает справку по использованию бота.
    """
    help_text = (
        "📖 <b>Справка по использованию бота:</b>\n\n"
        "<b>/start</b> - Начать работу с ботом\n"
        "<b>/help</b> - Показать эту справку\n\n"
        "📝 <b>Запись тренировки:</b>\n"
        "Отправьте текст с описанием тренировки в любом формате.\n"
        "Бот автоматически распознает упражнения, веса и повторения.\n\n"
        "💡 <b>Советы:</b>\n"
        "- Указывайте дату тренировки (если не сегодня)\n"
        "- Пишите названия упражнений, вес, подходы и повторения\n"
        "- Добавляйте заметки о самочувствии для лучшего анализа"
    )
    
    await message.answer(
        text=help_text,
        parse_mode="HTML"
    )