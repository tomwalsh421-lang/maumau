from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection, Engine

from cbb.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = REPO_ROOT / "sql" / "schema.sql"
UPCOMING_LOOKBACK_HOURS = 6
UPCOMING_LOOKAHEAD_DAYS = 7

FETCH_TEAM_BY_NAME_SQL = text(
    """
    SELECT team_id, team_key, name
    FROM teams
    WHERE LOWER(name) = LOWER(:team_name)
       OR team_key = :team_key
    ORDER BY name
    LIMIT 1
    """
)

FETCH_TEAM_BY_ALIAS_SQL = text(
    """
    SELECT teams.team_id, teams.team_key, teams.name
    FROM team_aliases
    JOIN teams ON teams.team_id = team_aliases.team_id
    WHERE LOWER(team_aliases.alias_name) = LOWER(:team_name)
       OR team_aliases.alias_key = :team_key
    ORDER BY teams.name
    LIMIT 1
    """
)

FETCH_ALL_TEAMS_SQL = text(
    """
    SELECT team_id, team_key, name
    FROM teams
    ORDER BY name
    """
)

FETCH_RECENT_TEAM_RESULTS_SQL = text(
    """
    SELECT
        CAST(g.commence_time AS TEXT) AS commence_time,
        CASE
            WHEN g.team1_id = :team_id THEN away_team.name
            ELSE home_team.name
        END AS opponent_name,
        CASE
            WHEN g.team1_id = :team_id THEN 'vs'
            ELSE 'at'
        END AS venue_label,
        CASE
            WHEN g.team1_id = :team_id THEN g.home_score
            ELSE g.away_score
        END AS team_score,
        CASE
            WHEN g.team1_id = :team_id THEN g.away_score
            ELSE g.home_score
        END AS opponent_score,
        CASE
            WHEN g.result IS NULL THEN NULL
            WHEN g.team1_id = :team_id THEN g.result
            WHEN g.result = 'W' THEN 'L'
            WHEN g.result = 'L' THEN 'W'
            ELSE g.result
        END AS team_result
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE g.completed
      AND (g.team1_id = :team_id OR g.team2_id = :team_id)
    ORDER BY g.commence_time DESC NULLS LAST
    LIMIT :limit
    """
)

FETCH_TEAM_SCHEDULED_GAMES_SQL = text(
    """
    SELECT
        CAST(g.commence_time AS TEXT) AS commence_time,
        home_team.name AS home_team,
        away_team.name AS away_team,
        g.home_score,
        g.away_score,
        (
            SELECT odds.team1_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.captured_at DESC,
                     CASE odds.bookmaker_key
                         WHEN 'draftkings' THEN 0
                         WHEN 'fanduel' THEN 1
                         WHEN 'betmgm' THEN 2
                         ELSE 3
                     END ASC
            LIMIT 1
        ) AS home_pregame_moneyline,
        (
            SELECT odds.team2_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.captured_at DESC,
                     CASE odds.bookmaker_key
                         WHEN 'draftkings' THEN 0
                         WHEN 'fanduel' THEN 1
                         WHEN 'betmgm' THEN 2
                         ELSE 3
                     END ASC
            LIMIT 1
        ) AS away_pregame_moneyline
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE NOT g.completed
      AND g.commence_time IS NOT NULL
      AND (g.team1_id = :team_id OR g.team2_id = :team_id)
      AND g.commence_time >= :window_start
      AND g.commence_time <= :window_end
    ORDER BY g.commence_time ASC
    LIMIT :limit
    """
)

