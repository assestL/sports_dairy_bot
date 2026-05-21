import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from database.crud import get_or_create_user

logger = logging.getLogger(__name__)

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """
    Обработчик команды /start.
    Регистрирует пользователя и отправляет приветствие с инструкцией.
    """
    telegram_id = message.from_user.id
    username = message.from_user.username
    
    logger.info(f"📥 Команда /start от пользователя: telegram_id={telegram_id}, username={username}")
    
    try:
        # Гарантируем наличие пользователя в БД
        user = get_or_create_user(
            telegram_id=telegram_id,
            username=username
        )
        logger.info(f"✅ Пользователь успешно сохранён в БД: {user}")
    except Exception as e:
        logger.error(f"❌ Ошибка при сохранении пользователя в БД: {e}", exc_info=True)
        await message.answer("⚠️ Произошла ошибка при регистрации. Попробуйте позже.")
        return
    
    await message.answer(
        "👋 Привет! Я твой персональный тренер-ассистент.\n\n"
        "Я помогу тебе вести учет тренировок и давать рекомендации.\n\n"
        "📝 <b>Как записать тренировку?</b>\n"
        "Просто напиши мне текст в свободной форме. Например:\n"
        "<i>'Сегодня делал жим лежа 60кг 3 по 10, присед 80кг 4 по 8. Чувствовал себя бодро.'</i>\n\n"
        "Я проанализирую текст, покажу результат и сохраню в дневник."
    )