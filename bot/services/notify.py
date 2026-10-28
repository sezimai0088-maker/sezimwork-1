"""Отправка сообщений в общий чат."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.services.employees import get_group_chat_id

log = logging.getLogger(__name__)


async def send_to_group(bot: Bot, session: AsyncSession, settings: Settings, text: str) -> bool:
    """Отправляет сообщение в общий чат. Возвращает False, если чат не подключён или Telegram вернул ошибку.

    Ошибка отправки не должна ломать отметку: отметка уже сохранена в базе.
    """
    chat_id = await get_group_chat_id(session, settings.group_chat_id)
    if chat_id is None:
        log.warning("Общий чат не подключён, сообщение не отправлено")
        return False
    try:
        await bot.send_message(chat_id, text, disable_web_page_preview=True)
    except TelegramAPIError:
        log.exception("Не удалось отправить сообщение в общий чат %s", chat_id)
        return False
    return True
