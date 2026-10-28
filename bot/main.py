"""Точка входа: python -m bot.main"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats

from bot.config import Settings
from bot.db import init_db, make_engine, make_sessionmaker
from bot.handlers import build_router
from bot.middlewares import DbSessionMiddleware
from bot.scheduler import run_scheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()

    engine = make_engine(settings.database_url)
    await init_db(engine)
    sessionmaker = make_sessionmaker(engine)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.include_router(build_router())

    await bot.set_my_commands(
        [BotCommand(command="start", description="Открыть меню")], scope=BotCommandScopeAllPrivateChats()
    )

    # Расписание: напоминания, отчёты, повтор алертов, бэкап
    scheduler = asyncio.create_task(run_scheduler(bot, sessionmaker, settings))

    logging.getLogger(__name__).info("Бот запущен")
    try:
        # Long polling: бот сам забирает сообщения у Telegram, домен и HTTPS не нужны.
        await dp.start_polling(bot, settings=settings, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.cancel()
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
