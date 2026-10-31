"""Кнопки. Внизу экрана — не больше 2–3 рядов крупных кнопок; под сообщениями — выбор вариантов."""

from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from bot import texts
from bot.callbacks import AcceptCb, AlertCb, AssignCb, LangCb, PlanCb, ReportCb, ReportsCb, TaskCb, TsCb
from bot.i18n import tr
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


def outside_checkin() -> ReplyKeyboardMarkup:
    """Сотрудник не в офисе: написать комментарий, отправить место ещё раз или отменить."""
    return _kb(
        [
            [KeyboardButton(text=texts.BTN_CHECK_IN, request_location=True)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ]
    )


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
    rows.append([KeyboardButton(text=texts.BTN_HELP), KeyboardButton(text=texts.BTN_LANG)])
    return _kb(rows)


def lang_choice(first: bool = False) -> InlineKeyboardMarkup:
    """Выбор языка. first=True — сразу после подключения по номеру."""
    flag = "1" if first else "0"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_LANG_KY, LangCb(code="ky", first=flag)),
                _btn(texts.BTN_LANG_RU, LangCb(code="ru", first=flag)),
            ]
        ]
    )


# ---------- План на день ----------


def plan_buttons(tasks: list[Task], *, send_button: bool = False) -> InlineKeyboardMarkup | None:
    """🗑 под каждой задачей, которую сотрудник может убрать, и (пока план не отправлен) «Отправить план»."""
    rows = []
    for i, task in enumerate(tasks, 1):
        if task.from_manager:
            continue
        rows.append([_btn(f"🗑 {i}. {task.text}"[:60], PlanCb(action="del", task_id=task.id))])
    if send_button:
        rows.append([_btn(texts.BTN_SEND_PLAN, PlanCb(action="send"))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


# ---------- Мои задачи ----------


def my_tasks(tasks: list[Task]) -> InlineKeyboardMarkup | None:
    """Под каждой открытой задачей — только смена срока: сегодня или завтра.

    Срок задачи от руководителя сотрудник не меняет — для неё кнопки нет.
    """
    rows = []
    for i, task in enumerate(tasks, 1):
        if task.status not in (TaskStatus.NEW, TaskStatus.IN_PROGRESS) or task.from_manager:
            continue
        rows.append([_btn(f"📅 {i}. {task.text}"[:60], TaskCb(action="due", task_id=task.id))])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


def due_choice(task_id: int, today: date) -> InlineKeyboardMarkup:
    """Срок задачи: только сегодня или завтра."""
    buttons = [
        _btn(texts.DUE_LABELS[key], TaskCb(action="setdue", task_id=task_id, value=key)) for key in ("today", "tomorrow")
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# ---------- Итог дня ----------


def report_status() -> InlineKeyboardMarkup:
    s = TaskStatus
    b = lambda st: _btn(texts.STATUS_BUTTON[st.value], ReportCb(action="status", value=st))  # noqa: E731
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [b(s.DONE)],
            [b(s.CONTINUE), b(s.NOT_DONE)],
            [b(s.BLOCKED), b(s.CANCELLED)],
        ]
    )


def report_reason() -> InlineKeyboardMarkup:
    r = BlockReason
    b = lambda rs: _btn(texts.REASON_BUTTON[rs.value], ReportCb(action="reason", value=rs))  # noqa: E731
    rows = [
        [b(r.MATERIALS)],
        [b(r.WAITING)],
        [b(r.EQUIPMENT)],
        [b(r.WEATHER), b(r.OTHER)],
        [b(r.MANAGER)],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def report_skip_comment() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(texts.BTN_SKIP, ReportCb(action="skip"))]])


def report_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[_btn(texts.BTN_REPORT_SEND, ReportCb(action="send")), _btn(texts.BTN_REPORT_REDO, ReportCb(action="redo"))]]
    )


# ---------- Руководитель ----------


def assign_employees(people: list[Employee]) -> InlineKeyboardMarkup:
    rows = [[_btn(p.full_name[:60], AssignCb(action="emp", value=str(p.id)))] for p in people]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def assign_due(today: date) -> InlineKeyboardMarkup:
    buttons = [_btn(texts.DUE_LABELS[key], AssignCb(action="due", value=key)) for key in due_options(today)]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def accept_task(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn(texts.BTN_ACCEPT, AcceptCb(task_id=task_id))]])


