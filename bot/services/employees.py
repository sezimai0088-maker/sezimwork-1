"""Сотрудники, роли и настройки."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Employee, Role, Setting
from bot.phones import normalize_phone

GROUP_CHAT_KEY = "group_chat_id"


class RegisterStatus(StrEnum):
    REGISTERED = "registered"          # номер найден, Telegram привязан
    OWNER_CREATED = "owner_created"    # первый вход владельца
    ALREADY = "already"                # этот Telegram уже привязан
    NOT_FOUND = "not_found"            # номера нет в списке
    PHONE_TAKEN = "phone_taken"        # номер привязан к другому Telegram
    INACTIVE = "inactive"              # сотрудник отключён


@dataclass
class RegisterResult:
    status: RegisterStatus
    employee: Employee | None = None


async def get_by_telegram(session: AsyncSession, telegram_id: int) -> Employee | None:
    return await session.scalar(select(Employee).where(Employee.telegram_id == telegram_id))


async def get_by_phone(session: AsyncSession, phone: str) -> Employee | None:
    return await session.scalar(select(Employee).where(Employee.phone == normalize_phone(phone)))


async def register_by_contact(
    session: AsyncSession,
    *,
    telegram_id: int,
    phone: str,
    telegram_name: str,
    owner_phone: str,
) -> RegisterResult:
    """Привязывает Telegram-аккаунт к сотруднику по номеру телефона."""
    phone = normalize_phone(phone)

    existing = await get_by_telegram(session, telegram_id)
    if existing is not None:
        return RegisterResult(RegisterStatus.ALREADY, existing)

    employee = await get_by_phone(session, phone)

    if employee is None and phone == owner_phone:
        employee = Employee(phone=phone, full_name=telegram_name or "Владелец", role=Role.OWNER)
        session.add(employee)
        employee.telegram_id = telegram_id
        await session.commit()
        return RegisterResult(RegisterStatus.OWNER_CREATED, employee)

    if employee is None:
        return RegisterResult(RegisterStatus.NOT_FOUND)
    if not employee.is_active:
        return RegisterResult(RegisterStatus.INACTIVE, employee)
    if employee.telegram_id is not None and employee.telegram_id != telegram_id:
        return RegisterResult(RegisterStatus.PHONE_TAKEN, employee)

    if phone == owner_phone:
        employee.role = Role.OWNER
    employee.telegram_id = telegram_id
    await session.commit()
    return RegisterResult(RegisterStatus.REGISTERED, employee)


async def add_employee(
    session: AsyncSession, *, phone: str, full_name: str, role: Role = Role.EMPLOYEE
) -> tuple[Employee, bool]:
    """Добавляет сотрудника или обновляет имя и роль существующего. Возвращает (сотрудник, создан_ли)."""
    phone = normalize_phone(phone)
    employee = await get_by_phone(session, phone)
    created = employee is None
    if employee is None:
        employee = Employee(phone=phone, full_name=full_name, role=role)
        session.add(employee)
    else:
        employee.full_name = full_name
        if employee.role != Role.OWNER:
            employee.role = role
        employee.is_active = True
    await session.commit()
    return employee, created


async def deactivate(session: AsyncSession, phone: str) -> Employee | None:
    employee = await get_by_phone(session, phone)
    if employee is None or employee.role == Role.OWNER:
        return None
    employee.is_active = False
    employee.telegram_id = None
    await session.commit()
    return employee


async def list_employees(session: AsyncSession) -> list[Employee]:
    result = await session.scalars(
        select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.role, Employee.full_name)
    )
    return list(result)


async def get_setting(session: AsyncSession, key: str) -> str | None:
    setting = await session.get(Setting, key)
    return setting.value if setting else None


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    setting = await session.get(Setting, key)
    if setting is None:
        session.add(Setting(key=key, value=value))
    else:
        setting.value = value
    await session.commit()


async def get_group_chat_id(session: AsyncSession, fallback: int | None) -> int | None:
    value = await get_setting(session, GROUP_CHAT_KEY)
    return int(value) if value else fallback
