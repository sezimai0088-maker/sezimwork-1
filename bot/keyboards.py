"""Кнопки. Внизу экрана — не больше 2–3 рядов крупных кнопок; под сообщениями — выбор вариантов."""

from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot import texts
from bot.callbacks import AcceptCb, AlertCb, AssignCb, CarryCb, PlanCb, ReportCb, ReportsCb, TaskCb, TsCb
from bot.models import Employee, Task
from bot.task_rules import BlockReason, TaskStatus, due_options


def _kb(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def _btn(text: str, cb) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb.pack())


# ---------- Кнопки внизу экрана ----------


def share_phone() -> ReplyKeyboardMarkup:
    return _kb([[KeyboardButton(text=texts.BTN_SHARE_PHONE, request_contact=True)]])


def checkout_location() -> ReplyKeyboardMarkup:
    return _kb(
        [
            [KeyboardButton(text=texts.BTN_SEND_LOCATION, request_location=True)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ]
    )


def writing_tasks() -> ReplyKeyboardMarkup:
    return _kb([[KeyboardButton(text=texts.BTN_TASKS_DONE)]])


def main_menu(employee: Employee, *, checked_in: bool, checked_out: bool) -> ReplyKeyboardMarkup:
    """Главное меню зависит от того, отметился ли сотрудник сегодня."""
    if not checked_in:
        rows = [[KeyboardButton(text=texts.BTN_CHECK_IN, request_location=True)]]
    elif not checked_out:
        rows = [
            [KeyboardButton(text=texts.BTN_FINISH_DAY)],
            [KeyboardButton(text=texts.BTN_MY_TASKS), KeyboardButton(text=texts.BTN_ADD_TASK)],
        ]
    else:
        rows = [[KeyboardButton(text=texts.BTN_MY_TASKS)]]

    if employee.is_manager:
        rows.append([KeyboardButton(text=texts.BTN_REPORTS), KeyboardButton(text=texts.BTN_TIMESHEET)])
        rows.append([KeyboardButton(text=texts.BTN_EMPLOYEES), KeyboardButton(text=texts.BTN_ASSIGN)])
    rows.append([KeyboardButton(text=texts.BTN_HELP)])
    return _kb(rows)


# ---------- Утренний план ----------


def carry_choice(tasks: list[Task], keep_ids: set[int]) -> InlineKeyboardMarkup:
    rows = []
    for task in tasks:
        if task.from_manager:
            mark = "👤"
        else:
            mark = "✅" if task.id in keep_ids else "🗑"
        label = f"{mark} {task.text}"[:60]
        rows.append([_btn(label, CarryCb(action="toggle", task_id=task.id))])
    rows.append([_btn("Дальше ▶️", CarryCb(action="next"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_review() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("✅ Всё верно", PlanCb(action="ok")), _btn("✏️ Исправить", PlanCb(action="edit"))]]
    )


def plan_edit(tasks: list[Task]) -> InlineKeyboardMarkup:
    rows = []
    for task in tasks:
        if task.from_manager:
            continue
        rows.append([_btn(f"🗑 {task.text}"[:60], PlanCb(action="del", task_id=task.id))])
    rows.append([_btn("✅ Готово", PlanCb(action="ok"))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Мои задачи ----------


def my_tasks(tasks: list[Task]) -> InlineKeyboardMarkup | None:
    rows = []
    for i, task in enumerate(tasks, 1):
        if task.status not in (TaskStatus.NEW, TaskStatus.IN_PROGRESS):
            continue
        row = []
        if task.status == TaskStatus.NEW:
            row.append(_btn(f"▶️ {i}. Начал", TaskCb(action="start", task_id=task.id)))
        row.append(_btn(f"📅 {i}. Срок", TaskCb(action="due", task_id=task.id)))
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


DUE_LABELS = {"today": "Сегодня", "tomorrow": "Завтра", "week": "До пятницы"}


def due_choice(task_id: int, today: date) -> InlineKeyboardMarkup:
    buttons = [
        _btn(DUE_LABELS[key], TaskCb(action="setdue", task_id=task_id, value=key)) for key in due_options(today)
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# ---------- Итог дня ----------


def report_status() -> InlineKeyboardMarkup:
    s = TaskStatus
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("✅ Выполнено", ReportCb(action="status", value=s.DONE))],
            [
                _btn("🔄 В работе", ReportCb(action="status", value=s.CONTINUE)),
                _btn("⏳ Не успел", ReportCb(action="status", value=s.NOT_DONE)),
            ],
            [
                _btn("🚧 Не по моей вине", ReportCb(action="status", value=s.BLOCKED)),
                _btn("❌ Отменена", ReportCb(action="status", value=s.CANCELLED)),
            ],
        ]
    )


def report_reason() -> InlineKeyboardMarkup:
    r = BlockReason
    rows = [
        [_btn("Нет материалов", ReportCb(action="reason", value=r.MATERIALS))],
        [_btn("Жду другого человека", ReportCb(action="reason", value=r.WAITING))],
        [_btn("Техника / транспорт", ReportCb(action="reason", value=r.EQUIPMENT))],
        [
            _btn("Погода", ReportCb(action="reason", value=r.WEATHER)),
            _btn("Другое", ReportCb(action="reason", value=r.OTHER)),
        ],
        [_btn("Руководитель изменил задачу", ReportCb(action="reason", value=r.MANAGER))],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_skip_comment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("Пропустить ▶️", ReportCb(action="skip"))]])


