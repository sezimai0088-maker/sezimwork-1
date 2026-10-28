from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from bot.worktime import (
    as_utc,
    early_leave_minutes,
    format_duration,
    is_workday,
    late_minutes,
    worked_minutes,
)

TZ = ZoneInfo("Asia/Bishkek")
START = time(9, 0)
END = time(18, 0)


def at(h: int, m: int) -> datetime:
    return datetime(2026, 10, 29, h, m, tzinfo=TZ)


def test_on_time():
    assert late_minutes(at(8, 55), START, 5) == 0
    assert late_minutes(at(9, 0), START, 5) == 0


def test_within_grace_is_not_late():
    assert late_minutes(at(9, 5), START, 5) == 0


def test_late_counts_from_start():
    assert late_minutes(at(9, 7), START, 5) == 7
    assert late_minutes(at(10, 30), START, 5) == 90


def test_early_leave():
    assert early_leave_minutes(at(17, 30), END) == 30
    assert early_leave_minutes(at(18, 10), END) == 0


def test_worked():
    assert worked_minutes(at(9, 7), at(18, 5)) == 538


def test_format_duration():
    assert format_duration(7) == "7 мин"
    assert format_duration(60) == "1 ч"
    assert format_duration(538) == "8 ч 58 мин"


def test_workdays():
    week = frozenset({1, 2, 3, 4, 5})
    assert is_workday(date(2026, 10, 29), week)  # четверг
    assert not is_workday(date(2026, 10, 31), week)  # суббота


def test_as_utc_restores_naive_value_from_sqlite():
    naive = datetime(2026, 10, 29, 3, 7)
    assert as_utc(naive) == datetime(2026, 10, 29, 3, 7, tzinfo=timezone.utc)
    assert as_utc(naive).astimezone(TZ).hour == 9
