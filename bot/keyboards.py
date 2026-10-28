"""Кнопки внизу экрана. У сотрудника всегда не больше 2–3 крупных кнопок."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot import texts
from bot.models import Employee


def _kb(rows: list[list[KeyboardButton]]) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def share_phone() -> ReplyKeyboardMarkup:
    return _kb([[KeyboardButton(text=texts.BTN_SHARE_PHONE, request_contact=True)]])


def checkout_location() -> ReplyKeyboardMarkup:
    return _kb(
        [
            [KeyboardButton(text=texts.BTN_SEND_LOCATION, request_location=True)],
            [KeyboardButton(text=texts.BTN_CANCEL)],
        ]
    )


def main_menu(employee: Employee, *, checked_in: bool, checked_out: bool) -> ReplyKeyboardMarkup:
    """Главное меню зависит от того, отметился ли сотрудник сегодня."""
    if not checked_in:
        rows = [[KeyboardButton(text=texts.BTN_CHECK_IN, request_location=True)]]
    elif not checked_out:
        rows = [[KeyboardButton(text=texts.BTN_FINISH_DAY)]]
    else:
        rows = []

    extra = [KeyboardButton(text=texts.BTN_HELP)]
    if employee.is_manager:
        extra.insert(0, KeyboardButton(text=texts.BTN_EMPLOYEES))
    rows.append(extra)
    return _kb(rows)
