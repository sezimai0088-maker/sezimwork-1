"""Точка входа: python -m bot.main

Два режима:
- обычный (компьютер, свой сервер): бот сам забирает сообщения у Telegram (long polling);
- webhook (Render и похожие хостинги): Telegram присылает сообщения на адрес бота,
  а адрес /health отвечает «ok» — его открывает «будильник», чтобы бесплатный сервер не засыпал.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Settings
from bot.db import init_db, make_engine, make_sessionmaker
from bot.handlers import build_router
from bot.middlewares import DbSessionMiddleware
from bot.scheduler import run_scheduler

log = logging.getLogger(__name__)
WEBHOOK_PATH = "/webhook"


def webhook_secret(settings: Settings) -> str:
    """Секрет, по которому бот узнаёт настоящие запросы от Telegram. Если не задан — выводится из токена."""
    if settings.webhook_secret:
        return settings.webhook_secret
    return hashlib.sha256(f"webhook:{settings.bot_token}".encode()).hexdigest()[:48]


def build_dispatcher(sessionmaker, settings: Settings) -> Dispatcher:  # noqa: ANN001
    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings  # доступно всем обработчикам в обоих режимах
    dp.update.outer_middleware(DbSessionMiddleware(sessionmaker))
    dp.include_router(build_router())
    return dp


async def health(_request: web.Request) -> web.Response:
    # Без обращения к базе: будильник лишь не даёт серверу уснуть
    return web.Response(text="ok")


def build_web_app(bot: Bot, dp: Dispatcher, settings: Settings) -> web.Application:
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/", health)
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=webhook_secret(settings)).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    return app


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()

    engine = make_engine(settings.database_url)
    await init_db(engine)
    sessionmaker = make_sessionmaker(engine)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = build_dispatcher(sessionmaker, settings)

    await bot.set_my_commands(
        [BotCommand(command="start", description="Открыть меню")], scope=BotCommandScopeAllPrivateChats()
    )

    # Расписание: напоминания, отчёты, повтор алертов, бэкап
    scheduler = asyncio.create_task(run_scheduler(bot, sessionmaker, settings))
    try:
        if settings.public_url:
            await run_webhook(bot, dp, settings)
        else:
            # Если раньше бот работал на сервере через webhook — отключаем его, иначе сообщения не придут сюда
            await bot.delete_webhook(drop_pending_updates=False)
            log.info("Бот запущен")
            await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.cancel()
        await bot.session.close()
        await engine.dispose()


async def run_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    url = settings.public_url + WEBHOOK_PATH
    await bot.set_webhook(
        url,
        secret_token=webhook_secret(settings),
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=False,
    )
    runner = web.AppRunner(build_web_app(bot, dp, settings))
    await runner.setup()
    await web.TCPSite(runner, host="0.0.0.0", port=settings.port).start()
    log.info("Бот запущен (webhook): %s, порт %s", url, settings.port)
    try:
        await asyncio.Event().wait()  # работаем, пока сервер не остановят
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
