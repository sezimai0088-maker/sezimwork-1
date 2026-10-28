"""Первое подключение: сотрудник отправляет свой номер, бот находит его в списке."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, texts
from bot.config import Settings
from bot.handlers.menu import menu_for
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
    menu = await menu_for(session, settings, employee)
    if result.status == RegisterStatus.OWNER_CREATED:
        await message.answer(texts.owner_created(employee.full_name), reply_markup=menu)
    else:
        await message.answer(texts.registered(employee.full_name), reply_markup=menu)
