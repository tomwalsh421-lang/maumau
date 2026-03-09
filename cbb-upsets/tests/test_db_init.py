from __future__ import annotations

from pathlib import Path

import pytest

from cbb.db import init_db


def test_init_db_rejects_sqlite_urls() -> None:
    with pytest.raises(ValueError) as exc_info:
        init_db(database_url="sqlite+pysqlite:///unit-test.sqlite")

    assert "only supports PostgreSQL" in str(exc_info.value)


def test_init_db_executes_supplied_schema_against_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    schema_path = tmp_path / "schema.sql"
    schema_path.write_text("CREATE TABLE demo (id INT);", encoding="utf-8")
    executed_sql: list[str] = []

    class FakeConnection:
        def exec_driver_sql(self, sql: str) -> None:
            executed_sql.append(sql)

    class FakeTransaction:
        def __enter__(self) -> FakeConnection:
            return FakeConnection()

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class FakeEngine:
        def begin(self) -> FakeTransaction:
            return FakeTransaction()

    monkeypatch.setattr("cbb.db.get_engine", lambda _database_url=None: FakeEngine())

    result = init_db(
        database_url="postgresql://cbb:cbbpass@127.0.0.1:5432/cbb_upsets",
        schema_path=schema_path,
    )

    assert result == schema_path
    assert executed_sql == ["CREATE TABLE demo (id INT);"]
