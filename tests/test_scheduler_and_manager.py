"""Расписание (напоминания, сводка, отчёты, повтор алертов, бэкап) и кнопки руководителя «Отчёты» и «Табель»."""

import asyncio
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

pytest.importorskip("aiogram")
pytest.importorskip("xlsxwriter")

from sqlalchemy import select  # noqa: E402

from bot.db import make_sessionmaker  # noqa: E402
from bot.models import Attendance, AuditLog, DayMark, Employee, TaskAlert  # noqa: E402
from bot.scheduler import make_backup, tick  # noqa: E402
from bot.services import attendance as att  # noqa: E402
from bot.services import tasks as task_svc  # noqa: E402
from bot.task_rules import TaskStatus  # noqa: E402
from tests.test_bot_flow import GROUP_ID, MANAGER, OFFICE, OWNER, WORKER, Harness, onboard, run  # noqa: E402

TZ = ZoneInfo("Asia/Bishkek")
THU = date(2026, 10, 29)


def at(day: date, h: int, m: int) -> datetime:
    return datetime.combine(day, time(h, m), tzinfo=TZ)


async def _employee(h: Harness, uid: int) -> Employee:
    async with make_sessionmaker(h.engine)() as session:
        return await session.scalar(select(Employee).where(Employee.telegram_id == uid))


def test_reminders_summary_and_daily_report():
    async def scenario(h: Harness):
        await onboard(h)
        sm = make_sessionmaker(h.engine)
        # Рабочие дни в тестовом харнессе — все 7, начало 09:00
        await tick(h.bot, sm, h.settings, now=at(THU, 9, 10))
        assert not any("ещё не отметились" in t for t in h.tg.texts(WORKER))

        await tick(h.bot, sm, h.settings, now=at(THU, 9, 16))
        assert "Вы ещё не отметились" in h.tg.texts(WORKER)[-1]
        assert "Вы ещё не отметились" in h.tg.texts(MANAGER)[-1]
        assert not any("не отметились" in t for t in h.tg.texts(OWNER))  # владельцу не напоминаем
        count = len(h.tg.texts(WORKER))
        await tick(h.bot, sm, h.settings, now=at(THU, 9, 20))
        assert len(h.tg.texts(WORKER)) == count  # без повторов

        await tick(h.bot, sm, h.settings, now=at(THU, 9, 31))
        summary = h.tg.texts(GROUP_ID)[-1]
        assert "Ещё не отметились" in summary and "Айбек Асанов" in summary and "Нурлан Касымов" in summary

        worker = await _employee(h, WORKER)
        async with sm() as session:
            await att.check_in(
                session, h.settings, worker, lat=OFFICE[0], lon=OFFICE[1], accuracy_m=10,
                now=at(THU, 9, 40).astimezone(timezone.utc),
            )
        await tick(h.bot, sm, h.settings, now=at(THU, 18, 31))
        assert "не забудьте" in h.tg.texts(WORKER)[-1].lower()
        assert not any("Рабочий день закончился" in t for t in h.tg.texts(MANAGER))

        await tick(h.bot, sm, h.settings, now=at(THU, 19, 0))
        for uid in (MANAGER, OWNER):
            report = h.tg.texts(uid)[-1]
            assert "Отчёт за 29.10.2026" in report
            assert "Айбек Асанов — 09:40" in report
        assert "Айбек" not in h.tg.texts(WORKER)[-1]  # сотрудник отчёт не получает

    run(scenario)


def test_weekly_and_monthly_reports_with_excel():
    async def scenario(h: Harness):
        await onboard(h)
        sm = make_sessionmaker(h.engine)
        await tick(h.bot, sm, h.settings, now=at(date(2026, 11, 2), 9, 5))  # понедельник
        assert "Отчёт за неделю: 26.10–01.11.2026" in h.tg.texts(OWNER)[-1]
        docs = h.tg.documents(OWNER)
        assert docs and docs[-1].document.filename == "tabel_2026-10-26_2026-11-01.xlsx"

        await tick(h.bot, sm, h.settings, now=at(date(2026, 12, 1), 9, 5))  # 1-е число
        assert any("Отчёт за месяц: 01.11–30.11.2026" in t for t in h.tg.texts(MANAGER))
        assert h.tg.documents(MANAGER)[-1].document.filename == "tabel_2026-11-01_2026-11-30.xlsx"

    run(scenario)


