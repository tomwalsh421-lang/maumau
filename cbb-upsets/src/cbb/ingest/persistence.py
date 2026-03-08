"""Database persistence helpers shared by ingest workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import orjson
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from cbb.ingest.utils import (
    parse_timestamp_or_none,
    to_float_or_none,
)
from cbb.team_catalog import TeamCatalog, resolve_team_id

GameUpsertValue = str | int | bool | None
MarketPayload = Mapping[str, object]
BookmakerPayload = Mapping[str, object]


UPSERT_GAME_SQL = text(
    """
    INSERT INTO games (
        season,
        date,
        commence_time,
        team1_id,
        team2_id,
        round,
        source_event_id,
        sport_key,
        sport_title,
        result,
        completed,
        home_score,
        away_score,
        last_score_update
    )
    VALUES (
        :season,
        :date,
        :commence_time,
        :team1_id,
        :team2_id,
        :round,
        :source_event_id,
        :sport_key,
        :sport_title,
        :result,
        :completed,
        :home_score,
        :away_score,
        :last_score_update
    )
    ON CONFLICT (season, date, team1_id, team2_id) DO UPDATE SET
        season = excluded.season,
        date = excluded.date,
        commence_time = excluded.commence_time,
        team1_id = excluded.team1_id,
        team2_id = excluded.team2_id,
        round = excluded.round,
        source_event_id = excluded.source_event_id,
        sport_key = excluded.sport_key,
        sport_title = excluded.sport_title,
        result = excluded.result,
        completed = excluded.completed,
        home_score = excluded.home_score,
        away_score = excluded.away_score,
        last_score_update = excluded.last_score_update
    RETURNING game_id
    """
)

FETCH_EXISTING_GAME_STATE_SQL = text(
    """
    SELECT
        source_event_id,
        completed,
        result,
        home_score,
        away_score,
        CAST(last_score_update AS TEXT) AS last_score_update
    FROM games
    WHERE season = :season
      AND date = :date
      AND team1_id = :team1_id
      AND team2_id = :team2_id
    """
)

UPSERT_ODDS_SNAPSHOT_SQL = text(
    """
    INSERT INTO odds_snapshots (
        game_id,
        bookmaker_key,
        bookmaker_title,
        market_key,
        captured_at,
        is_closing_line,
        team1_price,
        team2_price,
        team1_point,
        team2_point,
        over_price,
        under_price,
        total_points,
        payload
    )
    VALUES (
        :game_id,
        :bookmaker_key,
        :bookmaker_title,
        :market_key,
        :captured_at,
        :is_closing_line,
        :team1_price,
        :team2_price,
        :team1_point,
        :team2_point,
        :over_price,
        :under_price,
        :total_points,
        :payload
    )
    ON CONFLICT (game_id, bookmaker_key, market_key, captured_at) DO UPDATE SET
        bookmaker_title = excluded.bookmaker_title,
        is_closing_line = odds_snapshots.is_closing_line OR excluded.is_closing_line,
        team1_price = excluded.team1_price,
        team2_price = excluded.team2_price,
        team1_point = excluded.team1_point,
        team2_point = excluded.team2_point,
        over_price = excluded.over_price,
        under_price = excluded.under_price,
        total_points = excluded.total_points,
        payload = excluded.payload
    """
)

CREATE_HISTORICAL_ODDS_CHECKPOINTS_SQL = text(
    """
    CREATE TABLE IF NOT EXISTS historical_odds_checkpoints (
        historical_odds_checkpoint_id SERIAL PRIMARY KEY,
        source_name VARCHAR(64) NOT NULL,
        sport_key VARCHAR(64) NOT NULL,
        market_key VARCHAR(64) NOT NULL,
        filters_key VARCHAR(128) NOT NULL,
        snapshot_time TIMESTAMP WITH TIME ZONE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_name, sport_key, market_key, filters_key, snapshot_time)
    )
    """
)

ADD_IS_CLOSING_LINE_COLUMN_SQL = text(
    """
    ALTER TABLE odds_snapshots
    ADD COLUMN is_closing_line BOOLEAN NOT NULL DEFAULT FALSE
    """
)

ODDS_NUMERIC_TARGET_PRECISION = 12
ODDS_NUMERIC_TARGET_SCALE = 4
ODDS_NUMERIC_COLUMNS = (
    "team1_price",
    "team2_price",
    "team1_point",
    "team2_point",
    "over_price",
    "under_price",
    "total_points",
)


@dataclass(frozen=True)
class PreparedGame:
    """Normalized game payload ready for database upsert."""

    home_team_name: str
    away_team_name: str
    payload: dict[str, GameUpsertValue]


@dataclass(frozen=True)
class ExistingGameState:
    """Existing persisted game state used for ingest conflict decisions."""

    source_event_id: str | None
    completed: bool
    result: str | None
    home_score: int | None
    away_score: int | None
    last_score_update: str | None


def upsert_prepared_game(
    connection: Connection,
    prepared_game: PreparedGame,
    *,
    team_catalog: TeamCatalog,
    team_ids_by_key: Mapping[str, int],
    preserve_existing_completed: bool = False,
) -> int | None:
    """Resolve teams and upsert a prepared game row.

    Args:
        connection: Open SQLAlchemy connection.
        prepared_game: Normalized game payload with team names.
        team_catalog: Canonical D1 team catalog.
        team_ids_by_key: Canonical team-key to DB team-id mapping.

    Returns:
        The database game ID, or ``None`` when either team is not canonical D1.
    """
    home_team_id = resolve_team_id(
        connection,
        team_name=prepared_game.home_team_name,
        catalog=team_catalog,
        team_ids_by_key=team_ids_by_key,
    )
    away_team_id = resolve_team_id(
        connection,
        team_name=prepared_game.away_team_name,
        catalog=team_catalog,
        team_ids_by_key=team_ids_by_key,
    )
    if home_team_id is None or away_team_id is None:
        return None

    game_payload = {
        **prepared_game.payload,
        "team1_id": home_team_id,
        "team2_id": away_team_id,
    }
    existing_game_state = _fetch_existing_game_state(
        connection,
        game_payload,
    )
    if (
        preserve_existing_completed
        and existing_game_state is not None
        and existing_game_state.completed
        and existing_game_state.home_score is not None
        and existing_game_state.away_score is not None
    ):
        game_payload.update(
            {
                "result": existing_game_state.result,
                "completed": True,
                "home_score": existing_game_state.home_score,
                "away_score": existing_game_state.away_score,
                "last_score_update": existing_game_state.last_score_update,
            }
        )
    game_payload["source_event_id"] = _select_source_event_id(
        (
            existing_game_state.source_event_id
            if existing_game_state is not None
            else None
        ),
        prepared_game.payload.get("source_event_id"),
    )
    return int(connection.execute(UPSERT_GAME_SQL, game_payload).scalar_one())


def upsert_odds_snapshots(
    connection: Connection,
    game_id: int,
    prepared_game: PreparedGame,
    bookmakers: Sequence[BookmakerPayload],
    is_closing_line: bool = False,
) -> int:
    """Persist bookmaker market snapshots for a game.

    Args:
        connection: Open SQLAlchemy connection.
        game_id: Database ID for the game.
        prepared_game: Normalized game metadata.
        bookmakers: Bookmaker payloads from the odds endpoint.
        is_closing_line: Whether the inserted rows represent a closing-line snapshot.

    Returns:
        The number of market snapshots upserted.
    """
    inserted = 0
    for bookmaker in bookmakers:
        for market in _as_market_list(bookmaker.get("markets")):
            fields = _extract_market_fields(
                market=market,
                home_team_name=prepared_game.home_team_name,
                away_team_name=prepared_game.away_team_name,
            )
            connection.execute(
                UPSERT_ODDS_SNAPSHOT_SQL,
                {
                    "game_id": game_id,
                    "bookmaker_key": _required_string(bookmaker, "key"),
                    "bookmaker_title": _required_string(bookmaker, "title"),
                    "market_key": _required_string(market, "key"),
                    "captured_at": (
                        parse_timestamp_or_none(market.get("last_update"))
                        or parse_timestamp_or_none(bookmaker.get("last_update"))
                        or datetime.now(UTC).isoformat()
                    ),
                    "is_closing_line": is_closing_line,
                    "team1_price": fields["team1_price"],
                    "team2_price": fields["team2_price"],
                    "team1_point": fields["team1_point"],
                    "team2_point": fields["team2_point"],
                    "over_price": fields["over_price"],
                    "under_price": fields["under_price"],
                    "total_points": fields["total_points"],
                    "payload": orjson.dumps(
                        dict(market),
                        option=orjson.OPT_SORT_KEYS,
                    ).decode("utf-8"),
                },
            )
            inserted += 1

    return inserted


def ensure_odds_schema_extensions(connection: Connection) -> None:
    """Ensure odds-related schema extensions required by ingest workflows exist.

    Args:
        connection: Open SQLAlchemy connection.
    """
    inspector = inspect(connection)
    odds_snapshot_columns = {
        column["name"] for column in inspector.get_columns("odds_snapshots")
    }
    if "is_closing_line" not in odds_snapshot_columns:
        connection.execute(ADD_IS_CLOSING_LINE_COLUMN_SQL)

    if connection.dialect.name == "postgresql":
        _ensure_postgres_odds_numeric_precision(connection, inspector)

    connection.execute(CREATE_HISTORICAL_ODDS_CHECKPOINTS_SQL)


def _ensure_postgres_odds_numeric_precision(
    connection: Connection,
    inspector,
) -> None:
    for column in inspector.get_columns("odds_snapshots"):
        column_name = column["name"]
        if column_name not in ODDS_NUMERIC_COLUMNS:
            continue

        column_type = column["type"]
        precision = getattr(column_type, "precision", None)
        scale = getattr(column_type, "scale", None)
        if precision is None or scale is None:
            continue
        if (
            precision >= ODDS_NUMERIC_TARGET_PRECISION
            and scale == ODDS_NUMERIC_TARGET_SCALE
        ):
            continue

        connection.execute(
            text(
                "ALTER TABLE odds_snapshots "
                f"ALTER COLUMN {column_name} TYPE "
                f"NUMERIC({ODDS_NUMERIC_TARGET_PRECISION},"
                f"{ODDS_NUMERIC_TARGET_SCALE})"
            )
        )


def _fetch_existing_game_state(
    connection: Connection,
    game_payload: Mapping[str, GameUpsertValue],
) -> ExistingGameState | None:
    row = connection.execute(
        FETCH_EXISTING_GAME_STATE_SQL,
        {
            "season": game_payload["season"],
            "date": game_payload["date"],
            "team1_id": game_payload["team1_id"],
            "team2_id": game_payload["team2_id"],
        },
    ).mappings().first()
    if row is None:
        return None
    source_event_id = row.get("source_event_id")
    return ExistingGameState(
        source_event_id=(
            str(source_event_id) if source_event_id is not None else None
        ),
        completed=bool(row.get("completed")),
        result=(str(row["result"]) if row.get("result") is not None else None),
        home_score=_as_optional_int(row.get("home_score")),
        away_score=_as_optional_int(row.get("away_score")),
        last_score_update=(
            str(row["last_score_update"])
            if row.get("last_score_update") is not None
            else None
        ),
    )


def _select_source_event_id(
    existing_source_event_id: str | None,
    incoming_source_event_id: GameUpsertValue,
) -> str | None:
    incoming_value = _coerce_source_event_id(incoming_source_event_id)
    if existing_source_event_id is None:
        return incoming_value
    if incoming_value is None:
        return existing_source_event_id
    if _looks_like_espn_event_id(incoming_value):
        return incoming_value
    if _looks_like_espn_event_id(existing_source_event_id):
        return existing_source_event_id
    return existing_source_event_id


def _coerce_source_event_id(value: GameUpsertValue) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError("Expected source_event_id to be a string or None")


def _looks_like_espn_event_id(value: str) -> bool:
    return value.isdigit()


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"Expected int-compatible value, got {type(value).__name__}")


def _extract_market_fields(
    market: MarketPayload,
    home_team_name: str,
    away_team_name: str,
) -> dict[str, float | None]:
    outcomes = _as_market_list(market.get("outcomes"))
    fields: dict[str, float | None] = {
        "team1_price": None,
        "team2_price": None,
        "team1_point": None,
        "team2_point": None,
        "over_price": None,
        "under_price": None,
        "total_points": None,
    }

    market_key = market.get("key")
    if market_key in {"h2h", "spreads"}:
        for outcome in outcomes:
            outcome_name = outcome.get("name")
            if outcome_name == home_team_name:
                fields["team1_price"] = to_float_or_none(outcome.get("price"))
                fields["team1_point"] = to_float_or_none(outcome.get("point"))
            elif outcome_name == away_team_name:
                fields["team2_price"] = to_float_or_none(outcome.get("price"))
                fields["team2_point"] = to_float_or_none(outcome.get("point"))

    if market_key == "totals":
        for outcome in outcomes:
            outcome_name = str(outcome.get("name", "")).lower()
            if outcome_name == "over":
                fields["over_price"] = to_float_or_none(outcome.get("price"))
                fields["total_points"] = to_float_or_none(outcome.get("point"))
            elif outcome_name == "under":
                fields["under_price"] = to_float_or_none(outcome.get("price"))
                fields["total_points"] = fields["total_points"] or to_float_or_none(
                    outcome.get("point")
                )

    return fields


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected {key!r} to be a string")


def _as_market_list(value: object) -> list[MarketPayload]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []
