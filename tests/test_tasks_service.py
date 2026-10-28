"""Задачи на настоящей базе SQLite в памяти: перенос, повторы, итоги, алерты."""

import asyncio
from datetime import date

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")

from bot.db import init_db, make_engine, make_sessionmaker  # noqa: E402
from bot.models import Role  # noqa: E402
from bot.services import employees as emp  # noqa: E402
from bot.services import tasks as svc  # noqa: E402
from bot.task_rules import AlertKind, BlockReason, TaskStatus  # noqa: E402

D1, D2, D3 = date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29)


def run(fn):
    async def wrapper():
        engine = make_engine("sqlite+aiosqlite:///:memory:")
        await init_db(engine)
        async with make_sessionmaker(engine)() as session:
            await fn(session)
        await engine.dispose()

    asyncio.run(wrapper())


def test_add_and_carry_over_keeps_same_task():
    async def scenario(session):
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        added = await svc.add_tasks(session, e, ["Сдать отчёт", "Позвонить"], D1)
        assert [a.continued for a in added] == [False, False]
        await svc.save_day_report(
            session,
            e,
            [svc.ReportAnswer(added[0].task.id, TaskStatus.NOT_DONE), svc.ReportAnswer(added[1].task.id, TaskStatus.DONE)],
            D1,
            alert_days=2,
        )
        carry = await svc.carry_candidates(session, e.id, D2)
        assert [t.text for t in carry] == ["Сдать отчёт"]  # выполненная не переносится

        await svc.keep_for_today(session, carry, {carry[0].id}, D2)
        today = await svc.today_tasks(session, e.id, D2)
        assert [t.id for t in today] == [added[0].task.id]

    run(scenario)


def test_retyped_task_continues_old_one():
    async def scenario(session):
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        first = (await svc.add_tasks(session, e, ["Сдать отчёт"], D1))[0].task
        await svc.save_day_report(session, e, [svc.ReportAnswer(first.id, TaskStatus.NOT_DONE)], D1, 2)
        again = await svc.add_tasks(session, e, ["сдать отчет"], D2)
        assert again[0].task.id == first.id
        assert again[0].continued is True

    run(scenario)


def test_dropped_carry_task_is_cancelled():
    async def scenario(session):
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        t = (await svc.add_tasks(session, e, ["Лишняя задача"], D1))[0].task
        carry = await svc.carry_candidates(session, e.id, D2)
        await svc.keep_for_today(session, carry, set(), D2)
        assert t.status == TaskStatus.CANCELLED
        assert await svc.carry_candidates(session, e.id, D3) == []

    run(scenario)


def test_manager_task_cannot_be_dropped_or_deleted():
    async def scenario(session):
        boss, _ = await emp.add_employee(session, phone="996555000009", full_name="Нурлан", role=Role.MANAGER)
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        t = (await svc.add_tasks(session, e, ["Задача от руководителя"], D1, author=boss, due_date=D3))[0].task
        assert t.from_manager and not t.accepted and t.due_date == D3
        carry = await svc.carry_candidates(session, e.id, D2)
        await svc.keep_for_today(session, carry, set(), D2)
        assert t.plan_date == D2 and t.status == TaskStatus.NEW
        assert await svc.remove_from_today(session, t) is False

    run(scenario)


def test_alert_after_two_days_not_done():
    async def scenario(session):
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        t = (await svc.add_tasks(session, e, ["Сдать отчёт"], D1))[0].task
        r1 = await svc.save_day_report(session, e, [svc.ReportAnswer(t.id, TaskStatus.NOT_DONE)], D1, 2)
        assert r1 == []
        await svc.keep_for_today(session, await svc.carry_candidates(session, e.id, D2), {t.id}, D2)
        r2 = await svc.save_day_report(
            session, e, [svc.ReportAnswer(t.id, TaskStatus.NOT_DONE, comment="не хватило времени")], D2, 2
        )
        assert len(r2) == 1 and r2[0].kind == AlertKind.NOT_DONE and r2[0].alert.days == 2
        history = await svc.task_history(session, t.id, limit=2)
        assert [h.work_date for h in history] == [D1, D2]

        boss, _ = await emp.add_employee(session, phone="996555000009", full_name="Нурлан", role=Role.MANAGER)
        alert = await svc.get_alert(session, r2[0].alert.id)
        await svc.ack_alert(session, alert, boss)
        assert alert.acked_by_id == boss.id

    run(scenario)


def test_blocked_two_days_raises_help_alert():
    async def scenario(session):
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        t = (await svc.add_tasks(session, e, ["Покрасить фасад"], D1))[0].task
        blocked = svc.ReportAnswer(t.id, TaskStatus.BLOCKED, reason=BlockReason.WEATHER)
        await svc.save_day_report(session, e, [blocked], D1, 2)
        await svc.keep_for_today(session, await svc.carry_candidates(session, e.id, D2), {t.id}, D2)
        raised = await svc.save_day_report(session, e, [blocked], D2, 2)
        assert [r.kind for r in raised] == [AlertKind.BLOCKED]
        assert t.not_done_streak == 0

    run(scenario)


def test_report_saved_once_per_day_and_open_list_shrinks():
    async def scenario(session):
        e, _ = await emp.add_employee(session, phone="996555000001", full_name="Айбек")
        added = await svc.add_tasks(session, e, ["А задача", "Б задача"], D1)
        assert len(await svc.open_today_tasks(session, e.id, D1)) == 2
        ans = [svc.ReportAnswer(added[0].task.id, TaskStatus.CONTINUE)]
        await svc.save_day_report(session, e, ans, D1, 2)
        await svc.save_day_report(session, e, ans, D1, 2)  # повтор не создаёт второй записи
        assert len(await svc.day_results(session, e.id, D1)) == 1
        assert [t.text for t in await svc.open_today_tasks(session, e.id, D1)] == ["Б задача"]

    run(scenario)
