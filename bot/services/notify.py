"""Отправка и обновление сообщений в общем чате."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import Message, ReplyParameters
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.services.employees import get_group_chat_id

log = logging.getLogger(__name__)


async def group_chat(session: AsyncSession, settings: Settings) -> int | None:
    return await get_group_chat_id(session, settings.group_chat_id)


async def post_to_group(
    bot: Bot, session: AsyncSession, settings: Settings, text: str, *, reply_to: int | None = None
) -> Message | None:
    """Отправляет сообщение в общий чат (можно ответом на другое). None — чат не подключён или ошибка.

    Ошибка отправки не должна ломать отметку: отметка уже сохранена в базе.
    """
    chat_id = await group_chat(session, settings)
    if chat_id is None:
        log.warning("Общий чат не подключён, сообщение не отправлено")
        return None
    reply = ReplyParameters(message_id=reply_to, allow_sending_without_reply=True) if reply_to else None
    try:
        return await bot.send_message(chat_id, text, disable_web_page_preview=True, reply_parameters=reply)
    except TelegramAPIError:
        log.exception("Не удалось отправить сообщение в общий чат %s", chat_id)
        return None


async def send_to_group(bot: Bot, session: AsyncSession, settings: Settings, text: str) -> bool:
    return await post_to_group(bot, session, settings, text) is not None


async def edit_in_group(bot: Bot, chat_id: int, message_id: int, text: str) -> bool:
    """Обновляет сообщение в общем чате. True — обновлено (или текст не изменился)."""
    try:
        await bot.edit_message_text(
            text=text, chat_id=chat_id, message_id=message_id, disable_web_page_preview=True
        )
    except TelegramBadRequest as error:
        return "not modified" in str(error).lower()
    except TelegramAPIError:
        log.exception("Не удалось обновить сообщение %s в чате %s", message_id, chat_id)
        return False
    return True
