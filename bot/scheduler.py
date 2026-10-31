"""Задачи по расписанию: отчёты, напоминания, повтор алертов, ночной бэкап.

Работает внутри бота: раз в 30 секунд проверяет, не пора ли что-то сделать.
Что уже сделано сегодня, хранится в базе — после перезапуска бот не повторит отправку.
Если бот был выключен в нужное время, он догонит пропущенное в течение 3 часов.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from bot import keyboards, texts
from bot.config import Settings
from bot.i18n import lang_of, use_lang
from bot.models import Attendance, Employee, Role, Task, TaskAlert
from bot.schedule import schedule_for
from bot.services import delivery
from bot.services import tasks as task_svc
from bot.services.calendar import get_mark
from bot.services.employees import get_setting, set_setting
from bot.services.notify import send_to_group
from bot.services.reports import previous_month, previous_week, report_recipients

log = logging.getLogger(__name__)

CATCH_UP = timedelta(hours=3)
TICK_SECONDS = 30


@dataclass
class Clock:
    now: datetime  # местное время

    @property
    def today(self) -> date:
        return self.now.date()

    def at(self, t: time, day: date | None = None) -> datetime:
        return datetime.combine(day or self.today, t, tzinfo=self.now.tzinfo)

    def due(self, t: time) -> bool:
        """Время t уже наступило сегодня, но прошло не больше CATCH_UP."""
        moment = self.at(t)
        return moment <= self.now < moment + CATCH_UP


async def _once_per_day(session: AsyncSession, key: str, today: date) -> bool:
    """True, если сегодня это ещё не делали (и сразу отмечает как сделанное)."""
    if await get_setting(session, key) == today.isoformat():
        return False
    await set_setting(session, key, today.isoformat())
    return True


async def _active_staff(session: AsyncSession) -> list[Employee]:
    result = await session.scalars(
        select(Employee).where(
            Employee.is_active.is_(True), Employee.telegram_id.is_not(None), Employee.role != Role.OWNER
        )
    )
    return list(result)


async def _today_attendance(session: AsyncSession, today: date) -> dict[int, Attendance]:
    result = await session.scalars(select(Attendance).where(Attendance.work_date == today))
    return {a.employee_id: a for a in result}


async def _safe_dm(bot: Bot, chat_id: int, text: str, **kwargs) -> None:
    try:
        await bot.send_message(chat_id, text, **kwargs)
    except Exception:  # noqa: BLE001
        log.warning("Не удалось написать %s", chat_id)


# ---------------- задачи расписания ----------------


async def job_reminders(bot: Bot, session: AsyncSession, settings: Settings, clock: Clock) -> None:
    """Личные напоминания: отметиться утром и завершить день вечером."""
    attendance = await _today_attendance(session, clock.today)
    for person in await _active_staff(session):
        sched = schedule_for(person, settings)
        if not sched.is_workday(clock.today) or await get_mark(session, person.id, clock.today):
            continue
        att = attendance.get(person.id)
        if att is None:
            moment = clock.at(sched.start) + timedelta(minutes=settings.checkin_reminder_min)
            if moment <= clock.now < moment + CATCH_UP and await _once_per_day(
                session, f"rem:in:{person.id}", clock.today
            ):
                with use_lang(lang_of(person)):
                    text = texts.REMIND_CHECK_IN
                await _safe_dm(bot, person.telegram_id, text)
        elif att.check_out_at is None:
            moment = clock.at(sched.end) + timedelta(minutes=settings.checkout_reminder_min)
            if moment <= clock.now < moment + timedelta(hours=5) and await _once_per_day(
                session, f"rem:out:{person.id}", clock.today
            ):
                with use_lang(lang_of(person)):
                    text = texts.REMIND_CHECK_OUT
                await _safe_dm(bot, person.telegram_id, text)


async def job_morning_summary(bot: Bot, session: AsyncSession, settings: Settings, clock: Clock) -> None:
    """«Ещё не отметились» — в общий чат через N минут после начала смены."""
    moment_t = (clock.at(settings.work_start) + timedelta(minutes=settings.morning_summary_min)).time()
    if not clock.due(moment_t) or not await _once_per_day(session, "job:morning_summary", clock.today):
        return
    attendance = await _today_attendance(session, clock.today)
    missing = []
    for person in await _active_staff(session):
        sched = schedule_for(person, settings)
        if not sched.is_workday(clock.today) or person.id in attendance:
            continue
        if await get_mark(session, person.id, clock.today):
            continue
        if clock.at(sched.start) + timedelta(minutes=sched.grace_minutes) > clock.now:
            continue  # у этого сотрудника смена начинается позже
        missing.append(person.full_name)
    if missing:
        with use_lang(settings.group_lang):
            text = texts.not_checked_in_summary(missing)
        await send_to_group(bot, session, settings, text)


async def job_daily_report(bot: Bot, session: AsyncSession, settings: Settings, clock: Clock) -> None:
    if not clock.due(settings.daily_report_time) or not await _once_per_day(session, "job:daily", clock.today):
        return
    recipients = [(p.telegram_id, lang_of(p)) for p in await report_recipients(session)]
    if recipients:
        await delivery.send_daily(bot, session, settings, clock.today, recipients)


async def job_period_reports(bot: Bot, session: AsyncSession, settings: Settings, clock: Clock) -> None:
    if not clock.due(settings.weekly_report_time):
        return
    recipients = [(p.telegram_id, lang_of(p)) for p in await report_recipients(session)]
    if clock.today.weekday() == 0 and await _once_per_day(session, "job:weekly", clock.today):
        start, end = previous_week(clock.today)
        if recipients:
            await delivery.send_period(bot, session, settings, start, end, "week", recipients)
    if clock.today.day == 1 and await _once_per_day(session, "job:monthly", clock.today):
        start, end = previous_month(clock.today)
        if recipients:
            await delivery.send_period(bot, session, settings, start, end, "month", recipients)


async def job_repeat_alerts(bot: Bot, session: AsyncSession, settings: Settings, clock: Clock) -> None:
    """Алерт повторяется каждое рабочее утро, пока руководитель не нажал «Принял»."""
    if clock.today.isoweekday() not in settings.work_day_numbers or not clock.due(settings.work_start):
        return
    if not await _once_per_day(session, "job:repeat_alerts", clock.today):
        return
    start_of_day = clock.at(time(0, 0)).astimezone(timezone.utc)
    alerts = list(
        await session.scalars(
            select(TaskAlert)
            .options(selectinload(TaskAlert.task).selectinload(Task.employee))
            .where(TaskAlert.acked_at.is_(None), TaskAlert.created_at < start_of_day)
        )
    )
    if not alerts:
        return
    managers = await task_svc.managers(session)
    for full in alerts:
        if full.task.status in ("done", "cancelled"):
            continue
        history = await task_svc.task_history(session, full.task.id, limit=max(full.days, 2))
        for manager in managers:
            with use_lang(lang_of(manager)):
                text = texts.ALERT_REMINDER + texts.alert_text(
                    full.kind, full.task.employee.full_name, full.task.text, full.days, history
                )
                markup = keyboards.alert_actions(full.id)
            await _safe_dm(bot, manager.telegram_id, text, reply_markup=markup)


async def job_backup(bot: Bot, session: AsyncSession, settings: Settings, clock: Clock) -> None:
    """Ночной бэкап владельцу в личный чат: файл базы (SQLite) или JSON-выгрузка (PostgreSQL/Supabase)."""
    from bot.db import is_postgres

    if not clock.due(settings.backup_time) or not await _once_per_day(session, "job:backup", clock.today):
        return
    postgres = is_postgres(settings.database_url)
    db_path = sqlite_path(settings.database_url)
    if not postgres and (db_path is None or not db_path.exists()):
        return
    owners = list(
        await session.scalars(
            select(Employee).where(Employee.role == Role.OWNER, Employee.telegram_id.is_not(None))
        )
    )
    if not owners:
        return
    with tempfile.TemporaryDirectory() as tmp:
        if postgres:
            from bot.backup import write_backup

            copy = Path(tmp) / f"backup_{clock.today:%Y-%m-%d}.json.gz"
            await write_backup(session.bind, copy)
        else:
            copy = Path(tmp) / f"backup_{clock.today:%Y-%m-%d}.db"
            make_backup(db_path, copy)
        for owner in owners:
            try:
                with use_lang(lang_of(owner)):
                    caption = texts.backup_caption(clock.today)
                await bot.send_document(owner.telegram_id, FSInputFile(copy), caption=caption)
            except Exception:  # noqa: BLE001
                log.exception("Не удалось отправить бэкап")


def sqlite_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite") or ":///" not in database_url:
        return None
    path = database_url.split(":///", 1)[1]
    return None if path in ("", ":memory:") else Path(path)


def make_backup(source: Path, target: Path) -> None:
    """Целостная копия базы, даже если бот в этот момент в неё пишет."""
    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


async def job_autosend_plans(bot: Bot, session: AsyncSession, settings: Settings, clock: Clock) -> None:
    """Сотрудник отметился, но не нажал «Отправить план» — отправляем приход и план сами."""
    from bot.services import day_message
    from bot.services.notify import group_chat

    if await group_chat(session, settings) is None:
        return
    deadline = (clock.now - timedelta(minutes=settings.plan_autosend_min)).astimezone(timezone.utc)
    pending = list(
        await session.scalars(
            select(Attendance).where(
                Attendance.work_date == clock.today,
                Attendance.group_message_id.is_(None),
                Attendance.check_in_at <= deadline,
            )
        )
    )
    for att in pending:
        employee = await session.get(Employee, att.employee_id)
        if employee is not None:
            await day_message.refresh(bot, session, settings, employee, clock.today)


JOBS = (job_autosend_plans, job_reminders, job_morning_summary, job_daily_report, job_period_reports, job_repeat_alerts, job_backup)


async def tick(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings, now: datetime | None = None) -> None:
    clock = Clock((now or datetime.now(timezone.utc)).astimezone(settings.tz))
    for job in JOBS:
        try:
            async with sessionmaker() as session:
                await job(bot, session, settings, clock)
        except Exception:  # noqa: BLE001 — ошибка одной задачи не должна останавливать остальные
            log.exception("Ошибка в задаче расписания %s", job.__name__)


async def run_scheduler(bot: Bot, sessionmaker: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    log.info("Расписание запущено")
    while True:
        await tick(bot, sessionmaker, settings)
        await asyncio.sleep(TICK_SECONDS)
