"""Первое подключение: сотрудник отправляет свой номер, бот находит его в списке и спрашивает язык."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, texts
from bot.callbacks import LangCb
from bot.config import Settings
from bot.handlers.menu import menu_for
from bot.i18n import normalize, set_lang
from bot.models import Employee
from bot.services.employees import RegisterStatus, register_by_contact

router = Router()
router.message.filter(F.chat.type == "private")


@router.message(CommandStart())
async def cmd_start(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    await state.clear()
    if employee is None:
        await message.answer(texts.WELCOME_NEW, reply_markup=keyboards.share_phone())
        return
    if employee.lang is None:
        # Подключился до появления выбора языка — спрашиваем один раз
        await message.answer(texts.CHOOSE_LANG, reply_markup=keyboards.lang_choice(first=True))
        return
    await message.answer(
        texts.welcome_back(employee.full_name), reply_markup=await menu_for(session, settings, employee)
    )


@router.message(F.contact)
async def on_contact(message: Message, session: AsyncSession, settings: Settings) -> None:
    contact = message.contact
    # Принимаем только собственный номер: чужой контакт можно переслать, свой — только кнопкой.
    if contact.user_id != message.from_user.id:
        await message.answer(texts.SHARE_OWN_CONTACT, reply_markup=keyboards.share_phone())
        return

    result = await register_by_contact(
        session,
        telegram_id=message.from_user.id,
        phone=contact.phone_number,
        telegram_name=message.from_user.full_name,
        owner_phone=settings.owner_phone,
    )

    if result.status == RegisterStatus.NOT_FOUND:
        await message.answer(texts.NOT_FOUND, reply_markup=keyboards.share_phone())
        return
    if result.status == RegisterStatus.PHONE_TAKEN:
        await message.answer(texts.PHONE_TAKEN)
        return
    if result.status == RegisterStatus.INACTIVE:
        await message.answer(texts.INACTIVE)
        return

    employee = result.employee
    if employee.lang is None:
        # Сразу после номера — выбор языка; приветствие и меню будут уже на выбранном языке
        await message.answer(texts.CHOOSE_LANG, reply_markup=keyboards.lang_choice(first=True))
        return
    set_lang(employee.lang)
    await _greet(message, session, settings, employee, created=result.status == RegisterStatus.OWNER_CREATED)


async def _greet(message: Message, session: AsyncSession, settings: Settings, employee: Employee, *, created: bool) -> None:
    menu = await menu_for(session, settings, employee)
    if created or employee.is_owner:
        await message.answer(texts.owner_created(employee.full_name), reply_markup=menu)
    else:
        await message.answer(texts.registered(employee.full_name), reply_markup=menu)


@router.message(Command("lang"))
@router.message(F.text.in_(texts.variants("BTN_LANG")))
async def choose_lang(message: Message, employee: Employee | None) -> None:
    if employee is None:
        await message.answer(texts.WELCOME_NEW, reply_markup=keyboards.share_phone())
        return
    await message.answer(texts.CHOOSE_LANG, reply_markup=keyboards.lang_choice())


@router.callback_query(LangCb.filter())
async def lang_selected(
    callback: CallbackQuery, callback_data: LangCb, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if employee is None:
        return await callback.answer()
    employee.lang = normalize(callback_data.code)
    await session.commit()
    set_lang(employee.lang)  # дальше отвечаем уже на новом языке
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
    await callback.answer()
    if callback_data.first == "1":
        await _greet(callback.message, session, settings, employee, created=False)
    else:
        await callback.message.answer(texts.LANG_SET, reply_markup=await menu_for(session, settings, employee))
