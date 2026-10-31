"""Языки (кыргызский/русский), приход вне офиса, срок задач руководителя, опоздания в отчётах."""

import io
import zipfile
import pytest

pytest.importorskip("aiogram")

from aiogram.methods import AnswerCallbackQuery  # noqa: E402
from sqlalchemy import select  # noqa: E402

from bot import texts  # noqa: E402
from bot.i18n import use_lang  # noqa: E402
from bot.models import Attendance, Task  # noqa: E402
from bot.worktime import format_distance, format_duration  # noqa: E402
from tests.test_bot_flow import GROUP_ID, MANAGER, OFFICE, OWNER, WORKER, onboard, run  # noqa: E402

FAR = (OFFICE[0] + 0.03, OFFICE[1])  # ≈3,3 км от офиса


def test_duration_and_distance_formats():
    assert format_duration(844) == "14 ч 4 мин"
    assert format_duration(73) == "1 ч 13 мин"
    assert format_duration(60) == "1 ч" and format_duration(7) == "7 мин"
    with use_lang("ky"):
        assert format_duration(844) == "14 саат 4 мүн"
    assert format_distance(3250) == "3 км 250 м"
    assert format_distance(850) == "850 м" and format_distance(2000) == "2 км"


def test_texts_follow_current_language():
    assert texts.BTN_CHECK_IN == "🏢 Я в офисе"
    with use_lang("ky"):
        assert texts.BTN_CHECK_IN == "🏢 Кеңседемин"
    assert texts.variants("BTN_CHECK_IN") == {"🏢 Я в офисе", "🏢 Кеңседемин"}
    assert "🏢 Кеңседемин" in texts.MENU_BUTTONS and "🏢 Я в офисе" in texts.MENU_BUTTONS


def test_language_chosen_after_phone_and_kyrgyz_day_with_kyrgyz_group():
    async def scenario(h):
        h.settings.group_lang = "ky"
        await onboard(h, worker_lang="ky")
        # Выбор языка — сразу после номера, приветствие уже по-кыргызски
        assert any("Тилди тандаңыз" in t for t in h.tg.texts(WORKER))
        assert any("Даяр, Айбек Асанов" in t for t in h.tg.texts(WORKER))
        menu = h.tg.last_markup(WORKER)
        labels = [b.text for row in menu.keyboard for b in row]
        assert "🏢 Кеңседемин" in labels and "🌐 Тил / Язык" in labels

        await h.location(WORKER, *OFFICE)
        assert "Бүгүнкү тапшырмаларды жазыңыз" in h.tg.texts(WORKER)[-1]
        await h.text(WORKER, "Отчет тапшыруу")
        await h.press(WORKER, h.find_button(WORKER, "📤 Планды жөнөтүү"))
        group = list(h.tg.view(GROUP_ID).values())
        assert any("кеңсеге келди" in m and "Күндүн планы" in m and "Отчет тапшыруу" in m for m in group)

        # Кыргызская кнопка меню работает
        await h.text(WORKER, "📋 Менин тапшырмаларым")
        assert "Бүгүнкү тапшырмалар" in h.tg.texts(WORKER)[-1]

        # Сменить язык в любой момент
        await h.text(WORKER, "🌐 Тил / Язык")
        await h.press(WORKER, h.find_button(WORKER, "🇷🇺"))
        assert "Язык бота: русский" in h.tg.texts(WORKER)[-1]
        await h.text(WORKER, "📋 Мои задачи")
        assert "Задачи на сегодня" in h.tg.texts(WORKER)[-1]

        # Руководитель (русский) получает отчёт на русском
        await h.text(MANAGER, "📊 Отчёты")
        await h.press(MANAGER, h.find_button(MANAGER, "Сегодня"))
        assert any("Отчёт за" in t for t in h.tg.texts(MANAGER))

    run(scenario)


