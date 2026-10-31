"""Боттун тексттери кыргызча. Орусчасы — texts_ru.py, аттары бирдей.

Тексты бота на кыргызском. Имена — как в texts_ru.py. Чего здесь нет, берётся из русского файла.
"""

from __future__ import annotations

from datetime import datetime
from html import escape

from bot.texts_ru import (  # noqa: F401 — общие для обоих языков
    APPROX_THRESHOLD_M,
    BTN_LANG,
    BTN_LANG_KY,
    BTN_LANG_RU,
    CHOOSE_LANG,
    INACTIVE,
    NOT_FOUND,
    PHONE_TAKEN,
    SHARE_OWN_CONTACT,
    STATUS_ICON,
    WELCOME_NEW,
    hhmm,
)
from bot.worktime import format_distance, format_duration

# Баскычтар
BTN_SHARE_PHONE = "📱 Номеримди жөнөтүү"
BTN_CHECK_IN = "🏢 Кеңседемин"
BTN_FINISH_DAY = "🏁 Күндү аяктоо"
BTN_SEND_LOCATION = "📍 Жайгашкан жеримди жөнөтүү"
BTN_CANCEL = "↩️ Жокко чыгаруу"
BTN_HELP = "❓ Жардам"
BTN_EMPLOYEES = "👥 Кызматкерлер"
LANG_SET = "✅ Боттун тили: кыргызча."


def registered(name: str) -> str:
    return f"Даяр, {escape(name)}! ✅\n\nЭртең менен жумушка келгенде «{BTN_CHECK_IN}» баскычын басыңыз."


def owner_created(name: str) -> str:
    return (
        f"Саламатсызбы, {escape(name)}! Сиз <b>ээси</b> катары туташтырылдыңыз.\n\n"
        "Андан ары эмне кылуу керек:\n"
        "1. Ботту жалпы чатка кошуп, администратор кылыңыз жана ал жерге /bind_chat жөнөтүңүз\n"
        "2. Кызматкерлерди мындай команда менен кошуңуз:\n"
        "<code>/add +996555123456 Айбек Асанов</code>\n"
        "3. Жетекчини — мындай команда менен:\n"
        "<code>/add_manager +996555000000 Нурлан Касымов</code>\n\n"
        "Бардык командалар — /admin"
    )


def welcome_back(name: str) -> str:
    return f"Кайра кош келиңиз, {escape(name)}!"


# ---------- Келүү ----------
def outside_zone(distance_m: float) -> str:
    return (
        f"❌ Сиз кеңседен {format_distance(distance_m)} алыстасыз.\n"
        "Келгениңизди кеңседе гана белгилесе болот. Жакыныраак келип, кайра басыңыз."
    )


def outside_ask(distance_m: float) -> str:
    return (
        f"📍 Сиз кеңседе эмессиз — кеңседен <b>{format_distance(distance_m)}</b> алыстыкта.\n\n"
        "Эгер сиз <b>кеңседен тышкары иштеп жатсаңыз</b> (объектте, кардарда, тапшырма боюнча) — "
        "<b>кайда экениңизди жана эмне үчүн</b> бир билдирүү менен жазыңыз. Келгениңиз ушул "
        "түшүндүрмө менен белгиленет, жетекчи аны отчеттон көрөт.\n\n"
        f"Эгер чындыгында кеңседе болсоңуз — «{BTN_CANCEL}» басып, жайгашкан жериңизди кайра жөнөтүңүз."
    )


OUTSIDE_COMMENT_SHORT = "Бир аз кененирээк жазыңыз: кайдасыз жана кайсы иш боюнча (жок дегенде бир нече сөз)."
OUTSIDE_CANCELLED = "Макул, келгениңиз белгиленген жок."
OUTSIDE_EXPIRED = f"Өтө көп убакыт өтүп кетти. «{BTN_CHECK_IN}» баскычын кайра басыңыз."

