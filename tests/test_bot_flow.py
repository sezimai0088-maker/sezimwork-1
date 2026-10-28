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
        if isinstance(method, (SendMessage, EditMessageText, EditMessageReplyMarkup)):
            chat_id = getattr(method, "chat_id", None) or 0
            return Message(
                message_id=next(self._ids),
                date=datetime.now(timezone.utc),
                chat=Chat(id=chat_id, type="private"),
                text=getattr(method, "text", None) or "x",
            )
        return True

    async def stream_content(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise NotImplementedError

    async def close(self) -> None:
        pass

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
        )
        self.engine = make_engine(self.settings.database_url)
        await init_db(self.engine)
        self.bot = Bot("42:TEST", session=self.tg, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher(storage=MemoryStorage())
        self.dp["settings"] = self.settings
        self.dp.update.outer_middleware(DbSessionMiddleware(make_sessionmaker(self.engine)))
        # Роутеры модулей — общие объекты; в каждом тесте подключаем их заново
        from bot.handlers import admin, attendance, start, tasks

        for module in (admin, attendance, start, tasks):
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
            message=self._msg(uid, text="Задача 1 из 1:\n<b>x</b>\n\nКак прошло?"),
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


async def onboard(h: Harness) -> None:
    await h.text(OWNER, "/start")
    await h.contact(OWNER, "+996700000100")
    await h.text(OWNER, "/add_manager +996700000200 Нурлан Касымов")
    await h.text(OWNER, "/add +996700000300 Айбек Асанов")
    for uid in (MANAGER, WORKER):
        await h.text(uid, "/start")
        await h.contact(uid, f"+996700000{uid}")


def test_full_day_with_tasks():
    async def scenario(h: Harness):
        await onboard(h)
        assert any("владелец" in t for t in h.tg.texts(OWNER))
        assert any("Готово, Айбек Асанов" in t for t in h.tg.texts(WORKER))

        # Вне офиса — не засчитывается
        await h.location(WORKER, OFFICE[0] + 0.01, OFFICE[1])
        assert "от офиса" in h.tg.texts(WORKER)[-1]
        assert not h.tg.sent(GROUP_ID)

        # В офисе — приход, сообщение в чат, сразу просьба написать задачи
        await h.location(WORKER, OFFICE[0] + 0.0002, OFFICE[1])
        group = h.tg.texts(GROUP_ID)
        assert "Айбек Асанов</b> пришёл в офис" in group[-1]
        assert "каждую с новой строки" in h.tg.texts(WORKER)[-1]

        # Пишет задачи списком, затем «Готово» и «Всё верно»
        await h.text(WORKER, "1. Сдать отчёт\n2. Позвонить поставщику\n3. Проверить склад")
        assert "Добавлено задач: 3" in h.tg.texts(WORKER)[-1]
        await h.text(WORKER, "✅ Готово")
        await h.press(WORKER, h.find_button(WORKER, "✅ Всё верно"))
        plan_msg = h.tg.texts(GROUP_ID)[-1]
        assert "план на сегодня" in plan_msg and "Позвонить поставщику" in plan_msg

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
        await h.text(WORKER, "✅ Готово")
        await h.press(WORKER, h.find_button(WORKER, "✅ Всё верно"))

        await h.text(WORKER, "➕ Добавить задачу")
        await h.text(WORKER, "Вторая задача")
        await h.text(WORKER, "✅ Готово")
        await h.press(WORKER, h.find_button(WORKER, "✅ Всё верно"))
        assert "дополнил план" in h.tg.texts(GROUP_ID)[-1]
        assert "Первая задача" not in h.tg.texts(GROUP_ID)[-1]

        await h.text(WORKER, "📋 Мои задачи")
        assert "Вторая задача" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "▶️ 1."))
        edits = [c for c in h.tg.calls if isinstance(c, EditMessageText)]
        assert "▶️ Первая задача" in edits[-1].text

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
        await h.text(WORKER, "✅ Готово")
        await h.press(WORKER, h.find_button(WORKER, "✅ Всё верно"))
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
        assert "Вчера не закончены" in h.tg.texts(WORKER)[-1]
        await h.press(WORKER, h.find_button(WORKER, "✅ Убрать склад"))
        await h.press(WORKER, h.find_button(WORKER, "Дальше"))
        await h.text(WORKER, "✅ Готово")
        await h.press(WORKER, h.find_button(WORKER, "✅ Всё верно"))
        plan = h.tg.texts(GROUP_ID)[-1]
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
        await h.text(OWNER, "✅ Готово")
        await h.press(OWNER, h.find_button(OWNER, "✅ Всё верно"))
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
        assert "пришёл в офис" in h.tg.texts(GROUP_ID)[-1]
        await h.text(OWNER, "✅ Готово")
        await h.press(OWNER, h.find_button(OWNER, "✅ Всё верно"))
        await h.text(OWNER, "🏁 Завершить день")
        assert "Задача 1 из 1" in h.tg.texts(OWNER)[-1]

    run(scenario)
