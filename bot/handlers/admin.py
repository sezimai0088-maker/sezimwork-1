"""Команды владельца и список сотрудников для руководителя."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import texts
from bot.config import Settings
from bot.models import Employee, Role
from bot.phones import format_phone, normalize_phone
from bot.services import employees as emp
from bot.services.attendance import get_day, reset_day
from bot.worktime import as_utc

router = Router()

ROLE_NAMES = {Role.OWNER: "владелец", Role.MANAGER: "руководитель", Role.EMPLOYEE: "сотрудник"}
COMMAND_ROLES = {"add": Role.EMPLOYEE, "add_manager": Role.MANAGER, "add_owner": Role.OWNER}
ADD_USAGE = "Формат: <code>/add +996555123456 Имя Фамилия</code>"


def _parse_phone_and_name(args: str | None) -> tuple[str, str] | None:
    """'+996 555 12-34-56 Айбек Асанов' -> ('996555123456', 'Айбек Асанов')."""
    if not args:
        return None
    match = re.match(r"^\s*([+\d][\d\s\-()]{7,20}\d)\s+(.+?)\s*$", args)
    if not match:
        return None
    phone = normalize_phone(match.group(1))
    if not 9 <= len(phone) <= 15:
        return None
    return phone, match.group(2)


@router.message(Command("admin"), F.chat.type == "private")
async def cmd_admin(message: Message, employee: Employee | None) -> None:
    if employee is None or not employee.is_owner:
        await message.answer(texts.ADMIN_ONLY)
        return
    await message.answer(texts.HELP_ADMIN)


@router.message(Command("add", "add_manager", "add_owner"), F.chat.type == "private")
async def cmd_add(message: Message, command: CommandObject, session: AsyncSession, employee: Employee | None) -> None:
    if employee is None or not employee.is_owner:
        await message.answer(texts.ADMIN_ONLY)
        return
    parsed = _parse_phone_and_name(command.args)
    if parsed is None:
        usage = ADD_USAGE.replace("/add", f"/{command.command}")
        await message.answer(f"Не понял номер или имя.\n{usage}")
        return
    phone, name = parsed
    role = COMMAND_ROLES[command.command]
    try:
        new, created = await emp.add_employee(session, phone=phone, full_name=name, role=role, actor=employee)
    except emp.RemoveError as error:
        await message.answer(f"⚠️ {error}")
        return
    action = "Добавлен" if created else "Обновлён"
    await message.answer(
        f"✅ {action}: <b>{escape(new.full_name)}</b>, {format_phone(new.phone)} — {ROLE_NAMES[Role(new.role)]}.\n\n"
        "Отправьте человеку ссылку на бота: он нажмёт «Запустить» и «📱 Отправить мой номер»."
    )


@router.message(Command("remove"), F.chat.type == "private")
async def cmd_remove(message: Message, command: CommandObject, session: AsyncSession, employee: Employee | None) -> None:
    if employee is None or not employee.is_owner:
        await message.answer(texts.ADMIN_ONLY)
        return
    if not command.args:
        await message.answer("Формат: <code>/remove +996555123456</code>")
        return
    try:
        removed = await emp.deactivate(session, command.args, actor=employee)
    except emp.RemoveError as error:
        await message.answer(f"⚠️ {error}")
        return
    if removed is None:
        await message.answer("Сотрудник с таким номером не найден.")
        return
    await message.answer(f"Отключён: <b>{escape(removed.full_name)}</b>. Его история отметок сохранена.")


@router.message(Command("employees"), F.chat.type == "private")
@router.message(F.text == texts.BTN_EMPLOYEES, F.chat.type == "private")
async def cmd_employees(message: Message, session: AsyncSession, settings: Settings, employee: Employee | None) -> None:
    if employee is None or not employee.is_manager:
        await message.answer("Список сотрудников доступен только руководителю.")
        return
    today = datetime.now(timezone.utc).astimezone(settings.tz).date()
    people = await emp.list_employees(session)
    lines = [f"<b>Сотрудники на {today:%d.%m.%Y}</b>", ""]
    for person in people:
        day = await get_day(session, person.id, today)
        if person.telegram_id is None:
            status = "⚪ не подключён к боту"
        elif day is None:
            status = "— не отметился"
        else:
            status = f"🟢 пришёл {as_utc(day.check_in_at).astimezone(settings.tz):%H:%M}"
            if day.late_minutes:
                status += f" (опоздание {day.late_minutes} мин)"
            if day.check_out_at:
                status += f", ушёл {as_utc(day.check_out_at).astimezone(settings.tz):%H:%M}"
        role = "" if person.role == Role.EMPLOYEE else f" · {ROLE_NAMES[Role(person.role)]}"
        lines.append(f"{escape(person.full_name)}{role} — {status}")
    if len(people) == 0:
        lines.append("Пока никого нет. Добавьте: " + ADD_USAGE)
    await message.answer("\n".join(lines))


@router.message(Command("bind_chat"), F.chat.type.in_({"group", "supergroup"}))
async def cmd_bind_chat(message: Message, session: AsyncSession, employee: Employee | None) -> None:
    if employee is None or not employee.is_owner:
        await message.reply(texts.ADMIN_ONLY)
        return
    await emp.set_setting(session, emp.GROUP_CHAT_KEY, str(message.chat.id))
    await message.reply(texts.CHAT_BOUND)


@router.message(Command("reset_today"), F.chat.type == "private")
async def cmd_reset_today(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    """Для проверки: владелец сбрасывает свою сегодняшнюю отметку и итоги задач."""
    if employee is None or not employee.is_owner:
        await message.answer(texts.ADMIN_ONLY)
        return
    from bot.handlers.menu import menu_for

    await state.clear()
    today = datetime.now(timezone.utc).astimezone(settings.tz).date()
    await reset_day(session, employee.id, today)
    await message.answer(texts.RESET_DONE, reply_markup=await menu_for(session, settings, employee))