LOW_ACCURACY = (
    "📡 Телефон жайгашкан жерди так аныктай алган жок.\n"
    "Терезеге жакындаңыз же сыртка чыгып, кайра басыңыз."
)
APPROX_LOCATION = (
    "📡 Телефон болжолдуу жерди жөнөттү (катасы {km} км) — андан кайда экениңизди билүүгө болбойт.\n\n"
    "Telegram үчүн так геолокацияны күйгүзүңүз:\n"
    "<b>iPhone:</b> Настройки → Конфиденциальность и безопасность → Службы геолокации → Telegram → "
    "«При использовании» тандап, <b>«Точная геопозиция»</b> күйгүзүңүз.\n"
    "<b>Android:</b> Telegram белгисин басып кармап туруңуз → «О приложении» → Разрешения → Местоположение → "
    "«Разрешить только во время использования» тандап, <b>«Точное местоположение»</b> күйгүзүңүз.\n\n"
    "Андан кийин баскычты кайра басыңыз."
)


def low_accuracy_text(accuracy_m: float | None) -> str:
    if accuracy_m is not None and accuracy_m >= APPROX_THRESHOLD_M:
        return APPROX_LOCATION.format(km=f"{accuracy_m / 1000:.0f}" if accuracy_m >= 2000 else f"{accuracy_m / 1000:.1f}")
    return LOW_ACCURACY


FORWARDED_LOCATION = "Учурдагы жайгашкан жериңизди экрандын ылдыйкы баскычы менен жөнөтүңүз, башкадан жөнөтүлгөн билдирүүнү эмес."
VENUE_LOCATION = "Картадан жер тандабаңыз — экрандын ылдыйкы баскычын басыңыз, бот кайда экениңизди өзү аныктайт."
LIVE_LOCATION_NOTE = "Геолокацияны түз берүүнүн кереги жок — ылдыйкы баскычты басуу жетиштүү."


def already_checked_in(at_local: datetime) -> str:
    return f"Сиз бүгүн саат {hhmm(at_local)} келгениңизди белгилегенсиз."


def checked_in_private(at_local: datetime, late: int, outside: bool = False) -> str:
    late_line = f"Кечигүү: {format_duration(late)}." if late else "Өз убагында 👍"
    where = " (кеңседен тышкары)" if outside else ""
    return f"✅ Келгениңиз белгиленди{where}: {hhmm(at_local)}. {late_line}"


def _late_suffix(late: int, workday: bool) -> str:
    if not workday:
        return " (дем алыш күн)"
    if late:
        return f" (кечикти: {format_duration(late)})"
    return " (өз убагында)"


def checked_in_group(name: str, at_local: datetime, late: int, workday: bool) -> str:
    return f"🟢 <b>{escape(name)}</b> кеңсеге келди — {hhmm(at_local)}{_late_suffix(late, workday)}"


def checked_in_group_outside(
    name: str, at_local: datetime, late: int, workday: bool, distance_m: float, link: str, comment: str | None
) -> str:
    text = (
        f"🟠 <b>{escape(name)}</b> кеңседен тышкары белгиленди — {hhmm(at_local)}{_late_suffix(late, workday)}\n"
        f'📍 Кеңседен {format_distance(distance_m)} · <a href="{escape(link, quote=True)}">2ГИСтен ачуу</a>'
    )
    if comment:
        text += f"\n💬 {escape(comment)}"
    return text


def outside_manager_note(
    name: str, at_local: datetime, late: int, workday: bool, distance_m: float, link: str, comment: str | None
) -> str:
    return "🔔 " + checked_in_group_outside(name, at_local, late, workday, distance_m, link, comment)


# ---------- Кетүү ----------
NOT_CHECKED_IN = f"Бүгүн келгениңизди али белгилей элексиз. Кеңседе болгондо «{BTN_CHECK_IN}» басыңыз."
ASK_CHECKOUT_LOCATION = (
    f"Күндү аяктоо үчүн экрандын ылдый жагындагы «{BTN_SEND_LOCATION}» баскычын басыңыз.\n"
    "Бот кайда экениңизди өзү аныктайт: кеңседеби же сырттабы."
)
CHECKOUT_CANCELLED = "Макул, күн аяктаган жок."


