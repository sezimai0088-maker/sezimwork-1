"""Все тексты бота в одном месте, чтобы их было легко менять."""

from __future__ import annotations

from datetime import datetime
from html import escape

from bot.worktime import format_duration

# Кнопки
BTN_SHARE_PHONE = "📱 Отправить мой номер"
BTN_CHECK_IN = "🏢 Я в офисе"
BTN_FINISH_DAY = "🏁 Завершить день"
BTN_SEND_LOCATION = "📍 Отправить местоположение"
BTN_CANCEL = "↩️ Отмена"
BTN_HELP = "❓ Помощь"
BTN_EMPLOYEES = "👥 Сотрудники"


def hhmm(value: datetime) -> str:
    return value.strftime("%H:%M")


# Подключение
WELCOME_NEW = (
    "Здравствуйте! 👋\n\n"
    "Нажмите кнопку ниже, чтобы бот узнал вас по номеру телефона."
)
SHARE_OWN_CONTACT = "Пожалуйста, нажмите кнопку «📱 Отправить мой номер» — нужен именно ваш номер."
NOT_FOUND = (
    "Вашего номера нет в списке сотрудников.\n"
    "Попросите руководителя добавить вас, затем снова нажмите /start."
)
PHONE_TAKEN = "Этот номер уже подключён к другому аккаунту Telegram. Обратитесь к руководителю."
INACTIVE = "Ваш доступ отключён. Обратитесь к руководителю."


def registered(name: str) -> str:
    return f"Готово, {escape(name)}! ✅\n\nУтром, когда придёте на работу, нажмите «{BTN_CHECK_IN}»."


def owner_created(name: str) -> str:
    return (
        f"Здравствуйте, {escape(name)}! Вы подключены как <b>владелец</b>.\n\n"
        "Что сделать дальше:\n"
        "1. Добавьте бота в общий чат, сделайте администратором и отправьте там /bind_chat\n"
        "2. Добавьте сотрудников командой:\n"
        "<code>/add +996555123456 Айбек Асанов</code>\n"
        "3. Руководителя — командой:\n"
        "<code>/add_manager +996555000000 Нурлан Касымов</code>\n\n"
        "Все команды — /admin"
    )


def welcome_back(name: str) -> str:
    return f"С возвращением, {escape(name)}!"


# Приход
def outside_zone(distance_m: float) -> str:
    return (
        f"❌ Вы в {round(distance_m)} м от офиса.\n"
        "Отметка прихода возможна только в офисе. Подойдите ближе и нажмите ещё раз."
    )


LOW_ACCURACY = (
    "📡 Телефон неточно определил место.\n"
    "Подойдите к окну или выйдите на улицу и нажмите ещё раз."
)
FORWARDED_LOCATION = "Отправьте своё текущее местоположение кнопкой внизу экрана, а не пересланное сообщение."
VENUE_LOCATION = "Не выбирайте место на карте — нажмите кнопку внизу экрана, бот сам определит, где вы."
LIVE_LOCATION_NOTE = "Трансляция геопозиции не нужна — достаточно нажать кнопку внизу экрана."


def already_checked_in(at_local: datetime) -> str:
    return f"Вы уже отметились сегодня в {hhmm(at_local)}."


def checked_in_private(at_local: datetime, late: int) -> str:
    late_line = f"Опоздание: {format_duration(late)}." if late else "Вовремя 👍"
    return (
        f"✅ Приход отмечен: {hhmm(at_local)}. {late_line}\n\n"
        f"Хорошего дня! Вечером нажмите «{BTN_FINISH_DAY}»."
    )


def checked_in_group(name: str, at_local: datetime, late: int, workday: bool) -> str:
    if not workday:
        suffix = " (выходной день)"
    elif late:
        suffix = f" (опоздание {format_duration(late)})"
    else:
        suffix = " (вовремя)"
    return f"🟢 <b>{escape(name)}</b> пришёл в офис — {hhmm(at_local)}{suffix}"


# Уход
NOT_CHECKED_IN = f"Сегодня вы ещё не отмечали приход. Когда будете в офисе, нажмите «{BTN_CHECK_IN}»."
ASK_CHECKOUT_LOCATION = (
    "Чтобы завершить день, нажмите кнопку «📍 Отправить местоположение» внизу экрана.\n"
    "Бот сам определит, где вы: в офисе или в полях."
)
CHECKOUT_CANCELLED = "Хорошо, день не завершён."


def already_checked_out(at_local: datetime) -> str:
    return f"Вы уже завершили день в {hhmm(at_local)}. До завтра!"


