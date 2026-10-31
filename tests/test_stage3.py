"""Этап 3: графики, отметки дней, исправления, отчёты, Excel, миграция, расписание."""

import asyncio
import io
import sqlite3
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")
pytest.importorskip("xlsxwriter")

from bot.config import Settings  # noqa: E402
from bot.db import init_db, make_engine, make_sessionmaker  # noqa: E402
from bot.excel import build_timesheet  # noqa: E402
from bot.models import DayKind, Role  # noqa: E402
from bot.report_texts import daily_report, period_report, split_message  # noqa: E402
from bot.schedule import parse_hhmm, parse_range, schedule_for  # noqa: E402
from bot.services import attendance as att  # noqa: E402
from bot.services import calendar as cal  # noqa: E402
from bot.services import employees as emp  # noqa: E402
from bot.services import tasks as task_svc  # noqa: E402
from bot.services.reports import (  # noqa: E402
    ABSENT,
    PRESENT,
    WEEKEND,
    load_period,
    month_bounds,
    previous_month,
    previous_week,
    week_bounds,
)
from bot.task_rules import TaskStatus  # noqa: E402

TZ = ZoneInfo("Asia/Bishkek")
OFFICE = (42.857044, 74.641376)
MON, TUE, WED, THU, FRI, SAT = (date(2026, 10, d) for d in (26, 27, 28, 29, 30, 31))


def settings(**kw) -> Settings:
    base = dict(
        _env_file=None,
        bot_token="t",
        owner_phone="+996700000100",
        office_lat=OFFICE[0],
        office_lon=OFFICE[1],
        database_url="sqlite+aiosqlite:///:memory:",
        work_start="09:00",
        work_end="18:00",
        group_lang="ru",
    )
    base.update(kw)
    return Settings(**base)


def local(day: date, h: int, m: int) -> datetime:
    return datetime.combine(day, time(h, m), tzinfo=TZ).astimezone(timezone.utc)


def run(fn, **kw):
    async def wrapper():
        s = settings(**kw)
        engine = make_engine(s.database_url)
        await init_db(engine)
        async with make_sessionmaker(engine)() as session:
            await fn(session, s)
        await engine.dispose()

    asyncio.run(wrapper())


async def _backdate(session, *people):
    for p in people:
        p.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    await session.commit()


# ---------- график ----------


def test_parse_schedule_helpers():
    assert parse_hhmm("8.30") == time(8, 30)
    assert parse_hhmm("25:00") is None
    assert parse_range("08:30 – 17:30") == (time(8, 30), time(17, 30))
    assert parse_range("18:00-09:00") is None


def test_individual_schedule_overrides_default():
    s = settings()

    class P:
        work_start = "08:00"
        work_end = "17:00"
        work_days = "1,2,3,4,5,6"

    sched = schedule_for(P(), s)
    assert sched.start == time(8, 0) and sched.is_workday(SAT)
    assert sched.describe() == "08:00–17:00, Пн–Сб"
    default = schedule_for(object(), s)
    assert default.start == time(9, 0) and not default.is_workday(SAT)


def test_late_uses_individual_schedule():
    async def scenario(session, s):
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        e.work_start = "08:00"
        await session.commit()
        r = await att.check_in(session, s, e, lat=OFFICE[0], lon=OFFICE[1], accuracy_m=10, now=local(THU, 8, 20))
        assert r.attendance.late_minutes == 20

    run(scenario)


# ---------- отметки дней и исправления ----------


