"""Сборка и отправка отчётов (текст + Excel)."""

from __future__ import annotations

import logging
from datetime import date

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy.ext.asyncio import AsyncSession

from bot import report_texts
from bot.config import Settings
from bot.excel import build_timesheet
from bot.services.reports import load_period

log = logging.getLogger(__name__)


async def _send(bot: Bot, chat_id: int, text: str, document: tuple[bytes, str] | None = None) -> None:
    try:
        for chunk in report_texts.split_message(text):
            await bot.send_message(chat_id, chunk)
        if document is not None:
            data, filename = document
            await bot.send_document(chat_id, BufferedInputFile(data, filename=filename))
    except Exception:  # noqa: BLE001 — один недоступный получатель не должен мешать остальным
        log.exception("Не удалось отправить отчёт в %s", chat_id)


async def send_daily(bot: Bot, session: AsyncSession, settings: Settings, day: date, chat_ids: list[int]) -> str:
    rows = await load_period(session, settings, day, day)
    text = report_texts.daily_report(rows, day, settings.tz)
    for chat_id in chat_ids:
        await _send(bot, chat_id, text)
    return text


async def send_period(
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    start: date,
    end: date,
    title: str,
    chat_ids: list[int],
) -> str:
    rows = await load_period(session, settings, start, end)
    text = report_texts.period_report(rows, start, end, title)
    data = build_timesheet(rows, start, end, settings.tz, f"{title}: {report_texts.fmt_period(start, end)}")
    filename = f"tabel_{start:%Y-%m-%d}_{end:%Y-%m-%d}.xlsx"
    for chat_id in chat_ids:
        await _send(bot, chat_id, text, (data, filename))
    return text