def checked_out_private(at_local: datetime, worked: int, field: bool) -> str:
    place = "в полях" if field else "в офисе"
    return f"🏁 День завершён {place}: {hhmm(at_local)}. Отработано {format_duration(worked)}.\nСпасибо и до завтра!"


def checked_out_group_office(name: str, at_local: datetime, worked: int, early: int) -> str:
    early_part = f", ушёл раньше на {format_duration(early)}" if early else ""
    return (
        f"🔴 <b>{escape(name)}</b> ушёл из офиса — {hhmm(at_local)}, "
        f"отработано {format_duration(worked)}{early_part}"
    )


def checked_out_group_field(name: str, at_local: datetime, worked: int, link: str) -> str:
    return (
        f"🏁 <b>{escape(name)}</b> завершил работу в полях — {hhmm(at_local)}, "
        f"отработано {format_duration(worked)}\n"
        f'📍 <a href="{escape(link, quote=True)}">Открыть в 2ГИС</a>'
    )


# Помощь
HELP_EMPLOYEE = (
    "<b>Как пользоваться ботом</b>\n\n"
    "<b>Утром</b> в офисе — «🏢 Я в офисе», затем напишите задачи на день, каждую с новой строки, "
    "и нажмите «✅ Готово».\n\n"
    "<b>Днём</b> — «📋 Мои задачи» (отметить «Начал», изменить срок) и «➕ Добавить задачу».\n\n"
    "<b>Вечером</b> — «🏁 Завершить день»: по каждой задаче выберите статус кнопкой, "
    "затем «📍 Отправить местоположение».\n\n"
    "Статусы: ✅ Выполнено · 🔄 В работе (продолжу завтра) · ⏳ Не успел · "
    "🚧 Не по моей вине · ❌ Отменена.\n\n"
    "Если кнопки пропали — отправьте /start."
)

HELP_ADMIN = (
    "<b>Команды владельца</b>\n\n"
    "<code>/add +996555123456 Имя Фамилия</code> — добавить сотрудника\n"
    "<code>/add_manager +996555123456 Имя Фамилия</code> — добавить руководителя\n"
    "<code>/add_owner +996555123456 Имя Фамилия</code> — добавить ещё одного владельца (например, программиста)\n"
    "<code>/remove +996555123456</code> — отключить сотрудника\n"
    "/employees — список сотрудников\n"
    "/bind_chat — отправить в общем чате, чтобы бот писал туда\n"
    "/reset_today — <i>для проверки:</i> сбросить свою сегодняшнюю отметку и итоги задач\n\n"
    "<b>Кнопки руководителя</b>\n"
    "📊 Отчёты — за день, неделю, месяц (неделя и месяц — с Excel-табелем)\n"
    "🗓 Табель — выходной, больничный, отпуск, командировка, отгул, праздник; "
    "исправить время прихода и ухода; изменить график сотрудника\n"
)

ADMIN_ONLY = "Эта команда доступна только владельцу."
GROUP_NOT_SET = (
    "⚠️ Общий чат не подключён: сообщение не отправлено в группу.\n"
    "Добавьте бота в общий чат и отправьте там /bind_chat."
)
CHAT_BOUND = "✅ Этот чат подключён: сюда будут приходить отметки сотрудников."


# ================= Этап 2: задачи =================

BTN_MY_TASKS = "📋 Мои задачи"
BTN_ADD_TASK = "➕ Добавить задачу"
BTN_TASKS_DONE = "✅ Готово"
BTN_ASSIGN = "📌 Поставить задачу"

STATUS_ICON = {
    "new": "▫️",
    "in_progress": "▶️",
    "done": "✅",
    "continue": "🔄",
    "not_done": "⏳",
    "blocked": "🚧",
    "cancelled": "❌",
}
STATUS_LABEL = {
    "new": "Новая",
    "in_progress": "В работе",
    "done": "Выполнено",
    "continue": "В работе, продолжу",
    "not_done": "Не успел",
    "blocked": "Не по моей вине",
    "cancelled": "Отменена",
}
REASON_LABEL = {
    "materials": "нет материалов",
    "waiting": "жду другого человека",
    "equipment": "техника / транспорт",
    "weather": "погода",
    "manager": "руководитель изменил задачу",
    "other": "другое",
}

