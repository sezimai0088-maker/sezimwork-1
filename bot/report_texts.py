"""Тексты отчётов для руководителя и владельца (на языке получателя)."""

from __future__ import annotations

from datetime import date
from html import escape

from bot import texts
from bot.i18n import KY, get_lang, tr
from bot.services.reports import ABSENT, FUTURE, NOT_EMPLOYED, PENDING, PRESENT, WEEKEND, EmployeeRow
from bot.worktime import as_utc, format_distance, format_duration

WEEKDAYS_RU = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
WEEKDAYS_KY = ["дш", "шш", "шр", "бш", "жм", "иш", "жк"]

DAY_KIND_LABEL_RU = {
    "day_off": "выходной",
    "sick": "больничный",
    "vacation": "отпуск",
    "trip": "командировка",
    "time_off": "отгул",
    "holiday": "праздник",
}
DAY_KIND_LABEL_KY = {
    "day_off": "дем алыш",
    "sick": "оорулуу",
    "vacation": "өргүү",
    "trip": "иш сапар",
    "time_off": "отгул",
    "holiday": "майрам",
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
DAY_CODE_RU = {
    ABSENT: "Н", WEEKEND: "В", PENDING: "", FUTURE: "", NOT_EMPLOYED: "",
    "day_off": "В", "sick": "Б", "vacation": "О", "trip": "К", "time_off": "ОТ", "holiday": "П",
}
DAY_CODE_KY = {
    ABSENT: "К", WEEKEND: "Д", PENDING: "", FUTURE: "", NOT_EMPLOYED: "",
    "day_off": "Д", "sick": "О", "vacation": "Ө", "trip": "ИС", "time_off": "ОТ", "holiday": "М",
}


def weekdays() -> list[str]:
    return WEEKDAYS_KY if get_lang() == KY else WEEKDAYS_RU


def day_kind_label(kind: str) -> str:
    labels = DAY_KIND_LABEL_KY if get_lang() == KY else DAY_KIND_LABEL_RU
    return labels.get(kind, kind)


def day_code(status: str) -> str:
    codes = DAY_CODE_KY if get_lang() == KY else DAY_CODE_RU
    return codes.get(status, "")


def code_legend() -> str:
    return tr(
        "Н — неявка, В — выходной, Б — больничный, О — отпуск, К — командировка, ОТ — отгул, П — праздник",
        "К — келген жок, Д — дем алыш, О — оорулуу, Ө — өргүү, ИС — иш сапар, ОТ — отгул, М — майрам",
    )


def period_title(kind: str) -> str:
    """kind: week | month."""
    if kind == "week":
        return tr("Отчёт за неделю", "Жумалык отчет")
    return tr("Отчёт за месяц", "Айлык отчет")


def fmt_day(d: date) -> str:
    return f"{d:%d.%m.%Y} ({weekdays()[d.weekday()]})"


def fmt_period(start: date, end: date) -> str:
    return f"{start:%d.%m}–{end:%d.%m.%Y}"


def _hhmm(dt, tz) -> str:
    return as_utc(dt).astimezone(tz).strftime("%H:%M")


def times_word(n: int) -> str:
    """«3 раза» / «3 жолу»."""
    if get_lang() == KY:
        return f"{n} жолу"
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} раз"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return f"{n} раза"
    return f"{n} раз"


def outside_part(att) -> str:
    """« · вне офиса 3 км 250 м: на объекте» — для отчётов."""
    if not att.is_outside:
        return ""
    part = f" · 🟠 {tr('вне офиса', 'кеңседен тышкары')} {format_distance(att.check_in_distance_m or 0)}"
    if att.check_in_comment:
        part += f": {escape(att.check_in_comment)}"
    return part


def late_ranking(rows: list[EmployeeRow]) -> list[EmployeeRow]:
    """Кто опаздывал — по убыванию общего времени опозданий."""
    return sorted((r for r in rows if r.late_count), key=lambda r: (-r.late_total, -r.late_count))


