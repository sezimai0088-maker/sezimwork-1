"""Приход и уход сотрудников."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.geo import ZoneCheck, check_zone
from bot.models import Attendance, CheckoutMode, Employee
from bot.worktime import as_utc, early_leave_minutes, is_workday, late_minutes, worked_minutes


class CheckInStatus(StrEnum):
    OK = "ok"
    ALREADY = "already"
    OUTSIDE = "outside"
    LOW_ACCURACY = "low_accuracy"


@dataclass
class CheckInResult:
    status: CheckInStatus
    zone: ZoneCheck | None = None
    attendance: Attendance | None = None


@dataclass
class CheckOutResult:
    attendance: Attendance
    zone: ZoneCheck
    mode: CheckoutMode


def _zone(settings: Settings, lat: float, lon: float, accuracy_m: float | None) -> ZoneCheck:
    return check_zone(
        lat,
        lon,
        accuracy_m,
        office_lat=settings.office_lat,
        office_lon=settings.office_lon,
        radius_m=settings.office_radius_m,
        max_accuracy_m=settings.max_accuracy_m,
    )


async def get_day(session: AsyncSession, employee_id: int, day: date) -> Attendance | None:
    return await session.scalar(
        select(Attendance).where(Attendance.employee_id == employee_id, Attendance.work_date == day)
    )


async def check_in(
    session: AsyncSession,
    settings: Settings,
    employee: Employee,
    *,
    lat: float,
    lon: float,
    accuracy_m: float | None,
    now: datetime,
) -> CheckInResult:
    """Отмечает приход. Принимается только внутри геозоны офиса."""
    local_now = now.astimezone(settings.tz)
    today = local_now.date()

    existing = await get_day(session, employee.id, today)
    if existing is not None:
        return CheckInResult(CheckInStatus.ALREADY, attendance=existing)

    zone = _zone(settings, lat, lon, accuracy_m)
    if zone.accuracy_too_low:
        return CheckInResult(CheckInStatus.LOW_ACCURACY, zone=zone)
    if not zone.inside:
        return CheckInResult(CheckInStatus.OUTSIDE, zone=zone)

    workday = is_workday(today, settings.work_day_numbers)
    attendance = Attendance(
        employee_id=employee.id,
        work_date=today,
        is_workday=workday,
        check_in_at=now,
        check_in_lat=lat,
        check_in_lon=lon,
        check_in_accuracy_m=accuracy_m,
        check_in_distance_m=round(zone.distance_m, 1),
        late_minutes=late_minutes(local_now, settings.work_start, settings.grace_minutes) if workday else 0,
    )
    session.add(attendance)
    await session.commit()
    return CheckInResult(CheckInStatus.OK, zone=zone, attendance=attendance)


async def check_out(
    session: AsyncSession,
    settings: Settings,
    attendance: Attendance,
    *,
    lat: float,
    lon: float,
    accuracy_m: float | None,
    now: datetime,
) -> CheckOutResult:
    """Отмечает уход. В офисе — если внутри геозоны, иначе — «в полях»."""
    zone = _zone(settings, lat, lon, accuracy_m)
    mode = CheckoutMode.OFFICE if zone.inside else CheckoutMode.FIELD
    local_now = now.astimezone(settings.tz)
    check_in_local = as_utc(attendance.check_in_at).astimezone(settings.tz)

    attendance.check_out_at = now
    attendance.check_out_lat = lat
    attendance.check_out_lon = lon
    attendance.check_out_accuracy_m = accuracy_m
    attendance.check_out_distance_m = round(zone.distance_m, 1)
    attendance.check_out_mode = mode
    attendance.worked_minutes = worked_minutes(check_in_local, local_now)
    attendance.early_leave_minutes = (
        early_leave_minutes(local_now, settings.work_end) if attendance.is_workday else 0
    )
    await session.commit()
    return CheckOutResult(attendance=attendance, zone=zone, mode=mode)


async def reset_day(session: AsyncSession, employee_id: int, day: date) -> None:
    """Только для проверки бота владельцем: стирает отметку и итоги задач за день.

    Задачи сегодняшнего плана возвращаются в статус «Новая», чтобы сценарий можно было пройти заново.
    """
    from sqlalchemy import delete

    from bot.models import Task, TaskAlert, TaskReport
    from bot.task_rules import TaskStatus

    await session.execute(delete(Attendance).where(Attendance.employee_id == employee_id, Attendance.work_date == day))
    reported = select(TaskReport.task_id).where(TaskReport.employee_id == employee_id, TaskReport.work_date == day)
    task_ids = list(await session.scalars(reported))
    if task_ids:
        await session.execute(delete(TaskAlert).where(TaskAlert.task_id.in_(task_ids)))
    await session.execute(
        delete(TaskReport).where(TaskReport.employee_id == employee_id, TaskReport.work_date == day)
    )
    tasks = await session.scalars(select(Task).where(Task.employee_id == employee_id, Task.plan_date == day))
    for task in tasks:
        task.status = TaskStatus.NEW
        task.closed_at = None
        task.not_done_streak = 0
        task.blocked_streak = 0
    await session.commit()