def alert_actions(alert_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(texts.BTN_ALERT_ACK, AlertCb(action="ack", alert_id=alert_id)),
                _btn(texts.BTN_ALERT_CANCEL, AlertCb(action="cancel", alert_id=alert_id)),
            ]
        ]
    )


# ---------- Отчёты и табель ----------


def reports_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(tr("Сегодня", "Бүгүн"), ReportsCb(period="today")),
                _btn(tr("Вчера", "Кечээ"), ReportsCb(period="yesterday")),
            ],
            [
                _btn(tr("Эта неделя", "Ушул жума"), ReportsCb(period="week")),
                _btn(tr("Прошлая неделя", "Өткөн жума"), ReportsCb(period="prev_week")),
            ],
            [
                _btn(tr("Этот месяц", "Ушул ай"), ReportsCb(period="month")),
                _btn(tr("Прошлый месяц", "Өткөн ай"), ReportsCb(period="prev_month")),
            ],
        ]
    )


def ts_employees(people: list[Employee]) -> InlineKeyboardMarkup:
    rows = [[_btn(p.full_name[:60], TsCb(action="emp", emp=p.id))] for p in people]
    rows.append([_btn(tr("🎉 Праздник для всех", "🎉 Баары үчүн майрам"), TsCb(action="emp", emp=0))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ts_days(emp_id: int, today: date) -> InlineKeyboardMarkup:
    def label(d: date) -> str:
        from bot.schedule import weekday_short

        if d == today:
            return tr("Сегодня", "Бүгүн")
        if d == today - timedelta(days=1):
            return tr("Вчера", "Кечээ")
        if d == today + timedelta(days=1):
            return tr("Завтра", "Эртең")
        return f"{weekday_short(d.isoweekday())} {d:%d.%m}"

    days = [today + timedelta(days=1)] + [today - timedelta(days=i) for i in range(0, 7)]
    buttons = [_btn(label(d), TsCb(action="day", emp=emp_id, day=f"{d:%Y%m%d}")) for d in days]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([_btn(tr("📅 Другая дата", "📅 Башка күн"), TsCb(action="other", emp=emp_id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ts_actions(emp_id: int, day: date) -> InlineKeyboardMarkup:
    d = f"{day:%Y%m%d}"
    if emp_id == 0:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [_btn(tr("🎉 Праздник", "🎉 Майрам"), TsCb(action="kind", emp=0, day=d, value="holiday"))],
                [_btn(tr("🧹 Снять праздник", "🧹 Майрамды алып салуу"), TsCb(action="unmark", emp=0, day=d))],
            ]
        )
    k = lambda text, kind: _btn(text, TsCb(action="kind", emp=emp_id, day=d, value=kind))  # noqa: E731
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [k(tr("🏖 Выходной", "🏖 Дем алыш"), "day_off"), k(tr("🤒 Больничный", "🤒 Оорулуу"), "sick")],
            [k(tr("✈️ Отпуск", "✈️ Өргүү"), "vacation"), k(tr("🚗 Командировка", "🚗 Иш сапар"), "trip")],
            [
                k(tr("🕐 Отгул", "🕐 Отгул"), "time_off"),
                _btn(tr("🧹 Снять отметку", "🧹 Белгини алуу"), TsCb(action="unmark", emp=emp_id, day=d)),
            ],
            [
                _btn(tr("✏️ Время прихода", "✏️ Келген убакыт"), TsCb(action="in", emp=emp_id, day=d)),
                _btn(tr("✏️ Время ухода", "✏️ Кеткен убакыт"), TsCb(action="out", emp=emp_id, day=d)),
            ],
            [_btn(tr("⏰ Изменить график", "⏰ Графикти өзгөртүү"), TsCb(action="sched", emp=emp_id, day=d))],
            [_btn(tr("◀️ Другой день", "◀️ Башка күн"), TsCb(action="emp", emp=emp_id))],
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
                _btn(tr("Пн–Пт", "Дш–Жм"), TsCb(action="sdays", emp=emp_id, value="1,2,3,4,5")),
                _btn(tr("Пн–Сб", "Дш–Иш"), TsCb(action="sdays", emp=emp_id, value="1,2,3,4,5,6")),
                _btn(tr("Каждый день", "Күн сайын"), TsCb(action="sdays", emp=emp_id, value="1,2,3,4,5,6,7")),
            ]
        ]
    )