def daily_report(rows: list[EmployeeRow], day: date, tz) -> str:
    present = [r for r in rows if r.days[day].status == PRESENT]
    late = [r for r in present if r.days[day].late]
    absent = [r for r in rows if r.days[day].status == ABSENT]
    marked = [r for r in rows if r.days[day].mark is not None and r.days[day].status != PRESENT]
    outside = [r for r in present if r.days[day].attendance.is_outside]

    summary = tr(
        f"Пришли: {len(present)} · опоздали: {len(late)} · не пришли: {len(absent)}",
        f"Келди: {len(present)} · кечикти: {len(late)} · келген жок: {len(absent)}",
    )
    if outside:
        summary += tr(f" · вне офиса: {len(outside)}", f" · кеңседен тышкары: {len(outside)}")
    if marked:
        summary += tr(f" · отметки: {len(marked)}", f" · белгилер: {len(marked)}")
    lines = [f"📊 <b>{tr('Отчёт за', 'Отчет')} {fmt_day(day)}</b>", summary, ""]
    for r in rows:
        info = r.days[day]
        name = escape(r.employee.full_name)
        if info.status == PRESENT:
            att = info.attendance
            icon = "🟠" if att.is_outside else "🟢"
            part = f"{icon} {name} — {_hhmm(att.check_in_at, tz)}"
            if info.late:
                part += f" ({tr('опозд.', 'кечикти')} {format_duration(info.late)})"
            if att.check_out_at:
                where = tr("в полях", "сыртта") if att.check_out_mode == "field" else tr("офис", "кеңсе")
                part += f" → {_hhmm(att.check_out_at, tz)} {where}"
            else:
                part += tr(" → уход не отмечен", " → кеткени белгиленген жок")
            day_tasks = [t for t in r.task_reports if t.work_date == day]
            if day_tasks:
                done = sum(1 for t in day_tasks if t.status == "done")
                part += f" · {tr('задачи', 'тапшырмалар')} {done}/{len(day_tasks)}"
            if att.corrected:
                part += " ✏️"
            part += outside_part(att)
            lines.append(part)
        elif info.status == ABSENT:
            lines.append(f"🔴 {name} — {tr('не пришёл', 'келген жок')}")
        elif info.status == PENDING:
            lines.append(f"⏳ {name} — {tr('ещё не время', 'али убакыт боло элек')}")
        elif info.mark is not None:
            lines.append(f"{DAY_KIND_ICON.get(info.status, '•')} {name} — {day_kind_label(info.status)}")

    if late:
        lines += ["", f"<b>⏰ {tr('Опоздали', 'Кечиккендер')}:</b>"]
        for r in sorted(late, key=lambda r: -r.days[day].late):
            lines.append(f"{escape(r.employee.full_name)} — {format_duration(r.days[day].late)}")

    problems = []
    for r in rows:
        for t in r.task_reports:
            if t.work_date == day and t.status in ("not_done", "blocked", "cancelled"):
                detail = texts.REASON_LABEL.get(t.reason, "") if t.reason else ""
                if t.comment:
                    detail = f"{detail}; {t.comment}" if detail else t.comment
                problems.append(
                    f"{texts.STATUS_ICON[t.status]} {escape(r.employee.full_name)}: {escape(t.task.text)}"
                    + (f" — {escape(detail)}" if detail else f" — {texts.STATUS_LABEL[t.status].lower()}")
                )
    if problems:
        lines += ["", f"<b>{tr('Не выполнено', 'Аткарылган жок')}:</b>", *problems]
    if not rows:
        lines.append(tr("Сотрудников пока нет.", "Азырынча кызматкерлер жок."))
    return "\n".join(lines)