CARRY_INTRO = "Вчера не закончены задачи. Отметьте, какие оставить на сегодня:"
CARRY_HINT = "✅ — оставить на сегодня, 🗑 — убрать. 👤 — задача от руководителя, её убрать нельзя."
ASK_NEW_TASKS = (
    "Напишите задачи на сегодня — <b>каждую с новой строки</b>, одним сообщением.\n\n"
    "Например:\n"
    "<i>Сдать отчёт по объекту\n"
    "Позвонить поставщику\n"
    "Проверить склад</i>\n\n"
    f"Когда закончите — нажмите «{BTN_TASKS_DONE}»."
)
ASK_MORE_TASKS = f"Можно дописать ещё задачи или нажать «{BTN_TASKS_DONE}»."
NO_TASKS_IN_TEXT = "Не нашёл задач в сообщении. Напишите каждую задачу с новой строки."
PLAN_EMPTY = "В плане на сегодня нет задач. Добавить их можно кнопкой «➕ Добавить задачу»."
PLAN_CONFIRMED = "👍 План сохранён и отправлен в общий чат. Хорошего дня!"
PLAN_EDIT_HINT = "Нажмите 🗑, чтобы убрать задачу. Задачи руководителя (👤) убрать нельзя."
NEED_CHECK_IN_FOR_TASKS = f"Сначала отметьте приход кнопкой «{BTN_CHECK_IN}», потом можно будет написать задачи."


def added_tasks(count: int, continued: int) -> str:
    text = f"Добавлено задач: {count}."
    if continued:
        text += f"\n🔁 {continued} из них — продолжение незакрытых задач прошлых дней."
    return text


def due_suffix(due, today) -> str:
    if due is None or due <= today:
        return ""
    return f" (срок до {due:%d.%m})"


def task_line(task, today, *, with_status: bool = False) -> str:
    icon = STATUS_ICON.get(task.status, "▫️") + " " if with_status else ""
    manager = " 👤" if task.from_manager else ""
    return f"{icon}{escape(task.text)}{manager}{due_suffix(task.due_date, today)}"


def plan_text(tasks, today, *, title: str = "Ваш план на сегодня") -> str:
    if not tasks:
        return PLAN_EMPTY
    lines = [f"<b>{title}:</b>"]
    lines += [f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)]
    return "\n".join(lines)


def plan_group(name: str, tasks, today) -> str:
    lines = [f"📋 <b>{escape(name)}</b> — план на сегодня:"]
    lines += [f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)]
    return "\n".join(lines)


def my_tasks_text(tasks, today) -> str:
    if not tasks:
        return PLAN_EMPTY
    lines = ["<b>Задачи на сегодня:</b>"]
    lines += [f"{i}. {task_line(t, today, with_status=True)}" for i, t in enumerate(tasks, 1)]
    lines.append("\n▶️ — отметить, что начали. 📅 — изменить срок.")
    return "\n".join(lines)


# Итог дня
def report_question(index: int, total: int, task, today) -> str:
    return f"Задача {index} из {total}:\n<b>{task_line(task, today)}</b>\n\nКак прошло?"


ASK_REASON = "Что помешало?"
ASK_COMMENT_OPTIONAL = "💬 Добавьте комментарий одним сообщением или нажмите «Пропустить»."
ASK_COMMENT_REQUIRED = "💬 Напишите коротко причину — для этого статуса комментарий обязателен."


def result_line(task_text: str, status: str, reason: str | None, comment: str | None) -> str:
    parts = [f"{STATUS_ICON.get(status, '')} {escape(task_text)}"]
    details = []
    if status in ("not_done", "cancelled", "blocked", "continue"):
        if reason:
            details.append(REASON_LABEL.get(reason, reason))
        elif status == "not_done":
            details.append("не успел")
    if comment:
        details.append(escape(comment))
    if details:
        parts.append(" — " + "; ".join(details))
    return "".join(parts)


def report_summary(rows) -> str:
    """rows: список (текст задачи, статус, причина, комментарий)."""
    done = sum(1 for r in rows if r[1] == "done")
    lines = [f"<b>Итог дня: выполнено {done} из {len(rows)}</b>", ""]
    lines += [result_line(*r) for r in rows]
    lines.append("\nВсё верно?")
    return "\n".join(lines)


def tasks_block_for_group(rows) -> str:
    if not rows:
        return ""
    done = sum(1 for r in rows if r[1] == "done")
    lines = [f"\nЗадачи: выполнено {done} из {len(rows)}"]
    lines += [result_line(*r) for r in rows]
    return "\n".join(lines)


# Задачи от руководителя
ASSIGN_CHOOSE_EMPLOYEE = "Кому поставить задачу?"
ASSIGN_NO_EMPLOYEES = "Нет сотрудников. Владелец добавляет их командой /add."
ASSIGN_DONE = "✅ Задача поставлена. Сотрудник получил уведомление."
ASSIGN_DUE = "Какой срок?"


def assign_ask_text(name: str) -> str:
    return f"Напишите задачу для <b>{escape(name)}</b> одним сообщением."


