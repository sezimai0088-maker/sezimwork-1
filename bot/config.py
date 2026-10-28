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

    twogis_base_url: str = "https://2gis.kg"
    database_url: str = "sqlite+aiosqlite:///data/bot.db"

    @field_validator("group_chat_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("owner_phone")
    @classmethod
    def _normalize_owner(cls, value: str) -> str:
        return normalize_phone(value)

    @cached_property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @cached_property
    def work_day_numbers(self) -> frozenset[int]:
        return frozenset(int(x) for x in self.work_days.split(",") if x.strip())
