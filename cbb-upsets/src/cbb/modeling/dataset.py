"""Database queries for modeling datasets and prediction candidates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, RowMapping
from sqlalchemy.sql.elements import TextClause

from cbb.db import get_engine
from cbb.ingest.utils import parse_timestamp

BOOKMAKER_RANK = {
    "draftkings": 0,
    "fanduel": 1,
    "betmgm": 2,
}
PREDICTION_LOOKAHEAD_DAYS = 7


FETCH_AVAILABLE_SEASONS_SQL = text(
    """
    SELECT DISTINCT season
    FROM games
    WHERE completed
    ORDER BY season
    """
)

FETCH_GAMES_SQL_TEMPLATE = """
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
        {home_conference_key_sql} AS home_conference_key,
        {home_conference_name_sql} AS home_conference_name,
        away_team.team_id AS away_team_id,
        away_team.name AS away_team_name,
        {away_conference_key_sql} AS away_conference_key,
        {away_conference_name_sql} AS away_conference_name
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE {completed_clause}
      AND g.commence_time IS NOT NULL
      AND {window_clause}
    ORDER BY g.commence_time ASC, g.game_id ASC
"""

FETCH_COMPLETED_ODDS_SNAPSHOTS_SQL = text(
    """
    SELECT
        odds.game_id,
        odds.bookmaker_key,
        odds.market_key,
        CAST(odds.captured_at AS TEXT) AS captured_at,
        odds.is_closing_line,
        odds.team1_price,
        odds.team2_price,
        odds.team1_point,
        odds.team2_point,
        odds.total_points
    FROM odds_snapshots AS odds
    JOIN games AS g ON g.game_id = odds.game_id
    WHERE g.completed
      AND g.commence_time IS NOT NULL
      AND g.season <= :max_season
      AND odds.captured_at <= g.commence_time
    ORDER BY odds.game_id ASC,
             odds.market_key ASC,
             odds.bookmaker_key ASC,
             odds.captured_at ASC
    """
)

FETCH_UPCOMING_ODDS_SNAPSHOTS_SQL = text(
    """
    SELECT
        odds.game_id,
        odds.bookmaker_key,
        odds.market_key,
        CAST(odds.captured_at AS TEXT) AS captured_at,
        odds.is_closing_line,
        odds.team1_price,
        odds.team2_price,
        odds.team1_point,
        odds.team2_point,
        odds.total_points
    FROM odds_snapshots AS odds
    JOIN games AS g ON g.game_id = odds.game_id
    WHERE NOT g.completed
      AND g.commence_time IS NOT NULL
      AND g.commence_time > :line_cutoff
      AND g.commence_time <= :window_end
      AND odds.captured_at <= :line_cutoff
    ORDER BY odds.game_id ASC,
             odds.market_key ASC,
             odds.bookmaker_key ASC,
             odds.captured_at ASC
    """
)


@dataclass(frozen=True)
class MarketSnapshotAggregate:
    """Opening or closing bookmaker consensus for one market."""

    bookmaker_count: int
    team1_price: float | None
    team2_price: float | None
    team1_point: float | None
    team2_point: float | None
    total_points: float | None
    team1_implied_probability: float | None
    team2_implied_probability: float | None
    team1_probability_range: float | None
    team2_probability_range: float | None
    team1_point_range: float | None
    team2_point_range: float | None
    total_points_range: float | None


@dataclass(frozen=True)
class GameOddsRecord:
    """One game row with preferred pregame lines and bookmaker aggregates."""

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
    h2h_open: MarketSnapshotAggregate | None
    h2h_close: MarketSnapshotAggregate | None
    spread_open: MarketSnapshotAggregate | None
    spread_close: MarketSnapshotAggregate | None
    total_open: MarketSnapshotAggregate | None
    total_close: MarketSnapshotAggregate | None
    home_conference_key: str | None = None
    home_conference_name: str | None = None
    away_conference_key: str | None = None
    away_conference_name: str | None = None
    observation_time: datetime | None = None
    snapshots: tuple[OddsSnapshotRecord, ...] = ()
    current_h2h_quotes: tuple[OddsSnapshotRecord, ...] = ()
    current_spread_quotes: tuple[OddsSnapshotRecord, ...] = ()


@dataclass(frozen=True)
class OddsSnapshotRecord:
    """One stored bookmaker snapshot used to build market aggregates."""

    game_id: int
    bookmaker_key: str
    market_key: str
    captured_at: datetime
    is_closing_line: bool
    team1_price: float | None
    team2_price: float | None
    team1_point: float | None
    team2_point: float | None
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
    """Load completed games and bookmaker-derived pregame markets."""
    engine = get_engine(database_url)
    with engine.connect() as connection:
        completed_games_sql = _games_query_sql(
            connection,
            completed=True,
        )
        game_rows = (
            connection.execute(
                completed_games_sql,
                {"max_season": max_season},
            )
            .mappings()
            .all()
        )
        snapshot_rows = (
            connection.execute(
                FETCH_COMPLETED_ODDS_SNAPSHOTS_SQL,
                {"max_season": max_season},
            )
            .mappings()
            .all()
        )
    return _build_game_records(
        game_rows=game_rows,
        snapshot_rows=snapshot_rows,
        observation_time=None,
    )


def load_upcoming_game_records(
    *,
    database_url: str | None = None,
    now: datetime | None = None,
) -> list[GameOddsRecord]:
    """Load upcoming games with the latest currently available markets."""
    current_time = now or datetime.now(UTC)
    window_end = current_time + timedelta(days=PREDICTION_LOOKAHEAD_DAYS)
    engine = get_engine(database_url)
    with engine.connect() as connection:
        upcoming_games_sql = _games_query_sql(
            connection,
            completed=False,
        )
        parameters = {
            "line_cutoff": current_time.isoformat(),
            "window_end": window_end.isoformat(),
        }
        game_rows = (
            connection.execute(
                upcoming_games_sql,
                parameters,
            )
            .mappings()
            .all()
        )
        snapshot_rows = (
            connection.execute(
                FETCH_UPCOMING_ODDS_SNAPSHOTS_SQL,
                parameters,
            )
            .mappings()
            .all()
        )
    return _build_game_records(
        game_rows=game_rows,
        snapshot_rows=snapshot_rows,
        observation_time=current_time,
    )


def _games_query_sql(
    connection: Connection,
    *,
    completed: bool,
) -> TextClause:
    """Build the game query with backward-compatible team conference columns."""
    team_columns = {
        str(column["name"]) for column in inspect(connection).get_columns("teams")
    }
    has_conference_key = "conference_key" in team_columns
    has_conference_name = "conference_name" in team_columns
    return text(
        FETCH_GAMES_SQL_TEMPLATE.format(
            home_conference_key_sql=(
                "home_team.conference_key"
                if has_conference_key
                else "CAST(NULL AS TEXT)"
            ),
            home_conference_name_sql=(
                "home_team.conference_name"
                if has_conference_name
                else "CAST(NULL AS TEXT)"
            ),
            away_conference_key_sql=(
                "away_team.conference_key"
                if has_conference_key
                else "CAST(NULL AS TEXT)"
            ),
            away_conference_name_sql=(
                "away_team.conference_name"
                if has_conference_name
                else "CAST(NULL AS TEXT)"
            ),
            completed_clause="g.completed" if completed else "NOT g.completed",
            window_clause=(
                "g.season <= :max_season"
                if completed
                else "g.commence_time > :line_cutoff\n"
                "      AND g.commence_time <= :window_end"
            ),
        )
    )


def derive_game_record_at_observation_time(
    record: GameOddsRecord,
    *,
    observation_time: datetime,
) -> GameOddsRecord:
    """Rebuild one game record using only snapshots available by observation_time."""
    available_snapshots = [
        snapshot
        for snapshot in record.snapshots
        if snapshot.captured_at <= observation_time
    ]
    return _build_game_record_from_values(
        game_id=record.game_id,
        season=record.season,
        game_date=record.game_date,
        commence_time=record.commence_time,
        completed=record.completed,
        home_score=record.home_score,
        away_score=record.away_score,
        home_team_id=record.home_team_id,
        home_team_name=record.home_team_name,
        away_team_id=record.away_team_id,
        away_team_name=record.away_team_name,
        home_conference_key=record.home_conference_key,
        home_conference_name=record.home_conference_name,
        away_conference_key=record.away_conference_key,
        away_conference_name=record.away_conference_name,
        snapshots=available_snapshots,
        observation_time=observation_time,
        full_snapshot_history=record.snapshots,
    )


def _build_game_records(
    *,
    game_rows: Sequence[RowMapping],
    snapshot_rows: Sequence[RowMapping],
    observation_time: datetime | None,
) -> list[GameOddsRecord]:
    snapshots_by_game: dict[int, list[OddsSnapshotRecord]] = defaultdict(list)
    for snapshot_row in snapshot_rows:
        snapshot = _build_snapshot_record(snapshot_row)
        snapshots_by_game[snapshot.game_id].append(snapshot)
    return [
        _build_game_record(
            row=row,
            snapshots=snapshots_by_game.get(_required_int(row["game_id"]), []),
            observation_time=observation_time,
        )
        for row in game_rows
    ]


def _build_game_record(
    *,
    row: RowMapping,
    snapshots: list[OddsSnapshotRecord],
    observation_time: datetime | None,
) -> GameOddsRecord:
    commence_time = parse_timestamp(str(row["commence_time"]))
    effective_observation_time = observation_time or commence_time
    available_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.captured_at <= effective_observation_time
    ]
    return _build_game_record_from_values(
        game_id=_required_int(row["game_id"]),
        season=_required_int(row["season"]),
        game_date=str(row["game_date"]),
        commence_time=commence_time,
        completed=bool(row["completed"]),
        home_score=_optional_int(row["home_score"]),
        away_score=_optional_int(row["away_score"]),
        home_team_id=_required_int(row["home_team_id"]),
        home_team_name=str(row["home_team_name"]),
        away_team_id=_required_int(row["away_team_id"]),
        away_team_name=str(row["away_team_name"]),
        home_conference_key=_optional_string(row["home_conference_key"]),
        home_conference_name=_optional_string(row["home_conference_name"]),
        away_conference_key=_optional_string(row["away_conference_key"]),
        away_conference_name=_optional_string(row["away_conference_name"]),
        snapshots=available_snapshots,
        observation_time=effective_observation_time,
        full_snapshot_history=tuple(snapshots),
    )


def _build_game_record_from_values(
    *,
    game_id: int,
    season: int,
    game_date: str,
    commence_time: datetime,
    completed: bool,
    home_score: int | None,
    away_score: int | None,
    home_team_id: int,
    home_team_name: str,
    away_team_id: int,
    away_team_name: str,
    home_conference_key: str | None,
    home_conference_name: str | None,
    away_conference_key: str | None,
    away_conference_name: str | None,
    snapshots: Sequence[OddsSnapshotRecord],
    observation_time: datetime,
    full_snapshot_history: Sequence[OddsSnapshotRecord],
) -> GameOddsRecord:
    snapshots_by_market: dict[str, list[OddsSnapshotRecord]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_market[snapshot.market_key].append(snapshot)

    preferred_h2h = _select_preferred_snapshot(snapshots_by_market.get("h2h", []))
    preferred_spread = _select_preferred_snapshot(
        snapshots_by_market.get("spreads", [])
    )
    preferred_total = _select_preferred_snapshot(snapshots_by_market.get("totals", []))
    current_h2h_quotes = _latest_quotes_by_bookmaker(snapshots_by_market.get("h2h", []))
    current_spread_quotes = _latest_quotes_by_bookmaker(
        snapshots_by_market.get("spreads", [])
    )
    h2h_open, h2h_close = _aggregate_market_history(snapshots_by_market.get("h2h", []))
    spread_open, spread_close = _aggregate_market_history(
        snapshots_by_market.get("spreads", [])
    )
    total_open, total_close = _aggregate_market_history(
        snapshots_by_market.get("totals", [])
    )
    return GameOddsRecord(
        game_id=game_id,
        season=season,
        game_date=game_date,
        commence_time=commence_time,
        completed=completed,
        home_score=home_score,
        away_score=away_score,
        home_team_id=home_team_id,
        home_team_name=home_team_name,
        away_team_id=away_team_id,
        away_team_name=away_team_name,
        home_h2h_price=preferred_h2h.team1_price if preferred_h2h is not None else None,
        away_h2h_price=preferred_h2h.team2_price if preferred_h2h is not None else None,
        home_spread_line=(
            preferred_spread.team1_point if preferred_spread is not None else None
        ),
        away_spread_line=(
            preferred_spread.team2_point if preferred_spread is not None else None
        ),
        home_spread_price=(
            preferred_spread.team1_price if preferred_spread is not None else None
        ),
        away_spread_price=(
            preferred_spread.team2_price if preferred_spread is not None else None
        ),
        total_points=preferred_total.total_points
        if preferred_total is not None
        else None,
        h2h_open=h2h_open,
        h2h_close=h2h_close,
        spread_open=spread_open,
        spread_close=spread_close,
        total_open=total_open,
        total_close=total_close,
        home_conference_key=home_conference_key,
        home_conference_name=home_conference_name,
        away_conference_key=away_conference_key,
        away_conference_name=away_conference_name,
        observation_time=observation_time,
        snapshots=tuple(full_snapshot_history),
        current_h2h_quotes=current_h2h_quotes,
        current_spread_quotes=current_spread_quotes,
    )


def _build_snapshot_record(row: RowMapping) -> OddsSnapshotRecord:
    return OddsSnapshotRecord(
        game_id=_required_int(row["game_id"]),
        bookmaker_key=str(row["bookmaker_key"]),
        market_key=str(row["market_key"]),
        captured_at=parse_timestamp(str(row["captured_at"])),
        is_closing_line=bool(row["is_closing_line"]),
        team1_price=_optional_float(row["team1_price"]),
        team2_price=_optional_float(row["team2_price"]),
        team1_point=_optional_float(row["team1_point"]),
        team2_point=_optional_float(row["team2_point"]),
        total_points=_optional_float(row["total_points"]),
    )


def _aggregate_market_history(
    snapshots: list[OddsSnapshotRecord],
) -> tuple[MarketSnapshotAggregate | None, MarketSnapshotAggregate | None]:
    if not snapshots:
        return None, None
    snapshots_by_bookmaker: dict[str, list[OddsSnapshotRecord]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_bookmaker[snapshot.bookmaker_key].append(snapshot)
    opening_snapshots = [
        _select_opening_snapshot(bookmaker_snapshots)
        for bookmaker_snapshots in snapshots_by_bookmaker.values()
    ]
    closing_snapshots = [
        _select_latest_snapshot(bookmaker_snapshots)
        for bookmaker_snapshots in snapshots_by_bookmaker.values()
    ]
    return (
        _aggregate_snapshot_window(
            [snapshot for snapshot in opening_snapshots if snapshot is not None]
        ),
        _aggregate_snapshot_window(
            [snapshot for snapshot in closing_snapshots if snapshot is not None]
        ),
    )


def _aggregate_snapshot_window(
    snapshots: list[OddsSnapshotRecord],
) -> MarketSnapshotAggregate | None:
    if not snapshots:
        return None

    team1_prices = [
        snapshot.team1_price
        for snapshot in snapshots
        if snapshot.team1_price is not None
    ]
    team2_prices = [
        snapshot.team2_price
        for snapshot in snapshots
        if snapshot.team2_price is not None
    ]
    team1_points = [
        snapshot.team1_point
        for snapshot in snapshots
        if snapshot.team1_point is not None
    ]
    team2_points = [
        snapshot.team2_point
        for snapshot in snapshots
        if snapshot.team2_point is not None
    ]
    totals = [
        snapshot.total_points
        for snapshot in snapshots
        if snapshot.total_points is not None
    ]

    team1_probabilities: list[float] = []
    team2_probabilities: list[float] = []
    for snapshot in snapshots:
        team1_probability, team2_probability = _normalized_implied_probabilities(
            team1_price=snapshot.team1_price,
            team2_price=snapshot.team2_price,
        )
        if team1_probability is not None:
            team1_probabilities.append(team1_probability)
        if team2_probability is not None:
            team2_probabilities.append(team2_probability)

    return MarketSnapshotAggregate(
        bookmaker_count=len(snapshots),
        team1_price=_mean(team1_prices),
        team2_price=_mean(team2_prices),
        team1_point=_mean(team1_points),
        team2_point=_mean(team2_points),
        total_points=_mean(totals),
        team1_implied_probability=_mean(team1_probabilities),
        team2_implied_probability=_mean(team2_probabilities),
        team1_probability_range=_value_range(team1_probabilities),
        team2_probability_range=_value_range(team2_probabilities),
        team1_point_range=_value_range(team1_points),
        team2_point_range=_value_range(team2_points),
        total_points_range=_value_range(totals),
    )


def _select_preferred_snapshot(
    snapshots: list[OddsSnapshotRecord],
) -> OddsSnapshotRecord | None:
    if not snapshots:
        return None
    return max(
        snapshots,
        key=lambda snapshot: (
            int(snapshot.is_closing_line),
            snapshot.captured_at,
            -_bookmaker_rank(snapshot.bookmaker_key),
        ),
    )


def _select_opening_snapshot(
    snapshots: list[OddsSnapshotRecord],
) -> OddsSnapshotRecord | None:
    if not snapshots:
        return None
    return min(
        snapshots,
        key=lambda snapshot: (
            snapshot.captured_at,
            _bookmaker_rank(snapshot.bookmaker_key),
        ),
    )


def _select_latest_snapshot(
    snapshots: list[OddsSnapshotRecord],
) -> OddsSnapshotRecord | None:
    if not snapshots:
        return None
    return max(
        snapshots,
        key=lambda snapshot: (
            int(snapshot.is_closing_line),
            snapshot.captured_at,
        ),
    )


def _latest_quotes_by_bookmaker(
    snapshots: list[OddsSnapshotRecord],
) -> tuple[OddsSnapshotRecord, ...]:
    """Return one currently executable quote per bookmaker for a market."""
    if not snapshots:
        return ()
    snapshots_by_bookmaker: dict[str, list[OddsSnapshotRecord]] = defaultdict(list)
    for snapshot in snapshots:
        snapshots_by_bookmaker[snapshot.bookmaker_key].append(snapshot)
    latest_quotes = [
        _select_latest_snapshot(bookmaker_snapshots)
        for bookmaker_snapshots in snapshots_by_bookmaker.values()
    ]
    return tuple(
        sorted(
            (quote for quote in latest_quotes if quote is not None),
            key=lambda quote: (
                _bookmaker_rank(quote.bookmaker_key),
                quote.bookmaker_key,
            ),
        )
    )


def _bookmaker_rank(bookmaker_key: str) -> int:
    return BOOKMAKER_RANK.get(bookmaker_key, 3)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _value_range(values: list[float]) -> float | None:
    if not values:
        return None
    return max(values) - min(values)


def _normalized_implied_probabilities(
    *,
    team1_price: float | None,
    team2_price: float | None,
) -> tuple[float | None, float | None]:
    team1_probability = _implied_probability_from_american(team1_price)
    team2_probability = _implied_probability_from_american(team2_price)
    if team1_probability is None and team2_probability is None:
        return None, None
    if team1_probability is None:
        return None, team2_probability
    if team2_probability is None:
        return team1_probability, None
    total_probability = team1_probability + team2_probability
    if total_probability <= 0:
        return None, None
    return (
        team1_probability / total_probability,
        team2_probability / total_probability,
    )


def _implied_probability_from_american(american_price: float | None) -> float | None:
    if american_price is None:
        return None
    if american_price > 0:
        return 100.0 / (american_price + 100.0)
    if american_price < 0:
        return -american_price / (-american_price + 100.0)
    return None


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


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)