def report_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn("✅ Отправить", ReportCb(action="send")), _btn("✏️ Исправить", ReportCb(action="redo"))]]
    )


# ---------- Руководитель ----------


def assign_employees(people: list[Employee]) -> InlineKeyboardMarkup:
    rows = [[_btn(p.full_name[:60], AssignCb(action="emp", value=str(p.id)))] for p in people]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def assign_due(today: date) -> InlineKeyboardMarkup:
    buttons = [_btn(DUE_LABELS[key], AssignCb(action="due", value=key)) for key in due_options(today)]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def accept_task(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("👍 Принял", AcceptCb(task_id=task_id))]])


def alert_actions(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("👌 Принял", AlertCb(action="ack", alert_id=alert_id)),
                _btn("❌ Отменить задачу", AlertCb(action="cancel", alert_id=alert_id)),
            ]
        ]
    )


# ---------- Отчёты и табель ----------


def reports_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn("Сегодня", ReportsCb(period="today")), _btn("Вчера", ReportsCb(period="yesterday"))],
            [_btn("Эта неделя", ReportsCb(period="week")), _btn("Прошлая неделя", ReportsCb(period="prev_week"))],
            [_btn("Этот месяц", ReportsCb(period="month")), _btn("Прошлый месяц", ReportsCb(period="prev_month"))],
        ]
    )


def ts_employees(people: list[Employee]) -> InlineKeyboardMarkup:
    rows = [[_btn(p.full_name[:60], TsCb(action="emp", emp=p.id))] for p in people]
    rows.append([_btn("🎉 Праздник для всех", TsCb(action="emp", emp=0))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


_WD = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def ts_days(emp_id: int, today: date) -> InlineKeyboardMarkup:
    def label(d: date) -> str:
        if d == today:
            return "Сегодня"
        if d == today - timedelta(days=1):
            return "Вчера"
        if d == today + timedelta(days=1):
            return "Завтра"
        return f"{_WD[d.weekday()]} {d:%d.%m}"

    days = [today + timedelta(days=1)] + [today - timedelta(days=i) for i in range(0, 7)]
    buttons = [_btn(label(d), TsCb(action="day", emp=emp_id, day=f"{d:%Y%m%d}")) for d in days]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([_btn("📅 Другая дата", TsCb(action="other", emp=emp_id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ts_actions(emp_id: int, day: date) -> InlineKeyboardMarkup:
    d = f"{day:%Y%m%d}"
    if emp_id == 0:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [_btn("🎉 Праздник", TsCb(action="kind", emp=0, day=d, value="holiday"))],
                [_btn("🧹 Снять праздник", TsCb(action="unmark", emp=0, day=d))],
            ]
        )
    k = lambda text, kind: _btn(text, TsCb(action="kind", emp=emp_id, day=d, value=kind))  # noqa: E731
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [k("🏖 Выходной", "day_off"), k("🤒 Больничный", "sick")],
            [k("✈️ Отпуск", "vacation"), k("🚗 Командировка", "trip")],
            [k("🕐 Отгул", "time_off"), _btn("🧹 Снять отметку", TsCb(action="unmark", emp=emp_id, day=d))],
            [
                _btn("✏️ Время прихода", TsCb(action="in", emp=emp_id, day=d)),
                _btn("✏️ Время ухода", TsCb(action="out", emp=emp_id, day=d)),
            ],
            [_btn("⏰ Изменить график", TsCb(action="sched", emp=emp_id, day=d))],
            [_btn("◀️ Другой день", TsCb(action="emp", emp=emp_id))],
        ]
    )


def ts_days_count(emp_id: int, day: date, kind: str) -> InlineKeyboardMarkup:
    d = f"{day:%Y%m%d}"
    buttons = [_btn(str(n), TsCb(action="days", emp=emp_id, day=d, value=f"{kind}|{n}")) for n in (1, 2, 3, 5, 7, 14)]
    return InlineKeyboardMarkup(inline_keyboard=[buttons[:3], buttons[3:]])


def ts_schedule_days(emp_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn("Пн–Пт", TsCb(action="sdays", emp=emp_id, value="1,2,3,4,5")),
                _btn("Пн–Сб", TsCb(action="sdays", emp=emp_id, value="1,2,3,4,5,6")),
                _btn("Каждый день", TsCb(action="sdays", emp=emp_id, value="1,2,3,4,5,6,7")),
            ]
        ]
    )