def new_task_from_manager(manager_name: str, text: str, due, today) -> str:
    when = "сегодня" if due is None or due <= today else f"до {due:%d.%m}"
    return f"👤 <b>Новая задача от {escape(manager_name)}</b>\n{escape(text)}\nСрок: {when}"


def task_accepted_note(employee_name: str, text: str) -> str:
    return f"👍 {escape(employee_name)} принял задачу: {escape(text)}"


# Алерты
def alert_text(kind: str, employee_name: str, task_text: str, days_count: int, history) -> str:
    """history: список TaskReport за последние дни."""
    days = ", ".join(f"{r.work_date:%d.%m} — {STATUS_LABEL.get(r.status, r.status).lower()}" for r in history)
    comments = "; ".join(escape(r.comment) for r in history if r.comment)
    if kind == "blocked":
        head = (
            f"🆘 <b>Сотруднику нужна помощь</b>\n{escape(employee_name)}: задача «{escape(task_text)}» "
            f"не выполняется не по его вине {days_count} дн. подряд."
        )
    else:
        head = (
            f"⚠️ <b>Задача не выполняется</b>\nУ {escape(employee_name)} задача «{escape(task_text)}» "
            f"не выполнена {days_count} дн. подряд."
        )
    text = f"{head}\n\n{days}"
    if comments:
        text += f"\nКомментарии: {comments}"
    return text


ALERT_ACKED = "👌 Принято"
ALERT_TASK_CANCELLED = "❌ Задача отменена"


RESET_DONE = (
    "🔄 Ваша сегодняшняя отметка и итоги задач сброшены. Задачи плана снова «Новые».\n"
    f"Можно пройти день заново: «{BTN_CHECK_IN}»."
)


# ================= Этап 3: отчёты, табель, напоминания =================

BTN_REPORTS = "📊 Отчёты"
BTN_TIMESHEET = "🗓 Табель"

REMIND_CHECK_IN = f"⏰ Доброе утро! Вы ещё не отметились. Когда будете в офисе, нажмите «{BTN_CHECK_IN}»."
REMIND_CHECK_OUT = f"🕕 Рабочий день закончился. Не забудьте нажать «{BTN_FINISH_DAY}» и отметить задачи."


def not_checked_in_summary(names: list[str]) -> str:
    return "⚠️ Ещё не отметились: " + ", ".join(escape(n) for n in names)


def backup_caption(day) -> str:
    return f"💾 Бэкап базы за {day:%d.%m.%Y}. Храните этот файл — из него можно восстановить все данные."


REPORTS_CHOOSE = "Какой отчёт показать?"
REPORTS_ONLY_MANAGERS = "Отчёты доступны только руководителю и владельцу."
TS_CHOOSE_EMPLOYEE = "🗓 <b>Табель.</b> Выберите сотрудника:"
TS_CHOOSE_DAY = "Выберите день:"
TS_ASK_DATE = "Напишите дату в формате ДД.ММ, например <code>05.11</code>."
TS_BAD_DATE = "Не понял дату. Пример: <code>05.11</code> или <code>05.11.2026</code>."
TS_ASK_DAYS = "На сколько дней (включая этот)?"
TS_ASK_TIME_IN = "Напишите правильное время прихода, например <code>09:00</code>."
TS_ASK_TIME_OUT = "Напишите правильное время ухода, например <code>18:00</code>."
TS_BAD_TIME = "Не понял время. Пример: <code>09:05</code>."
TS_ASK_REASON = "Почему исправляете? Напишите коротко — причина сохранится в журнале."
TS_ASK_SCHEDULE = "Напишите время работы, например <code>08:30-17:30</code>."
TS_BAD_SCHEDULE = "Не понял. Пример: <code>08:30-17:30</code> (конец позже начала)."
TS_ASK_SCHEDULE_DAYS = "Какие дни рабочие?"
TS_SAVED = "✅ Сохранено."
TS_UNMARKED = "🧹 Отметка снята."
TS_NOTHING_TO_UNMARK = "На этот день отметки нет."

# Все кнопки меню: их текст не должен попадать в задачи, комментарии и ответы на вопросы
MENU_BUTTONS = frozenset(
    {
        BTN_CHECK_IN, BTN_FINISH_DAY, BTN_MY_TASKS, BTN_ADD_TASK, BTN_HELP, BTN_EMPLOYEES, BTN_ASSIGN,
        BTN_TASKS_DONE, BTN_SEND_LOCATION, BTN_CANCEL, BTN_REPORTS, BTN_TIMESHEET, BTN_SHARE_PHONE,
    }
)
