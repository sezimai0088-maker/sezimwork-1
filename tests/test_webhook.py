"""Режим webhook для Render: /health, приём сообщений от Telegram, защита секретом, адрес базы."""

import asyncio

import pytest

pytest.importorskip("aiogram")

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

from bot.config import Settings  # noqa: E402
from bot.db import init_db, is_postgres, make_engine, make_sessionmaker, normalize_database_url  # noqa: E402
from bot.main import WEBHOOK_PATH, build_dispatcher, build_web_app, webhook_secret  # noqa: E402
from tests.test_bot_flow import FakeTelegram  # noqa: E402


def test_database_url_from_supabase_is_converted():
    url = "postgresql://postgres.abc:pass123@aws-0-eu-central-1.pooler.supabase.com:5432/postgres?sslmode=require"
    assert normalize_database_url(url) == (
        "postgresql+asyncpg://postgres.abc:pass123@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    )
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert is_postgres(url)
    assert not is_postgres("sqlite+aiosqlite:///data/bot.db")
    assert normalize_database_url("sqlite+aiosqlite:///data/bot.db") == "sqlite+aiosqlite:///data/bot.db"


def test_public_url_from_render_environment():
    s = Settings(_env_file=None, bot_token="1:x", owner_phone="1", office_lat=1, office_lon=1,
                 render_external_url="https://attendance-bot.onrender.com/")
    assert s.public_url == "https://attendance-bot.onrender.com"
    assert len(webhook_secret(s)) >= 32
    s2 = Settings(_env_file=None, bot_token="1:x", owner_phone="1", office_lat=1, office_lon=1)
    assert s2.public_url == ""


def test_webhook_app_health_secret_and_updates():
    async def scenario():
        from aiogram import Bot
        from aiogram.client.default import DefaultBotProperties
        from aiogram.enums import ParseMode
        from aiogram.methods import SendMessage

        from bot.handlers import admin, attendance, reports, start, tasks

        for module in (admin, attendance, reports, start, tasks):
            module.router._parent_router = None

        settings = Settings(_env_file=None, bot_token="42:TEST", owner_phone="+996700000100", office_lat=1,
                            office_lon=1, database_url="sqlite+aiosqlite:///:memory:")
        engine = make_engine(settings.database_url)
        await init_db(engine)
        tg = FakeTelegram()
        bot = Bot("42:TEST", session=tg, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        dp = build_dispatcher(make_sessionmaker(engine), settings)
        client = TestClient(TestServer(build_web_app(bot, dp, settings)))
        await client.start_server()
        try:
            r = await client.get("/health")
            assert r.status == 200 and await r.text() == "ok"

            update = {
                "update_id": 1,
                "message": {
                    "message_id": 1, "date": 1761800000, "text": "/start",
                    "chat": {"id": 555, "type": "private"},
                    "from": {"id": 555, "is_bot": False, "first_name": "Test"},
                    "entities": [{"type": "bot_command", "offset": 0, "length": 6}],
                },
            }
            # Без секрета — отказ: чужие не могут подделать сообщения
            r = await client.post(WEBHOOK_PATH, json=update)
            assert r.status == 401
            r = await client.post(
                WEBHOOK_PATH, json=update, headers={"X-Telegram-Bot-Api-Secret-Token": webhook_secret(settings)}
            )
            assert r.status == 200
            for _ in range(50):
                if any(isinstance(c, SendMessage) for c in tg.calls):
                    break
                await asyncio.sleep(0.05)
            sent = [c for c in tg.calls if isinstance(c, SendMessage)]
            assert sent and sent[-1].chat_id == 555 and "номеру телефона" in sent[-1].text
        finally:
            await client.close()
            await engine.dispose()

    asyncio.run(scenario())


def test_json_backup_roundtrip(tmp_path):
    """Выгрузка → восстановление в пустую базу: все записи и даты на месте, новые записи добавляются."""
    from datetime import date, datetime, timezone

    from bot.backup import RestoreError, read_backup, restore_data, write_backup
    from bot.models import Attendance, Employee, Task

    async def scenario():
        src = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'src.db'}")
        await init_db(src)
        sm = make_sessionmaker(src)
        async with sm() as s:
            e = Employee(phone="+996700000001", full_name="Айгуль", role="employee")
            s.add(e)
            await s.flush()
            s.add(Attendance(employee_id=e.id, work_date=date(2026, 11, 2),
                             check_in_at=datetime(2026, 11, 2, 3, 5, tzinfo=timezone.utc),
                             check_in_lat=1, check_in_lon=1, check_in_distance_m=5))
            s.add(Task(employee_id=e.id, text="Отчёт", created_date=date(2026, 11, 2), plan_date=date(2026, 11, 2)))
            await s.commit()
        path = await write_backup(src, tmp_path / "b.json.gz")
        await src.dispose()

        dst = make_engine(f"sqlite+aiosqlite:///{tmp_path / 'dst.db'}")
        counts = await restore_data(dst, read_backup(path))
        assert counts["employees"] == 1 and counts["attendance"] == 1 and counts["tasks"] == 1
        async with make_sessionmaker(dst)() as s:
            att = (await s.scalars(__import__("sqlalchemy").select(Attendance))).one()
            assert att.work_date == date(2026, 11, 2)
            s.add(Employee(phone="+996700000002", full_name="Новый", role="employee"))
            await s.commit()
        with pytest.raises(RestoreError):
            await restore_data(dst, read_backup(path))
        await dst.dispose()

    asyncio.run(scenario())


def test_database_hints_hide_password():
    from bot.db import database_hint, describe_database_url

    url = "postgresql://postgres.abc:secret@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
    d = describe_database_url(url)
    assert "secret" not in d and "pooler.supabase.com" in d and "пароль задан" in d
    assert "YOUR-PASSWORD" in database_hint("postgresql://postgres.abc:[YOUR-PASSWORD]@h:5432/postgres", OSError("x"))
    assert "Session pooler" in database_hint("postgresql://postgres:p@db.abc.supabase.co:5432/postgres",
                                             OSError("[Errno 101] Network is unreachable"))
    assert "пароль" in database_hint(url, Exception("password authentication failed for user"))
