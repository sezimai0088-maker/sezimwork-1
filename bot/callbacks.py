"""Данные inline-кнопок (под сообщениями)."""

from aiogram.filters.callback_data import CallbackData


class CarryCb(CallbackData, prefix="cr"):
    action: str          # toggle | next
    task_id: int = 0


class PlanCb(CallbackData, prefix="pl"):
    action: str          # ok | edit | del | back
    task_id: int = 0


class TaskCb(CallbackData, prefix="tk"):
    action: str          # start | due | setdue
    task_id: int
    value: str = ""


class ReportCb(CallbackData, prefix="rp"):
    action: str          # status | reason | skip | send | redo
    value: str = ""


class AssignCb(CallbackData, prefix="as"):
    action: str          # emp | due
    value: str = ""


class AcceptCb(CallbackData, prefix="ac"):
    task_id: int


class AlertCb(CallbackData, prefix="al"):
    action: str          # ack | cancel
    alert_id: int
