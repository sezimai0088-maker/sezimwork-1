"""Открывает сессию базы данных и находит текущего сотрудника для каждого сообщения."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.i18n import lang_of, use_lang
from bot.services.employees import get_by_telegram


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.sessionmaker() as session:
            data["session"] = session
            user: User | None = data.get("event_from_user")
            employee = await get_by_telegram(session, user.id) if user else None
            employee = employee if employee is not None and employee.is_active else None
            data["employee"] = employee
            # Отвечаем на языке сотрудника; в общем чате — на языке группы
            chat = data.get("event_chat")
            if chat is not None and chat.type in ("group", "supergroup"):
                settings = data.get("settings")
                lang = getattr(settings, "group_lang", None)
            else:
                lang = lang_of(employee)
            with use_lang(lang):
                return await handler(event, data)
