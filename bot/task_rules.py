"""Правила задач без базы данных: статусы, перенос, счётчики, разбор текста."""

from __future__ import annotations

import re
from datetime import date, timedelta
from enum import StrEnum


class TaskStatus(StrEnum):
    NEW = "new"                # в плане, ещё не начата
    IN_PROGRESS = "in_progress"  # начата в течение дня
    DONE = "done"              # ✅ Выполнено
    CONTINUE = "continue"      # 🔄 В работе (многодневная, по плану)
    NOT_DONE = "not_done"      # ⏳ Не успел
    BLOCKED = "blocked"        # 🚧 Не по моей вине
    CANCELLED = "cancelled"    # ❌ Отменена


# Статусы, которые сотрудник выбирает в конце дня
FINAL_STATUSES = (
    TaskStatus.DONE,
    TaskStatus.CONTINUE,
    TaskStatus.NOT_DONE,
    TaskStatus.BLOCKED,
    TaskStatus.CANCELLED,
)
# После этих статусов задача закрывается и не переносится
CLOSED_STATUSES = frozenset({TaskStatus.DONE, TaskStatus.CANCELLED})


class BlockReason(StrEnum):
    MATERIALS = "materials"
    WAITING = "waiting"
    EQUIPMENT = "equipment"
    WEATHER = "weather"
    MANAGER = "manager"
    OTHER = "other"


class AlertKind(StrEnum):
    NOT_DONE = "not_done"   # не выполняется по вине сотрудника
    BLOCKED = "blocked"     # сотруднику нужна помощь


def needs_comment(status: TaskStatus, reason: BlockReason | None) -> bool:
    """Комментарий обязателен для «Отменена» и для причины «Другое»."""
    return status == TaskStatus.CANCELLED or (status == TaskStatus.BLOCKED and reason == BlockReason.OTHER)


def next_streaks(
    status: TaskStatus, due_date: date | None, today: date, not_done_streak: int, blocked_streak: int
) -> tuple[int, int]:
    """Обновляет счётчики дней подряд после итога дня.

    - «Не успел» → +1 к счётчику невыполнения;
    - «В работе» после срока → тоже +1; «В работе» в срок → счётчик сбрасывается;
    - «Не по моей вине» → +1 к отдельному счётчику, счётчик невыполнения не растёт;
    - любой другой итог сбрасывает счётчик «Не по моей вине».
    """
    if status == TaskStatus.NOT_DONE:
        return not_done_streak + 1, 0
    if status == TaskStatus.CONTINUE:
        overdue = due_date is not None and due_date < today
        return (not_done_streak + 1 if overdue else 0), 0
    if status == TaskStatus.BLOCKED:
        return not_done_streak, blocked_streak + 1
    return 0, 0


def alert_to_send(
    old: tuple[int, int], new: tuple[int, int], threshold: int
) -> AlertKind | None:
    """Алерт отправляется один раз — в день, когда счётчик достиг порога."""
    if new[0] >= threshold > old[0]:
        return AlertKind.NOT_DONE
    if new[1] >= threshold > old[1]:
        return AlertKind.BLOCKED
    return None


_BULLET = re.compile(r"^\s*(?:[-–—•*·]+|\d{1,2}\s*[.)]|\(\d{1,2}\))\s*")


def parse_task_lines(text: str, *, max_len: int = 300) -> list[str]:
    """Превращает сообщение в список задач: каждая строка — задача.

    Убирает номера и маркеры («1.», «2)», «-», «•»), пустые строки и повторы.
    """
    tasks: list[str] = []
    seen: set[str] = set()
    for raw in (text or "").splitlines():
        line = _BULLET.sub("", raw).strip()
        if len(line) < 2:
            continue
        line = line[:max_len]
        key = normalize_text(line)
        if key in seen:
            continue
        seen.add(key)
        tasks.append(line)
    return tasks


def normalize_text(text: str) -> str:
    """Для сравнения задач: регистр, ё/е, пробелы и знаки препинания не важны."""
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def due_options(today: date) -> dict[str, date]:
    """Варианты срока для кнопок: сегодня, завтра, до конца рабочей недели (пятница)."""
    days_to_friday = (4 - today.weekday()) % 7
    friday = today + timedelta(days=days_to_friday)
    options = {"today": today, "tomorrow": today + timedelta(days=1)}
    if friday > options["tomorrow"]:
        options["week"] = friday
    return options
