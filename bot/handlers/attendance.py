"""Приход («Я в офисе») и уход («Завершить день»)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta

from bot import keyboards, texts
from bot.config import Settings
from bot.geo import twogis_link
from bot.i18n import lang_of, use_lang
from bot.handlers.menu import menu_for
from bot.handlers.tasks import start_planning, start_report
from bot.models import CheckoutMode, Employee
from bot.services import attendance as att
from bot.services import tasks as task_svc
from bot.services import day_message
from bot.states import Checkout, OutsideCheckin
from bot.worktime import as_utc

router = Router()
router.message.filter(F.chat.type == "private")


async def _require_employee(message: Message, employee: Employee | None) -> bool:
    if employee is None:
        await message.answer(texts.WELCOME_NEW, reply_markup=keyboards.share_phone())
        return False
    return True


async def _reject_untrusted_location(message: Message) -> bool:
    """Отклоняет место, выбранное на карте вручную, и пересланные геопозиции."""
    if message.venue is not None:
        await message.answer(texts.VENUE_LOCATION)
        return True
    if message.forward_origin is not None:
        await message.answer(texts.FORWARDED_LOCATION)
        return True
    return False


# ---------- Уход ----------


@router.message(F.text.in_(texts.variants("BTN_FINISH_DAY")))
async def finish_day(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if not await _require_employee(message, employee):
        return
    today = message.date.astimezone(settings.tz).date()
    day = await att.get_day(session, employee.id, today)
    if day is None:
        await message.answer(texts.NOT_CHECKED_IN, reply_markup=await menu_for(session, settings, employee))
        return
    if day.check_out_at is not None:
        await message.answer(
            texts.already_checked_out(as_utc(day.check_out_at).astimezone(settings.tz)),
            reply_markup=await menu_for(session, settings, employee),
        )
        return
    # Сначала итог по задачам, потом геолокация
    if await start_report(message, state, session, employee, today):
        return
    await state.set_state(Checkout.waiting_location)
    await message.answer(texts.ASK_CHECKOUT_LOCATION, reply_markup=keyboards.checkout_location())


@router.message(StateFilter(Checkout.waiting_location), F.text.in_(texts.variants("BTN_CANCEL")))
async def cancel_checkout(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    await state.clear()
    if employee is None:
        return
    await message.answer(texts.CHECKOUT_CANCELLED, reply_markup=await menu_for(session, settings, employee))


@router.message(StateFilter(Checkout.waiting_location), F.location)
async def checkout_location(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if not await _require_employee(message, employee):
        await state.clear()
        return
    if await _reject_untrusted_location(message):
        return

    today = message.date.astimezone(settings.tz).date()
    day = await att.get_day(session, employee.id, today)
    if day is None or day.check_out_at is not None:
        await state.clear()
        await message.answer(texts.NOT_CHECKED_IN, reply_markup=await menu_for(session, settings, employee))
        return

    loc = message.location
    # При неточной геопозиции нельзя понять, офис это или поле: просим повторить, шаг не сбрасываем
    if loc.horizontal_accuracy is not None and loc.horizontal_accuracy > settings.max_accuracy_m:
        await message.answer(texts.low_accuracy_text(loc.horizontal_accuracy), reply_markup=keyboards.checkout_location())
        return
    result = await att.check_out(
        session,
        settings,
        day,
        lat=loc.latitude,
        lon=loc.longitude,
        accuracy_m=loc.horizontal_accuracy,
        now=message.date,
    )
    await state.clear()

    at_local = message.date.astimezone(settings.tz)
    is_field = result.mode == CheckoutMode.FIELD
    worked = result.attendance.worked_minutes or 0
    results = await task_svc.day_results(session, employee.id, today)
    with use_lang(settings.group_lang):  # в общий чат — на языке группы
        if is_field:
            group_text = texts.checked_out_group_field(
                employee.full_name, at_local, worked, twogis_link(loc.latitude, loc.longitude, settings.twogis_base_url)
            )
        else:
            group_text = texts.checked_out_group_office(
                employee.full_name, at_local, worked, result.attendance.early_leave_minutes
            )
        group_text += texts.tasks_block_for_group([(r.task.text, r.status, r.reason, r.comment) for r in results])

    # План так и не отправили — сначала публикуем приход и план, уход будет ответом на них
    if result.attendance.group_message_id is None:
        await day_message.refresh(bot, session, settings, employee, today)
    sent = await day_message.post_departure(bot, session, settings, result.attendance, group_text)
    await message.answer(
        texts.checked_out_private(at_local, worked, is_field),
        reply_markup=await menu_for(session, settings, employee),
    )
    if not sent and employee.is_owner:
        await message.answer(texts.GROUP_NOT_SET)


# ---------- Приход ----------


@router.message(F.location)
async def checkin_location(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if not await _require_employee(message, employee):
        return
    if await state.get_state() == OutsideCheckin.comment.state:
        await state.clear()  # сотрудник отправил место ещё раз — проверяем заново
    if await _reject_untrusted_location(message):
        return

    loc = message.location
    result = await att.check_in(
        session,
        settings,
        employee,
        lat=loc.latitude,
        lon=loc.longitude,
        accuracy_m=loc.horizontal_accuracy,
        now=message.date,
    )
    menu = await menu_for(session, settings, employee)

    if result.status == att.CheckInStatus.ALREADY:
        day = result.attendance
        if day.check_out_at is not None:
            text = texts.already_checked_out(as_utc(day.check_out_at).astimezone(settings.tz))
        else:
            text = texts.already_checked_in(as_utc(day.check_in_at).astimezone(settings.tz))
        await message.answer(text, reply_markup=menu)
        return
    if result.status == att.CheckInStatus.LOW_ACCURACY:
        await message.answer(texts.low_accuracy_text(message.location.horizontal_accuracy), reply_markup=menu)
        return
    if result.status == att.CheckInStatus.OUTSIDE:
        if not settings.allow_outside_checkin:
            await message.answer(texts.outside_zone(result.zone.distance_m), reply_markup=menu)
            return
        # Не в офисе: просим написать, где он и почему — приход отметится вне офиса с комментарием
        await state.set_state(OutsideCheckin.comment)
        await state.update_data(
            out_lat=loc.latitude,
            out_lon=loc.longitude,
            out_acc=loc.horizontal_accuracy,
            out_at=message.date.isoformat(),
        )
        await message.answer(texts.outside_ask(result.zone.distance_m), reply_markup=keyboards.outside_checkin())
        return

    day = result.attendance
    at_local = message.date.astimezone(settings.tz)
    # В общий чат пока ничего не отправляем: сначала сотрудник пишет план,
    # затем «📤 Отправить план» — и уходит одно сообщение «приход + план».
    await message.answer(texts.checked_in_private(at_local, day.late_minutes), reply_markup=menu)
    # Сразу после прихода — план на день
    await start_planning(message, state, bot, session, settings, employee, day.work_date)


# ---------- Приход вне офиса ----------

OUTSIDE_TTL = timedelta(hours=2)


@router.message(StateFilter(OutsideCheckin.comment), F.text.in_(texts.variants("BTN_CANCEL")))
async def outside_cancel(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    await state.clear()
    if employee is None:
        return
    await message.answer(texts.OUTSIDE_CANCELLED, reply_markup=await menu_for(session, settings, employee))


@router.message(StateFilter(OutsideCheckin.comment), F.text, ~F.text.in_(texts.MENU_BUTTONS), ~F.text.startswith("/"))
async def outside_comment(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if not await _require_employee(message, employee):
        await state.clear()
        return
    comment = message.text.strip()
    if len(comment) < 3:
        await message.answer(texts.OUTSIDE_COMMENT_SHORT)
        return
    data = await state.get_data()
    sent_at = datetime.fromisoformat(data["out_at"])
    # Время прихода — когда отправил местоположение. Если комментарий пришёл слишком поздно — заново.
    if message.date - sent_at > OUTSIDE_TTL or (
        message.date.astimezone(settings.tz).date() != sent_at.astimezone(settings.tz).date()
    ):
        await state.clear()
        await message.answer(texts.OUTSIDE_EXPIRED, reply_markup=await menu_for(session, settings, employee))
        return
    result = await att.check_in_outside(
        session,
        settings,
        employee,
        lat=data["out_lat"],
        lon=data["out_lon"],
        accuracy_m=data.get("out_acc"),
        now=sent_at,
        comment=comment,
    )
    await state.clear()
    menu = await menu_for(session, settings, employee)
    day = result.attendance
    if result.status == att.CheckInStatus.ALREADY:
        await message.answer(texts.already_checked_in(as_utc(day.check_in_at).astimezone(settings.tz)), reply_markup=menu)
        return

    at_local = sent_at.astimezone(settings.tz)
    await message.answer(texts.checked_in_private(at_local, day.late_minutes, outside=True), reply_markup=menu)
    await _notify_outside(bot, session, settings, employee, day)
    await start_planning(message, state, bot, session, settings, employee, day.work_date)


async def _notify_outside(bot: Bot, session: AsyncSession, settings: Settings, employee: Employee, day) -> None:
    """Руководителю сразу: кто, где (расстояние, 2ГИС) и почему не в офисе."""
    from bot.services.reports import report_recipients

    recipients = await task_svc.managers(session) or await report_recipients(session)
    at_local = as_utc(day.check_in_at).astimezone(settings.tz)
    distance, link, comment = day_message.outside_info(settings, day)
    for person in recipients:
        if person.id == employee.id or not person.telegram_id:
            continue
        with use_lang(lang_of(person)):
            text = texts.outside_manager_note(
                employee.full_name, at_local, day.late_minutes, day.is_workday, distance, link, comment
            )
        try:
            await bot.send_message(person.telegram_id, text, disable_web_page_preview=True)
        except Exception:  # noqa: BLE001 — недоступный руководитель не должен мешать отметке
            pass


# ---------- Помощь ----------


@router.message(F.text.in_(texts.variants("BTN_HELP")))
async def help_button(message: Message, session: AsyncSession, settings: Settings, employee: Employee | None) -> None:
    if not await _require_employee(message, employee):
        return
    text = texts.HELP_EMPLOYEE + ("\n\n" + texts.HELP_ADMIN if employee.is_owner else "")
    await message.answer(text, reply_markup=await menu_for(session, settings, employee))
