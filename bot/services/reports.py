"""Расчёт отчётов: что происходило с каждым сотрудником по дням за период."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.config import Settings
from bot.models import Attendance, DayMark, Employee, Role, TaskReport
from bot.schedule import Schedule, schedule_for
from bot.services.calendar import marks_between
from bot.worktime import as_utc

# Что было в день
PRESENT = "present"
ABSENT = "absent"
WEEKEND = "weekend"
PENDING = "pending"        # сегодня, время прихода ещё не наступило
FUTURE = "future"
NOT_EMPLOYED = "not_employed"


@dataclass
class DayInfo:
    status: str                     # одно из значений выше или вид особого дня (sick, vacation...)
    attendance: Attendance | None = None
    mark: DayMark | None = None
    no_checkout: bool = False

    @property
    def late(self) -> int:
        return self.attendance.late_minutes if self.attendance else 0


@dataclass
class EmployeeRow:
    employee: Employee
    schedule: Schedule
    days: dict[date, DayInfo] = field(default_factory=dict)
    task_reports: list[TaskReport] = field(default_factory=list)

    @property
    def present_days(self) -> int:
        return sum(1 for d in self.days.values() if d.status == PRESENT)

    @property
    def absences(self) -> int:
        return sum(1 for d in self.days.values() if d.status == ABSENT)

    @property
    def late_count(self) -> int:
        return sum(1 for d in self.days.values() if d.late)

    @property
    def late_total(self) -> int:
        return sum(d.late for d in self.days.values())

    @property
    def late_days(self) -> list[tuple[date, int]]:
        """Дни с опозданием: (дата, минуты)."""
        return [(d, info.late) for d, info in sorted(self.days.items()) if info.late]

    @property
    def outside_count(self) -> int:
        return sum(1 for d in self.days.values() if d.attendance is not None and d.attendance.is_outside)

    @property
    def worked_total(self) -> int:
        return sum((d.attendance.worked_minutes or 0) for d in self.days.values() if d.attendance)

    @property
    def no_checkout_count(self) -> int:
        return sum(1 for d in self.days.values() if d.no_checkout)

    @property
    def marks(self) -> Counter:
        return Counter(d.status for d in self.days.values() if d.mark is not None and d.attendance is None)

    @property
    def tasks_done(self) -> int:
        return sum(1 for r in self.task_reports if r.status == "done")

    @property
    def tasks_total(self) -> int:
        return len(self.task_reports)

    @property
    def tasks_percent(self) -> int | None:
        return round(100 * self.tasks_done / self.tasks_total) if self.tasks_total else None


def day_status(
    *,
    employee: Employee,
    schedule: Schedule,
    day: date,
    attendance: Attendance | None,
    mark: DayMark | None,
    now_local: datetime,
    tz,
) -> DayInfo:
    today = now_local.date()
    hired = as_utc(employee.created_at).astimezone(tz).date() if employee.created_at else None
    if attendance is not None:
        return DayInfo(PRESENT, attendance, mark, no_checkout=attendance.check_out_at is None and day < today)
    if hired is not None and day < hired:
        return DayInfo(NOT_EMPLOYED)
    if mark is not None:
        return DayInfo(mark.kind, mark=mark)
    if day > today:
        return DayInfo(FUTURE)
    if not schedule.is_workday(day):
        return DayInfo(WEEKEND)
    if day == today:
        start = now_local.replace(hour=schedule.start.hour, minute=schedule.start.minute, second=0, microsecond=0)
        if now_local < start + timedelta(minutes=schedule.grace_minutes):
            return DayInfo(PENDING)
    return DayInfo(ABSENT)


def report_people_filter(employee: Employee, has_attendance: bool) -> bool:
    """В отчёт попадают сотрудники и руководители; владелец — только если сам отмечался."""
    return employee.role != Role.OWNER or has_attendance


async def load_period(
    session: AsyncSession, settings: Settings, start: date, end: date, now: datetime | None = None
) -> list[EmployeeRow]:
    now_local = (now or datetime.now(timezone.utc)).astimezone(settings.tz)
    people = list(
        await session.scalars(select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.full_name))
    )
    attendances = await session.scalars(
        select(Attendance).where(Attendance.work_date >= start, Attendance.work_date <= end)
    )
    att_by = {(a.employee_id, a.work_date): a for a in attendances}
    marks = await marks_between(session, start, end)
    reports = await session.scalars(
        select(TaskReport)
        .options(selectinload(TaskReport.task))
        .where(TaskReport.work_date >= start, TaskReport.work_date <= end)
        .order_by(TaskReport.work_date, TaskReport.task_id)
    )
    reports_by: dict[int, list[TaskReport]] = {}
    for r in reports:
        reports_by.setdefault(r.employee_id, []).append(r)

    rows: list[EmployeeRow] = []
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    for person in people:
        has_att = any((person.id, d) in att_by for d in days)
        if not report_people_filter(person, has_att):
            continue
        sched = schedule_for(person, settings)
        row = EmployeeRow(employee=person, schedule=sched, task_reports=reports_by.get(person.id, []))
        for d in days:
            mark = marks.get((person.id, d)) or marks.get((None, d))
            row.days[d] = day_status(
                employee=person,
                schedule=sched,
                day=d,
                attendance=att_by.get((person.id, d)),
                mark=mark,
                now_local=now_local,
                tz=settings.tz,
            )
        rows.append(row)
    return rows


def week_bounds(day: date) -> tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def month_bounds(day: date) -> tuple[date, date]:
    first = day.replace(day=1)
    next_first = (first + timedelta(days=32)).replace(day=1)
    return first, next_first - timedelta(days=1)


def previous_week(day: date) -> tuple[date, date]:
    return week_bounds(day - timedelta(days=7))


def previous_month(day: date) -> tuple[date, date]:
    return month_bounds(day.replace(day=1) - timedelta(days=1))


async def report_recipients(session: AsyncSession) -> list[Employee]:
    """Отчёты получают руководители и владелец."""
    result = await session.scalars(
        select(Employee).where(
            Employee.role.in_([Role.MANAGER, Role.OWNER]),
            Employee.is_active.is_(True),
            Employee.telegram_id.is_not(None),
        )
    )
    return list(result)
