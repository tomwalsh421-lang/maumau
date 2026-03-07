from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from cbb.config import get_settings


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = REPO_ROOT / "sql" / "schema.sql"


def resolve_database_url(database_url: str | None = None) -> str:
    if database_url:
        return database_url
    return get_settings().database_url


def get_engine(database_url: str | None = None) -> Engine:
    return create_engine(resolve_database_url(database_url), future=True)


def init_db(database_url: str | None = None, schema_path: Path | None = None) -> Path:
    schema_file = schema_path or DEFAULT_SCHEMA_PATH
    sql = schema_file.read_text(encoding="utf-8").strip()
    db_url = resolve_database_url(database_url)

    if db_url.startswith("sqlite"):
        raise ValueError("init-db only supports PostgreSQL because sql/schema.sql uses PostgreSQL syntax.")

    engine = get_engine(db_url)
    with engine.begin() as connection:
        connection.exec_driver_sql(sql)

    return schema_file
