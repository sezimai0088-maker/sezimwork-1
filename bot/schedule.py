"""График работы сотрудника: общий из настроек или индивидуальный."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, time

from bot.config import Settings

WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@dataclass(frozen=True)
class Schedule:
    start: time
    end: time
    grace_minutes: int
    work_days: frozenset[int]

    def is_workday(self, day: date) -> bool:
        return day.isoweekday() in self.work_days

    def describe(self) -> str:
        return f"{self.start:%H:%M}–{self.end:%H:%M}, {describe_days(self.work_days)}"


def parse_days(value: str | None) -> frozenset[int] | None:
    if not value:
        return None
    days = frozenset(int(x) for x in value.split(",") if x.strip().isdigit() and 1 <= int(x) <= 7)
    return days or None


def describe_days(days: frozenset[int]) -> str:
    ordered = sorted(days)
    if ordered == list(range(ordered[0], ordered[-1] + 1)) and len(ordered) > 2:
        return f"{WEEKDAY_SHORT[ordered[0] - 1]}–{WEEKDAY_SHORT[ordered[-1] - 1]}"
    return ", ".join(WEEKDAY_SHORT[d - 1] for d in ordered)


def parse_hhmm(value: str | None) -> time | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", value)
    if not match:
        return None
    hours, minutes = int(match.group(1)), int(match.group(2))
    if hours > 23 or minutes > 59:
        return None
    return time(hours, minutes)


def parse_range(value: str) -> tuple[time, time] | None:
    """'08:30-17:30' или '8.30 – 17.30' → (08:30, 17:30)."""
    parts = re.split(r"\s*[-–—]\s*", value.strip())
    if len(parts) != 2:
        return None
    start, end = parse_hhmm(parts[0]), parse_hhmm(parts[1])
    if start is None or end is None or end <= start:
        return None
    return start, end


def schedule_for(employee, settings: Settings) -> Schedule:  # noqa: ANN001
    """Индивидуальный график, если задан, иначе общий."""
    return Schedule(
        start=parse_hhmm(getattr(employee, "work_start", None)) or settings.work_start,
        end=parse_hhmm(getattr(employee, "work_end", None)) or settings.work_end,
        grace_minutes=settings.grace_minutes,
        work_days=parse_days(getattr(employee, "work_days", None)) or settings.work_day_numbers,
    )
