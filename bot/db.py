"""Подключение к базе данных."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bot.models import Base


def normalize_database_url(url: str) -> str:
    """Адрес из Supabase/Neon/Render ('postgresql://...' или 'postgres://...') → 'postgresql+asyncpg://...'.

    Параметр sslmode из адреса убираем: asyncpg его не понимает, SSL включается отдельно.
    """
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix):]
            break
    if url.startswith("postgresql+asyncpg://") and "?" in url:
        base, query = url.split("?", 1)
        params = [p for p in query.split("&") if p and not p.startswith("sslmode=")]
        url = base + ("?" + "&".join(params) if params else "")
    return url


def is_postgres(url: str) -> bool:
    return normalize_database_url(url).startswith("postgresql+asyncpg://")


def make_engine(database_url: str) -> AsyncEngine:
    database_url = normalize_database_url(database_url)
    if database_url.startswith("sqlite") and ":///" in database_url:
        db_path = database_url.split(":///", 1)[1]
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    if is_postgres(database_url):
        local = "@localhost" in database_url or "@127.0.0.1" in database_url
        engine = create_async_engine(
            database_url,
            pool_pre_ping=True,      # облачная база может закрыть простаивающее соединение
            pool_recycle=300,
            pool_size=3,
            max_overflow=2,
            connect_args={
                # Облачные базы требуют шифрование; через пулер (pgbouncer) не кешируем запросы
                "ssl": None if local else "require",
                "statement_cache_size": 0,
            },
        )
        return engine

    engine = create_async_engine(database_url)

    if database_url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


def _add_missing_columns(sync_conn) -> None:  # noqa: ANN001
    """Простая миграция: добавляет в старые таблицы новые колонки (все они необязательные).

    Новые таблицы создаёт create_all, а колонки в существующих таблицах — эта функция.
    Так база с прошлых этапов обновляется сама, отметки не теряются.
    """
    inspector = inspect(sync_conn)
    for table in Base.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            col_type = column.type.compile(dialect=sync_conn.dialect)
            sync_conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
