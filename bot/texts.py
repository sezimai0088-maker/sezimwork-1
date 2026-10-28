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
    f"Утром в офисе — «{BTN_CHECK_IN}».\n"
    f"Вечером — «{BTN_FINISH_DAY}», затем «{BTN_SEND_LOCATION}».\n\n"
    "Если кнопки пропали — отправьте /start."
)

HELP_ADMIN = (
    "<b>Команды владельца</b>\n\n"
    "<code>/add +996555123456 Имя Фамилия</code> — добавить сотрудника\n"
    "<code>/add_manager +996555123456 Имя Фамилия</code> — добавить руководителя\n"
    "<code>/remove +996555123456</code> — отключить сотрудника\n"
    "/employees — список сотрудников\n"
    "/bind_chat — отправить в общем чате, чтобы бот писал туда\n"
)

ADMIN_ONLY = "Эта команда доступна только владельцу."
GROUP_NOT_SET = (
    "⚠️ Общий чат не подключён: сообщение не отправлено в группу.\n"
    "Добавьте бота в общий чат и отправьте там /bind_chat."
)
CHAT_BOUND = "✅ Этот чат подключён: сюда будут приходить отметки сотрудников."