FETCH_IN_PROGRESS_GAMES_SQL = text(
    """
    SELECT
        CAST(g.commence_time AS TEXT) AS commence_time,
        home_team.name AS home_team,
        away_team.name AS away_team,
        g.home_score,
        g.away_score,
        (
            SELECT odds.team1_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.captured_at DESC,
                     CASE odds.bookmaker_key
                         WHEN 'draftkings' THEN 0
                         WHEN 'fanduel' THEN 1
                         WHEN 'betmgm' THEN 2
                         ELSE 3
                     END ASC
            LIMIT 1
        ) AS home_pregame_moneyline,
        (
            SELECT odds.team2_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.captured_at DESC,
                     CASE odds.bookmaker_key
                         WHEN 'draftkings' THEN 0
                         WHEN 'fanduel' THEN 1
                         WHEN 'betmgm' THEN 2
                         ELSE 3
                     END ASC
            LIMIT 1
        ) AS away_pregame_moneyline
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE NOT g.completed
      AND g.commence_time IS NOT NULL
      AND g.commence_time >= :window_start
      AND g.commence_time <= :current_time
    ORDER BY g.commence_time ASC
    """
)

FETCH_FUTURE_GAMES_SQL = text(
    """
    SELECT
        CAST(g.commence_time AS TEXT) AS commence_time,
        home_team.name AS home_team,
        away_team.name AS away_team,
        g.home_score,
        g.away_score,
        (
            SELECT odds.team1_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.captured_at DESC,
                     CASE odds.bookmaker_key
                         WHEN 'draftkings' THEN 0
                         WHEN 'fanduel' THEN 1
                         WHEN 'betmgm' THEN 2
                         ELSE 3
                     END ASC
            LIMIT 1
        ) AS home_pregame_moneyline,
        (
            SELECT odds.team2_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.captured_at DESC,
                     CASE odds.bookmaker_key
                         WHEN 'draftkings' THEN 0
                         WHEN 'fanduel' THEN 1
                         WHEN 'betmgm' THEN 2
                         ELSE 3
                     END ASC
            LIMIT 1
        ) AS away_pregame_moneyline
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE NOT g.completed
      AND g.commence_time IS NOT NULL
      AND g.commence_time > :current_time
      AND g.commence_time <= :window_end
    ORDER BY g.commence_time ASC
    LIMIT :limit
    """
)


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


@dataclass(frozen=True)
class TeamLookup:
    """Canonical team lookup row used by DB views."""

    team_id: int
    team_key: str
    name: str


@dataclass(frozen=True)
class TeamRecentResult:
    """Recent completed result for one team."""

    commence_time: str | None
    opponent_name: str
    venue_label: str
    team_score: int | None
    opponent_score: int | None
    result: str | None


@dataclass(frozen=True)
class TeamView:
    """Resolved team view response for CLI rendering."""

    team_name: str | None
    scheduled_games: list[UpcomingGameView]
    recent_results: list[TeamRecentResult]
    suggestions: list[str]


@dataclass(frozen=True)
class UpcomingGameView:
    """Upcoming or currently in-progress game for CLI rendering."""

    commence_time: str | None
    home_team: str
    away_team: str
    status: str
    home_score: int | None = None
    away_score: int | None = None
    home_pregame_moneyline: float | None = None
    away_pregame_moneyline: float | None = None


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
            "cbb db init only supports PostgreSQL because sql/schema.sql uses "
            "PostgreSQL syntax."
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