def already_checked_out(at_local: datetime) -> str:
    return f"Сиз күндү саат {hhmm(at_local)} аяктагансыз. Эртеңкиге чейин!"


def checked_out_private(at_local: datetime, worked: int, field: bool) -> str:
    place = "сыртта" if field else "кеңседе"
    return f"🏁 Күн {place} аяктады: {hhmm(at_local)}. Иштелди: {format_duration(worked)}.\nРахмат, эртеңкиге чейин!"


def checked_out_group_office(name: str, at_local: datetime, worked: int, early: int) -> str:
    early_part = f", {format_duration(early)} эрте кетти" if early else ""
    return (
        f"🔴 <b>{escape(name)}</b> кеңседен кетти — {hhmm(at_local)}, "
        f"иштеди: {format_duration(worked)}{early_part}"
    )


def checked_out_group_field(name: str, at_local: datetime, worked: int, link: str) -> str:
    return (
        f"🏁 <b>{escape(name)}</b> ишти сыртта аяктады — {hhmm(at_local)}, "
        f"иштеди: {format_duration(worked)}\n"
        f'📍 <a href="{escape(link, quote=True)}">2ГИСтен ачуу</a>'
    )


# ---------- Жардам ----------
HELP_EMPLOYEE = (
    "<b>Ботту кантип колдонуу керек</b>\n\n"
    f"<b>Эртең менен</b> — «{BTN_CHECK_IN}», андан кийин бүгүнкү тапшырмаларды бир билдирүү менен, "
    "ар бирин жаңы саптан жазып, «📤 Планды жөнөтүү» басыңыз. Тапшырманы унутсаңыз — жөн гана ботко жазыңыз.\n\n"
    f"<b>Кеңседен тышкары иштесеңиз</b> (объектте, кардарда) — ошондой эле «{BTN_CHECK_IN}» басыңыз: "
    "бот кеңседен канча алыс экениңизди көрсөтүп, кайда жана эмне үчүн экениңизди жазууну сурайт.\n\n"
    "<b>Күндүз</b> — «📋 Менин тапшырмаларым» (өз тапшырмаңыздын мөөнөтүн жылдыруу) жана «➕ Тапшырма кошуу». "
    "Жетекчинин тапшырмасынын (👤) мөөнөтүн жетекчи гана өзгөртөт.\n\n"
    f"<b>Кечинде</b> — «{BTN_FINISH_DAY}»: ар бир тапшырма боюнча баскыч менен статус тандап, "
    f"андан кийин «{BTN_SEND_LOCATION}» басыңыз.\n\n"
    "Статустар: ✅ Аткарылды · 🔄 Аткарылууда (эртең улантам) · ⏳ Үлгүрбөдүм · "
    "🚧 Менин күнөөм эмес · ❌ Жокко чыгарылды.\n\n"
    "Тилди алмаштыруу — «🌐 Тил / Язык». Баскычтар жоголуп кетсе — /start жөнөтүңүз."
)

HELP_ADMIN = (
    "<b>Ээсинин командалары</b>\n\n"
    "<code>/add +996555123456 Аты Фамилиясы</code> — кызматкер кошуу\n"
    "<code>/add_manager +996555123456 Аты Фамилиясы</code> — жетекчи кошуу\n"
    "<code>/add_owner +996555123456 Аты Фамилиясы</code> — дагы бир ээ кошуу (мисалы, программист)\n"
    "<code>/remove +996555123456</code> — кызматкерди өчүрүү\n"
    "/employees — кызматкерлердин тизмеси\n"
    "/bind_chat — бот жазышы үчүн жалпы чатта жөнөтүңүз\n"
    "/lang — тилди алмаштыруу\n"
    "/reset_today — <i>текшерүү үчүн:</i> өзүңүздүн бүгүнкү белгиңизди жана тапшырмалардын жыйынтыгын өчүрүү\n\n"
    "<b>Жетекчинин баскычтары</b>\n"
    "📊 Отчеттор — күн, жума, ай боюнча (жума жана ай — Excel-табель жана кечигүүлөрдүн тизмеси менен)\n"
    "🗓 Табель — дем алыш, оорулуу, өргүү, иш сапар, отгул, майрам; "
    "келген жана кеткен убакытты оңдоо; кызматкердин графигин өзгөртүү\n"
)

