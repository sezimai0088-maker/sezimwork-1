"""Табель в Excel: сводка по дням, опоздания, подробные отметки и задачи (на языке получателя)."""

from __future__ import annotations

import io
from datetime import date, timedelta

import xlsxwriter

from bot import texts
from bot.i18n import tr
from bot.report_texts import code_legend, day_code, day_kind_label, late_ranking, times_word, weekdays
from bot.services.reports import ABSENT, PRESENT, EmployeeRow
from bot.worktime import as_utc, format_distance, format_duration


def build_timesheet(rows: list[EmployeeRow], start: date, end: date, tz, title: str) -> bytes:
    buffer = io.BytesIO()
    wb = xlsxwriter.Workbook(buffer, {"in_memory": True})
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    wd = weekdays()

    f_title = wb.add_format({"bold": True, "font_size": 14})
    f_head = wb.add_format({"bold": True, "bg_color": "#E7F1FB", "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
    f_name = wb.add_format({"border": 1})
    f_cell = wb.add_format({"border": 1, "align": "center"})
    f_late = wb.add_format({"border": 1, "align": "center", "bg_color": "#F9EEDA"})
    f_outside = wb.add_format({"border": 1, "align": "center", "bg_color": "#FFE3C2"})
    f_absent = wb.add_format({"border": 1, "align": "center", "bg_color": "#FBEBEB", "font_color": "#B42318", "bold": True})
    f_off = wb.add_format({"border": 1, "align": "center", "font_color": "#888888"})
    f_mark = wb.add_format({"border": 1, "align": "center", "bg_color": "#E5F4E4"})
    f_total = wb.add_format({"border": 1, "align": "center", "bold": True})
    f_text = wb.add_format({"border": 1, "text_wrap": True, "valign": "top"})
    f_note = wb.add_format({"italic": True, "font_color": "#555555"})

    # --- Лист 1: Табель ---
    ws = wb.add_worksheet(tr("Табель", "Табель"))
    ws.write(0, 0, title, f_title)
    ws.write(
        1, 0,
        tr(f"Период: {start:%d.%m.%Y} – {end:%d.%m.%Y}. В ячейке — время прихода.",
           f"Мезгил: {start:%d.%m.%Y} – {end:%d.%m.%Y}. Уячада — келген убакыт."),
        f_note,
    )
    head_row = 3
    ws.set_row(head_row, 30)
    ws.write(head_row, 0, tr("Сотрудник", "Кызматкер"), f_head)
    ws.set_column(0, 0, 26)
    for i, d in enumerate(days, start=1):
        ws.write(head_row, i, f"{d:%d}\n{wd[d.weekday()]}", f_head)
        ws.set_column(i, i, 6.5)
    totals = [
        tr("Дней", "Күн"), tr("Отработано", "Иштеди"), tr("Опозданий, раз", "Кечигүү, жолу"),
        tr("Опоздания, всего", "Кечигүү, жалпы"), tr("Неявок", "Келбеген"), tr("Вне офиса", "Кеңседен тышкары"),
        tr("Без ухода", "Кеткени белгисиз"), tr("Задачи", "Тапшырмалар"), tr("% задач", "% тапшырма"),
    ]
    widths = [7, 12, 10, 13, 9, 10, 10, 10, 9]
    t0 = len(days) + 1
    for j, (name, w) in enumerate(zip(totals, widths)):
        ws.write(head_row, t0 + j, name, f_head)
        ws.set_column(t0 + j, t0 + j, w)

    for r_i, row in enumerate(rows, start=head_row + 1):
        ws.write(r_i, 0, row.employee.full_name, f_name)
        for c_i, d in enumerate(days, start=1):
            info = row.days[d]
            if info.status == PRESENT:
                value = as_utc(info.attendance.check_in_at).astimezone(tz).strftime("%H:%M")
                if info.attendance.is_outside:
                    value += "*"
                    fmt = f_outside
                else:
                    fmt = f_late if info.late else f_cell
            else:
                value = day_code(info.status)
                if info.status == ABSENT:
                    fmt = f_absent
                elif info.mark is not None:
                    fmt = f_mark
                else:
                    fmt = f_off
            ws.write(r_i, c_i, value, fmt)
        values = [
            row.present_days,
            format_duration(row.worked_total),
            row.late_count,
            format_duration(row.late_total) if row.late_total else "",
            row.absences,
            row.outside_count or "",
            row.no_checkout_count,
            f"{row.tasks_done}/{row.tasks_total}" if row.tasks_total else "",
            row.tasks_percent if row.tasks_percent is not None else "",
        ]
        for j, v in enumerate(values):
            ws.write(r_i, t0 + j, v, f_total)
    legend_row = head_row + len(rows) + 2
    ws.write(legend_row, 0, code_legend(), f_note)
    ws.write(
        legend_row + 1, 0,
        tr("Жёлтым — опоздание, оранжевым и * — приход вне офиса, красным — неявка, зелёным — особый день.",
           "Сары — кечигүү, кызгылт сары жана * — кеңседен тышкары келүү, кызыл — келген жок, жашыл — өзгөчө күн."),
        f_note,
    )
    ws.freeze_panes(head_row + 1, 1)
    ws.set_landscape()
    ws.fit_to_pages(1, 0)

    # --- Лист 2: Опоздания ---
    ws_late = wb.add_worksheet(tr("Опоздания", "Кечигүүлөр"))
    head_l = [tr("Сотрудник", "Кызматкер"), tr("Сколько раз", "Канча жолу"), tr("Всего", "Жалпы"),
              tr("Когда и на сколько", "Качан жана канчага")]
    for j, (h, w) in enumerate(zip(head_l, [26, 12, 14, 70])):
        ws_late.write(0, j, h, f_head)
        ws_late.set_column(j, j, w)
    r_l = 1
    for row in late_ranking(rows):
        details = "; ".join(f"{d:%d.%m} — {format_duration(m)}" for d, m in row.late_days)
        ws_late.write(r_l, 0, row.employee.full_name, f_text)
        ws_late.write(r_l, 1, times_word(row.late_count), f_cell)
        ws_late.write(r_l, 2, format_duration(row.late_total), f_total)
        ws_late.write(r_l, 3, details, f_text)
        r_l += 1
    if r_l == 1:
        ws_late.write(1, 0, tr("Никто не опоздал", "Эч ким кечиккен жок"), f_note)
    ws_late.freeze_panes(1, 0)

    # --- Лист 3: Подробно ---
    ws2 = wb.add_worksheet(tr("Подробно", "Толук"))
    head2 = [
        tr("Дата", "Күнү"), tr("Сотрудник", "Кызматкер"), tr("Приход", "Келди"), tr("Где отметил приход", "Кайда келди"),
        tr("Комментарий к приходу", "Келүүгө түшүндүрмө"), tr("Уход", "Кетти"), tr("Где завершил", "Кайда аяктады"),
        tr("Опоздание", "Кечигүү"), tr("Ранний уход", "Эрте кетүү"), tr("Отработано", "Иштеди"),
        tr("Отметка дня", "Күндүн белгиси"), tr("Исправлено", "Оңдолгон"),
    ]
    widths2 = [12, 26, 9, 22, 34, 9, 13, 13, 13, 13, 14, 11]
    for j, (h, w) in enumerate(zip(head2, widths2)):
        ws2.write(0, j, h, f_head)
        ws2.set_column(j, j, w)
    yes = tr("да", "ооба")
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
                if att.is_outside:
                    ws2.write(r2, 3, f"{tr('вне офиса', 'кеңседен тышкары')}, {format_distance(att.check_in_distance_m or 0)}")
                    ws2.write(r2, 4, att.check_in_comment or "")
                else:
                    ws2.write(r2, 3, tr("в офисе", "кеңседе"))
                ws2.write(r2, 5, as_utc(att.check_out_at).astimezone(tz).strftime("%H:%M") if att.check_out_at else "—")
                ws2.write(r2, 6, {"field": tr("в полях", "сыртта"), "office": tr("в офисе", "кеңседе")}.get(att.check_out_mode or "", ""))
                ws2.write(r2, 7, format_duration(att.late_minutes) if att.late_minutes else "")
                ws2.write(r2, 8, format_duration(att.early_leave_minutes) if att.early_leave_minutes else "")
                ws2.write(r2, 9, format_duration(att.worked_minutes) if att.worked_minutes else "")
                ws2.write(r2, 11, yes if att.corrected else "")
            elif info.status == ABSENT:
                ws2.write(r2, 2, tr("неявка", "келген жок"))
            if info.mark is not None:
                ws2.write(r2, 10, day_kind_label(info.mark.kind))
            r2 += 1
    ws2.autofilter(0, 0, max(r2 - 1, 1), len(head2) - 1)
    ws2.freeze_panes(1, 0)

    # --- Лист 4: Задачи ---
    ws3 = wb.add_worksheet(tr("Задачи", "Тапшырмалар"))
    head3 = [tr("Дата", "Күнү"), tr("Сотрудник", "Кызматкер"), tr("Задача", "Тапшырма"), tr("Статус", "Статус"),
             tr("Причина", "Себеби"), tr("Комментарий", "Түшүндүрмө"), tr("От руководителя", "Жетекчиден")]
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
            ws3.write(r3, 3, texts.STATUS_LABEL.get(t.status, t.status))
            ws3.write(r3, 4, texts.REASON_LABEL.get(t.reason, "") if t.reason else "")
            ws3.write(r3, 5, t.comment or "")
            ws3.write(r3, 6, yes if t.task.from_manager else "")
            r3 += 1
    ws3.autofilter(0, 0, max(r3 - 1, 1), len(head3) - 1)
    ws3.freeze_panes(1, 0)

    wb.close()
    return buffer.getvalue()
