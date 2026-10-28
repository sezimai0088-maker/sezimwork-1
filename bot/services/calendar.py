"""Особые дни (выходной, больничный, отпуск...), графики и журнал изменений."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import Settings
from bot.models import Attendance, AuditLog, DayKind, DayMark, Employee
from bot.schedule import schedule_for
from bot.worktime import as_utc, early_leave_minutes, late_minutes, worked_minutes


def audit(
    session: AsyncSession,
    *,
    actor: Employee | None,
    employee_id: int | None,
    day: date | None,
    action: str,
    old: str | None = None,
    new: str | None = None,
    reason: str | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor.id if actor else None,
            employee_id=employee_id,
            work_date=day,
            action=action,
            old_value=old,
            new_value=new,
            reason=reason,
        )
    )


# ---------- Особые дни ----------


async def get_mark(session: AsyncSession, employee_id: int, day: date) -> DayMark | None:
    """Отметка сотрудника на день; если её нет — праздник для всех."""
    personal = await session.scalar(select(DayMark).where(DayMark.employee_id == employee_id, DayMark.day == day))
    if personal is not None:
        return personal
    return await session.scalar(select(DayMark).where(DayMark.employee_id.is_(None), DayMark.day == day))


async def marks_between(session: AsyncSession, start: date, end: date) -> dict[tuple[int | None, date], DayMark]:
    result = await session.scalars(select(DayMark).where(DayMark.day >= start, DayMark.day <= end))
    return {(m.employee_id, m.day): m for m in result}


async def set_marks(
    session: AsyncSession,
    *,
    employee_id: int | None,
    start: date,
    days: int,
    kind: DayKind,
    comment: str | None,
    actor: Employee,
) -> list[date]:
    """Ставит отметку на несколько дней подряд (календарных). Возвращает список дат."""
    marked: list[date] = []
    for offset in range(max(days, 1)):
        day = start + timedelta(days=offset)
        stmt = select(DayMark).where(DayMark.day == day)
        stmt = stmt.where(DayMark.employee_id.is_(None) if employee_id is None else DayMark.employee_id == employee_id)
        mark = await session.scalar(stmt)
        old = mark.kind if mark else None
        if mark is None:
            mark = DayMark(employee_id=employee_id, day=day, kind=kind, comment=comment, created_by_id=actor.id)
            session.add(mark)
        else:
            mark.kind, mark.comment, mark.created_by_id = kind, comment, actor.id
        audit(session, actor=actor, employee_id=employee_id, day=day, action="day_mark", old=old, new=kind, reason=comment)
        marked.append(day)
    await session.commit()
    return marked


async def remove_mark(
    session: AsyncSession, *, employee_id: int | None, day: date, actor: Employee, reason: str | None = None
) -> bool:
    stmt = select(DayMark).where(DayMark.day == day)
    stmt = stmt.where(DayMark.employee_id.is_(None) if employee_id is None else DayMark.employee_id == employee_id)
    mark = await session.scalar(stmt)
    if mark is None:
        return False
    audit(session, actor=actor, employee_id=employee_id, day=day, action="day_mark", old=mark.kind, new=None, reason=reason)
    await session.delete(mark)
    await session.commit()
    return True


# ---------- График ----------


async def set_schedule(
    session: AsyncSession,
    *,
    employee: Employee,
    start: time,
    end: time,
    work_days: frozenset[int],
    actor: Employee,
    settings: Settings,
) -> None:
    old = schedule_for(employee, settings).describe()
    employee.work_start = f"{start:%H:%M}"
    employee.work_end = f"{end:%H:%M}"
    employee.work_days = ",".join(str(d) for d in sorted(work_days))
    audit(
        session,
        actor=actor,
        employee_id=employee.id,
        day=None,
        action="schedule",
        old=old,
        new=schedule_for(employee, settings).describe(),
    )
    await session.commit()


# ---------- Исправление времени ----------


class CorrectionError(Exception):
    pass


async def correct_time(
    session: AsyncSession,
    settings: Settings,
    *,
    employee: Employee,
    day: date,
    kind: str,  # "in" | "out"
    new_time: time,
    reason: str,
    actor: Employee,
) -> Attendance:
    """Руководитель исправляет время прихода или ухода. Опоздание и отработанное время пересчитываются."""
    sched = schedule_for(employee, settings)
    local_dt = datetime.combine(day, new_time, tzinfo=settings.tz)
    utc_dt = local_dt.astimezone(timezone.utc)

    att = await session.scalar(
        select(Attendance).where(Attendance.employee_id == employee.id, Attendance.work_date == day)
    )
    mark = await get_mark(session, employee.id, day)
    counts = sched.is_workday(day) and mark is None

    if kind == "in":
        old = None
        if att is None:
            att = Attendance(
                employee_id=employee.id,
                work_date=day,
                is_workday=sched.is_workday(day),
                check_in_at=utc_dt,
                check_in_lat=settings.office_lat,
                check_in_lon=settings.office_lon,
                check_in_accuracy_m=None,
                check_in_distance_m=0,
            )
            session.add(att)
        else:
            old = f"{as_utc(att.check_in_at).astimezone(settings.tz):%H:%M}"
            if att.check_out_at is not None and as_utc(att.check_out_at) <= utc_dt:
                raise CorrectionError("Время прихода должно быть раньше ухода.")
            att.check_in_at = utc_dt
        att.late_minutes = late_minutes(local_dt, sched.start, sched.grace_minutes) if counts else 0
        new = f"{new_time:%H:%M}"
        action = "check_in"
    else:
        if att is None:
            raise CorrectionError("В этот день нет прихода — сначала исправьте время прихода.")
        check_in_local = as_utc(att.check_in_at).astimezone(settings.tz)
        if local_dt <= check_in_local:
            raise CorrectionError("Время ухода должно быть позже прихода.")
        old = f"{as_utc(att.check_out_at).astimezone(settings.tz):%H:%M}" if att.check_out_at else None
        att.check_out_at = utc_dt
        att.check_out_mode = att.check_out_mode or "office"
        att.early_leave_minutes = early_leave_minutes(local_dt, sched.end) if counts else 0
        new = f"{new_time:%H:%M}"
        action = "check_out"

    if att.check_out_at is not None:
        att.worked_minutes = worked_minutes(
            as_utc(att.check_in_at).astimezone(settings.tz), as_utc(att.check_out_at).astimezone(settings.tz)
        )
    att.corrected = True
    audit(session, actor=actor, employee_id=employee.id, day=day, action=action, old=old, new=new, reason=reason)
    await session.commit()
    return att


async def recent_audit(session: AsyncSession, employee_id: int, limit: int = 10) -> list[AuditLog]:
    result = await session.scalars(
        select(AuditLog)
        .where(or_(AuditLog.employee_id == employee_id))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result)