ADMIN_ONLY = "Бул команда ээси үчүн гана."
GROUP_NOT_SET = (
    "⚠️ Жалпы чат туташтырылган эмес: билдирүү топко жөнөтүлгөн жок.\n"
    "Ботту жалпы чатка кошуп, ал жерге /bind_chat жөнөтүңүз."
)
CHAT_BOUND = "✅ Бул чат туташтырылды: кызматкерлердин белгилери ушул жакка келет."


# ================= Тапшырмалар =================

BTN_MY_TASKS = "📋 Менин тапшырмаларым"
BTN_ADD_TASK = "➕ Тапшырма кошуу"
BTN_TASKS_DONE = "✅ Даяр"
BTN_ASSIGN = "📌 Тапшырма берүү"

STATUS_LABEL = {
    "new": "Жаңы",
    "in_progress": "Аткарылууда",
    "done": "Аткарылды",
    "continue": "Аткарылууда, улантам",
    "not_done": "Үлгүрбөдүм",
    "blocked": "Менин күнөөм эмес",
    "cancelled": "Жокко чыгарылды",
}
REASON_LABEL = {
    "materials": "материал жок",
    "waiting": "башка адамды күтүп жатам",
    "equipment": "техника / транспорт",
    "weather": "аба ырайы",
    "manager": "жетекчи тапшырманы өзгөрттү",
    "other": "башка",
}
STATUS_BUTTON = {
    "done": "✅ Аткарылды",
    "continue": "🔄 Аткарылууда",
    "not_done": "⏳ Үлгүрбөдүм",
    "blocked": "🚧 Менин күнөөм эмес",
    "cancelled": "❌ Жокко чыгарылды",
}
REASON_BUTTON = {
    "materials": "Материал жок",
    "waiting": "Башка адамды күтүп жатам",
    "equipment": "Техника / транспорт",
    "weather": "Аба ырайы",
    "other": "Башка",
    "manager": "Жетекчи тапшырманы өзгөрттү",
}
BTN_SKIP = "Өткөрүп жиберүү ▶️"
BTN_REPORT_SEND = "✅ Жөнөтүү"
BTN_REPORT_REDO = "✏️ Оңдоо"
BTN_ACCEPT = "👍 Кабыл алдым"
BTN_ALERT_ACK = "👌 Кабыл алдым"
BTN_ALERT_CANCEL = "❌ Тапшырманы жокко чыгаруу"
DUE_LABELS = {"today": "Бүгүн", "tomorrow": "Эртең", "week": "Жумага чейин"}

BTN_SEND_PLAN = "📤 Планды жөнөтүү"
ASK_NEW_TASKS = (
    "📝 Бүгүнкү тапшырмаларды жазыңыз — <b>ар бирин жаңы саптан</b>, бир билдирүү менен.\n\n"
    "Мисалы:\n"
    "<i>Объект боюнча отчет тапшыруу\n"
    "Жеткирүүчүгө чалуу\n"
    "Кампаны текшерүү</i>\n\n"
    f"Андан кийин планды текшерип, «{BTN_SEND_PLAN}» басыңыз."
)
ASK_ADD_TASKS = "📝 Кошула турган тапшырмаларды жазыңыз — ар бирин жаңы саптан. Жөнөтсөңүз, алар дароо планга кошулат."
NO_TASKS_IN_TEXT = "Билдирүүдөн тапшырма таппадым. Ар бир тапшырманы жаңы саптан жазыңыз."
PLAN_EMPTY = f"Бүгүнкү планда тапшырма жок. Кошуу үчүн «{BTN_ADD_TASK}» басыңыз же тапшырманы ушул жакка жазыңыз."
NEED_CHECK_IN_FOR_TASKS = f"Адегенде «{BTN_CHECK_IN}» баскычы менен келгениңизди белгилеңиз, андан кийин тапшырмаларды жазсаңыз болот."
DAY_CLOSED_FOR_TASKS = "Жумуш күнү аяктады — тапшырмаларды эртең келгенден кийин жазсаңыз болот."
PLAN_SENT_OK = "✅ План жалпы чатка жөнөтүлдү. Ийгиликтүү күн болсун!"
DUE_LOCKED = "🔒 Бул тапшырманын мөөнөтүн жетекчи койгон — аны жетекчи гана өзгөртө алат."


