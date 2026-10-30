"""Настройки бота. Читаются из переменных окружения и файла .env."""

from __future__ import annotations

from datetime import time
from functools import cached_property
from zoneinfo import ZoneInfo

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.phones import normalize_phone


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    owner_phone: str
    group_chat_id: int | None = None

    office_lat: float
    office_lon: float
    office_radius_m: float = 100
    max_accuracy_m: float = 100

    timezone: str = "Asia/Bishkek"
    work_start: time = time(9, 0)
    work_end: time = time(18, 0)
    grace_minutes: int = 5
    work_days: str = "1,2,3,4,5"
    # Через сколько дней подряд «Не успел» руководитель получает алерт
    alert_days: int = 2

    # Отчёты и напоминания
    daily_report_time: time = time(19, 0)       # ежедневный отчёт руководителю и владельцу
    weekly_report_time: time = time(9, 0)       # недельный (понедельник) и месячный (1-е число)
    checkin_reminder_min: int = 15              # через сколько минут после начала напомнить отметиться
    morning_summary_min: int = 30               # через сколько минут после начала — «ещё не отметились» в чат
    checkout_reminder_min: int = 30             # через сколько минут после конца напомнить завершить день
    backup_time: time = time(3, 0)              # ночной бэкап базы владельцу
    plan_autosend_min: int = 15                 # если план не отправили — бот отправит приход сам через N минут

    twogis_base_url: str = "https://2gis.kg"
    database_url: str = "sqlite+aiosqlite:///data/bot.db"

    # Режим webhook для хостингов вроде Render. Пусто — бот работает как раньше (сам забирает сообщения).
    # На Render адрес подставляется автоматически из RENDER_EXTERNAL_URL.
    webhook_base_url: str = ""
    render_external_url: str = ""
    webhook_secret: str = ""
    port: int = 8080

    @property
    def public_url(self) -> str:
        return (self.webhook_base_url or self.render_external_url).rstrip("/")

    @field_validator("group_chat_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("owner_phone")
    @classmethod
    def _normalize_owner(cls, value: str) -> str:
        # Можно указать несколько владельцев через запятую: +996555111111,+996555222222
        return ",".join(p for p in (normalize_phone(x) for x in value.split(",")) if p)

    @property
    def owner_phones(self) -> frozenset[str]:
        return frozenset(p for p in self.owner_phone.split(",") if p)

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @cached_property
    def work_day_numbers(self) -> frozenset[int]:
        return frozenset(int(x) for x in self.work_days.split(",") if x.strip())