def test_existing_employee_without_language_is_asked_once():
    async def scenario(h):
        await onboard(h)
        async with h.sessionmaker() as s:
            from bot.models import Employee

            worker = await s.scalar(select(Employee).where(Employee.telegram_id == WORKER))
            worker.lang = None
            await s.commit()
        await h.text(WORKER, "/start")
        assert "Тилди тандаңыз" in h.tg.texts(WORKER)[-1]

    run(scenario)


def test_outside_checkin_with_comment():
    async def scenario(h):
        await onboard(h)
        await h.location(WORKER, *FAR)
        ask = h.tg.texts(WORKER)[-1]
        assert "Вы не в офисе" in ask and "3 км" in ask
        assert not h.tg.sent(GROUP_ID)

        # Слишком короткий комментарий — просим подробнее
        await h.text(WORKER, "ок")
        assert "подробнее" in h.tg.texts(WORKER)[-1]
        await h.text(WORKER, "На объекте в Ноокате, принимаю материалы")
        assert "Приход отмечен (вне офиса)" in "\n".join(h.tg.texts(WORKER)[-3:])

        async with h.sessionmaker() as s:
            att = await s.scalar(select(Attendance))
            assert att.is_outside and att.check_in_comment.startswith("На объекте")
            assert 3000 < att.check_in_distance_m < 3600

        # Руководитель сразу получил уведомление: где, как далеко, почему
        note = h.tg.texts(MANAGER)[-1]
        assert "вне офиса" in note and "3 км" in note and "2gis" in note.lower() and "Ноокате" in note

        # План → в общий чат одно сообщение с отметкой вне офиса
        await h.text(WORKER, "Принять материалы")
        await h.press(WORKER, h.find_button(WORKER, "📤 Отправить план"))
        group = list(h.tg.view(GROUP_ID).values())
        assert any("🟠" in m and "вне офиса" in m and "Ноокате" in m and "Принять материалы" in m for m in group)

        # В отчёте за день — тоже
        await h.text(MANAGER, "📊 Отчёты")
        await h.press(MANAGER, h.find_button(MANAGER, "Сегодня"))
        report = h.tg.texts(MANAGER)[-1]
        assert "вне офиса: 1" in report and "Ноокате" in report

    run(scenario)


def test_outside_checkin_cancel_and_accuracy_rules():
    async def scenario(h):
        await onboard(h)
        await h.location(WORKER, *FAR)
        await h.text(WORKER, "↩️ Отмена")
        assert "приход не отмечен" in h.tg.texts(WORKER)[-1]
        async with h.sessionmaker() as s:
            assert await s.scalar(select(Attendance)) is None

        # Погрешность 300 м, но до офиса 3 км — точно не в офисе: можно отметиться вне офиса
        await h.location(WORKER, *FAR, acc=300)
        assert "Вы не в офисе" in h.tg.texts(WORKER)[-1]
        # Примерное место (погрешность 3 км) — ничего не доказывает, просим включить точную геопозицию
        await h.location(WORKER, *FAR, acc=3000)
        assert "Точная геопозиция" in h.tg.texts(WORKER)[-1]
        # Рядом с офисом, но неточно — просим повторить, а не «вне офиса»
        await h.location(WORKER, OFFICE[0] + 0.0005, OFFICE[1], acc=250)
        assert "неточно" in h.tg.texts(WORKER)[-1]

    run(scenario)


def test_outside_checkin_can_be_disabled():
    async def scenario(h):
        h.settings.allow_outside_checkin = False
        await onboard(h)
        await h.location(WORKER, *FAR)
        assert "только в офисе" in h.tg.texts(WORKER)[-1]

    run(scenario)


