"""Язык бота: кыргызский или русский.

Язык выбирает каждый сотрудник. Текущий язык хранится в «контексте» обработки сообщения:
бот выставляет его перед каждым ответом, поэтому `texts.X` всегда отдаёт текст на нужном языке.
Когда бот пишет другому человеку или в общий чат, язык временно меняют через `with use_lang(...)`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

KY = "ky"
RU = "ru"
LANGS = (KY, RU)
DEFAULT = RU

_current: ContextVar[str] = ContextVar("bot_lang", default=DEFAULT)


def normalize(code: str | None) -> str:
    return code if code in LANGS else DEFAULT


def get_lang() -> str:
    return _current.get()


def set_lang(code: str | None) -> None:
    _current.set(normalize(code))


@contextmanager
def use_lang(code: str | None) -> Iterator[None]:
    token = _current.set(normalize(code))
    try:
        yield
    finally:
        _current.reset(token)


def lang_of(person) -> str:  # noqa: ANN001
    """Язык сотрудника; если ещё не выбран — русский."""
    return normalize(getattr(person, "lang", None))


def tr(ru: str, ky: str) -> str:
    """Короткий текст на текущем языке: tr("Сотрудник", "Кызматкер")."""
    return ky if get_lang() == KY else ru
