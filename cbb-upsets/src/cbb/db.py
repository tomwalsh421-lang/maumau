from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from cbb.config import get_settings


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = REPO_ROOT / "sql" / "schema.sql"


@dataclass(frozen=True)
class TableCount:
    """Row count for a database table or logical slice."""

    name: str
    row_count: int


@dataclass(frozen=True)
class GameSummary:
    """Small game summary used for database inspection output."""

    commence_time: str | None
    home_team: str
    away_team: str
    home_score: int | None = None
    away_score: int | None = None
    result: str | None = None


@dataclass(frozen=True)
class OddsSnapshotSummary:
    """Small odds snapshot summary used for database inspection output."""

    market_key: str
    bookmaker_key: str
    home_team: str
    away_team: str
    team1_price: float | None
    team2_price: float | None
    total_points: float | None
    captured_at: str


@dataclass(frozen=True)
class DatabaseSummary:
    """High-level summary of the currently loaded database contents."""

    teams: int
    games: int
    completed_games: int
    upcoming_games: int
    odds_snapshots: int
    first_game_time: str | None
    last_game_time: str | None
    completed_samples: list[GameSummary]
    upcoming_samples: list[GameSummary]
    odds_samples: list[OddsSnapshotSummary]


def resolve_database_url(database_url: str | None = None) -> str:
    """Return an explicit database URL or fall back to configured settings.

    Args:
        database_url: Optional override for the configured database URL.

    Returns:
        A SQLAlchemy-compatible database URL.
    """
    if database_url:
        return database_url
    return get_settings().database_url


def get_engine(database_url: str | None = None) -> Engine:
    """Create a SQLAlchemy engine for the configured database.

    Args:
        database_url: Optional override for the configured database URL.

    Returns:
        A SQLAlchemy engine.
    """
    return create_engine(resolve_database_url(database_url), future=True)


def init_db(database_url: str | None = None, schema_path: Path | None = None) -> Path:
    """Initialize the PostgreSQL schema.

    Args:
        database_url: Optional override for the configured database URL.
        schema_path: Optional override for the schema file path.

    Returns:
        The path to the schema file that was executed.

    Raises:
        ValueError: If the configured database is SQLite.
    """
    schema_file = schema_path or DEFAULT_SCHEMA_PATH
    sql = schema_file.read_text(encoding="utf-8").strip()
    db_url = resolve_database_url(database_url)

    if db_url.startswith("sqlite"):
        raise ValueError(
            "init-db only supports PostgreSQL because sql/schema.sql uses PostgreSQL syntax."
        )

    engine = get_engine(db_url)
    with engine.begin() as connection:
        connection.exec_driver_sql(sql)

    return schema_file


def get_database_summary(database_url: str | None = None) -> DatabaseSummary:
    """Collect a concise summary of the loaded game and odds data.

    Args:
        database_url: Optional override for the configured database URL.

    Returns:
        A structured summary of counts, date range, and sample rows.
    """
    engine = get_engine(database_url)

    with engine.connect() as connection:
        counts = {row.name: row.row_count for row in _fetch_table_counts(connection)}
        first_game_time, last_game_time = _fetch_date_range(connection)

        return DatabaseSummary(
            teams=counts["teams"],
            games=counts["games"],
            completed_games=counts["completed_games"],
            upcoming_games=counts["upcoming_games"],
            odds_snapshots=counts["odds_snapshots"],
            first_game_time=first_game_time,
            last_game_time=last_game_time,
            completed_samples=_fetch_completed_samples(connection),
            upcoming_samples=_fetch_upcoming_samples(connection),
            odds_samples=_fetch_odds_samples(connection),
        )


def _fetch_table_counts(connection: Connection) -> list[TableCount]:
    """Fetch key table counts for summary output."""
    rows = connection.execute(
        text(
            """
            SELECT 'teams' AS name, COUNT(*) AS row_count FROM teams
            UNION ALL
            SELECT 'games' AS name, COUNT(*) AS row_count FROM games
            UNION ALL
            SELECT 'completed_games' AS name, COUNT(*) AS row_count FROM games WHERE completed
            UNION ALL
            SELECT 'upcoming_games' AS name, COUNT(*) AS row_count FROM games WHERE NOT completed
            UNION ALL
            SELECT 'odds_snapshots' AS name, COUNT(*) AS row_count FROM odds_snapshots
            """
        )
    ).mappings()
    return [
        TableCount(name=str(row["name"]), row_count=int(row["row_count"]))
        for row in rows
    ]


