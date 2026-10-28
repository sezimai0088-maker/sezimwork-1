"""Общая логика: какое меню показать сотруднику прямо сейчас."""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import ReplyKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards
from bot.config import Settings
from bot.models import Employee
from bot.services.attendance import get_day


async def menu_for(session: AsyncSession, settings: Settings, employee: Employee) -> ReplyKeyboardMarkup:
    today = datetime.now(timezone.utc).astimezone(settings.tz).date()
    day = await get_day(session, employee.id, today)
    return keyboards.main_menu(
        employee,
        checked_in=day is not None,
        checked_out=day is not None and day.check_out_at is not None,
    )
