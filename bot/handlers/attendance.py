"""Приход («Я в офисе») и уход («Завершить день»)."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, texts
from bot.config import Settings
from bot.geo import twogis_link
from bot.handlers.menu import menu_for
from bot.handlers.tasks import start_planning, start_report
from bot.models import CheckoutMode, Employee
from bot.services import attendance as att
from bot.services import tasks as task_svc
from bot.services.notify import send_to_group
from bot.states import Checkout
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


@router.message(F.text == texts.BTN_FINISH_DAY)
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


@router.message(StateFilter(Checkout.waiting_location), F.text == texts.BTN_CANCEL)
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
    if is_field:
        group_text = texts.checked_out_group_field(
            employee.full_name, at_local, worked, twogis_link(loc.latitude, loc.longitude, settings.twogis_base_url)
        )
    else:
        group_text = texts.checked_out_group_office(
            employee.full_name, at_local, worked, result.attendance.early_leave_minutes
        )

    results = await task_svc.day_results(session, employee.id, today)
    group_text += texts.tasks_block_for_group([(r.task.text, r.status, r.reason, r.comment) for r in results])

    sent = await send_to_group(bot, session, settings, group_text)
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
        await message.answer(texts.LOW_ACCURACY, reply_markup=menu)
        return
    if result.status == att.CheckInStatus.OUTSIDE:
        await message.answer(texts.outside_zone(result.zone.distance_m), reply_markup=menu)
        return

    day = result.attendance
    at_local = message.date.astimezone(settings.tz)
    sent = await send_to_group(
        bot, session, settings, texts.checked_in_group(employee.full_name, at_local, day.late_minutes, day.is_workday)
    )
    await message.answer(texts.checked_in_private(at_local, day.late_minutes), reply_markup=menu)
    if not sent and employee.is_owner:
        await message.answer(texts.GROUP_NOT_SET)
    # Сразу после прихода — план на день
    await start_planning(message, state, session, employee, at_local.date())


# ---------- Помощь ----------


@router.message(F.text == texts.BTN_HELP)
async def help_button(message: Message, session: AsyncSession, settings: Settings, employee: Employee | None) -> None:
    if not await _require_employee(message, employee):
        return
    text = texts.HELP_EMPLOYEE + ("\n\n" + texts.HELP_ADMIN if employee.is_owner else "")
    await message.answer(text, reply_markup=await menu_for(session, settings, employee))
