"""Приведение номеров телефонов к единому виду."""

import re


def normalize_phone(raw: str) -> str:
    """Оставляет только цифры: '+996 (555) 12-34-56' -> '996555123456'.

    Номер, начинающийся с 0 (местный формат Кыргызстана, 0555123456),
    приводится к международному с кодом 996.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("0") and len(digits) == 10:
        digits = "996" + digits[1:]
    return digits


def format_phone(digits: str) -> str:
    return f"+{digits}" if digits else ""
