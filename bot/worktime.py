"""Расчёт опозданий, раннего ухода и отработанного времени."""

from __future__ import annotations

from datetime import date, datetime, time, timezone


def is_workday(day: date, work_days: frozenset[int]) -> bool:
    return day.isoweekday() in work_days


def late_minutes(arrival: datetime, work_start: time, grace_minutes: int) -> int:
    """Минуты опоздания относительно начала смены.

    Если сотрудник пришёл в пределах допустимой задержки, опоздания нет.
    Если позже — опоздание считается от начала смены
    (пришёл в 09:07 при начале в 09:00 и задержке 5 мин → 7 мин).
    """
    start = arrival.replace(hour=work_start.hour, minute=work_start.minute, second=0, microsecond=0)
    diff = int((arrival - start).total_seconds() // 60)
    return diff if diff > grace_minutes else 0


def early_leave_minutes(departure: datetime, work_end: time) -> int:
    end = departure.replace(hour=work_end.hour, minute=work_end.minute, second=0, microsecond=0)
    diff = int((end - departure).total_seconds() // 60)
    return max(diff, 0)


def worked_minutes(check_in: datetime, check_out: datetime) -> int:
    return max(int((check_out - check_in).total_seconds() // 60), 0)


def format_duration(minutes: int) -> str:
    """844 → «14 ч 4 мин» (по-кыргызски «14 саат 4 мүн»)."""
    from bot.i18n import tr

    h_unit, m_unit = tr("ч", "саат"), tr("мин", "мүн")
    hours, mins = divmod(int(minutes or 0), 60)
    if hours and mins:
        return f"{hours} {h_unit} {mins} {m_unit}"
    if hours:
        return f"{hours} {h_unit}"
    return f"{mins} {m_unit}"


def format_distance(meters: float) -> str:
    """3250 → «3 км 250 м», 850 → «850 м»."""
    total = int(round(meters))
    km, m = divmod(total, 1000)
    if km and m:
        return f"{km} км {m} м"
    if km:
        return f"{km} км"
    return f"{m} м"


def as_utc(value: datetime) -> datetime:
    """SQLite теряет часовой пояс при чтении: время в базе всегда хранится в UTC."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