def period_report(rows: list[EmployeeRow], start: date, end: date, title: str) -> str:
    lines = [f"📊 <b>{title}: {fmt_period(start, end)}</b>", ""]
    for r in rows:
        parts = [f"{r.present_days} {tr('дн.', 'күн')}", format_duration(r.worked_total)]
        if r.late_count:
            parts.append(
                tr(
                    f"опозданий {r.late_count} ({format_duration(r.late_total)})",
                    f"кечигүү {r.late_count} ({format_duration(r.late_total)})",
                )
            )
        if r.absences:
            parts.append(tr(f"неявок {r.absences}", f"келбеген {r.absences}"))
        if r.outside_count:
            parts.append(tr(f"вне офиса {r.outside_count}", f"кеңседен тышкары {r.outside_count}"))
        for kind, count in r.marks.items():
            parts.append(f"{day_kind_label(kind)} {count}")
        if r.no_checkout_count:
            parts.append(tr(f"без ухода {r.no_checkout_count}", f"кеткени белгисиз {r.no_checkout_count}"))
        if r.tasks_total:
            parts.append(f"{tr('задачи', 'тапшырмалар')} {r.tasks_done}/{r.tasks_total} ({r.tasks_percent}%)")
        lines.append(f"<b>{escape(r.employee.full_name)}</b>: " + ", ".join(parts))

    ranking = late_ranking(rows)
    lines += ["", f"<b>⏰ {tr('Опоздания за период', 'Мезгил ичиндеги кечигүүлөр')}:</b>"]
    if ranking:
        for i, r in enumerate(ranking, 1):
            lines.append(
                f"{i}. {escape(r.employee.full_name)} — {times_word(r.late_count)}, "
                f"{tr('всего', 'жалпы')} {format_duration(r.late_total)}"
            )
    else:
        lines.append(tr("Никто не опоздал 👍", "Эч ким кечиккен жок 👍"))
    if not rows:
        lines.append(tr("Сотрудников пока нет.", "Азырынча кызматкерлер жок."))
    lines.append(tr("\nПодробно — в Excel-файле.", "\nТолугу менен — Excel-файлда."))
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
    lines = [f"🗓 <b>{escape(name)}</b> · {fmt_day(day)}", f"{tr('График', 'График')}: {schedule.describe()}"]
    if info.status == PRESENT:
        att = info.attendance
        line = f"{tr('Приход', 'Келди')}: {_hhmm(att.check_in_at, tz)}"
        if info.late:
            line += f" ({tr('опоздание', 'кечигүү')} {format_duration(info.late)})"
        lines.append(line)
        if att.is_outside:
            where = f"🟠 {tr('Вне офиса', 'Кеңседен тышкары')}: {format_distance(att.check_in_distance_m or 0)}"
            if att.check_in_comment:
                where += f" — {escape(att.check_in_comment)}"
            lines.append(where)
        if att.check_out_at:
            where = tr("в полях", "сыртта") if att.check_out_mode == "field" else tr("в офисе", "кеңседе")
            lines.append(
                f"{tr('Уход', 'Кетти')}: {_hhmm(att.check_out_at, tz)} {where}, "
                f"{tr('отработано', 'иштеди')} {format_duration(att.worked_minutes or 0)}"
            )
        else:
            lines.append(tr("Уход: не отмечен", "Кетти: белгиленген жок"))
        if att.corrected:
            lines.append(tr("✏️ Время исправлялось руководителем", "✏️ Убакытты жетекчи оңдогон"))
    elif info.status == ABSENT:
        lines.append(tr("🔴 Не пришёл", "🔴 Келген жок"))
    elif info.status == WEEKEND:
        lines.append(tr("Нерабочий день по графику", "График боюнча дем алыш күн"))
    elif info.status in (FUTURE, PENDING):
        lines.append(tr("Отметок пока нет", "Азырынча белги жок"))
    if info.mark is not None:
        lines.append(f"{DAY_KIND_ICON.get(info.mark.kind, '•')} {tr('Отметка дня', 'Күндүн белгиси')}: {day_kind_label(info.mark.kind)}")
    lines.append(tr("\nЧто сделать?", "\nЭмне кылабыз?"))
    return "\n".join(lines)


def mark_notice(kind: str, start: date, end: date) -> str:
    period = f"{start:%d.%m}" if start == end else f"{start:%d.%m}–{end:%d.%m}"
    return f"{DAY_KIND_ICON.get(kind, '•')} {tr('Руководитель отметил', 'Жетекчи белгиледи')}: {day_kind_label(kind)}, {period}."


def correction_notice(kind: str, day: date, new_time: str, reason: str) -> str:
    if get_lang() == KY:
        what = "келген" if kind == "in" else "кеткен"
        return f"✏️ Жетекчи {day:%d.%m} күнкү {what} убактыңызды оңдоду: {new_time}. Себеби: {escape(reason)}"
    what = "прихода" if kind == "in" else "ухода"
    return f"✏️ Руководитель исправил время {what} за {day:%d.%m}: {new_time}. Причина: {escape(reason)}"