def test_sick_mark_cancels_lateness_and_absence():
    async def scenario(session, s):
        boss, _ = await emp.add_employee(session, phone="996555000009", full_name="Нурлан", role=Role.MANAGER)
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        await _backdate(session, boss, e)
        marked = await cal.set_marks(
            session, employee_id=e.id, start=TUE, days=2, kind=DayKind.SICK, comment=None, actor=boss
        )
        assert marked == [TUE, WED]
        r = await att.check_in(session, s, e, lat=OFFICE[0], lon=OFFICE[1], accuracy_m=10, now=local(TUE, 10, 0))
        assert r.attendance.late_minutes == 0  # пришёл в больничный день — без опоздания

        rows = await load_period(session, s, MON, THU, now=local(THU, 20, 0))
        row = next(x for x in rows if x.employee.id == e.id)
        assert row.days[MON].status == ABSENT
        assert row.days[TUE].status == PRESENT
        assert row.days[WED].status == "sick"
        assert row.absences == 2  # пн и чт
        assert row.marks["sick"] == 1

        assert await cal.remove_mark(session, employee_id=e.id, day=WED, actor=boss)
        rows = await load_period(session, s, WED, WED, now=local(THU, 20, 0))
        assert next(x for x in rows if x.employee.id == e.id).days[WED].status == ABSENT

    run(scenario)


def test_holiday_for_everyone():
    async def scenario(session, s):
        boss, _ = await emp.add_employee(session, phone="996555000009", full_name="Нурлан", role=Role.MANAGER)
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        await _backdate(session, boss, e)
        await cal.set_marks(session, employee_id=None, start=FRI, days=1, kind=DayKind.HOLIDAY, comment=None, actor=boss)
        await cal.set_marks(session, employee_id=None, start=FRI, days=1, kind=DayKind.HOLIDAY, comment=None, actor=boss)
        rows = await load_period(session, s, FRI, SAT, now=local(SAT, 12, 0))
        assert all(r.days[FRI].status == "holiday" for r in rows)
        assert all(r.days[SAT].status == WEEKEND for r in rows)

    run(scenario)


def test_correct_times_recomputes_and_logs():
    async def scenario(session, s):
        boss, _ = await emp.add_employee(session, phone="996555000009", full_name="Нурлан", role=Role.MANAGER)
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        # Нет прихода: уход исправить нельзя
        with pytest.raises(cal.CorrectionError):
            await cal.correct_time(session, s, employee=e, day=THU, kind="out", new_time=time(18, 0), reason="x", actor=boss)
        a = await cal.correct_time(
            session, s, employee=e, day=THU, kind="in", new_time=time(9, 20), reason="GPS не работал", actor=boss
        )
        assert a.late_minutes == 20 and a.corrected
        a = await cal.correct_time(session, s, employee=e, day=THU, kind="out", new_time=time(17, 20), reason="забыл", actor=boss)
        assert a.worked_minutes == 480 and a.early_leave_minutes == 40
        a = await cal.correct_time(session, s, employee=e, day=THU, kind="in", new_time=time(9, 0), reason="ошибся", actor=boss)
        assert a.late_minutes == 0 and a.worked_minutes == 500
        with pytest.raises(cal.CorrectionError):
            await cal.correct_time(session, s, employee=e, day=THU, kind="out", new_time=time(8, 0), reason="x", actor=boss)
        log = await cal.recent_audit(session, e.id)
        assert [entry.action for entry in log][:3] == ["check_in", "check_out", "check_in"]
        assert log[0].old_value == "09:20" and log[0].new_value == "09:00" and log[0].reason == "ошибся"

    run(scenario)


def test_set_schedule_logged():
    async def scenario(session, s):
        boss, _ = await emp.add_employee(session, phone="996555000009", full_name="Нурлан", role=Role.MANAGER)
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        await cal.set_schedule(
            session, employee=e, start=time(8, 0), end=time(17, 0), work_days=frozenset({1, 2, 3, 4, 5, 6}), actor=boss, settings=s
        )
        log = await cal.recent_audit(session, e.id)
        assert log[0].action == "schedule" and log[0].new_value == "08:00–17:00, Пн–Сб"

    run(scenario)


# ---------- отчёты и Excel ----------


def test_period_helpers():
    assert week_bounds(THU) == (MON, date(2026, 11, 1))
    assert previous_week(THU) == (date(2026, 10, 19), date(2026, 10, 25))
    assert month_bounds(THU) == (date(2026, 10, 1), date(2026, 10, 31))
    assert previous_month(date(2026, 11, 1)) == (date(2026, 10, 1), date(2026, 10, 31))
    assert previous_month(date(2026, 1, 1)) == (date(2025, 12, 1), date(2025, 12, 31))


