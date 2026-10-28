"""Геозона офиса и ссылки на карту."""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками по формуле гаверсинуса, в метрах."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class ZoneCheck:
    distance_m: float
    inside: bool
    accuracy_too_low: bool


def check_zone(
    lat: float,
    lon: float,
    accuracy_m: float | None,
    *,
    office_lat: float,
    office_lon: float,
    radius_m: float,
    max_accuracy_m: float,
) -> ZoneCheck:
    """Проверяет, находится ли точка внутри круга офиса.

    Погрешность GPS не расширяет круг: если телефон сообщает погрешность
    больше допустимой, отметка не принимается и сотрудника просят повторить.
    """
    dist = distance_m(lat, lon, office_lat, office_lon)
    too_low = accuracy_m is not None and accuracy_m > max_accuracy_m
    return ZoneCheck(distance_m=dist, inside=dist <= radius_m and not too_low, accuracy_too_low=too_low)


def twogis_link(lat: float, lon: float, base_url: str = "https://2gis.kg", zoom: int = 17) -> str:
    """Ссылка на точку в 2ГИС. В 2ГИС долгота идёт первой."""
    base = base_url.rstrip("/")
    return f"{base}/geo/{lon:.6f},{lat:.6f}?m={lon:.6f},{lat:.6f}/{zoom}"
