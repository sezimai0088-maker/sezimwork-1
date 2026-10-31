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
from bot.i18n import tr
from bot.models import Employee, Role
from bot.phones import format_phone, normalize_phone
from bot.services import employees as emp
from bot.services.attendance import get_day, reset_day
from bot.worktime import as_utc, format_duration

router = Router()

def role_name(role: str) -> str:
    names = {
        Role.OWNER: tr("владелец", "ээси"),
        Role.MANAGER: tr("руководитель", "жетекчи"),
        Role.EMPLOYEE: tr("сотрудник", "кызматкер"),
    }
    return names[Role(role)]


COMMAND_ROLES = {"add": Role.EMPLOYEE, "add_manager": Role.MANAGER, "add_owner": Role.OWNER}
def add_usage(command: str = "add") -> str:
    return tr("Формат", "Формат") + f": <code>/{command} +996555123456 {tr('Имя Фамилия', 'Аты Фамилиясы')}</code>"


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
        await message.answer(tr("Не понял номер или имя.", "Номерди же атты түшүнгөн жокмун.") + "\n" + add_usage(command.command))
        return
    phone, name = parsed
    role = COMMAND_ROLES[command.command]
    try:
        new, created = await emp.add_employee(session, phone=phone, full_name=name, role=role, actor=employee)
    except emp.RemoveError as error:
        await message.answer(f"⚠️ {error}")
        return
    action = tr("Добавлен", "Кошулду") if created else tr("Обновлён", "Жаңыртылды")
    await message.answer(
        f"✅ {action}: <b>{escape(new.full_name)}</b>, {format_phone(new.phone)} — {role_name(new.role)}.\n\n"
        + tr(
            "Отправьте человеку ссылку на бота: он нажмёт «Запустить», «📱» (свой номер) и выберет язык.",
            "Адамга боттун шилтемесин жөнөтүңүз: ал «Запустить», «📱» (өз номери) басып, тилди тандайт.",
        )
    )


@router.message(Command("remove"), F.chat.type == "private")
async def cmd_remove(message: Message, command: CommandObject, session: AsyncSession, employee: Employee | None) -> None:
    if employee is None or not employee.is_owner:
        await message.answer(texts.ADMIN_ONLY)
        return
    if not command.args:
        await message.answer(tr("Формат", "Формат") + ": <code>/remove +996555123456</code>")
        return
    try:
        removed = await emp.deactivate(session, command.args, actor=employee)
    except emp.RemoveError as error:
        await message.answer(f"⚠️ {error}")
        return
    if removed is None:
        await message.answer(tr("Сотрудник с таким номером не найден.", "Мындай номери бар кызматкер табылган жок."))
        return
    await message.answer(
        tr("Отключён", "Өчүрүлдү") + f": <b>{escape(removed.full_name)}</b>. "
        + tr("Его история отметок сохранена.", "Анын белгилеринин тарыхы сакталды.")
    )


@router.message(Command("employees"), F.chat.type == "private")
@router.message(F.text.in_(texts.variants("BTN_EMPLOYEES")), F.chat.type == "private")
async def cmd_employees(message: Message, session: AsyncSession, settings: Settings, employee: Employee | None) -> None:
    if employee is None or not employee.is_manager:
        await message.answer(tr("Список сотрудников доступен только руководителю.", "Кызматкерлердин тизмеси жетекчи үчүн гана."))
        return
    today = datetime.now(timezone.utc).astimezone(settings.tz).date()
    people = await emp.list_employees(session)
    lines = [f"<b>{tr('Сотрудники на', 'Кызматкерлер,')} {today:%d.%m.%Y}</b>", ""]
    for person in people:
        day = await get_day(session, person.id, today)
        if person.telegram_id is None:
            status = tr("⚪ не подключён к боту", "⚪ ботко туташа элек")
        elif day is None:
            status = tr("— не отметился", "— белгилене элек")
        else:
            icon = "🟠" if day.is_outside else "🟢"
            came = tr("вне офиса", "кеңседен тышкары") if day.is_outside else tr("пришёл", "келди")
            status = f"{icon} {came} {as_utc(day.check_in_at).astimezone(settings.tz):%H:%M}"
            if day.late_minutes:
                status += f" ({tr('опоздание', 'кечигүү')} {format_duration(day.late_minutes)})"
            if day.check_out_at:
                status += f", {tr('ушёл', 'кетти')} {as_utc(day.check_out_at).astimezone(settings.tz):%H:%M}"
        role = "" if person.role == Role.EMPLOYEE else f" · {role_name(person.role)}"
        lines.append(f"{escape(person.full_name)}{role} — {status}")
    if len(people) == 0:
        lines.append(tr("Пока никого нет. Добавьте: ", "Азырынча эч ким жок. Кошуңуз: ") + add_usage())
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
