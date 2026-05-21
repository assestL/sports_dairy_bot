"""
Главный файл приложения Telegram бота для дневника тренировок.
Инициализирует базу данных, настраивает логирование и запускает поллинг.
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config.config import BOT_TOKEN
from database.connection import init_db
from handlers.common import router as common_router
from handlers.workout import router as workout_router
from handlers.analytics import router as analytics_router

# Настраиваем базовое логирование
# level=logging.INFO - показывает информационные сообщения и выше (WARNING, ERROR)
# format - формат вывода логов с временем, уровнем и сообщением
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Получаем logger для текущего модуля
logger = logging.getLogger(__name__)


async def main() -> None:
    """
    Главная асинхронная функция приложения.
    
    Инициализирует базу данных, создает бота и диспетчер,
    регистрирует роутеры и запускает поллинг.
    """
    # Инициализируем базу данных: создаем все таблицы согласно моделям
    logger.info("Инициализация базы данных...")
    init_db()
    logger.info("База данных успешно инициализирована.")
    
    # Создаем объект бота с токеном из конфигурации
    # default=DefaultBotProperties(parse_mode=ParseMode.HTML) устанавливает режим парсинга по умолчанию
    # Это новый способ установки parse_mode в aiogram 3.7.0+
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    
    # Создаем диспетчер с хранилищем состояний FSM в памяти
    # MemoryStorage подходит для простых случаев; для production лучше использовать Redis
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Подключаем роутеры к диспетчеру
    # Роутер analytics содержит обработчики для команд /start, /help, /exercises и аналитики
    # ВАЖНО: analytics_router должен быть подключен ПЕРВЫМ, чтобы команды обрабатывались до workout_router
    dp.include_router(analytics_router)
    # Роутер common содержит обработчики команд /start и /help (дублируются в analytics)
    dp.include_router(common_router)
    # Роутер workout содержит обработчики для записи тренировок (только обычные текстовые сообщения)
    dp.include_router(workout_router)
    
    # Логгируем успешный старт
    logger.info("Бот запущен и готов к работе!")
    
    # Запускаем поллинг (опрос сервера Telegram на наличие новых сообщений)
    # allowed_updates=[] означает, что бот будет получать все типы обновлений
    await dp.start_polling(bot, allowed_updates=[])


if __name__ == "__main__":
    # Запускаем главную асинхронную функцию
    # asyncio.run() создает event loop и выполняет main() до завершения
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Обрабатываем прерывание работы (Ctrl+C)
        logger.info("Бот остановлен пользователем.")
