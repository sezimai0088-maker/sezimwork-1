"""Тексты отчётов для руководителя и владельца."""

from __future__ import annotations

from datetime import date
from html import escape

from bot.services.reports import ABSENT, FUTURE, NOT_EMPLOYED, PENDING, PRESENT, WEEKEND, EmployeeRow
from bot.texts import REASON_LABEL, STATUS_ICON, STATUS_LABEL
from bot.worktime import as_utc, format_duration

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

DAY_KIND_LABEL = {
    "day_off": "выходной",
    "sick": "больничный",
    "vacation": "отпуск",
    "trip": "командировка",
    "time_off": "отгул",
    "holiday": "праздник",
}
DAY_KIND_ICON = {
    "day_off": "🏖",
    "sick": "🤒",
    "vacation": "✈️",
    "trip": "🚗",
    "time_off": "🕐",
    "holiday": "🎉",
}
# Коды для табеля в Excel
DAY_CODE = {
    ABSENT: "Н",
    WEEKEND: "В",
    PENDING: "",
    FUTURE: "",
    NOT_EMPLOYED: "",
    "day_off": "В",
    "sick": "Б",
    "vacation": "О",
    "trip": "К",
    "time_off": "ОТ",
    "holiday": "П",
}
CODE_LEGEND = "Н — неявка, В — выходной, Б — больничный, О — отпуск, К — командировка, ОТ — отгул, П — праздник"


def fmt_day(d: date) -> str:
    return f"{d:%d.%m.%Y} ({WEEKDAYS[d.weekday()]})"


def fmt_period(start: date, end: date) -> str:
    return f"{start:%d.%m}–{end:%d.%m.%Y}"


def _hhmm(dt, tz) -> str:
    return as_utc(dt).astimezone(tz).strftime("%H:%M")


def daily_report(rows: list[EmployeeRow], day: date, tz) -> str:
    present = [r for r in rows if r.days[day].status == PRESENT]
    late = [r for r in present if r.days[day].late]
    absent = [r for r in rows if r.days[day].status == ABSENT]
    marked = [r for r in rows if r.days[day].mark is not None and r.days[day].status != PRESENT]

    lines = [
        f"📊 <b>Отчёт за {fmt_day(day)}</b>",
        f"Пришли: {len(present)} · опоздали: {len(late)} · не пришли: {len(absent)}"
        + (f" · отметки: {len(marked)}" if marked else ""),
        "",
    ]
    for r in rows:
        info = r.days[day]
        name = escape(r.employee.full_name)
        if info.status == PRESENT:
            att = info.attendance
            part = f"🟢 {name} — {_hhmm(att.check_in_at, tz)}"
            if info.late:
                part += f" (опозд. {format_duration(info.late)})"
            if att.check_out_at:
                where = "в полях" if att.check_out_mode == "field" else "офис"
                part += f" → {_hhmm(att.check_out_at, tz)} {where}"
            else:
                part += " → уход не отмечен"
            day_tasks = [t for t in r.task_reports if t.work_date == day]
            if day_tasks:
                done = sum(1 for t in day_tasks if t.status == "done")
                part += f" · задачи {done}/{len(day_tasks)}"
            if att.corrected:
                part += " ✏️"
            lines.append(part)
        elif info.status == ABSENT:
            lines.append(f"🔴 {name} — не пришёл")
        elif info.status == PENDING:
            lines.append(f"⏳ {name} — ещё не время")
        elif info.mark is not None:
            lines.append(f"{DAY_KIND_ICON.get(info.status, '•')} {name} — {DAY_KIND_LABEL.get(info.status, info.status)}")

    problems = []
    for r in rows:
        for t in r.task_reports:
            if t.work_date == day and t.status in ("not_done", "blocked", "cancelled"):
                detail = REASON_LABEL.get(t.reason, "") if t.reason else ""
                if t.comment:
                    detail = f"{detail}; {t.comment}" if detail else t.comment
                problems.append(
                    f"{STATUS_ICON[t.status]} {escape(r.employee.full_name)}: {escape(t.task.text)}"
                    + (f" — {escape(detail)}" if detail else f" — {STATUS_LABEL[t.status].lower()}")
                )
    if problems:
        lines += ["", "<b>Не выполнено:</b>", *problems]
    if not rows:
        lines.append("Сотрудников пока нет.")
    return "\n".join(lines)


def period_report(rows: list[EmployeeRow], start: date, end: date, title: str) -> str:
    lines = [f"📊 <b>{title}: {fmt_period(start, end)}</b>", ""]
    for r in rows:
        parts = [f"{r.present_days} дн.", format_duration(r.worked_total)]
        if r.late_count:
            parts.append(f"опозданий {r.late_count} ({format_duration(r.late_total)})")
        if r.absences:
            parts.append(f"неявок {r.absences}")
        for kind, count in r.marks.items():
            parts.append(f"{DAY_KIND_LABEL.get(kind, kind)} {count}")
        if r.no_checkout_count:
            parts.append(f"без ухода {r.no_checkout_count}")
        if r.tasks_total:
            parts.append(f"задачи {r.tasks_done}/{r.tasks_total} ({r.tasks_percent}%)")
        lines.append(f"<b>{escape(r.employee.full_name)}</b>: " + ", ".join(parts))
    if not rows:
        lines.append("Сотрудников пока нет.")
    lines.append("\nПодробно — в Excel-файле.")
    return "\n".join(lines)


def split_message(text: str, limit: int = 3900) -> list[str]:
    """Telegram принимает до 4096 символов: длинный отчёт делим по строкам."""
    chunks, current = [], ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > limit and current:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def day_card(name: str, day: date, info, schedule, tz) -> str:
    """Карточка дня сотрудника для руководителя (раздел «Табель»)."""
    lines = [f"🗓 <b>{escape(name)}</b> · {fmt_day(day)}", f"График: {schedule.describe()}"]
    if info.status == PRESENT:
        att = info.attendance
        line = f"Приход: {_hhmm(att.check_in_at, tz)}"
        if info.late:
            line += f" (опоздание {format_duration(info.late)})"
        lines.append(line)
        if att.check_out_at:
            where = "в полях" if att.check_out_mode == "field" else "в офисе"
            lines.append(f"Уход: {_hhmm(att.check_out_at, tz)} {where}, отработано {format_duration(att.worked_minutes or 0)}")
        else:
            lines.append("Уход: не отмечен")
        if att.corrected:
            lines.append("✏️ Время исправлялось руководителем")
    elif info.status == ABSENT:
        lines.append("🔴 Не пришёл")
    elif info.status == WEEKEND:
        lines.append("Нерабочий день по графику")
    elif info.status in (FUTURE, PENDING):
        lines.append("Отметок пока нет")
    if info.mark is not None:
        label = DAY_KIND_LABEL.get(info.mark.kind, info.mark.kind)
        lines.append(f"{DAY_KIND_ICON.get(info.mark.kind, '•')} Отметка дня: {label}")
    lines.append("\nЧто сделать?")
    return "\n".join(lines)


def mark_notice(kind: str, start: date, end: date) -> str:
    period = f"{start:%d.%m}" if start == end else f"{start:%d.%m}–{end:%d.%m}"
    return f"{DAY_KIND_ICON.get(kind, '•')} Руководитель отметил: {DAY_KIND_LABEL.get(kind, kind)}, {period}."


def correction_notice(kind: str, day: date, new_time: str, reason: str) -> str:
    what = "прихода" if kind == "in" else "ухода"
    return f"✏️ Руководитель исправил время {what} за {day:%d.%m}: {new_time}. Причина: {escape(reason)}"