def test_employee_cannot_change_due_of_manager_task():
    async def scenario(h):
        from bot.callbacks import TaskCb

        await onboard(h)
        await h.location(WORKER, *OFFICE)
        await h.text(WORKER, "Своя задача")
        await h.text(MANAGER, "📌 Поставить задачу")
        await h.press(MANAGER, h.find_button(MANAGER, "Айбек"))
        await h.text(MANAGER, "Сдать отчёт директору")
        await h.press(MANAGER, h.find_button(MANAGER, "Сегодня"))

        await h.text(WORKER, "📋 Мои задачи")
        buttons = [b.text for row in h.tg.last_inline(WORKER).inline_keyboard for b in row]
        assert any("Своя задача" in b for b in buttons)
        assert not any("Сдать отчёт директору" in b for b in buttons)
        assert "срок меняет только руководитель" in h.tg.texts(WORKER)[-1]

        # Даже старой кнопкой срок задачи руководителя не поменять
        async with h.sessionmaker() as s:
            task = await s.scalar(select(Task).where(Task.from_manager.is_(True)))
            due_before = task.due_date
        await h.press(WORKER, TaskCb(action="setdue", task_id=task.id, value="tomorrow").pack())
        alerts = [c for c in h.tg.calls if isinstance(c, AnswerCallbackQuery) and c.show_alert]
        assert alerts and "только он" in alerts[-1].text
        async with h.sessionmaker() as s:
            assert (await s.get(Task, task.id)).due_date == due_before

    run(scenario)


def test_late_ranking_in_period_report_and_excel():
    from datetime import datetime, timedelta, timezone

    from bot.excel import build_timesheet
    from bot.models import Employee
    from bot.report_texts import period_report
    from bot.services.reports import load_period

    async def scenario(h):
        await onboard(h)
        tz = h.settings.tz
        today = datetime.now(timezone.utc).astimezone(tz).date()
        mon = today - timedelta(days=today.weekday())
        async with h.sessionmaker() as s:
            worker = await s.scalar(select(Employee).where(Employee.telegram_id == WORKER))
            boss = await s.scalar(select(Employee).where(Employee.telegram_id == MANAGER))
            for person, lates in ((worker, [844, 15]), (boss, [7])):
                for i, late in enumerate(lates):
                    day = mon - timedelta(days=7) + timedelta(days=i)
                    s.add(Attendance(employee_id=person.id, work_date=day, check_in_at=datetime.now(timezone.utc),
                                     check_in_lat=1, check_in_lon=1, check_in_distance_m=0, late_minutes=late))
            await s.commit()
            start, end = mon - timedelta(days=7), mon - timedelta(days=1)
            rows = await load_period(s, h.settings, start, end)
        text = period_report(rows, start, end, "Отчёт за неделю")
        assert "Опоздания за период" in text
        block = text.split("Опоздания за период")[1]
        assert block.index("Айбек") < block.index("Нурлан")  # больше всех опоздал — первый
        assert "Айбек Асанов — 2 раза, всего 14 ч 19 мин" in block
        assert "844" not in text

        data = build_timesheet(rows, start, end, tz, "Отчёт за неделю")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            book = z.read("xl/workbook.xml").decode()
            strings = z.read("xl/sharedStrings.xml").decode()
        assert "Опоздания" in book
        assert "14 ч 19 мин" in strings and "14 ч 4 мин" in strings

        with use_lang("ky"):
            ky_text = period_report(rows, start, end, "Жумалык отчет")
        assert "2 жолу" in ky_text and "14 саат 19 мүн" in ky_text

    run(scenario)


def test_default_work_hours_are_0830_1730():
    from datetime import time

    from bot.config import Settings

    s = Settings(_env_file=None, bot_token="1:x", owner_phone="1", office_lat=1, office_lon=1)
    assert s.work_start == time(8, 30) and s.work_end == time(17, 30) and s.group_lang == "ky"


def test_kyrgyz_and_russian_texts_have_same_names():
    from bot import texts_ky, texts_ru

    def names(m):
        return {n for n in dir(m) if n.isupper() or (callable(getattr(m, n)) and not n.startswith("_"))}

    assert names(texts_ru) - names(texts_ky) <= {"annotations"}
