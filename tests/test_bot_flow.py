"""Сквозная проверка: настоящие обработчики бота, поддельный Telegram.

Бот получает обновления (нажатия, сообщения, геолокацию), а все его ответы
записываются, чтобы проверить, что увидит пользователь и общий чат.
"""

import asyncio
from datetime import datetime, timezone
from itertools import count

import pytest

pytest.importorskip("aiogram")
pytest.importorskip("sqlalchemy")

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import (  # noqa: E402
    AnswerCallbackQuery,
    EditMessageReplyMarkup,
    EditMessageText,
    SendDocument,
    SendMessage,
    TelegramMethod,
)
from aiogram.types import CallbackQuery, Chat, Contact, Location, Message, Update, User  # noqa: E402

from bot.config import Settings  # noqa: E402
from bot.db import init_db, make_engine, make_sessionmaker  # noqa: E402
from bot.handlers import build_router  # noqa: E402
from bot.middlewares import DbSessionMiddleware  # noqa: E402

OFFICE = (42.857044, 74.641376)
GROUP_ID = -1001
OWNER, MANAGER, WORKER = 100, 200, 300


class FakeTelegram(BaseSession):
    """Записывает всё, что бот отправляет, и возвращает правдоподобные ответы."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod] = []
        self._ids = count(1000)

    async def make_request(self, bot, method, timeout=None):  # noqa: ANN001
        self.calls.append(method)
        if isinstance(method, (SendMessage, SendDocument, EditMessageText, EditMessageReplyMarkup)):
            chat_id = getattr(method, "chat_id", None) or 0
            msg_id = getattr(method, "message_id", None) if not isinstance(method, (SendMessage, SendDocument)) else None
            msg_id = msg_id or next(self._ids)
            if isinstance(method, SendMessage):
                object.__setattr__(method, "_sent_id", msg_id)
            return Message(
                message_id=msg_id,
                date=datetime.now(timezone.utc),
                chat=Chat(id=chat_id, type="private"),
                text=getattr(method, "text", None) or "x",
            )
        return True

    async def stream_content(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError

    async def close(self) -> None:
        pass

    def view(self, chat_id: int) -> dict[int, str]:
        """Как сейчас выглядит чат: id сообщения → текст после всех правок."""
        result: dict[int, str] = {}
        for c in self.calls:
            if isinstance(c, SendMessage) and c.chat_id == chat_id:
                result[c._sent_id] = c.text
            elif isinstance(c, EditMessageText) and c.chat_id == chat_id and c.message_id in result:
                result[c.message_id] = c.text
        return result

    def documents(self, chat_id: int) -> list[SendDocument]:
        return [c for c in self.calls if isinstance(c, SendDocument) and c.chat_id == chat_id]

    def sent(self, chat_id: int | None = None) -> list[SendMessage]:
        return [c for c in self.calls if isinstance(c, SendMessage) and (chat_id is None or c.chat_id == chat_id)]

    def texts(self, chat_id: int) -> list[str]:
        return [m.text for m in self.sent(chat_id)]

    def last_markup(self, chat_id: int):
        for c in reversed(self.calls):
            if isinstance(c, SendMessage) and c.chat_id == chat_id and c.reply_markup is not None:
                return c.reply_markup
        return None

    def last_inline(self, chat_id: int):
        for c in reversed(self.calls):
            markup = getattr(c, "reply_markup", None)
            if markup is not None and hasattr(markup, "inline_keyboard"):
                if getattr(c, "chat_id", chat_id) == chat_id:
                    return markup
        return None


class Harness:
    def __init__(self) -> None:
        self.ids = count(1)
        self.tg = FakeTelegram()

    async def setup(self) -> None:
        self.settings = Settings(
            _env_file=None,
            bot_token="42:TEST",
            owner_phone="+996700000100",
            office_lat=OFFICE[0],
            office_lon=OFFICE[1],
            group_chat_id=GROUP_ID,
            database_url="sqlite+aiosqlite:///:memory:",
            work_days="1,2,3,4,5,6,7",
            work_start="09:00",
            work_end="18:00",
            group_lang="ru",
        )
        self.engine = make_engine(self.settings.database_url)
        await init_db(self.engine)
        self.bot = Bot("42:TEST", session=self.tg, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher(storage=MemoryStorage())
        self.dp["settings"] = self.settings
        self.sessionmaker = make_sessionmaker(self.engine)
        self.dp.update.outer_middleware(DbSessionMiddleware(self.sessionmaker))
        # Роутеры модулей — общие объекты; в каждом тесте подключаем их заново
        from bot.handlers import admin, attendance, reports, start, tasks

        for module in (admin, attendance, reports, start, tasks):
            module.router._parent_router = None
        self.dp.include_router(build_router())

    def _user(self, uid: int) -> User:
        return User(id=uid, is_bot=False, first_name=f"U{uid}")

    def _msg(self, uid: int, **kw) -> Message:
        return Message(
            message_id=next(self.ids),
            date=datetime.now(timezone.utc),
            chat=Chat(id=uid, type="private"),
            from_user=self._user(uid),
            **kw,
        )

    async def feed(self, update: Update) -> None:
        await self.dp.feed_update(self.bot, update)

    async def text(self, uid: int, text: str, chat_id: int | None = None) -> None:
        msg = self._msg(uid, text=text)
        if chat_id is not None:
            msg = msg.model_copy(update={"chat": Chat(id=chat_id, type="supergroup")})
        await self.feed(Update(update_id=next(self.ids), message=msg))

    async def contact(self, uid: int, phone: str) -> None:
        c = Contact(phone_number=phone, first_name="X", user_id=uid)
        await self.feed(Update(update_id=next(self.ids), message=self._msg(uid, contact=c)))

    async def location(self, uid: int, lat: float, lon: float, acc: float = 15) -> None:
        loc = Location(latitude=lat, longitude=lon, horizontal_accuracy=acc)
        await self.feed(Update(update_id=next(self.ids), message=self._msg(uid, location=loc)))

    async def press(self, uid: int, data: str) -> None:
        cq = CallbackQuery(
            id=str(next(self.ids)),
            from_user=self._user(uid),
            chat_instance="ci",
            data=data,
            # Как в настоящем Telegram: нажатая кнопка приходит вместе с сообщением и его кнопками
            message=self._msg(
                uid, text="Задача 1 из 1:\n<b>x</b>\n\nКак прошло?", reply_markup=self.tg.last_inline(uid)
            ),
        )
        await self.feed(Update(update_id=next(self.ids), callback_query=cq))

    def find_button(self, uid: int, startswith: str) -> str:
        markup = self.tg.last_inline(uid)
        for row in markup.inline_keyboard:
            for b in row:
                if b.text.startswith(startswith):
                    return b.callback_data
        raise AssertionError(f"Нет кнопки «{startswith}»: {[[b.text for b in r] for r in markup.inline_keyboard]}")


def run(fn):
    async def wrapper():
        h = Harness()
        await h.setup()
        try:
            await fn(h)
        finally:
            await h.engine.dispose()

    asyncio.run(wrapper())


async def onboard(h: Harness, lang: str = "ru", worker_lang: str | None = None) -> None:
    """Подключение: номер → выбор языка (по умолчанию все выбирают русский)."""
    flags = {"ru": "🇷🇺", "ky": "🇰🇬"}
    await h.text(OWNER, "/start")
    await h.contact(OWNER, "+996700000100")
    await h.press(OWNER, h.find_button(OWNER, flags[lang]))
    await h.text(OWNER, "/add_manager +996700000200 Нурлан Касымов")
    await h.text(OWNER, "/add +996700000300 Айбек Асанов")
    for uid in (MANAGER, WORKER):
        await h.text(uid, "/start")
        await h.contact(uid, f"+996700000{uid}")
        chosen = worker_lang if uid == WORKER and worker_lang else lang
        await h.press(uid, h.find_button(uid, flags[chosen]))


def test_full_day_with_tasks():
    async def scenario(h: Harness):
        await onboard(h)
        assert any("владелец" in t for t in h.tg.texts(OWNER))
        assert any("Готово, Айбек Асанов" in t for t in h.tg.texts(WORKER))

        # Вне офиса — бот спрашивает, где он и почему; пока не ответил — приход не отмечен
        await h.location(WORKER, OFFICE[0] + 0.01, OFFICE[1])
        assert "от офиса" in h.tg.texts(WORKER)[-1]
        assert not h.tg.sent(GROUP_ID)

        # В офисе — приход отмечен, но в чат пока ничего: бот сначала просит задачи
        await h.location(WORKER, OFFICE[0] + 0.0002, OFFICE[1])
        assert not h.tg.sent(GROUP_ID)
        assert "каждую с новой строки" in h.tg.texts(WORKER)[-1]

        # Пишет задачи одним сообщением → бот показывает план с 🗑 и «Отправить план»
        await h.text(WORKER, "1. Сдать отчёт\n2. Позвонить поставщику\n3. Проверить склад\n4. Лишняя задача")
        assert "Ваш план на сегодня" in h.tg.texts(WORKER)[-1]
        assert not h.tg.sent(GROUP_ID)
        await h.press(WORKER, h.find_button(WORKER, "🗑 4."))
        await h.press(WORKER, h.find_button(WORKER, "📤 Отправить план"))
        # В общем чате — одно сообщение: приход и план, без сроков
        chat = h.tg.view(GROUP_ID)
        assert len(chat) == 1
        day_msg_id, day_msg = next(iter(chat.items()))
        assert "пришёл в офис" in day_msg and "План на день" in day_msg and "Позвонить поставщику" in day_msg
        assert "Лишняя задача" not in day_msg and "срок" not in day_msg

        # Руководитель ставит задачу, сотрудник принимает
        await h.text(MANAGER, "📌 Поставить задачу")
        await h.press(MANAGER, h.find_button(MANAGER, "Айбек"))
        await h.text(MANAGER, "Заказать цемент")
        await h.press(MANAGER, h.find_button(MANAGER, "Сегодня"))
        assert "Новая задача от Нурлан" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "👍 Принял"))
        assert "принял задачу" in h.tg.texts(MANAGER)[-1]

        # Вечер: итог по 4 задачам кнопками
        await h.text(WORKER, "🏁 Завершить день")
        assert "Задача 1 из 4" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "✅ Выполнено"))
        await h.press(WORKER, h.find_button(WORKER, "Пропустить"))
        await h.press(WORKER, h.find_button(WORKER, "⏳ Не успел"))
        await h.text(WORKER, "не хватило времени")
        await h.press(WORKER, h.find_button(WORKER, "🚧"))
        await h.press(WORKER, h.find_button(WORKER, "Нет материалов"))
        await h.press(WORKER, h.find_button(WORKER, "Пропустить"))
        await h.press(WORKER, h.find_button(WORKER, "❌ Отменена"))
        # Для «Отменена» комментарий обязателен: «Пропустить» не показывается
        assert "обязателен" in h.tg.texts(WORKER)[-1]
        await h.text(WORKER, "заказал руководитель")
        assert "выполнено 1 из 4" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "✅ Отправить"))
        assert "Отправить местоположение" in h.tg.texts(WORKER)[-1]

        # Уход в полях — ссылка 2ГИС и итог задач в общем чате
        await h.location(WORKER, OFFICE[0] + 0.05, OFFICE[1])
        out = h.tg.texts(GROUP_ID)[-1]
        # Уход — ответом на сообщение о приходе (одна ветка дня)
        assert h.tg.sent(GROUP_ID)[-1].reply_parameters.message_id == day_msg_id
        assert "Заказать цемент" in h.tg.view(GROUP_ID)[day_msg_id]  # задача руководителя попала в план
        assert "завершил работу в полях" in out
        assert "2gis.kg/geo/" in out
        assert "выполнено 1 из 4" in out
        assert "не хватило времени" in out and "нет материалов" in out

    run(scenario)


def test_add_task_midday_and_my_tasks():
    async def scenario(h: Harness):
        await onboard(h)
        await h.location(WORKER, *OFFICE)
        await h.text(WORKER, "Первая задача")
        await h.press(WORKER, h.find_button(WORKER, "📤 Отправить план"))

        await h.text(WORKER, "➕ Добавить задачу")
        await h.text(WORKER, "Вторая задача")
        # Не новое сообщение в чате, а обновлённое сообщение дня
        chat = h.tg.view(GROUP_ID)
        assert len(chat) == 1
        assert "Первая задача" in list(chat.values())[0] and "Вторая задача" in list(chat.values())[0]

        # Можно просто написать ещё одну задачу — без кнопок
        await h.text(WORKER, "Третья задача")
        assert "Третья задача" in list(h.tg.view(GROUP_ID).values())[0]

        # Убрать задачу кнопкой 🗑 — план в чате обновится
        await h.press(WORKER, h.find_button(WORKER, "🗑 3."))
        assert "Третья задача" not in list(h.tg.view(GROUP_ID).values())[0]

        # «Мои задачи»: только срок — сегодня или завтра, без «Начал»
        await h.text(WORKER, "📋 Мои задачи")
        assert "Вторая задача" in h.tg.texts(WORKER)[-1]
        buttons = [b.text for row in h.tg.last_inline(WORKER).inline_keyboard for b in row]
        assert not any("Начал" in b for b in buttons)
        await h.press(WORKER, h.find_button(WORKER, "📅 1."))
        due_buttons = [b.text for row in h.tg.last_inline(WORKER).inline_keyboard for b in row]
        assert due_buttons == ["Сегодня", "Завтра"]
        await h.press(WORKER, h.find_button(WORKER, "Завтра"))
        edits = [c for c in h.tg.calls if isinstance(c, EditMessageText)]
        assert "Первая задача (срок до" in edits[-1].text
        # В общем чате срок не показывается
        assert "срок" not in list(h.tg.view(GROUP_ID).values())[0]

    run(scenario)


def test_bind_chat_and_unknown_user():
    async def scenario(h: Harness):
        await h.text(999, "/start")
        await h.contact(999, "+996555999999")
        assert "нет в списке" in h.tg.texts(999)[-1]
        await h.text(OWNER, "/start")
        await h.contact(OWNER, "+996700000100")
        await h.text(OWNER, "/bind_chat", chat_id=-555)
        assert any("подключён" in t for t in h.tg.texts(-555))

    run(scenario)


def test_stale_button_is_answered():
    async def scenario(h: Harness):
        await onboard(h)
        await h.press(WORKER, "rp:send:")
        answers = [c for c in h.tg.calls if isinstance(c, AnswerCallbackQuery)]
        assert answers and "неактуальна" in (answers[-1].text or "")

    run(scenario)


async def _shift_to_yesterday(h: Harness) -> None:
    """Делает вид, что всё было вчера: переносит даты задач, итогов и отметок на день назад."""
    from sqlalchemy import text

    async with h.engine.begin() as conn:
        for table, col in (("tasks", "plan_date"), ("task_reports", "work_date"), ("attendance", "work_date")):
            await conn.execute(text(f"UPDATE {table} SET {col} = date({col}, '-1 day')"))


def test_next_day_carry_over_and_alert_to_manager():
    async def scenario(h: Harness):
        await onboard(h)
        # День 1: одна задача, «Не успел»
        await h.location(WORKER, *OFFICE)
        await h.text(WORKER, "Сдать отчёт по объекту\nУбрать склад")
        await h.text(WORKER, "🏁 Завершить день")
        await h.press(WORKER, h.find_button(WORKER, "⏳ Не успел"))
        await h.press(WORKER, h.find_button(WORKER, "Пропустить"))
        await h.press(WORKER, h.find_button(WORKER, "⏳ Не успел"))
        await h.press(WORKER, h.find_button(WORKER, "Пропустить"))
        await h.press(WORKER, h.find_button(WORKER, "✅ Отправить"))
        await h.location(WORKER, *OFFICE)
        assert "ушёл из офиса" in h.tg.texts(GROUP_ID)[-1]
        assert not any("не выполняется" in t for t in h.tg.texts(MANAGER))

        await _shift_to_yesterday(h)

        # День 2: бот предлагает вчерашние задачи; «Убрать склад» убираем
        await h.location(WORKER, *OFFICE)
        assert "Перенесены вчерашние" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "🗑 2. Убрать склад"))
        await h.press(WORKER, h.find_button(WORKER, "📤 Отправить план"))
        plan = list(h.tg.view(GROUP_ID).values())[-1]
        assert "Сдать отчёт по объекту" in plan and "Убрать склад" not in plan

        # Второй день подряд «Не успел» → алерт руководителю, владельцу — нет
        await h.text(WORKER, "🏁 Завершить день")
        assert "Задача 1 из 1" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "⏳ Не успел"))
        await h.text(WORKER, "ждал данные от бухгалтерии")
        await h.press(WORKER, h.find_button(WORKER, "✅ Отправить"))
        alert = h.tg.texts(MANAGER)[-1]
        assert "Задача не выполняется" in alert and "2 дн. подряд" in alert
        assert "ждал данные от бухгалтерии" in alert
        assert not any("не выполняется" in t for t in h.tg.texts(OWNER))

        # Руководитель нажимает «Принял»
        await h.press(MANAGER, h.find_button(MANAGER, "👌 Принял"))
        edits = [c for c in h.tg.calls if isinstance(c, EditMessageText)]
        assert "Принято" in edits[-1].text

    run(scenario)


def test_owner_can_reset_today_for_testing():
    async def scenario(h: Harness):
        await onboard(h)
        await h.location(OWNER, *OFFICE)
        await h.text(OWNER, "Тестовая задача")
        await h.text(OWNER, "🏁 Завершить день")
        await h.press(OWNER, h.find_button(OWNER, "✅ Выполнено"))
        await h.press(OWNER, h.find_button(OWNER, "Пропустить"))
        await h.press(OWNER, h.find_button(OWNER, "✅ Отправить"))
        await h.location(OWNER, *OFFICE)

        # Сотрудник не может сбросить
        await h.text(WORKER, "/reset_today")
        assert "только владельцу" in h.tg.texts(WORKER)[-1]

        await h.text(OWNER, "/reset_today")
        assert "сброшены" in h.tg.texts(OWNER)[-1]
        buttons = [b.text for row in h.tg.last_markup(OWNER).keyboard for b in row]
        assert "🏢 Я в офисе" in buttons

        # День проходится заново: приход и снова итог по той же задаче
        await h.location(OWNER, *OFFICE)
        await h.press(OWNER, h.find_button(OWNER, "📤 Отправить план"))
        assert "пришёл в офис" in h.tg.texts(GROUP_ID)[-1]
        await h.text(OWNER, "🏁 Завершить день")
        assert "Задача 1 из 1" in h.tg.texts(OWNER)[-1]

    run(scenario)


def test_second_owner_by_command_and_removal_rules():
    async def scenario(h: Harness):
        await onboard(h)
        PROG = 400
        # Руководитель не может добавить владельца
        await h.text(MANAGER, "/add_owner +996700000400 Программист")
        assert "только владельцу" in h.tg.texts(MANAGER)[-1]

        await h.text(OWNER, "/add_owner +996700000400 Программист")
        assert "владелец" in h.tg.texts(OWNER)[-1]
        await h.text(PROG, "/start")
        await h.contact(PROG, "+996700000400")
        await h.text(PROG, "/admin")
        assert "Команды владельца" in h.tg.texts(PROG)[-1]

        # Себя отключить нельзя, другого владельца — можно, последнего — нельзя
        await h.text(PROG, "/remove +996700000400")
        assert "Себя отключить нельзя" in h.tg.texts(PROG)[-1]
        await h.text(OWNER, "/remove +996700000400")
        assert "Отключён" in h.tg.texts(OWNER)[-1]
        await h.text(OWNER, "/remove +996700000100")
        assert "Себя отключить нельзя" in h.tg.texts(OWNER)[-1]

    run(scenario)


def test_several_owner_phones_in_settings():
    from bot.config import Settings as S

    s = S(_env_file=None, bot_token="t", owner_phone="+996 555 111 111, 0555222222", office_lat=1, office_lon=1)
    assert s.owner_phones == {"996555111111", "996555222222"}


def test_approximate_location_on_iphone_gets_clear_instructions():
    async def scenario(h: Harness):
        await onboard(h)
        # «Точная геопозиция» выключена: iOS присылает погрешность в километры
        await h.location(WORKER, *OFFICE, acc=3200)
        text = h.tg.texts(WORKER)[-1]
        assert "примерное место" in text and "3 км" in text and "Точная геопозиция" in text
        assert not h.tg.sent(GROUP_ID)

        # Просто неточный GPS в здании — короткая подсказка про окно
        await h.location(WORKER, *OFFICE, acc=250)
        assert "Подойдите к окну" in h.tg.texts(WORKER)[-1]

        # Точная — приход засчитан
        await h.location(WORKER, *OFFICE, acc=12)
        assert "Приход отмечен" in h.tg.texts(WORKER)[-2]
        await h.text(WORKER, "Задача")
        await h.press(WORKER, h.find_button(WORKER, "📤 Отправить план"))
        assert "пришёл в офис" in h.tg.texts(GROUP_ID)[-1]

        # Уход с примерной геопозицией не превращается в «поле»: бот просит повторить
        await h.text(WORKER, "🏁 Завершить день")
        await h.press(WORKER, h.find_button(WORKER, "✅ Выполнено"))
        await h.press(WORKER, h.find_button(WORKER, "Пропустить"))
        await h.press(WORKER, h.find_button(WORKER, "✅ Отправить"))
        before = len(h.tg.texts(GROUP_ID))
        await h.location(WORKER, *OFFICE, acc=5000)
        assert "Точная геопозиция" in h.tg.texts(WORKER)[-1]
        assert len(h.tg.texts(GROUP_ID)) == before
        await h.location(WORKER, *OFFICE, acc=15)
        assert "ушёл из офиса" in h.tg.texts(GROUP_ID)[-1]

    run(scenario)


def test_tasks_sent_one_by_one_and_after_restart():
    async def scenario(h: Harness):
        await onboard(h)
        await h.location(WORKER, *OFFICE)
        # Человек пишет задачи по одной — все собираются в один план
        await h.text(WORKER, "Позвонить клиенту")
        await h.text(WORKER, "Купить краску")
        assert "Позвонить клиенту" in h.tg.texts(WORKER)[-1] and "Купить краску" in h.tg.texts(WORKER)[-1]

        # Старая кнопка «Готово» на телефоне не ломает ничего — показывает план с «Отправить»
        await h.text(WORKER, "✅ Готово")
        assert "Ваш план на сегодня" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "📤 Отправить план"))
        msg = list(h.tg.view(GROUP_ID).values())
        assert len(msg) == 1 and "Позвонить клиенту" in msg[0] and "Купить краску" in msg[0]

        # Бот перезапустили (шаг диалога забыт) — обычный текст всё равно становится задачей
        await h.dp.storage.close()
        h.dp.fsm.storage = type(h.dp.storage)()
        await h.text(WORKER, "Отправить фото объекта")
        assert "Отправить фото объекта" in list(h.tg.view(GROUP_ID).values())[0]

        # Кто ещё не пришёл — получает подсказку, а не задачу
        await h.text(MANAGER, "Какая-то задача")
        assert "Сначала отметьте приход" in h.tg.texts(MANAGER)[-1]

    run(scenario)



def test_manager_multiline_task_becomes_several_tasks():
    async def scenario(h: Harness):
        await onboard(h)
        await h.location(WORKER, *OFFICE)
        await h.text(MANAGER, "📌 Поставить задачу")
        await h.press(MANAGER, h.find_button(MANAGER, "Айбек"))
        await h.text(MANAGER, "авпвап\nпапав")
        await h.press(MANAGER, h.find_button(MANAGER, "Сегодня"))
        got = [t for t in h.tg.texts(WORKER) if "Новая задача" in t]
        assert len(got) == 2 and "авпвап" in got[0] and "папав" in got[1]

    run(scenario)


def test_plan_autosent_if_employee_forgets_button():
    async def scenario(h: Harness):
        from datetime import timedelta as td

        from bot.db import make_sessionmaker as msm
        from bot.scheduler import tick

        await onboard(h)
        await h.location(WORKER, *OFFICE)
        await h.text(WORKER, "Забыл нажать отправить")
        assert not h.tg.sent(GROUP_ID)
        later = datetime.now(timezone.utc) + td(minutes=h.settings.plan_autosend_min + 1)
        await tick(h.bot, msm(h.engine), h.settings, now=later)
        chat = list(h.tg.view(GROUP_ID).values())
        assert any("пришёл в офис" in m and "Забыл нажать отправить" in m for m in chat)

    run(scenario)


def test_re_adding_former_owner_as_employee_keeps_employee_role():
    async def scenario(h: Harness):
        await onboard(h)
        await h.text(OWNER, "/add_owner +996501720170 Мырзахмед")
        await h.text(OWNER, "/remove +996501720170")
        await h.text(OWNER, "/add +996501720170 Мырзахмед")
        assert "— сотрудник" in h.tg.texts(OWNER)[-1]
        # Повышение и понижение работают явно
        await h.text(OWNER, "/add_manager +996501720170 Мырзахмед")
        assert "— руководитель" in h.tg.texts(OWNER)[-1]
        # Себя понизить нельзя
        await h.text(OWNER, "/add +996700000100 Я")
        assert "Себя понизить нельзя" in h.tg.texts(OWNER)[-1]

    run(scenario)
