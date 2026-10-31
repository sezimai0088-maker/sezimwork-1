"""Тексты бота на языке текущего пользователя.

Сами тексты — в texts_ru.py (русский) и texts_ky.py (кыргызский), с одинаковыми именами.
`texts.BTN_CHECK_IN` вернёт кнопку на языке того, кому бот сейчас отвечает (см. bot/i18n.py).
Если в кыргызском файле чего-то нет, берётся русский вариант.
"""

from __future__ import annotations

from bot import texts_ky, texts_ru
from bot.i18n import KY, get_lang

_MODULES = {KY: texts_ky}


def __getattr__(name: str):
    module = _MODULES.get(get_lang())
    if module is not None and hasattr(module, name):
        return getattr(module, name)
    return getattr(texts_ru, name)


def variants(name: str) -> frozenset[str]:
    """Текст кнопки на всех языках — чтобы обработчик понимал нажатие на любом языке."""
    return frozenset({getattr(texts_ru, name), getattr(texts_ky, name, getattr(texts_ru, name))})


# Все кнопки меню на обоих языках: их текст не должен попадать в задачи и комментарии
MENU_BUTTONS = texts_ru.MENU_BUTTONS | texts_ky.MENU_BUTTONS