def get_team_view(
    team_name: str,
    database_url: str | None = None,
    limit: int = 5,
    now: datetime | None = None,
) -> TeamView:
    """Fetch recent completed results for one team.

    Args:
        team_name: User-provided team name lookup.
        database_url: Optional database URL override.
        limit: Maximum number of completed results to return.
        now: Optional current time override for tests.

    Returns:
        A resolved team view with results or suggestions.
    """
    engine = get_engine(database_url)
    current_time = now or datetime.now(UTC)
    window_start = current_time - timedelta(hours=UPCOMING_LOOKBACK_HOURS)
    window_end = current_time + timedelta(days=UPCOMING_LOOKAHEAD_DAYS)

    with engine.connect() as connection:
        teams = _fetch_all_teams(connection)
        resolved_team = _resolve_team_lookup(connection, team_name, teams)
        if resolved_team is None:
            return TeamView(
                team_name=None,
                scheduled_games=[],
                recent_results=[],
                suggestions=_suggest_team_names(team_name, teams),
            )

        scheduled_rows = connection.execute(
            FETCH_TEAM_SCHEDULED_GAMES_SQL,
            {
                "team_id": resolved_team.team_id,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "limit": limit,
            },
        ).mappings()
        rows = connection.execute(
            FETCH_RECENT_TEAM_RESULTS_SQL,
            {"team_id": resolved_team.team_id, "limit": limit},
        ).mappings()
        scheduled_games = [
            _build_upcoming_game_view(dict(row), current_time) for row in scheduled_rows
        ]
        recent_results = [
            TeamRecentResult(
                commence_time=_as_optional_str(row["commence_time"]),
                opponent_name=str(row["opponent_name"]),
                venue_label=str(row["venue_label"]),
                team_score=_as_optional_int(row["team_score"]),
                opponent_score=_as_optional_int(row["opponent_score"]),
                result=_as_optional_str(row["team_result"]),
            )
            for row in rows
        ]
        return TeamView(
            team_name=resolved_team.name,
            scheduled_games=scheduled_games,
            recent_results=recent_results,
            suggestions=[],
        )


def get_upcoming_games(
    database_url: str | None = None,
    *,
    limit: int = 10,
    now: datetime | None = None,
) -> list[UpcomingGameView]:
    """Fetch upcoming and in-progress games from the current time window.

    Args:
        database_url: Optional database URL override.
        limit: Maximum number of games to return.
        now: Optional current time override for tests.

    Returns:
        All in-progress games plus up to ``limit`` future upcoming games.
    """
    current_time = now or datetime.now(UTC)
    window_start = current_time - timedelta(hours=UPCOMING_LOOKBACK_HOURS)
    window_end = current_time + timedelta(days=UPCOMING_LOOKAHEAD_DAYS)
    engine = get_engine(database_url)

    with engine.connect() as connection:
        in_progress_rows = connection.execute(
            FETCH_IN_PROGRESS_GAMES_SQL,
            {
                "window_start": window_start.isoformat(),
                "current_time": current_time.isoformat(),
            },
        ).mappings()
        future_rows = connection.execute(
            FETCH_FUTURE_GAMES_SQL,
            {
                "current_time": current_time.isoformat(),
                "window_end": window_end.isoformat(),
                "limit": limit,
            },
        ).mappings()
        return [
            _build_upcoming_game_view(dict(row), current_time)
            for row in list(in_progress_rows) + list(future_rows)
        ]


