"""Табель в Excel: сводка по дням, подробные отметки и задачи."""

from __future__ import annotations

import io
from datetime import date, timedelta

import xlsxwriter

from bot.report_texts import CODE_LEGEND, DAY_CODE, DAY_KIND_LABEL, WEEKDAYS
from bot.services.reports import ABSENT, PRESENT, EmployeeRow
from bot.texts import REASON_LABEL, STATUS_LABEL
from bot.worktime import as_utc


def build_timesheet(rows: list[EmployeeRow], start: date, end: date, tz, title: str) -> bytes:
    buffer = io.BytesIO()
    wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]

    f_title = wb.add_format({"bold": True, "font_size": 14})
    f_head = wb.add_format({"bold": True, "bg_color": "#E7F1FB", "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    f_name = wb.add_format({"border": 1})
    f_cell = wb.add_format({"border": 1, "align": "center"})
    f_late = wb.add_format({"border": 1, "align": "center", "bg_color": "#F9EEDA"})
    f_absent = wb.add_format({"border": 1, "align": "center", "bg_color": "#FBEBEB", "font_color": "#B42318", "bold": True})
    f_off = wb.add_format({"border": 1, "align": "center", "font_color": "#888888"})
    f_mark = wb.add_format({"border": 1, "align": "center", "bg_color": "#E5F4E4"})
    f_total = wb.add_format({"border": 1, "align": "center", "bold": True})
    f_note = wb.add_format({"italic": True, "font_color": "#555555"})

    # --- Лист 1: Табель ---
    ws = wb.add_worksheet("Табель")
    ws.write(0, 0, title, f_title)
    ws.write(1, 0, f"Период: {start:%d.%m.%Y} – {end:%d.%m.%Y}. В ячейке — время прихода.", f_note)
    head_row = 3
    ws.set_row(head_row, 30)
    ws.write(head_row, 0, "Сотрудник", f_head)
    ws.set_column(0, 0, 26)
    for i, d in enumerate(days, start=1):
        ws.write(head_row, i, f"{d:%d}\n{WEEKDAYS[d.weekday()]}", f_head)
        ws.set_column(i, i, 6.5)
    totals = ["Дней", "Часов", "Опоздан.", "Мин. опозд.", "Неявок", "Без ухода", "Задачи", "% задач"]
    t0 = len(days) + 1
    for j, name in enumerate(totals):
        ws.write(head_row, t0 + j, name, f_head)
        ws.set_column(t0 + j, t0 + j, 9)

    for r_i, row in enumerate(rows, start=head_row + 1):
        ws.write(r_i, 0, row.employee.full_name, f_name)
        for c_i, d in enumerate(days, start=1):
            info = row.days[d]
            if info.status == PRESENT:
                value = as_utc(info.attendance.check_in_at).astimezone(tz).strftime("%H:%M")
                fmt = f_late if info.late else f_cell
            else:
                value = DAY_CODE.get(info.status, "")
                if info.status == ABSENT:
                    fmt = f_absent
                elif info.mark is not None:
                    fmt = f_mark
                else:
                    fmt = f_off
            ws.write(r_i, c_i, value, fmt)
        values = [
            row.present_days,
            round(row.worked_total / 60, 1),
            row.late_count,
            row.late_total,
            row.absences,
            row.no_checkout_count,
            f"{row.tasks_done}/{row.tasks_total}" if row.tasks_total else "",
            row.tasks_percent if row.tasks_percent is not None else "",
        ]
        for j, v in enumerate(values):
            ws.write(r_i, t0 + j, v, f_total)
    legend_row = head_row + len(rows) + 2
    ws.write(legend_row, 0, CODE_LEGEND, f_note)
    ws.write(legend_row + 1, 0, "Жёлтым — опоздание, красным — неявка, зелёным — особый день.", f_note)
    ws.freeze_panes(head_row + 1, 1)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)

    # --- Лист 2: Подробно ---
    ws2 = wb.add_worksheet("Подробно")
    head2 = ["Дата", "Сотрудник", "Приход", "Уход", "Где завершил", "Опоздание, мин", "Ранний уход, мин",
             "Отработано, ч", "Отметка дня", "Исправлено"]
    widths = [12, 26, 9, 9, 13, 14, 15, 13, 14, 11]
    for j, (h, w) in enumerate(zip(head2, widths)):
        ws2.write(0, j, h, f_head)
        ws2.set_column(j, j, w)
    r2 = 1
    for d in days:
        for row in rows:
            info = row.days[d]
            if info.status != PRESENT and info.mark is None and info.status != ABSENT:
                continue
            att = info.attendance
            ws2.write(r2, 0, d.strftime("%d.%m.%Y"))
            ws2.write(r2, 1, row.employee.full_name)
            if att:
                ws2.write(r2, 2, as_utc(att.check_in_at).astimezone(tz).strftime("%H:%M"))
                ws2.write(r2, 3, as_utc(att.check_out_at).astimezone(tz).strftime("%H:%M") if att.check_out_at else "—")
                ws2.write(r2, 4, {"field": "в полях", "office": "в офисе"}.get(att.check_out_mode or "", ""))
                ws2.write(r2, 5, att.late_minutes or 0)
                ws2.write(r2, 6, att.early_leave_minutes or 0)
                ws2.write(r2, 7, round((att.worked_minutes or 0) / 60, 2))
                ws2.write(r2, 9, "да" if att.corrected else "")
            elif info.status == ABSENT:
                ws2.write(r2, 2, "неявка")
            if info.mark is not None:
                ws2.write(r2, 8, DAY_KIND_LABEL.get(info.mark.kind, info.mark.kind))
            r2 += 1
    ws2.autofilter(0, 0, max(r2 - 1, 1), len(head2) - 1)
    ws2.freeze_panes(1, 0)

    # --- Лист 3: Задачи ---
    ws3 = wb.add_worksheet("Задачи")
    head3 = ["Дата", "Сотрудник", "Задача", "Статус", "Причина", "Комментарий", "От руководителя"]
    widths3 = [12, 26, 45, 18, 22, 40, 15]
    for j, (h, w) in enumerate(zip(head3, widths3)):
        ws3.write(0, j, h, f_head)
        ws3.set_column(j, j, w)
    r3 = 1
    for row in rows:
        for t in row.task_reports:
            ws3.write(r3, 0, t.work_date.strftime("%d.%m.%Y"))
            ws3.write(r3, 1, row.employee.full_name)
            ws3.write(r3, 2, t.task.text)
            ws3.write(r3, 3, STATUS_LABEL.get(t.status, t.status))
            ws3.write(r3, 4, REASON_LABEL.get(t.reason, "") if t.reason else "")
            ws3.write(r3, 5, t.comment or "")
            ws3.write(r3, 6, "да" if t.task.from_manager else "")
            r3 += 1
    ws3.autofilter(0, 0, max(r3 - 1, 1), len(head3) - 1)
    ws3.freeze_panes(1, 0)

    wb.close()
    return buffer.getvalue()