def carried_intro(tasks, today, *, carried: bool = True) -> str:
    head = "🔁 <b>Кечээки аяктабаган тапшырмалар которулду:</b>" if carried else "📋 <b>Бүгүнкү планда бар:</b>"
    lines = [head]
    lines += [f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)]
    lines.append(f"\nКереги жогун 🗑 баскычы менен алып салыңыз. Жаңы тапшырма жок болсо — дароо «{BTN_SEND_PLAN}» басыңыз.\n")
    return "\n".join(lines) + "\n" + ASK_NEW_TASKS


def plan_preview(tasks, today) -> str:
    if not tasks:
        return ASK_NEW_TASKS
    lines = ["📋 <b>Бүгүнкү планыңыз:</b>"]
    lines += [f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)]
    lines.append("\nАшыкчасын 🗑 менен алып салыңыз, унутканыңызды билдирүү менен жазыңыз.")
    lines.append(f"Баары туура болсо — <b>«{BTN_SEND_PLAN}»</b> басыңыз.")
    return "\n".join(lines)


def plan_sent(tasks, today) -> str:
    lines = ["✅ <b>План жалпы чатка жөнөтүлдү:</b>"]
    lines += [f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)] or ["(тапшырмасыз)"]
    lines.append("\nТапшырманы унутсаңыз — жөн гана ушул жакка жазыңыз.")
    return "\n".join(lines)


def plan_after_delete(tasks, today) -> str:
    if not tasks:
        return PLAN_EMPTY
    lines = ["<b>Бүгүнкү планыңыз:</b>"]
    lines += [f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)]
    lines.append("\nТапшырманы унутсаңыз — жөн гана ушул жакка жазыңыз.")
    return "\n".join(lines)


def due_suffix(due, today) -> str:
    if due is None or due <= today:
        return ""
    return f" (мөөнөтү {due:%d.%m} чейин)"


def task_line(task, today, *, with_status: bool = False, show_due: bool = False) -> str:
    icon = STATUS_ICON.get(task.status, "▫️") + " " if with_status else ""
    manager = " 👤" if task.from_manager else ""
    due = due_suffix(task.due_date, today) if show_due else ""
    return f"{icon}{escape(task.text)}{manager}{due}"


def plan_text(tasks, today, *, title: str = "Бүгүнкү планыңыз") -> str:
    if not tasks:
        return PLAN_EMPTY
    lines = [f"<b>{title}:</b>"]
    lines += [f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)]
    return "\n".join(lines)


def my_tasks_text(tasks, today) -> str:
    if not tasks:
        return PLAN_EMPTY
    lines = ["<b>Бүгүнкү тапшырмалар:</b>"]
    lines += [f"{i}. {task_line(t, today, with_status=True, show_due=True)}" for i, t in enumerate(tasks, 1)]
    lines.append("\n📅 — мөөнөтүн эртеңге жылдыруу же бүгүнгө кайтаруу үчүн өз тапшырмаңызды басыңыз.")
    if any(t.from_manager for t in tasks):
        lines.append("👤 — жетекчинин тапшырмасы: анын мөөнөтүн жетекчи гана өзгөртөт.")
    return "\n".join(lines)


# ---------- Күндүн жыйынтыгы ----------
def report_question(index: int, total: int, task, today) -> str:
    return f"Тапшырма {index}/{total}:\n<b>{task_line(task, today)}</b>\n\nКандай болду?"


