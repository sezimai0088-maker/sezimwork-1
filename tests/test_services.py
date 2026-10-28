"""Сценарии подключения, прихода и ухода на настоящей базе SQLite в памяти."""

import asyncio
from datetime import datetime, timezone

import pytest

pytest.importorskip("sqlalchemy")
pytest.importorskip("aiosqlite")
pytest.importorskip("pydantic_settings")

from bot.config import Settings  # noqa: E402
from bot.db import init_db, make_engine, make_sessionmaker  # noqa: E402
from bot.models import CheckoutMode, Role  # noqa: E402
from bot.services import attendance as att  # noqa: E402
from bot.services import employees as emp  # noqa: E402

OFFICE_LAT, OFFICE_LON = 42.8746, 74.5698


def make_settings() -> Settings:
    return Settings(
        _env_file=None,
        bot_token="test",
        owner_phone="+996700000001",
        office_lat=OFFICE_LAT,
        office_lon=OFFICE_LON,
        database_url="sqlite+aiosqlite:///:memory:",
    )


def utc(h: int, m: int, day: int = 29) -> datetime:
    # 29.10.2026 — четверг; Бишкек = UTC+6, значит 03:07 UTC = 09:07 по Бишкеку
    return datetime(2026, 10, day, h, m, tzinfo=timezone.utc)


def run(coro_fn):
    async def wrapper():
        settings = make_settings()
        engine = make_engine(settings.database_url)
        await init_db(engine)
        sm = make_sessionmaker(engine)
        async with sm() as session:
            await coro_fn(session, settings)
        await engine.dispose()

    asyncio.run(wrapper())


def test_owner_registers_by_phone():
    async def scenario(session, settings):
        result = await emp.register_by_contact(
            session, telegram_id=1, phone="996700000001", telegram_name="Сезим", owner_phone=settings.owner_phone
        )
        assert result.status == emp.RegisterStatus.OWNER_CREATED
        assert result.employee.role == Role.OWNER

    run(scenario)


def test_unknown_phone_is_rejected_and_added_phone_is_accepted():
    async def scenario(session, settings):
        r = await emp.register_by_contact(
            session, telegram_id=2, phone="+996555123456", telegram_name="X", owner_phone=settings.owner_phone
        )
        assert r.status == emp.RegisterStatus.NOT_FOUND

        await emp.add_employee(session, phone="0555 123 456", full_name="Айбек Асанов")
        r = await emp.register_by_contact(
            session, telegram_id=2, phone="+996555123456", telegram_name="X", owner_phone=settings.owner_phone
        )
        assert r.status == emp.RegisterStatus.REGISTERED
        assert r.employee.full_name == "Айбек Асанов"

        # Тот же номер с другого аккаунта Telegram не подключится
        r = await emp.register_by_contact(
            session, telegram_id=3, phone="+996555123456", telegram_name="Y", owner_phone=settings.owner_phone
        )
        assert r.status == emp.RegisterStatus.PHONE_TAKEN

    run(scenario)


def test_checkin_late_then_checkout_in_office():
    async def scenario(session, settings):
        e, _ = await emp.add_employee(session, phone="996555123456", full_name="Айбек")
        r = await att.check_in(
            session, settings, e, lat=OFFICE_LAT + 0.0003, lon=OFFICE_LON, accuracy_m=20, now=utc(3, 7)
        )
        assert r.status == att.CheckInStatus.OK
        assert r.attendance.late_minutes == 7

        again = await att.check_in(session, settings, e, lat=OFFICE_LAT, lon=OFFICE_LON, accuracy_m=20, now=utc(3, 30))
        assert again.status == att.CheckInStatus.ALREADY

        day = await att.get_day(session, e.id, r.attendance.work_date)
        out = await att.check_out(session, settings, day, lat=OFFICE_LAT, lon=OFFICE_LON, accuracy_m=20, now=utc(12, 5))
        assert out.mode == CheckoutMode.OFFICE
        assert out.attendance.worked_minutes == 538
        assert out.attendance.early_leave_minutes == 0

    run(scenario)


def test_checkin_outside_zone_is_not_saved():
    async def scenario(session, settings):
        e, _ = await emp.add_employee(session, phone="996555123456", full_name="Айбек")
        r = await att.check_in(session, settings, e, lat=OFFICE_LAT + 0.003, lon=OFFICE_LON, accuracy_m=10, now=utc(3, 0))
        assert r.status == att.CheckInStatus.OUTSIDE
        assert 320 < r.zone.distance_m < 350
        assert await att.get_day(session, e.id, utc(3, 0).astimezone(settings.tz).date()) is None

    run(scenario)


def test_low_accuracy_checkin_asks_to_retry():
    async def scenario(session, settings):
        e, _ = await emp.add_employee(session, phone="996555123456", full_name="Айбек")
        r = await att.check_in(session, settings, e, lat=OFFICE_LAT, lon=OFFICE_LON, accuracy_m=500, now=utc(3, 0))
        assert r.status == att.CheckInStatus.LOW_ACCURACY

    run(scenario)


def test_checkout_in_field_and_early_leave():
    async def scenario(session, settings):
        e, _ = await emp.add_employee(session, phone="996555123456", full_name="Айбек")
        r = await att.check_in(session, settings, e, lat=OFFICE_LAT, lon=OFFICE_LON, accuracy_m=10, now=utc(2, 55))
        assert r.attendance.late_minutes == 0
        out = await att.check_out(
            session, settings, r.attendance, lat=OFFICE_LAT + 0.05, lon=OFFICE_LON, accuracy_m=30, now=utc(11, 30)
        )
        assert out.mode == CheckoutMode.FIELD
        assert out.attendance.early_leave_minutes == 30

    run(scenario)


def test_weekend_has_no_lateness():
    async def scenario(session, settings):
        e, _ = await emp.add_employee(session, phone="996555123456", full_name="Айбек")
        r = await att.check_in(
            session, settings, e, lat=OFFICE_LAT, lon=OFFICE_LON, accuracy_m=10, now=utc(5, 0, day=31)
        )
        assert r.attendance.is_workday is False
        assert r.attendance.late_minutes == 0

    run(scenario)


def test_deactivated_employee_cannot_register():
    async def scenario(session, settings):
        await emp.add_employee(session, phone="996555123456", full_name="Айбек")
        await emp.deactivate(session, "+996555123456")
        r = await emp.register_by_contact(
            session, telegram_id=5, phone="996555123456", telegram_name="A", owner_phone=settings.owner_phone
        )
        assert r.status == emp.RegisterStatus.INACTIVE

    run(scenario)