def _fetch_date_range(connection: Connection) -> tuple[str | None, str | None]:
    """Fetch the loaded game date range."""
    row = (
        connection.execute(
            text(
                """
            SELECT
                CAST(MIN(commence_time) AS TEXT) AS first_game_time,
                CAST(MAX(commence_time) AS TEXT) AS last_game_time
            FROM games
            """
            )
        )
        .mappings()
        .one()
    )
    return _as_optional_str(row["first_game_time"]), _as_optional_str(
        row["last_game_time"]
    )


def _fetch_completed_samples(connection: Connection) -> list[GameSummary]:
    """Fetch a few recent completed games."""
    rows = connection.execute(
        text(
            """
            SELECT
                CAST(g.commence_time AS TEXT) AS commence_time,
                home_team.name AS home_team,
                away_team.name AS away_team,
                g.home_score,
                g.away_score,
                g.result
            FROM games AS g
            JOIN teams AS home_team ON home_team.team_id = g.team1_id
            JOIN teams AS away_team ON away_team.team_id = g.team2_id
            WHERE g.completed
            ORDER BY g.commence_time DESC NULLS LAST
            LIMIT 5
            """
        )
    ).mappings()
    return [
        GameSummary(
            commence_time=_as_optional_str(row["commence_time"]),
            home_team=str(row["home_team"]),
            away_team=str(row["away_team"]),
            home_score=_as_optional_int(row["home_score"]),
            away_score=_as_optional_int(row["away_score"]),
            result=_as_optional_str(row["result"]),
        )
        for row in rows
    ]


def _fetch_upcoming_samples(connection: Connection) -> list[GameSummary]:
    """Fetch a few upcoming games."""
    rows = connection.execute(
        text(
            """
            SELECT
                CAST(g.commence_time AS TEXT) AS commence_time,
                home_team.name AS home_team,
                away_team.name AS away_team
            FROM games AS g
            JOIN teams AS home_team ON home_team.team_id = g.team1_id
            JOIN teams AS away_team ON away_team.team_id = g.team2_id
            WHERE NOT g.completed
            ORDER BY g.commence_time ASC NULLS LAST
            LIMIT 5
            """
        )
    ).mappings()
    return [
        GameSummary(
            commence_time=_as_optional_str(row["commence_time"]),
            home_team=str(row["home_team"]),
            away_team=str(row["away_team"]),
        )
        for row in rows
    ]


def _fetch_odds_samples(connection: Connection) -> list[OddsSnapshotSummary]:
    """Fetch a few recent odds snapshots."""
    rows = connection.execute(
        text(
            """
            SELECT
                snapshot.market_key,
                snapshot.bookmaker_key,
                home_team.name AS home_team,
                away_team.name AS away_team,
                snapshot.team1_price,
                snapshot.team2_price,
                snapshot.total_points,
                CAST(snapshot.captured_at AS TEXT) AS captured_at
            FROM odds_snapshots AS snapshot
            JOIN games AS g ON g.game_id = snapshot.game_id
            JOIN teams AS home_team ON home_team.team_id = g.team1_id
            JOIN teams AS away_team ON away_team.team_id = g.team2_id
            ORDER BY snapshot.captured_at DESC
            LIMIT 5
            """
        )
    ).mappings()
    return [
        OddsSnapshotSummary(
            market_key=str(row["market_key"]),
            bookmaker_key=str(row["bookmaker_key"]),
            home_team=str(row["home_team"]),
            away_team=str(row["away_team"]),
            team1_price=_as_optional_float(row["team1_price"]),
            team2_price=_as_optional_float(row["team2_price"]),
            total_points=_as_optional_float(row["total_points"]),
            captured_at=str(row["captured_at"]),
        )
        for row in rows
    ]


def _as_optional_str(value: object) -> str | None:
    """Convert a scalar value to string while preserving nulls."""
    if value is None:
        return None
    return str(value)


def _as_optional_int(value: object) -> int | None:
    """Convert a scalar value to int while preserving nulls."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"Expected int-compatible value, got {type(value).__name__}")


def _as_optional_float(value: object) -> float | None:
    """Convert a scalar value to float while preserving nulls."""
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"Expected float-compatible value, got {type(value).__name__}")
