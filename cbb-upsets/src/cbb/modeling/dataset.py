"""Database queries for modeling datasets and prediction candidates."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from cbb.db import get_engine
from cbb.ingest.utils import parse_timestamp

BOOKMAKER_RANK_SQL = """
CASE odds.bookmaker_key
    WHEN 'draftkings' THEN 0
    WHEN 'fanduel' THEN 1
    WHEN 'betmgm' THEN 2
    ELSE 3
END
"""
PREDICTION_LOOKAHEAD_DAYS = 7


FETCH_AVAILABLE_SEASONS_SQL = text(
    """
    SELECT DISTINCT season
    FROM games
    WHERE completed
    ORDER BY season
    """
)

FETCH_COMPLETED_GAMES_SQL = text(
    f"""
    SELECT
        g.game_id,
        g.season,
        CAST(g.date AS TEXT) AS game_date,
        CAST(g.commence_time AS TEXT) AS commence_time,
        g.completed,
        g.home_score,
        g.away_score,
        home_team.team_id AS home_team_id,
        home_team.name AS home_team_name,
        away_team.team_id AS away_team_id,
        away_team.name AS away_team_name,
        (
            SELECT odds.team1_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS home_h2h_price,
        (
            SELECT odds.team2_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS away_h2h_price,
        (
            SELECT odds.team1_point
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS home_spread_line,
        (
            SELECT odds.team2_point
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS away_spread_line,
        (
            SELECT odds.team1_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS home_spread_price,
        (
            SELECT odds.team2_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS away_spread_price,
        (
            SELECT odds.total_points
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'totals'
              AND odds.captured_at <= g.commence_time
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS total_points
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE g.completed
      AND g.commence_time IS NOT NULL
      AND g.season <= :max_season
    ORDER BY g.commence_time ASC, g.game_id ASC
    """
)

FETCH_UPCOMING_GAMES_SQL = text(
    f"""
    SELECT
        g.game_id,
        g.season,
        CAST(g.date AS TEXT) AS game_date,
        CAST(g.commence_time AS TEXT) AS commence_time,
        g.completed,
        g.home_score,
        g.away_score,
        home_team.team_id AS home_team_id,
        home_team.name AS home_team_name,
        away_team.team_id AS away_team_id,
        away_team.name AS away_team_name,
        (
            SELECT odds.team1_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= :line_cutoff
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS home_h2h_price,
        (
            SELECT odds.team2_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'h2h'
              AND odds.captured_at <= :line_cutoff
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS away_h2h_price,
        (
            SELECT odds.team1_point
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= :line_cutoff
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS home_spread_line,
        (
            SELECT odds.team2_point
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= :line_cutoff
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS away_spread_line,
        (
            SELECT odds.team1_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= :line_cutoff
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS home_spread_price,
        (
            SELECT odds.team2_price
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'spreads'
              AND odds.captured_at <= :line_cutoff
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS away_spread_price,
        (
            SELECT odds.total_points
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = 'totals'
              AND odds.captured_at <= :line_cutoff
            ORDER BY odds.is_closing_line DESC,
                     odds.captured_at DESC,
                     {BOOKMAKER_RANK_SQL}
            LIMIT 1
        ) AS total_points
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE NOT g.completed
      AND g.commence_time IS NOT NULL
      AND g.commence_time > :line_cutoff
      AND g.commence_time <= :window_end
    ORDER BY g.commence_time ASC, g.game_id ASC
    """
)


@dataclass(frozen=True)
class GameOddsRecord:
    """One game row with the preferred stored betting lines."""

    game_id: int
    season: int
    game_date: str
    commence_time: datetime
    completed: bool
    home_score: int | None
    away_score: int | None
    home_team_id: int
    home_team_name: str
    away_team_id: int
    away_team_name: str
    home_h2h_price: float | None
    away_h2h_price: float | None
    home_spread_line: float | None
    away_spread_line: float | None
    home_spread_price: float | None
    away_spread_price: float | None
    total_points: float | None


def get_available_seasons(database_url: str | None = None) -> list[int]:
    """Return all loaded seasons in the database."""
    engine = get_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(FETCH_AVAILABLE_SEASONS_SQL).scalars().all()
    return [int(value) for value in rows]


def load_completed_game_records(
    *,
    max_season: int,
    database_url: str | None = None,
) -> list[GameOddsRecord]:
    """Load completed games and preferred pregame lines up to one season."""
    engine = get_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            FETCH_COMPLETED_GAMES_SQL,
            {"max_season": max_season},
        ).mappings()
        return [_build_game_record(dict(row)) for row in rows]


def load_upcoming_game_records(
    *,
    database_url: str | None = None,
    now: datetime | None = None,
) -> list[GameOddsRecord]:
    """Load upcoming games with the latest currently available lines."""
    current_time = now or datetime.now(UTC)
    window_end = current_time + timedelta(days=PREDICTION_LOOKAHEAD_DAYS)
    engine = get_engine(database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            FETCH_UPCOMING_GAMES_SQL,
            {
                "line_cutoff": current_time.isoformat(),
                "window_end": window_end.isoformat(),
            },
        ).mappings()
        return [_build_game_record(dict(row)) for row in rows]


def _build_game_record(row: Mapping[str, object]) -> GameOddsRecord:
    return GameOddsRecord(
        game_id=_required_int(row["game_id"]),
        season=_required_int(row["season"]),
        game_date=str(row["game_date"]),
        commence_time=parse_timestamp(str(row["commence_time"])),
        completed=bool(row["completed"]),
        home_score=_optional_int(row["home_score"]),
        away_score=_optional_int(row["away_score"]),
        home_team_id=_required_int(row["home_team_id"]),
        home_team_name=str(row["home_team_name"]),
        away_team_id=_required_int(row["away_team_id"]),
        away_team_name=str(row["away_team_name"]),
        home_h2h_price=_optional_float(row["home_h2h_price"]),
        away_h2h_price=_optional_float(row["away_h2h_price"]),
        home_spread_line=_optional_float(row["home_spread_line"]),
        away_spread_line=_optional_float(row["away_spread_line"]),
        home_spread_price=_optional_float(row["home_spread_price"]),
        away_spread_price=_optional_float(row["away_spread_price"]),
        total_points=_optional_float(row["total_points"]),
    )


def _required_int(value: object) -> int:
    parsed_value = _optional_int(value)
    if parsed_value is None:
        raise TypeError("Expected required int-compatible value, got None")
    return parsed_value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (Decimal, int, float, str)):
        return int(value)
    raise TypeError(f"Expected int-compatible value, got {type(value).__name__}")


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (Decimal, int, float, str)):
        return float(value)
    raise TypeError(f"Expected float-compatible value, got {type(value).__name__}")
