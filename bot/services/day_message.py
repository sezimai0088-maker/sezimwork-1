"""Одно сообщение в общем чате на день сотрудника: приход + план. Уход — ответом на него."""

from __future__ import annotations

from datetime import date

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import Settings
from bot.geo import twogis_link
from bot.i18n import use_lang
from bot.models import Attendance, Employee
from bot.services import tasks as task_svc
from bot.services.attendance import get_day
from bot.services.notify import edit_in_group, group_chat, post_to_group
from bot.task_rules import TaskStatus
from bot.worktime import as_utc


async def plan_tasks(session: AsyncSession, employee_id: int, day: date):
    tasks = await task_svc.today_tasks(session, employee_id, day)
    return [t for t in tasks if t.status != TaskStatus.CANCELLED]


def outside_info(settings: Settings, att: Attendance):
    """(расстояние, ссылка 2ГИС, комментарий) — если приход отмечен вне офиса, иначе None."""
    if not att.is_outside:
        return None
    link = twogis_link(att.check_in_lat, att.check_in_lon, settings.twogis_base_url)
    return (att.check_in_distance_m or 0, link, att.check_in_comment)


async def render(session: AsyncSession, settings: Settings, employee: Employee, att: Attendance) -> str:
    """Текст сообщения дня — всегда на языке общего чата."""
    at_local = as_utc(att.check_in_at).astimezone(settings.tz)
    tasks = await plan_tasks(session, employee.id, att.work_date)
    with use_lang(settings.group_lang):
        return texts.day_message(
            employee.full_name, at_local, att.late_minutes, att.is_workday, tasks, att.work_date,
            outside=outside_info(settings, att),
        )


async def refresh(bot: Bot, session: AsyncSession, settings: Settings, employee: Employee, day: date) -> bool:
    """Создаёт или обновляет сообщение дня в общем чате. False — чат не подключён."""
    att = await get_day(session, employee.id, day)
    if att is None:
        return False
    text = await render(session, settings, employee, att)
    chat_id = await group_chat(session, settings)
    if chat_id is None:
        return False
    if att.group_message_id and att.group_chat_id == chat_id:
        if await edit_in_group(bot, chat_id, att.group_message_id, text):
            return True
    sent = await post_to_group(bot, session, settings, text)
    if sent is None:
        return False
    att.group_chat_id = chat_id
    att.group_message_id = sent.message_id
    await session.commit()
    return True


async def post_departure(bot: Bot, session: AsyncSession, settings: Settings, att: Attendance, text: str) -> bool:
    """Уход — ответом на сообщение о приходе, чтобы день сотрудника был одной веткой."""
    chat_id = await group_chat(session, settings)
    reply_to = att.group_message_id if att.group_chat_id == chat_id else None
    return await post_to_group(bot, session, settings, text, reply_to=reply_to) is not None