def _fetch_table_counts(connection: Connection) -> list[TableCount]:
    """Fetch key table counts for summary output."""
    rows = connection.execute(
        text(
            """
            SELECT 'teams' AS name, COUNT(*) AS row_count FROM teams
            UNION ALL
            SELECT 'games' AS name, COUNT(*) AS row_count FROM games
            UNION ALL
            SELECT
                'completed_games' AS name,
                COUNT(*) AS row_count
            FROM games
            WHERE completed
            UNION ALL
            SELECT
                'upcoming_games' AS name,
                COUNT(*) AS row_count
            FROM games
            WHERE NOT completed
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


def _fetch_all_teams(connection: Connection) -> list[TeamLookup]:
    """Fetch all canonical team rows for lookup and suggestion handling."""
    rows = connection.execute(FETCH_ALL_TEAMS_SQL).mappings()
    return [
        TeamLookup(
            team_id=int(row["team_id"]),
            team_key=str(row["team_key"]),
            name=str(row["name"]),
        )
        for row in rows
    ]


def _resolve_team_lookup(
    connection: Connection,
    team_name: str,
    teams: list[TeamLookup],
) -> TeamLookup | None:
    team_key = _normalize_team_key(team_name)
    row = (
        connection.execute(
            FETCH_TEAM_BY_NAME_SQL,
            {"team_name": team_name, "team_key": team_key},
        )
        .mappings()
        .first()
    )
    if row is not None:
        return TeamLookup(
            team_id=int(row["team_id"]),
            team_key=str(row["team_key"]),
            name=str(row["name"]),
        )

    if _has_table(connection, "team_aliases"):
        alias_row = (
            connection.execute(
                FETCH_TEAM_BY_ALIAS_SQL,
                {"team_name": team_name, "team_key": team_key},
            )
            .mappings()
            .first()
        )
        if alias_row is not None:
            return TeamLookup(
                team_id=int(alias_row["team_id"]),
                team_key=str(alias_row["team_key"]),
                name=str(alias_row["name"]),
            )

    normalized_input = _normalize_team_key(team_name)
    for team in teams:
        if team.team_key == normalized_input:
            return team
        if team.name.casefold() == team_name.casefold():
            return team
    return None


def _suggest_team_names(team_name: str, teams: list[TeamLookup]) -> list[str]:
    """Return likely team-name suggestions for a failed lookup."""
    input_name = team_name.casefold().strip()
    input_key = _normalize_team_key(team_name)
    ranked_matches: list[tuple[int, float, str]] = []

    for team in teams:
        contains_score = 0
        if input_name and input_name in team.name.casefold():
            contains_score += 2
        if input_key and input_key in team.team_key:
            contains_score += 2
        similarity = max(
            SequenceMatcher(None, input_name, team.name.casefold()).ratio(),
            SequenceMatcher(None, input_key, team.team_key).ratio(),
        )
        if contains_score > 0 or similarity >= 0.45:
            ranked_matches.append((contains_score, similarity, team.name))

    ranked_matches.sort(key=lambda item: (-item[0], -item[1], item[2]))
    suggestions: list[str] = []
    for _, _, suggestion in ranked_matches:
        if suggestion not in suggestions:
            suggestions.append(suggestion)
        if len(suggestions) == 5:
            break
    return suggestions


def _build_upcoming_game_view(
    row: dict[str, object],
    current_time: datetime,
) -> UpcomingGameView:
    """Build one upcoming or in-progress game view from a DB row."""
    return UpcomingGameView(
        commence_time=_as_optional_str(row["commence_time"]),
        home_team=str(row["home_team"]),
        away_team=str(row["away_team"]),
        status=_derive_upcoming_status(row["commence_time"], current_time),
        home_score=_as_optional_int(row["home_score"]),
        away_score=_as_optional_int(row["away_score"]),
        home_pregame_moneyline=_as_optional_float(row["home_pregame_moneyline"]),
        away_pregame_moneyline=_as_optional_float(row["away_pregame_moneyline"]),
    )


def _derive_upcoming_status(value: object, current_time: datetime) -> str:
    commence_time = _as_optional_datetime(value)
    if commence_time is None:
        return "upcoming"
    if commence_time <= current_time:
        return "in_progress"
    return "upcoming"


def _has_table(connection: Connection, table_name: str) -> bool:
    """Return whether the current database has a named table."""
    return inspect(connection).has_table(table_name)


def _as_optional_str(value: object) -> str | None:
    """Convert a scalar value to string while preserving nulls."""
    if value is None:
        return None
    return str(value)


def _as_optional_datetime(value: object) -> datetime | None:
    """Convert a scalar value to a timezone-aware datetime when present."""
    string_value = _as_optional_str(value)
    if string_value is None:
        return None
    return _parse_datetime(string_value)


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


def _parse_datetime(value: str) -> datetime:
    """Parse an ISO-like datetime string into an aware datetime."""
    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value


def _normalize_team_key(team_name: str) -> str:
    """Normalize a team name into a stable slug key."""
    normalized = (
        unicodedata.normalize("NFKD", team_name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    team_key = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    if not team_key:
        raise ValueError(f"Could not derive team key from {team_name!r}")
    return team_key