def test_reports_and_excel():
    async def scenario(session, s):
        e1, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек Асанов")
        e2, _ = await emp.add_employee(session, phone="996555000002", full_name="Айгуль Токтосунова")
        await _backdate(session, e1, e2)
        for day, h, m in ((MON, 9, 0), (TUE, 9, 15), (WED, 8, 50)):
            r = await att.check_in(session, s, e1, lat=OFFICE[0], lon=OFFICE[1], accuracy_m=10, now=local(day, h, m))
            await att.check_out(session, s, r.attendance, lat=OFFICE[0], lon=OFFICE[1], accuracy_m=10, now=local(day, 18, 0))
        t = (await task_svc.add_tasks(session, e1, ["Отчёт", "Склад"], WED))
        await task_svc.save_day_report(
            session, e1,
            [task_svc.ReportAnswer(t[0].task.id, TaskStatus.DONE), task_svc.ReportAnswer(t[1].task.id, TaskStatus.NOT_DONE, comment="нет ключа")],
            WED, 2,
        )

        rows = await load_period(session, s, MON, WED, now=local(THU, 10, 0))
        r1 = next(r for r in rows if r.employee.id == e1.id)
        r2 = next(r for r in rows if r.employee.id == e2.id)
        assert r1.present_days == 3 and r1.late_count == 1 and r1.late_total == 15
        assert r1.worked_total == 540 + 525 + 550
        assert r1.tasks_done == 1 and r1.tasks_total == 2 and r1.tasks_percent == 50
        assert r2.absences == 3

        day_text = daily_report(await load_period(session, s, WED, WED, now=local(WED, 20, 0)), WED, TZ)
        assert "Пришли: 1" in day_text and "не пришли: 1" in day_text
        assert "Айгуль Токтосунова — не пришёл" in day_text
        assert "задачи 1/2" in day_text and "нет ключа" in day_text

        week_text = period_report(rows, MON, WED, "Отчёт за неделю")
        assert "Айбек Асанов</b>: 3 дн." in week_text and "опозданий 1 (15 мин)" in week_text
        assert "неявок 3" in week_text

        data = build_timesheet(rows, MON, WED, TZ, "Отчёт за неделю")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = zf.namelist()
            assert "xl/worksheets/sheet1.xml" in names and "xl/worksheets/sheet3.xml" in names
            shared = zf.read("xl/sharedStrings.xml").decode()
            workbook = zf.read("xl/workbook.xml").decode()
        assert "Табель" in workbook and "Подробно" in workbook and "Задачи" in workbook
        assert "Айгуль Токтосунова" in shared and "09:15" in shared and "нет ключа" in shared

    run(scenario)


def test_split_long_message():
    text = "\n".join(f"строка {i} " + "x" * 50 for i in range(200))
    parts = split_message(text, limit=1000)
    assert all(len(p) <= 1000 for p in parts)
    assert "".join(parts).count("строка") == 200


# ---------- миграция старой базы ----------


def test_old_database_gets_new_columns(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE employees (id INTEGER PRIMARY KEY, phone VARCHAR(20), full_name VARCHAR(200), role VARCHAR(20),"
        " telegram_id BIGINT, is_active BOOLEAN, created_at DATETIME)"
    )
    con.execute("INSERT INTO employees VALUES (1, '996555', 'Старый сотрудник', 'employee', 5, 1, '2026-10-01 00:00:00')")
    con.commit()
    con.close()

    async def go():
        engine = make_engine(f"sqlite+aiosqlite:///{db}")
        await init_db(engine)
        await engine.dispose()

    asyncio.run(go())
    con = sqlite3.connect(db)
    cols = {row[1] for row in con.execute("PRAGMA table_info(employees)")}
    assert {"work_start", "work_end", "work_days"} <= cols
    assert con.execute("SELECT full_name FROM employees").fetchone()[0] == "Старый сотрудник"
    tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"day_marks", "audit_log", "tasks"} <= tables
    con.close()
