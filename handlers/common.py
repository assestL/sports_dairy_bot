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
    get_or_create_user(
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