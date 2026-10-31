"""Для руководителя и владельца: «📊 Отчёты» и «🗓 Табель» (отметки дней, исправления, график)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, report_texts, texts
from bot.callbacks import ReportsCb, TsCb
from bot.config import Settings
from bot.i18n import get_lang, lang_of, tr, use_lang
from bot.models import Attendance, DayKind, Employee, Role
from bot.schedule import parse_days, parse_hhmm, parse_range, schedule_for
from bot.services import calendar as cal
from bot.services import delivery
from bot.services.reports import day_status, month_bounds, previous_month, previous_week, week_bounds
from bot.states import Timesheet

router = Router()
router.message.filter(F.chat.type == "private")


def today_for(settings: Settings) -> date:
    return datetime.now(timezone.utc).astimezone(settings.tz).date()


def _manager(employee: Employee | None) -> bool:
    return employee is not None and employee.is_manager


async def _edit(message: Message, text: str, markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:
        await message.answer(text, reply_markup=markup)


# ======================= Отчёты =======================


@router.message(F.text.in_(texts.variants("BTN_REPORTS")))
async def reports_menu(message: Message, employee: Employee | None) -> None:
    if not _manager(employee):
        await message.answer(texts.REPORTS_ONLY_MANAGERS)
        return
    await message.answer(texts.REPORTS_CHOOSE, reply_markup=keyboards.reports_menu())


@router.callback_query(ReportsCb.filter())
async def reports_show(
    callback: CallbackQuery,
    callback_data: ReportsCb,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if not _manager(employee):
        return await callback.answer(texts.REPORTS_ONLY_MANAGERS, show_alert=True)
    await callback.answer(tr("Готовлю отчёт…", "Отчет даярдалып жатат…"))
    today = today_for(settings)
    chat = [(callback.from_user.id, get_lang())]
    period = callback_data.period
    if period in ("today", "yesterday"):
        day = today if period == "today" else today - timedelta(days=1)
        await delivery.send_daily(bot, session, settings, day, chat)
        return
    if period == "week":
        start, end, kind = *week_bounds(today), "week"
    elif period == "prev_week":
        start, end, kind = *previous_week(today), "week"
    elif period == "month":
        start, end, kind = *month_bounds(today), "month"
    else:
        start, end, kind = *previous_month(today), "month"
    await delivery.send_period(bot, session, settings, start, min(end, today) if end > today else end, kind, chat)


# ======================= Табель =======================


async def _staff(session: AsyncSession) -> list[Employee]:
    result = await session.scalars(
        select(Employee)
        .where(Employee.is_active.is_(True), Employee.role != Role.OWNER)
        .order_by(Employee.full_name)
    )
    return list(result)


def _parse_day(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()


def parse_user_date(text: str, today: date) -> date | None:
    """'05.11' или '05.11.2026' → дата. Без года — ближайшая к сегодняшнему дню."""
    match = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\s*", text or "")
    if not match:
        return None
    day_n, month_n, year_s = int(match.group(1)), int(match.group(2)), match.group(3)
    try:
        if year_s:
            year = int(year_s) + (2000 if len(year_s) == 2 else 0)
            return date(year, month_n, day_n)
        candidates = [date(today.year + dy, month_n, day_n) for dy in (-1, 0, 1)]
    except ValueError:
        return None
    return min(candidates, key=lambda d: abs((d - today).days))


async def _show_card(
    target: Message, session: AsyncSession, settings: Settings, emp_id: int, day: date, *, edit: bool
) -> None:
    if emp_id == 0:
        mark = await cal.get_mark(session, -1, day)  # -1: только общие отметки
        text = f"🎉 <b>{tr('Праздник для всех', 'Баары үчүн майрам')}</b> · {report_texts.fmt_day(day)}\n"
        if mark is not None:
            text += tr("Сейчас: праздник", "Азыр: майрам")
        else:
            text += tr("Сейчас: обычный день", "Азыр: кадимки күн")
    else:
        person = await session.get(Employee, emp_id)
        att = await session.scalar(
            select(Attendance).where(Attendance.employee_id == emp_id, Attendance.work_date == day)
        )
        sched = schedule_for(person, settings)
        info = day_status(
            employee=person,
            schedule=sched,
            day=day,
            attendance=att,
            mark=await cal.get_mark(session, emp_id, day),
            now_local=datetime.now(timezone.utc).astimezone(settings.tz),
            tz=settings.tz,
        )
        text = report_texts.day_card(person.full_name, day, info, sched, settings.tz)
    markup = keyboards.ts_actions(emp_id, day)
    if edit:
        await _edit(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text.in_(texts.variants("BTN_TIMESHEET")))
async def timesheet_start(message: Message, state: FSMContext, session: AsyncSession, employee: Employee | None) -> None:
    if not _manager(employee):
        await message.answer(texts.REPORTS_ONLY_MANAGERS)
        return
    await state.clear()
    await message.answer(texts.TS_CHOOSE_EMPLOYEE, reply_markup=keyboards.ts_employees(await _staff(session)))


@router.callback_query(TsCb.filter(F.action == "emp"))
async def ts_employee(
    callback: CallbackQuery, callback_data: TsCb, state: FSMContext, session: AsyncSession, settings: Settings,
    employee: Employee | None,
) -> None:
    if not _manager(employee):
        return await callback.answer()
    await state.clear()
    if callback_data.emp == 0:
        title = tr("🎉 Праздник для всех.", "🎉 Баары үчүн майрам.")
    else:
        person = await session.get(Employee, callback_data.emp)
        title = f"🗓 <b>{person.full_name}</b>"
    await _edit(callback.message, f"{title}\n{texts.TS_CHOOSE_DAY}", keyboards.ts_days(callback_data.emp, today_for(settings)))
    await callback.answer()


@router.callback_query(TsCb.filter(F.action == "day"))
async def ts_day(
    callback: CallbackQuery, callback_data: TsCb, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if not _manager(employee):
        return await callback.answer()
    await _show_card(callback.message, session, settings, callback_data.emp, _parse_day(callback_data.day), edit=True)
    await callback.answer()


@router.callback_query(TsCb.filter(F.action == "other"))
async def ts_other_date(callback: CallbackQuery, callback_data: TsCb, state: FSMContext, employee: Employee | None) -> None:
    if not _manager(employee):
        return await callback.answer()
    await state.set_state(Timesheet.date_text)
    await state.update_data(ts_emp=callback_data.emp)
    await callback.message.answer(texts.TS_ASK_DATE)
    await callback.answer()


@router.message(StateFilter(Timesheet.date_text), F.text, ~F.text.in_(texts.MENU_BUTTONS), ~F.text.startswith("/"))
async def ts_date_text(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    day = parse_user_date(message.text, today_for(settings))
    if day is None:
        await message.answer(texts.TS_BAD_DATE)
        return
    data = await state.get_data()
    await state.clear()
    await _show_card(message, session, settings, data["ts_emp"], day, edit=False)


@router.callback_query(TsCb.filter(F.action == "kind"))
async def ts_kind(callback: CallbackQuery, callback_data: TsCb, employee: Employee | None) -> None:
    if not _manager(employee):
        return await callback.answer()
    label = report_texts.day_kind_label(callback_data.value)
    since = tr(f"с {_parse_day(callback_data.day):%d.%m}", f"{_parse_day(callback_data.day):%d.%m} баштап")
    await _edit(
        callback.message,
        f"{report_texts.DAY_KIND_ICON.get(callback_data.value, '')} {label.capitalize()} {since}. {texts.TS_ASK_DAYS}",
        keyboards.ts_days_count(callback_data.emp, _parse_day(callback_data.day), callback_data.value),
    )
    await callback.answer()


@router.callback_query(TsCb.filter(F.action == "days"))
async def ts_days(
    callback: CallbackQuery, callback_data: TsCb, bot: Bot, session: AsyncSession, settings: Settings,
    employee: Employee | None,
) -> None:
    if not _manager(employee):
        return await callback.answer()
    kind, count = callback_data.value.split("|")
    start = _parse_day(callback_data.day)
    emp_id = callback_data.emp or None
    marked = await cal.set_marks(
        session, employee_id=emp_id, start=start, days=int(count), kind=DayKind(kind), comment=None, actor=employee
    )
    await callback.answer(texts.TS_SAVED)
    if emp_id is not None:
        person = await session.get(Employee, emp_id)
        if person.telegram_id:
            with use_lang(lang_of(person)):
                notice = report_texts.mark_notice(kind, marked[0], marked[-1])
            try:
                await bot.send_message(person.telegram_id, notice)
            except Exception:  # noqa: BLE001
                pass
    period = f"{marked[0]:%d.%m}" if marked[0] == marked[-1] else f"{marked[0]:%d.%m}–{marked[-1]:%d.%m}"
    await callback.message.answer(f"{texts.TS_SAVED} {report_texts.day_kind_label(kind)}, {period}.")
    await _show_card(callback.message, session, settings, callback_data.emp, start, edit=True)


@router.callback_query(TsCb.filter(F.action == "unmark"))
async def ts_unmark(
    callback: CallbackQuery, callback_data: TsCb, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if not _manager(employee):
        return await callback.answer()
    day = _parse_day(callback_data.day)
    removed = await cal.remove_mark(session, employee_id=callback_data.emp or None, day=day, actor=employee)
    await callback.answer(texts.TS_UNMARKED if removed else texts.TS_NOTHING_TO_UNMARK)
    await _show_card(callback.message, session, settings, callback_data.emp, day, edit=True)


@router.callback_query(TsCb.filter(F.action.in_({"in", "out"})))
async def ts_time_start(callback: CallbackQuery, callback_data: TsCb, state: FSMContext, employee: Employee | None) -> None:
    if not _manager(employee):
        return await callback.answer()
    await state.set_state(Timesheet.time)
    await state.update_data(ts_emp=callback_data.emp, ts_day=callback_data.day, ts_kind=callback_data.action)
    await callback.message.answer(texts.TS_ASK_TIME_IN if callback_data.action == "in" else texts.TS_ASK_TIME_OUT)
    await callback.answer()


@router.message(StateFilter(Timesheet.time), F.text, ~F.text.in_(texts.MENU_BUTTONS), ~F.text.startswith("/"))
async def ts_time_text(message: Message, state: FSMContext) -> None:
    value = parse_hhmm(message.text)
    if value is None:
        await message.answer(texts.TS_BAD_TIME)
        return
    await state.update_data(ts_time=f"{value:%H:%M}")
    await state.set_state(Timesheet.reason)
    await message.answer(texts.TS_ASK_REASON)


@router.message(StateFilter(Timesheet.reason), F.text, ~F.text.in_(texts.MENU_BUTTONS), ~F.text.startswith("/"))
async def ts_reason_text(
    message: Message, state: FSMContext, bot: Bot, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if not _manager(employee):
        return
    data = await state.get_data()
    reason = message.text.strip()[:500]
    if len(reason) < 2:
        await message.answer(texts.TS_ASK_REASON)
        return
    person = await session.get(Employee, data["ts_emp"])
    day = _parse_day(data["ts_day"])
    try:
        await cal.correct_time(
            session,
            settings,
            employee=person,
            day=day,
            kind=data["ts_kind"],
            new_time=parse_hhmm(data["ts_time"]),
            reason=reason,
            actor=employee,
        )
    except cal.CorrectionError as error:
        await state.clear()
        await message.answer(f"⚠️ {error}")
        await _show_card(message, session, settings, person.id, day, edit=False)
        return
    await state.clear()
    if person.telegram_id and person.id != employee.id:
        try:
            with use_lang(lang_of(person)):
                notice = report_texts.correction_notice(data["ts_kind"], day, data["ts_time"], reason)
            await bot.send_message(person.telegram_id, notice)
        except Exception:  # noqa: BLE001
            pass
    await message.answer(texts.TS_SAVED)
    await _show_card(message, session, settings, person.id, day, edit=False)


@router.callback_query(TsCb.filter(F.action == "sched"))
async def ts_schedule_start(
    callback: CallbackQuery, callback_data: TsCb, state: FSMContext, session: AsyncSession, settings: Settings,
    employee: Employee | None,
) -> None:
    if not _manager(employee):
        return await callback.answer()
    person = await session.get(Employee, callback_data.emp)
    await state.set_state(Timesheet.schedule)
    await state.update_data(ts_emp=person.id, ts_day=callback_data.day)
    await callback.message.answer(
        tr(f"Сейчас у {person.full_name}: ", f"{person.full_name} азыр: ")
        + f"{schedule_for(person, settings).describe()}.\n{texts.TS_ASK_SCHEDULE}"
    )
    await callback.answer()


@router.message(StateFilter(Timesheet.schedule), F.text, ~F.text.in_(texts.MENU_BUTTONS), ~F.text.startswith("/"))
async def ts_schedule_text(message: Message, state: FSMContext) -> None:
    parsed = parse_range(message.text)
    if parsed is None:
        await message.answer(texts.TS_BAD_SCHEDULE)
        return
    start, end = parsed
    await state.update_data(ts_start=f"{start:%H:%M}", ts_end=f"{end:%H:%M}")
    data = await state.get_data()
    await message.answer(texts.TS_ASK_SCHEDULE_DAYS, reply_markup=keyboards.ts_schedule_days(data["ts_emp"]))


@router.callback_query(StateFilter(Timesheet.schedule), TsCb.filter(F.action == "sdays"))
async def ts_schedule_days(
    callback: CallbackQuery, callback_data: TsCb, state: FSMContext, session: AsyncSession, settings: Settings,
    employee: Employee | None,
) -> None:
    if not _manager(employee):
        return await callback.answer()
    data = await state.get_data()
    if "ts_start" not in data:
        return await callback.answer(texts.TS_ASK_SCHEDULE, show_alert=True)
    person = await session.get(Employee, data["ts_emp"])
    await cal.set_schedule(
        session,
        employee=person,
        start=parse_hhmm(data["ts_start"]),
        end=parse_hhmm(data["ts_end"]),
        work_days=parse_days(callback_data.value),
        actor=employee,
        settings=settings,
    )
    await state.clear()
    await _edit(callback.message, f"{texts.TS_SAVED} {tr('График', 'График')} {person.full_name}: {schedule_for(person, settings).describe()}")
    await callback.answer(texts.TS_SAVED)
    await _show_card(callback.message, session, settings, person.id, _parse_day(data["ts_day"]), edit=False)
