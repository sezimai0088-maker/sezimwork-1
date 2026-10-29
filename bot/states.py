"""Шаги диалогов (где сейчас находится пользователь)."""

from aiogram.fsm.state import State, StatesGroup


class Checkout(StatesGroup):
    waiting_location = State()


class Plan(StatesGroup):
    writing = State()    # ввод задач текстом: каждое сообщение сразу сохраняется


class Report(StatesGroup):
    status = State()     # выбор статуса задачи
    reason = State()     # причина «Не по моей вине»
    comment = State()    # комментарий
    confirm = State()    # подтверждение итога дня


class Assign(StatesGroup):
    text = State()       # руководитель пишет текст задачи


class Timesheet(StatesGroup):
    date_text = State()      # руководитель вводит дату
    time = State()           # вводит время прихода/ухода
    reason = State()         # причина исправления
    schedule = State()       # время работы для графика
