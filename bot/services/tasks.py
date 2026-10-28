"""Задачи: план на день, перенос, итоги, алерты."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models import Employee, Role, Task, TaskAlert, TaskReport
from bot.task_rules import (
    CLOSED_STATUSES,
    AlertKind,
    BlockReason,
    TaskStatus,
    alert_to_send,
    next_streaks,
    normalize_text,
)


@dataclass
class AddedTask:
    task: Task
    continued: bool  # True — это незакрытая задача из прошлых дней, вписанная заново


@dataclass
class ReportAnswer:
    task_id: int
    status: TaskStatus
    reason: BlockReason | None = None
    comment: str | None = None


@dataclass
class RaisedAlert:
    alert: TaskAlert
    task: Task
    kind: AlertKind


def _open(stmt):
    return stmt.where(Task.status.not_in([s.value for s in CLOSED_STATUSES]))


async def get_task(session: AsyncSession, task_id: int) -> Task | None:
    return await session.get(Task, task_id, options=[selectinload(Task.employee), selectinload(Task.author)])


async def carry_candidates(session: AsyncSession, employee_id: int, today: date) -> list[Task]:
    """Незакрытые задачи из прошлых дней, которые ещё не в сегодняшнем плане."""
    result = await session.scalars(
        _open(select(Task).where(Task.employee_id == employee_id, Task.plan_date < today)).order_by(Task.id)
    )
    return list(result)


async def today_tasks(session: AsyncSession, employee_id: int, today: date) -> list[Task]:
    result = await session.scalars(
        select(Task).where(Task.employee_id == employee_id, Task.plan_date == today).order_by(Task.id)
    )
    return list(result)


async def open_today_tasks(session: AsyncSession, employee_id: int, today: date) -> list[Task]:
    """Задачи сегодняшнего плана, по которым ещё нет итога за сегодня."""
    reported = select(TaskReport.task_id).where(TaskReport.work_date == today)
    result = await session.scalars(
        _open(select(Task).where(Task.employee_id == employee_id, Task.plan_date == today))
        .where(Task.id.not_in(reported))
        .order_by(Task.id)
    )
    return list(result)


async def keep_for_today(session: AsyncSession, tasks: list[Task], keep_ids: set[int], today: date) -> None:
    """Переносит отмеченные задачи на сегодня, остальные убирает из плана (отменяет).

    Задачи от руководителя сотрудник убрать не может — они переносятся всегда.
    """
    now = datetime.now(timezone.utc)
    for task in tasks:
        if task.id in keep_ids or task.from_manager:
            task.plan_date = today
        else:
            task.status = TaskStatus.CANCELLED
            task.closed_at = now
    await session.commit()


async def add_tasks(
    session: AsyncSession,
    employee: Employee,
    lines: list[str],
    today: date,
    *,
    author: Employee | None = None,
    due_date: date | None = None,
) -> list[AddedTask]:
    """Добавляет задачи в план на сегодня.

    Если такая же незакрытая задача уже была раньше, она не дублируется:
    бот продолжает старую (тот же номер), чтобы правильно считать дни невыполнения.
    """
    open_tasks = list(
        await session.scalars(_open(select(Task).where(Task.employee_id == employee.id)))
    )
    by_text = {normalize_text(t.text): t for t in open_tasks}

    added: list[AddedTask] = []
    for line in lines:
        existing = by_text.get(normalize_text(line))
        if existing is not None:
            continued = existing.plan_date < today
            existing.plan_date = today
            if due_date is not None:
                existing.due_date = due_date
            added.append(AddedTask(existing, continued=continued))
            continue
        from_manager = author is not None and author.id != employee.id
        task = Task(
            employee_id=employee.id,
            author_id=(author or employee).id,
            text=line,
            status=TaskStatus.NEW,
            created_date=today,
            plan_date=today,
            due_date=due_date,
            from_manager=from_manager,
            accepted=not from_manager,
        )
        session.add(task)
        by_text[normalize_text(line)] = task
        added.append(AddedTask(task, continued=False))
    await session.commit()
    return added


async def remove_from_today(session: AsyncSession, task: Task) -> bool:
    """Удаляет задачу, вписанную по ошибке. Задачи руководителя и задачи с историей не удаляются."""
    if task.from_manager:
        return False
    has_history = await session.scalar(select(TaskReport.id).where(TaskReport.task_id == task.id).limit(1))
    if has_history:
        task.status = TaskStatus.CANCELLED
        task.closed_at = datetime.now(timezone.utc)
    else:
        await session.delete(task)
    await session.commit()
    return True


async def set_due(session: AsyncSession, task: Task, due: date) -> None:
    task.due_date = due
    await session.commit()


async def mark_started(session: AsyncSession, task: Task) -> None:
    if task.status == TaskStatus.NEW:
        task.status = TaskStatus.IN_PROGRESS
        await session.commit()


async def accept_task(session: AsyncSession, task: Task) -> None:
    task.accepted = True
    await session.commit()


async def save_day_report(
    session: AsyncSession, employee: Employee, answers: list[ReportAnswer], today: date, alert_days: int
) -> list[RaisedAlert]:
    """Сохраняет итоги дня по задачам, обновляет счётчики и возвращает новые алерты."""
    now = datetime.now(timezone.utc)
    raised: list[RaisedAlert] = []
    for answer in answers:
        task = await session.get(Task, answer.task_id)
        if task is None or task.employee_id != employee.id:
            continue
        exists = await session.scalar(
            select(TaskReport).where(TaskReport.task_id == task.id, TaskReport.work_date == today)
        )
        if exists is not None:
            continue  # итог за сегодня уже сохранён

        session.add(
            TaskReport(
                task_id=task.id,
                employee_id=employee.id,
                work_date=today,
                status=answer.status,
                reason=answer.reason,
                comment=(answer.comment or None),
            )
        )
        old = (task.not_done_streak, task.blocked_streak)
        new = next_streaks(answer.status, task.due_date, today, *old)
        task.not_done_streak, task.blocked_streak = new
        task.status = answer.status
        if answer.status in CLOSED_STATUSES:
            task.closed_at = now

        kind = alert_to_send(old, new, alert_days)
        if kind is not None:
            alert = TaskAlert(
                task_id=task.id,
                kind=kind,
                days=new[0] if kind == AlertKind.NOT_DONE else new[1],
            )
            session.add(alert)
            raised.append(RaisedAlert(alert=alert, task=task, kind=kind))
    await session.commit()
    return raised


async def day_results(session: AsyncSession, employee_id: int, today: date) -> list[TaskReport]:
    result = await session.scalars(
        select(TaskReport)
        .options(selectinload(TaskReport.task))
        .where(TaskReport.employee_id == employee_id, TaskReport.work_date == today)
        .order_by(TaskReport.task_id)
    )
    return list(result)


async def task_history(session: AsyncSession, task_id: int, limit: int = 5) -> list[TaskReport]:
    result = await session.scalars(
        select(TaskReport).where(TaskReport.task_id == task_id).order_by(TaskReport.work_date.desc()).limit(limit)
    )
    return list(reversed(list(result)))


async def managers(session: AsyncSession) -> list[Employee]:
    """Кому отправлять алерты: только руководителям (владельцу не приходят)."""
    result = await session.scalars(
        select(Employee).where(
            Employee.role == Role.MANAGER, Employee.is_active.is_(True), Employee.telegram_id.is_not(None)
        )
    )
    return list(result)


async def get_alert(session: AsyncSession, alert_id: int) -> TaskAlert | None:
    return await session.get(TaskAlert, alert_id, options=[selectinload(TaskAlert.task).selectinload(Task.employee)])


async def ack_alert(session: AsyncSession, alert: TaskAlert, manager: Employee) -> None:
    if alert.acked_at is None:
        alert.acked_by_id = manager.id
        alert.acked_at = datetime.now(timezone.utc)
        await session.commit()


async def cancel_task(session: AsyncSession, task: Task) -> None:
    task.status = TaskStatus.CANCELLED
    task.closed_at = datetime.now(timezone.utc)
    await session.commit()


async def assignable_employees(session: AsyncSession, manager: Employee) -> list[Employee]:
    result = await session.scalars(
        select(Employee)
        .where(Employee.is_active.is_(True), Employee.id != manager.id, Employee.role != Role.OWNER)
        .order_by(Employee.full_name)
    )
    return list(result)
