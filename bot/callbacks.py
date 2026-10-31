"""Данные inline-кнопок (под сообщениями)."""

from aiogram.filters.callback_data import CallbackData


class PlanCb(CallbackData, prefix="pl"):
    action: str          # del | none
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


class ReportsCb(CallbackData, prefix="rep"):
    period: str          # today | yesterday | week | prev_week | month | prev_month


class TsCb(CallbackData, prefix="ts"):
    action: str          # emp | day | other | kind | days | in | out | unmark | sched | sdays | back
    emp: int = 0         # 0 — все сотрудники (праздник)
    day: str = ""        # ГГГГММДД
    value: str = ""


class LangCb(CallbackData, prefix="lg"):
    code: str            # ky | ru
    first: str = "0"     # "1" — выбор сразу после подключения
