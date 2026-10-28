"""Задачи: утренний план, «Мои задачи», итог дня, задачи от руководителя, алерты."""

from __future__ import annotations

from datetime import date, datetime, timezone

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot import keyboards, texts
from bot.callbacks import AcceptCb, AlertCb, AssignCb, CarryCb, PlanCb, ReportCb, TaskCb
from bot.config import Settings
from bot.handlers.menu import menu_for
from bot.models import Employee
from bot.services import attendance as att
from bot.services import tasks as svc
from bot.services.notify import send_to_group
from bot.states import Assign, Checkout, Plan, Report
from bot.task_rules import BlockReason, TaskStatus, due_options, needs_comment, parse_task_lines

router = Router()
router.message.filter(F.chat.type == "private")

# Кнопки меню не должны попадать в текст задачи или комментария
MENU_BUTTONS = texts.MENU_BUTTONS


def today_for(settings: Settings) -> date:
    return datetime.now(timezone.utc).astimezone(settings.tz).date()


async def _safe_edit(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass  # сообщение не изменилось или слишком старое


# ======================= Утренний план =======================


async def start_planning(
    message: Message, state: FSMContext, session: AsyncSession, employee: Employee, today: date
) -> None:
    """Вызывается сразу после отметки прихода."""
    carry = await svc.carry_candidates(session, employee.id, today)
    if carry:
        keep = [t.id for t in carry]
        await state.set_state(Plan.carry)
        await state.update_data(carry_ids=keep, keep_ids=keep, mode="morning", before_ids=[])
        await message.answer(
            f"{texts.CARRY_INTRO}\n\n<i>{texts.CARRY_HINT}</i>", reply_markup=keyboards.carry_choice(carry, set(keep))
        )
        return
    await _begin_writing(message, state, mode="morning", before_ids=[])


async def _begin_writing(message: Message, state: FSMContext, *, mode: str, before_ids: list[int]) -> None:
    await state.set_state(Plan.writing)
    await state.update_data(mode=mode, before_ids=before_ids)
    await message.answer(texts.ASK_NEW_TASKS, reply_markup=keyboards.writing_tasks())


@router.callback_query(StateFilter(Plan.carry), CarryCb.filter(F.action == "toggle"))
async def carry_toggle(
    callback: CallbackQuery,
    callback_data: CarryCb,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if employee is None:
        return await callback.answer()
    data = await state.get_data()
    keep = set(data.get("keep_ids", []))
    keep.symmetric_difference_update({callback_data.task_id})
    await state.update_data(keep_ids=list(keep))
    candidates = await svc.carry_candidates(session, employee.id, today_for(settings))
    tasks = [t for t in candidates if t.id in data["carry_ids"]]
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboards.carry_choice(tasks, keep))
    except TelegramBadRequest:
        pass
    await callback.answer()


@router.callback_query(StateFilter(Plan.carry), CarryCb.filter(F.action == "next"))
async def carry_next(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if employee is None:
        return await callback.answer()
    today = today_for(settings)
    data = await state.get_data()
    tasks = [t for t in await svc.carry_candidates(session, employee.id, today) if t.id in data["carry_ids"]]
    await svc.keep_for_today(session, tasks, set(data.get("keep_ids", [])), today)
    kept = await svc.today_tasks(session, employee.id, today)
    await _safe_edit(callback.message, texts.plan_text(kept, today, title="Перенесено на сегодня"))
    await callback.answer()
    await _begin_writing(callback.message, state, mode="morning", before_ids=[])


@router.message(StateFilter(Plan.writing), F.text == texts.BTN_TASKS_DONE)
@router.message(StateFilter(Plan.review), F.text == texts.BTN_TASKS_DONE)
async def writing_done(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if employee is None:
        return
    today = today_for(settings)
    tasks = await svc.today_tasks(session, employee.id, today)
    tasks = [t for t in tasks if t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)]
    if not tasks:
        await state.clear()
        await message.answer(texts.PLAN_EMPTY, reply_markup=await menu_for(session, settings, employee))
        return
    await state.set_state(Plan.review)
    await message.answer(texts.plan_text(tasks, today), reply_markup=keyboards.plan_review())


@router.message(StateFilter(Plan.writing), F.text, ~F.text.in_(MENU_BUTTONS), ~F.text.startswith("/"))
async def writing_tasks(
    message: Message, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if employee is None:
        return
    lines = parse_task_lines(message.text)
    if not lines:
        await message.answer(texts.NO_TASKS_IN_TEXT)
        return
    added = await svc.add_tasks(session, employee, lines, today_for(settings))
    continued = sum(1 for a in added if a.continued)
    await message.answer(f"{texts.added_tasks(len(added), continued)}\n{texts.ASK_MORE_TASKS}")


@router.callback_query(StateFilter(Plan.review), PlanCb.filter(F.action == "ok"))
async def plan_ok(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if employee is None:
        return await callback.answer()
    today = today_for(settings)
    data = await state.get_data()
    tasks = [
        t for t in await svc.today_tasks(session, employee.id, today)
        if t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
    ]
    await state.clear()
    await _safe_edit(callback.message, texts.plan_text(tasks, today))
    await callback.answer("Сохранено")

    if data.get("mode") == "add":
        before = set(data.get("before_ids", []))
        new_tasks = [t for t in tasks if t.id not in before]
        if new_tasks:
            await send_to_group(bot, session, settings, texts.plan_group(employee.full_name, new_tasks, today)
                                .replace("план на сегодня", "дополнил план"))
    elif tasks:
        await send_to_group(bot, session, settings, texts.plan_group(employee.full_name, tasks, today))
    await callback.message.answer(texts.PLAN_CONFIRMED, reply_markup=await menu_for(session, settings, employee))


@router.callback_query(StateFilter(Plan.review), PlanCb.filter(F.action == "edit"))
async def plan_edit(callback: CallbackQuery, session: AsyncSession, settings: Settings, employee: Employee | None) -> None:
    if employee is None:
        return await callback.answer()
    today = today_for(settings)
    tasks = [
        t for t in await svc.today_tasks(session, employee.id, today)
        if t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
    ]
    await _safe_edit(
        callback.message, f"{texts.plan_text(tasks, today)}\n\n<i>{texts.PLAN_EDIT_HINT}</i>", keyboards.plan_edit(tasks)
    )
    await callback.answer()


@router.callback_query(StateFilter(Plan.review), PlanCb.filter(F.action == "del"))
async def plan_delete(
    callback: CallbackQuery, callback_data: PlanCb, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if employee is None:
        return await callback.answer()
    task = await svc.get_task(session, callback_data.task_id)
    if task is not None and task.employee_id == employee.id:
        await svc.remove_from_today(session, task)
    today = today_for(settings)
    tasks = [
        t for t in await svc.today_tasks(session, employee.id, today)
        if t.status not in (TaskStatus.DONE, TaskStatus.CANCELLED)
    ]
    await _safe_edit(
        callback.message, f"{texts.plan_text(tasks, today)}\n\n<i>{texts.PLAN_EDIT_HINT}</i>", keyboards.plan_edit(tasks)
    )
    await callback.answer("Убрано")


# ======================= Мои задачи / добавить =======================


@router.message(F.text == texts.BTN_ADD_TASK)
async def add_task_button(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if employee is None:
        return
    today = today_for(settings)
    if await att.get_day(session, employee.id, today) is None:
        await message.answer(texts.NEED_CHECK_IN_FOR_TASKS)
        return
    before = [t.id for t in await svc.today_tasks(session, employee.id, today)]
    await _begin_writing(message, state, mode="add", before_ids=before)


async def _show_my_tasks(target: Message, session: AsyncSession, employee: Employee, today: date, *, edit: bool) -> None:
    tasks = await svc.today_tasks(session, employee.id, today)
    text = texts.my_tasks_text(tasks, today)
    markup = keyboards.my_tasks(tasks)
    if edit:
        await _safe_edit(target, text, markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text == texts.BTN_MY_TASKS)
async def my_tasks_button(message: Message, session: AsyncSession, settings: Settings, employee: Employee | None) -> None:
    if employee is None:
        return
    await _show_my_tasks(message, session, employee, today_for(settings), edit=False)


@router.callback_query(TaskCb.filter())
async def task_action(
    callback: CallbackQuery, callback_data: TaskCb, session: AsyncSession, settings: Settings, employee: Employee | None
) -> None:
    if employee is None:
        return await callback.answer()
    task = await svc.get_task(session, callback_data.task_id)
    if task is None or task.employee_id != employee.id:
        return await callback.answer("Задача не найдена")
    today = today_for(settings)

    if callback_data.action == "start":
        await svc.mark_started(session, task)
        await callback.answer("Отмечено: в работе")
    elif callback_data.action == "due":
        await callback.message.edit_reply_markup(reply_markup=keyboards.due_choice(task.id, today))
        return await callback.answer("Выберите срок")
    elif callback_data.action == "setdue":
        due = due_options(today).get(callback_data.value)
        if due is not None:
            await svc.set_due(session, task, due)
        await callback.answer("Срок изменён")
    await _show_my_tasks(callback.message, session, employee, today, edit=True)


# ======================= Итог дня =======================


async def start_report(
    message: Message, state: FSMContext, session: AsyncSession, employee: Employee, today: date
) -> bool:
    """Запускает итог дня по задачам. Возвращает False, если отчитываться не о чем."""
    tasks = await svc.open_today_tasks(session, employee.id, today)
    if not tasks:
        return False
    await state.set_state(Report.status)
    await state.update_data(queue=[t.id for t in tasks], idx=0, answers=[], current={})
    await _ask_current(message, state, session, today)
    return True


async def _ask_current(target: Message, state: FSMContext, session: AsyncSession, today: date) -> None:
    data = await state.get_data()
    queue, idx = data["queue"], data["idx"]
    task = await svc.get_task(session, queue[idx])
    await state.set_state(Report.status)
    await state.update_data(current={"task_id": task.id, "text": task.text})
    await target.answer(texts.report_question(idx + 1, len(queue), task, today), reply_markup=keyboards.report_status())


async def _after_choice(target: Message, state: FSMContext, session: AsyncSession, today: date) -> None:
    """После статуса/причины: спросить комментарий (обязательный или по желанию)."""
    data = await state.get_data()
    current = data["current"]
    reason = BlockReason(current["reason"]) if current.get("reason") else None
    required = needs_comment(TaskStatus(current["status"]), reason)
    await state.update_data(comment_required=required)
    await state.set_state(Report.comment)
    if required:
        await target.answer(texts.ASK_COMMENT_REQUIRED)
    else:
        await target.answer(texts.ASK_COMMENT_OPTIONAL, reply_markup=keyboards.report_skip_comment())


async def _advance(target: Message, state: FSMContext, session: AsyncSession, today: date, comment: str | None) -> None:
    data = await state.get_data()
    current = dict(data["current"])
    current["comment"] = comment
    answers = data["answers"] + [current]
    idx = data["idx"] + 1
    await state.update_data(answers=answers, idx=idx, current={})
    if idx < len(data["queue"]):
        await _ask_current(target, state, session, today)
        return
    await state.set_state(Report.confirm)
    rows = [(a["text"], a["status"], a.get("reason"), a.get("comment")) for a in answers]
    await target.answer(texts.report_summary(rows), reply_markup=keyboards.report_confirm())


def _choice_label(current: dict) -> str:
    label = f"{texts.STATUS_ICON[current['status']]} {texts.STATUS_LABEL[current['status']]}"
    if current.get("reason"):
        label += f": {texts.REASON_LABEL[current['reason']]}"
    return label


@router.callback_query(StateFilter(Report.status), ReportCb.filter(F.action == "status"))
async def report_status(
    callback: CallbackQuery, callback_data: ReportCb, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    status = TaskStatus(callback_data.value)
    data = await state.get_data()
    current = {**data["current"], "status": status.value, "reason": None}
    await state.update_data(current=current)
    await _safe_edit(callback.message, f"{callback.message.html_text.split(chr(10)+chr(10))[0]}\n\n{_choice_label(current)}")
    await callback.answer()
    if status == TaskStatus.BLOCKED:
        await state.set_state(Report.reason)
        await callback.message.answer(texts.ASK_REASON, reply_markup=keyboards.report_reason())
        return
    await _after_choice(callback.message, state, session, today_for(settings))


@router.callback_query(StateFilter(Report.reason), ReportCb.filter(F.action == "reason"))
async def report_reason(
    callback: CallbackQuery, callback_data: ReportCb, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    data = await state.get_data()
    current = {**data["current"], "reason": BlockReason(callback_data.value).value}
    await state.update_data(current=current)
    await _safe_edit(callback.message, f"{texts.ASK_REASON} {texts.REASON_LABEL[current['reason']]}")
    await callback.answer()
    await _after_choice(callback.message, state, session, today_for(settings))


@router.callback_query(StateFilter(Report.comment), ReportCb.filter(F.action == "skip"))
async def report_skip(callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    data = await state.get_data()
    if data.get("comment_required"):
        return await callback.answer("Здесь нужен комментарий", show_alert=True)
    await _safe_edit(callback.message, "💬 Без комментария")
    await callback.answer()
    await _advance(callback.message, state, session, today_for(settings), None)


@router.message(StateFilter(Report.comment), F.text, ~F.text.in_(MENU_BUTTONS), ~F.text.startswith("/"))
async def report_comment(message: Message, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await _advance(message, state, session, today_for(settings), message.text.strip()[:500])


@router.callback_query(StateFilter(Report.confirm), ReportCb.filter(F.action == "redo"))
async def report_redo(callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings) -> None:
    await _safe_edit(callback.message, "✏️ Заполняем заново")
    await callback.answer()
    await state.update_data(idx=0, answers=[], current={})
    await _ask_current(callback.message, state, session, today_for(settings))


@router.callback_query(StateFilter(Report.confirm), ReportCb.filter(F.action == "send"))
async def report_send(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if employee is None:
        return await callback.answer()
    today = today_for(settings)
    data = await state.get_data()
    answers = [
        svc.ReportAnswer(
            task_id=a["task_id"],
            status=TaskStatus(a["status"]),
            reason=BlockReason(a["reason"]) if a.get("reason") else None,
            comment=a.get("comment"),
        )
        for a in data["answers"]
    ]
    raised = await svc.save_day_report(session, employee, answers, today, settings.alert_days)
    await _safe_edit(callback.message, callback.message.html_text.replace("\nВсё верно?", "\n✅ Отправлено"))
    await callback.answer("Сохранено")

    await _send_alerts(bot, session, employee, raised)

    await state.clear()
    await state.set_state(Checkout.waiting_location)
    await callback.message.answer(texts.ASK_CHECKOUT_LOCATION, reply_markup=keyboards.checkout_location())


async def _send_alerts(bot: Bot, session: AsyncSession, employee: Employee, raised: list[svc.RaisedAlert]) -> None:
    if not raised:
        return
    recipients = await svc.managers(session)
    for item in raised:
        history = await svc.task_history(session, item.task.id, limit=item.alert.days)
        text = texts.alert_text(item.kind, employee.full_name, item.task.text, item.alert.days, history)
        for manager in recipients:
            try:
                await bot.send_message(manager.telegram_id, text, reply_markup=keyboards.alert_actions(item.alert.id))
            except Exception:  # noqa: BLE001 — недоступный руководитель не должен ломать итог дня
                pass


@router.callback_query(AlertCb.filter())
async def alert_action(
    callback: CallbackQuery, callback_data: AlertCb, session: AsyncSession, employee: Employee | None
) -> None:
    if employee is None or not employee.is_manager:
        return await callback.answer("Только для руководителя")
    alert = await svc.get_alert(session, callback_data.alert_id)
    if alert is None:
        return await callback.answer("Алерт не найден")
    await svc.ack_alert(session, alert, employee)
    note = texts.ALERT_ACKED
    if callback_data.action == "cancel":
        await svc.cancel_task(session, alert.task)
        note = texts.ALERT_TASK_CANCELLED
    await _safe_edit(callback.message, f"{callback.message.html_text}\n\n{note} — {employee.full_name}")
    await callback.answer(note)


# ======================= Задачи от руководителя =======================


@router.message(F.text == texts.BTN_ASSIGN)
async def assign_start(message: Message, state: FSMContext, session: AsyncSession, employee: Employee | None) -> None:
    if employee is None or not employee.is_manager:
        return
    people = await svc.assignable_employees(session, employee)
    if not people:
        await message.answer(texts.ASSIGN_NO_EMPLOYEES)
        return
    await state.clear()
    await message.answer(texts.ASSIGN_CHOOSE_EMPLOYEE, reply_markup=keyboards.assign_employees(people))


@router.callback_query(AssignCb.filter(F.action == "emp"))
async def assign_employee(
    callback: CallbackQuery, callback_data: AssignCb, state: FSMContext, session: AsyncSession, employee: Employee | None
) -> None:
    if employee is None or not employee.is_manager:
        return await callback.answer()
    target = await session.get(Employee, int(callback_data.value))
    if target is None or not target.is_active:
        return await callback.answer("Сотрудник не найден")
    await state.set_state(Assign.text)
    await state.update_data(assign_to=target.id)
    await _safe_edit(callback.message, f"Сотрудник: <b>{target.full_name}</b>")
    await callback.answer()
    await callback.message.answer(texts.assign_ask_text(target.full_name))


@router.message(StateFilter(Assign.text), F.text, ~F.text.in_(MENU_BUTTONS), ~F.text.startswith("/"))
async def assign_text(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.update_data(assign_text=message.text.strip()[:300])
    await message.answer(texts.ASSIGN_DUE, reply_markup=keyboards.assign_due(today_for(settings)))


@router.callback_query(StateFilter(Assign.text), AssignCb.filter(F.action == "due"))
async def assign_due(
    callback: CallbackQuery,
    callback_data: AssignCb,
    state: FSMContext,
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    employee: Employee | None,
) -> None:
    if employee is None or not employee.is_manager:
        return await callback.answer()
    data = await state.get_data()
    if not data.get("assign_text"):
        return await callback.answer("Сначала напишите текст задачи")
    target = await session.get(Employee, data["assign_to"])
    today = today_for(settings)
    due = due_options(today).get(callback_data.value, today)
    added = await svc.add_tasks(session, target, [data["assign_text"]], today, author=employee, due_date=due)
    task = added[0].task
    await state.clear()
    await _safe_edit(callback.message, f"{texts.ASSIGN_DUE} {keyboards.DUE_LABELS.get(callback_data.value, '')}")
    await callback.answer()

    if target.telegram_id:
        try:
            await bot.send_message(
                target.telegram_id,
                texts.new_task_from_manager(employee.full_name, task.text, task.due_date, today),
                reply_markup=keyboards.accept_task(task.id),
            )
        except Exception:  # noqa: BLE001
            pass
    await callback.message.answer(texts.ASSIGN_DONE, reply_markup=await menu_for(session, settings, employee))


@router.callback_query(AcceptCb.filter())
async def accept(
    callback: CallbackQuery, callback_data: AcceptCb, bot: Bot, session: AsyncSession, employee: Employee | None
) -> None:
    if employee is None:
        return await callback.answer()
    task = await svc.get_task(session, callback_data.task_id)
    if task is None or task.employee_id != employee.id:
        return await callback.answer("Задача не найдена")
    await svc.accept_task(session, task)
    await _safe_edit(callback.message, f"{callback.message.html_text}\n\n✅ Принято")
    await callback.answer("Принято")
    author = task.author
    if author is not None and author.telegram_id:
        try:
            await bot.send_message(author.telegram_id, texts.task_accepted_note(employee.full_name, task.text))
        except Exception:  # noqa: BLE001
            pass


# Нажатие на старую кнопку, когда шаг уже пройден
@router.callback_query()
async def stale_button(callback: CallbackQuery) -> None:
    await callback.answer("Эта кнопка уже неактуальна")