def test_unacked_alert_repeats_next_morning():
    async def scenario(h: Harness):
        await onboard(h)
        sm = make_sessionmaker(h.engine)
        worker = await _employee(h, WORKER)
        async with sm() as session:
            t = (await task_svc.add_tasks(session, worker, ["Сдать отчёт"], THU))[0].task
            session.add(TaskAlert(task_id=t.id, kind="not_done", days=2, created_at=at(THU, 18, 0).astimezone(timezone.utc)))
            await session.commit()
        await tick(h.bot, sm, h.settings, now=at(THU + timedelta(days=1), 9, 1))
        text = h.tg.texts(MANAGER)[-1]
        assert "Напоминание" in text and "Сдать отчёт" in text
        assert not any("Напоминание" in x for x in h.tg.texts(OWNER))

        # Принятый алерт больше не повторяется
        async with sm() as session:
            alert = await session.scalar(select(TaskAlert))
            alert.acked_at = datetime.now(timezone.utc)
            await session.commit()
        before = len(h.tg.texts(MANAGER))
        await tick(h.bot, sm, h.settings, now=at(THU + timedelta(days=2), 9, 1))
        assert len(h.tg.texts(MANAGER)) == before

    run(scenario)


def test_backup_copy(tmp_path):
    src = tmp_path / "bot.db"
    con = sqlite3.connect(src)
    con.execute("CREATE TABLE t (x)")
    con.execute("INSERT INTO t VALUES (42)")
    con.commit()
    con.close()
    make_backup(src, tmp_path / "copy.db")
    assert sqlite3.connect(tmp_path / "copy.db").execute("SELECT x FROM t").fetchone()[0] == 42


# ---------- кнопки руководителя ----------


def test_manager_timesheet_marks_corrections_schedule():
    async def scenario(h: Harness):
        await onboard(h)
        assert any(
            b.text == "🗓 Табель" for row in h.tg.last_markup(MANAGER).keyboard for b in row
        )
        await h.text(MANAGER, "🗓 Табель")
        await h.press(MANAGER, h.find_button(MANAGER, "Айбек"))
        await h.press(MANAGER, h.find_button(MANAGER, "Сегодня"))
        await h.press(MANAGER, h.find_button(MANAGER, "🤒 Больничный"))
        await h.press(MANAGER, h.find_button(MANAGER, "3"))
        assert "больничный" in h.tg.texts(WORKER)[-1]  # сотрудник получил уведомление

        async with make_sessionmaker(h.engine)() as session:
            marks = list(await session.scalars(select(DayMark)))
        assert len(marks) == 3 and {m.kind for m in marks} == {"sick"}

        # Исправить время прихода с причиной
        await h.press(MANAGER, h.find_button(MANAGER, "✏️ Время прихода"))
        await h.text(MANAGER, "25:00")
        assert "Не понял время" in h.tg.texts(MANAGER)[-1]
        await h.text(MANAGER, "09:00")
        await h.text(MANAGER, "не сработала геолокация")
        assert "исправил время прихода" in h.tg.texts(WORKER)[-1]
        async with make_sessionmaker(h.engine)() as session:
            a = await session.scalar(select(Attendance))
            log = list(await session.scalars(select(AuditLog).where(AuditLog.action == "check_in")))
        assert a.corrected and log[0].reason == "не сработала геолокация"

        # Изменить график
        await h.press(MANAGER, h.find_button(MANAGER, "⏰ Изменить график"))
        await h.text(MANAGER, "08:30-17:30")
        await h.press(MANAGER, h.find_button(MANAGER, "Пн–Сб"))
        worker = await _employee(h, WORKER)
        assert (worker.work_start, worker.work_end, worker.work_days) == ("08:30", "17:30", "1,2,3,4,5,6")

        # Сотрудник не видит табель
        await h.text(WORKER, "🗓 Табель")
        assert "только руководителю" in h.tg.texts(WORKER)[-1]

    run(scenario)


def test_manager_reports_menu():
    async def scenario(h: Harness):
        await onboard(h)
        await h.location(WORKER, *OFFICE)
        await h.text(MANAGER, "📊 Отчёты")
        await h.press(MANAGER, h.find_button(MANAGER, "Сегодня"))
        assert "Отчёт за" in h.tg.texts(MANAGER)[-1] and "Айбек Асанов" in h.tg.texts(MANAGER)[-1]
        await h.press(MANAGER, "rep:week")
        assert h.tg.documents(MANAGER), "Excel-табель не отправлен"

    run(scenario)


def test_holiday_for_all_via_buttons():
    async def scenario(h: Harness):
        await onboard(h)
        await h.text(OWNER, "🗓 Табель")
        await h.press(OWNER, h.find_button(OWNER, "🎉 Праздник для всех"))
        await h.press(OWNER, h.find_button(OWNER, "Завтра"))
        await h.press(OWNER, h.find_button(OWNER, "🎉 Праздник"))
        await h.press(OWNER, h.find_button(OWNER, "1"))
        async with make_sessionmaker(h.engine)() as session:
            mark = await session.scalar(select(DayMark))
        assert mark.employee_id is None and mark.kind == "holiday"

    run(scenario)