ASK_REASON = "Эмне тоскоол болду?"
ASK_COMMENT_OPTIONAL = "💬 Бир билдирүү менен түшүндүрмө кошуңуз же «Өткөрүп жиберүү» басыңыз."
ASK_COMMENT_REQUIRED = "💬 Себебин кыскача жазыңыз — бул статус үчүн түшүндүрмө милдеттүү."
REPORT_CONFIRM_Q = "Баары туурабы?"


def result_line(task_text: str, status: str, reason: str | None, comment: str | None) -> str:
    parts = [f"{STATUS_ICON.get(status, '')} {escape(task_text)}"]
    details = []
    if status in ("not_done", "cancelled", "blocked", "continue"):
        if reason:
            details.append(REASON_LABEL.get(reason, reason))
        elif status == "not_done":
            details.append(STATUS_LABEL["not_done"].lower())
    if comment:
        details.append(escape(comment))
    if details:
        parts.append(" — " + "; ".join(details))
    return "".join(parts)


def report_summary(rows) -> str:
    done = sum(1 for r in rows if r[1] == "done")
    lines = [f"<b>Күндүн жыйынтыгы: {len(rows)} тапшырманын {done} аткарылды</b>", ""]
    lines += [result_line(*r) for r in rows]
    lines.append("\n" + REPORT_CONFIRM_Q)
    return "\n".join(lines)


def tasks_block_for_group(rows) -> str:
    if not rows:
        return ""
    done = sum(1 for r in rows if r[1] == "done")
    lines = [f"\nТапшырмалар: {len(rows)} тапшырманын {done} аткарылды"]
    lines += [result_line(*r) for r in rows]
    return "\n".join(lines)


# ---------- Жетекчинин тапшырмалары ----------
ASSIGN_CHOOSE_EMPLOYEE = "Тапшырманы кимге бересиз?"
ASSIGN_NO_EMPLOYEES = "Кызматкерлер жок. Ээси аларды /add командасы менен кошот."
ASSIGN_DONE = "✅ Тапшырма берилди. Кызматкерге билдирүү барды."
ASSIGN_DUE = "Мөөнөтү качан?"


def assign_ask_text(name: str) -> str:
    return f"<b>{escape(name)}</b> үчүн тапшырманы бир билдирүү менен жазыңыз."


def new_task_from_manager(manager_name: str, text: str, due, today) -> str:
    when = "бүгүн" if due is None or due <= today else f"{due:%d.%m} чейин"
    return f"👤 <b>{escape(manager_name)} жаңы тапшырма берди</b>\n{escape(text)}\nМөөнөтү: {when}"


def task_accepted_note(employee_name: str, text: str) -> str:
    return f"👍 {escape(employee_name)} тапшырманы кабыл алды: {escape(text)}"


# ---------- Эскертүүлөр ----------
def alert_text(kind: str, employee_name: str, task_text: str, days_count: int, history) -> str:
    days = ", ".join(f"{r.work_date:%d.%m} — {STATUS_LABEL.get(r.status, r.status).lower()}" for r in history)
    comments = "; ".join(escape(r.comment) for r in history if r.comment)
    if kind == "blocked":
        head = (
            f"🆘 <b>Кызматкерге жардам керек</b>\n{escape(employee_name)}: «{escape(task_text)}» тапшырмасы "
            f"анын күнөөсү менен эмес, {days_count} күн катары менен аткарылбай жатат."
        )
    else:
        head = (
            f"⚠️ <b>Тапшырма аткарылбай жатат</b>\n{escape(employee_name)}: «{escape(task_text)}» тапшырмасы "
            f"{days_count} күн катары менен аткарылган жок."
        )
    text = f"{head}\n\n{days}"
    if comments:
        text += f"\nТүшүндүрмөлөр: {comments}"
    return text


ALERT_REMINDER = "🔁 <b>Эскертүү</b>\n"
ALERT_ACKED = "👌 Кабыл алынды"
ALERT_TASK_CANCELLED = "❌ Тапшырма жокко чыгарылды"


