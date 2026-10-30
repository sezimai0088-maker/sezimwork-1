"""Бэкап и восстановление базы в виде файла JSON (сжатого gzip).

Работает и с SQLite, и с PostgreSQL (Supabase). Бот каждую ночь присылает такой файл владельцу.

Восстановить в пустую базу:
    python -m bot.backup restore backup_2026-11-05.json.gz
Адрес базы берётся из DATABASE_URL (.env или переменная окружения), либо: --db "postgresql://..."
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import Date, DateTime, func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine

from bot.db import init_db, is_postgres, make_engine
from bot.models import Base

FORMAT_VERSION = 1


def _encode(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


async def export_data(engine: AsyncEngine) -> dict:
    tables: dict[str, list[dict]] = {}
    async with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            rows = (await conn.execute(select(table))).mappings().all()
            tables[table.name] = [{k: _encode(v) for k, v in row.items()} for row in rows]
    return {"format": FORMAT_VERSION, "created_at": datetime.now().isoformat(timespec="seconds"), "tables": tables}


async def write_backup(engine: AsyncEngine, target: Path) -> Path:
    data = await export_data(engine)
    with gzip.open(target, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    return target


def _decode_row(table, row: dict) -> dict:  # noqa: ANN001
    out = {}
    for name, value in row.items():
        if name not in table.c:
            continue  # колонку убрали из новой версии — пропускаем
        col_type = table.c[name].type
        if isinstance(value, str) and isinstance(col_type, DateTime):
            value = datetime.fromisoformat(value)
        elif isinstance(value, str) and isinstance(col_type, Date):
            value = date.fromisoformat(value)
        out[name] = value
    return out


class RestoreError(Exception):
    pass


async def restore_data(engine: AsyncEngine, data: dict) -> dict[str, int]:
    """Загружает бэкап в ПУСТУЮ базу. Если в базе уже есть сотрудники — отказ, чтобы ничего не испортить."""
    if data.get("format") != FORMAT_VERSION:
        raise RestoreError("Неизвестный формат файла бэкапа.")
    await init_db(engine)
    counts: dict[str, int] = {}
    async with engine.begin() as conn:
        employees = Base.metadata.tables["employees"]
        if await conn.scalar(select(func.count()).select_from(employees)):
            raise RestoreError("База не пустая. Восстанавливать можно только в новую, пустую базу.")
        for table in Base.metadata.sorted_tables:
            rows = [_decode_row(table, r) for r in data["tables"].get(table.name, [])]
            if rows:
                await conn.execute(table.insert(), rows)
            counts[table.name] = len(rows)
        if conn.dialect.name == "postgresql":
            # После вставки с готовыми id счётчики надо сдвинуть, иначе новые записи упадут с ошибкой
            for table in Base.metadata.sorted_tables:
                pk = list(table.primary_key.columns)
                if len(pk) == 1 and pk[0].autoincrement in (True, "auto") and pk[0].type.python_type is int:
                    await conn.execute(text(
                        f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', '{pk[0].name}'), "
                        f"COALESCE((SELECT MAX(\"{pk[0].name}\") FROM \"{table.name}\"), 0) + 1, false)"
                    ))
    return counts


def read_backup(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


async def _cli_restore(path: Path, db_url: str) -> None:
    engine = make_engine(db_url)
    try:
        counts = await restore_data(engine, read_backup(path))
    finally:
        await engine.dispose()
    print("Готово, восстановлено:")
    for name, n in counts.items():
        print(f"  {name}: {n}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Бэкап базы бота")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("restore", help="восстановить из файла .json.gz в пустую базу")
    r.add_argument("file", type=Path)
    r.add_argument("--db", help="адрес базы; по умолчанию DATABASE_URL")
    e = sub.add_parser("export", help="сохранить базу в файл .json.gz")
    e.add_argument("file", type=Path)
    e.add_argument("--db", help="адрес базы; по умолчанию DATABASE_URL")
    args = parser.parse_args()

    db_url = args.db
    if not db_url:
        import os

        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            from bot.config import Settings

            db_url = Settings().database_url
    if args.cmd == "restore":
        try:
            asyncio.run(_cli_restore(args.file, db_url))
        except RestoreError as exc:
            raise SystemExit(f"Ошибка: {exc}") from None
    else:
        async def _export() -> None:
            engine = make_engine(db_url)
            try:
                await write_backup(engine, args.file)
            finally:
                await engine.dispose()
        asyncio.run(_export())
        print(f"Сохранено: {args.file}")


__all__ = ["export_data", "write_backup", "restore_data", "read_backup", "RestoreError", "is_postgres"]

if __name__ == "__main__":
    main()
