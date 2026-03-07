"""Database persistence helpers shared by ingest workflows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import orjson
from sqlalchemy import text
from sqlalchemy.engine import Connection

from cbb.ingest.utils import (
    normalize_team_key,
    parse_timestamp_or_none,
    to_float_or_none,
)


GameUpsertValue = str | int | bool | None
MarketPayload = Mapping[str, object]
BookmakerPayload = Mapping[str, object]


UPSERT_TEAM_SQL = text(
    """
    INSERT INTO teams (team_key, name)
    VALUES (:team_key, :name)
    ON CONFLICT (team_key) DO UPDATE SET
        name = excluded.name
    RETURNING team_id
    """
)

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
        source_event_id = COALESCE(games.source_event_id, excluded.source_event_id),
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

UPSERT_ODDS_SNAPSHOT_SQL = text(
    """
    INSERT INTO odds_snapshots (
        game_id,
        bookmaker_key,
        bookmaker_title,
        market_key,
        captured_at,
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


@dataclass(frozen=True)
class PreparedGame:
    """Normalized game payload ready for database upsert."""

    home_team_name: str
    away_team_name: str
    payload: dict[str, GameUpsertValue]


def upsert_prepared_game(connection: Connection, prepared_game: PreparedGame) -> int:
    """Resolve teams and upsert a prepared game row.

    Args:
        connection: Open SQLAlchemy connection.
        prepared_game: Normalized game payload with team names.

    Returns:
        The database game ID.
    """
    team_ids = {
        team_name: _upsert_team(connection, team_name)
        for team_name in _ordered_team_names(prepared_game)
    }
    game_payload = {
        **prepared_game.payload,
        "team1_id": team_ids[prepared_game.home_team_name],
        "team2_id": team_ids[prepared_game.away_team_name],
    }
    return int(connection.execute(UPSERT_GAME_SQL, game_payload).scalar_one())


def upsert_odds_snapshots(
    connection: Connection,
    game_id: int,
    prepared_game: PreparedGame,
    bookmakers: Sequence[BookmakerPayload],
) -> int:
    """Persist bookmaker market snapshots for a game.

    Args:
        connection: Open SQLAlchemy connection.
        game_id: Database ID for the game.
        prepared_game: Normalized game metadata.
        bookmakers: Bookmaker payloads from the odds endpoint.

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


def _upsert_team(connection: Connection, team_name: str) -> int:
    team_key = normalize_team_key(team_name)
    return int(
        connection.execute(
            UPSERT_TEAM_SQL,
            {"team_key": team_key, "name": team_name},
        ).scalar_one()
    )


def _ordered_team_names(prepared_game: PreparedGame) -> list[str]:
    unique_team_names = {
        prepared_game.home_team_name,
        prepared_game.away_team_name,
    }
    return sorted(unique_team_names, key=normalize_team_key)


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