RESET_DONE = (
    "🔄 Бүгүнкү белгиңиз жана тапшырмалардын жыйынтыгы өчүрүлдү. Пландагы тапшырмалар кайра «Жаңы».\n"
    f"Күндү кайра баштасаңыз болот: «{BTN_CHECK_IN}»."
)


# ================= Отчеттор, табель, эскертмелер =================

BTN_REPORTS = "📊 Отчеттор"
BTN_TIMESHEET = "🗓 Табель"

REMIND_CHECK_IN = f"⏰ Кутман таң! Сиз али белгилене элексиз. Кеңседе болгондо «{BTN_CHECK_IN}» басыңыз."
REMIND_CHECK_OUT = f"🕕 Жумуш күнү бүттү. «{BTN_FINISH_DAY}» басып, тапшырмаларды белгилөөнү унутпаңыз."


def not_checked_in_summary(names: list[str]) -> str:
    return "⚠️ Али белгилене электер: " + ", ".join(escape(n) for n in names)


def backup_caption(day) -> str:
    return f"💾 {day:%d.%m.%Y} күнкү базанын көчүрмөсү. Бул файлды сактаңыз — андан бардык маалыматты калыбына келтирсе болот."


REPORTS_CHOOSE = "Кайсы отчетту көрсөтөйүн?"
REPORTS_ONLY_MANAGERS = "Отчеттор жетекчи жана ээси үчүн гана."
TS_CHOOSE_EMPLOYEE = "🗓 <b>Табель.</b> Кызматкерди тандаңыз:"
TS_CHOOSE_DAY = "Күндү тандаңыз:"
TS_ASK_DATE = "Күндү КК.АА форматында жазыңыз, мисалы <code>05.11</code>."
TS_BAD_DATE = "Күндү түшүнгөн жокмун. Мисал: <code>05.11</code> же <code>05.11.2026</code>."
TS_ASK_DAYS = "Канча күнгө (ушул күндү кошо)?"
TS_ASK_TIME_IN = "Келген туура убакытты жазыңыз, мисалы <code>08:30</code>."
TS_ASK_TIME_OUT = "Кеткен туура убакытты жазыңыз, мисалы <code>17:30</code>."
TS_BAD_TIME = "Убакытты түшүнгөн жокмун. Мисал: <code>08:35</code>."
TS_ASK_REASON = "Эмне үчүн оңдоп жатасыз? Кыскача жазыңыз — себеби журналда сакталат."
TS_ASK_SCHEDULE = "Иш убактысын жазыңыз, мисалы <code>08:30-17:30</code>."
TS_BAD_SCHEDULE = "Түшүнгөн жокмун. Мисал: <code>08:30-17:30</code> (аягы башынан кеч болушу керек)."
TS_ASK_SCHEDULE_DAYS = "Кайсы күндөр жумуш күнү?"
TS_SAVED = "✅ Сакталды."
TS_UNMARKED = "🧹 Белги алынды."
TS_NOTHING_TO_UNMARK = "Бул күнгө белги жок."

MENU_BUTTONS = frozenset(
    {
        BTN_CHECK_IN, BTN_FINISH_DAY, BTN_MY_TASKS, BTN_ADD_TASK, BTN_HELP, BTN_EMPLOYEES, BTN_ASSIGN,
        BTN_TASKS_DONE, BTN_SEND_LOCATION, BTN_CANCEL, BTN_REPORTS, BTN_TIMESHEET, BTN_SHARE_PHONE, BTN_LANG,
    }
)


def day_message(name: str, at_local, late: int, workday: bool, tasks, today, outside=None) -> str:
    """Жалпы чаттагы күндүн билдирүүсү: келүү жана план бир билдирүүдө."""
    if outside is not None:
        text = checked_in_group_outside(name, at_local, late, workday, *outside)
    else:
        text = checked_in_group(name, at_local, late, workday)
    if tasks:
        text += "\n\n📋 <b>Күндүн планы:</b>\n" + "\n".join(
            f"{i}. {task_line(t, today)}" for i, t in enumerate(tasks, 1)
        )
    return text
