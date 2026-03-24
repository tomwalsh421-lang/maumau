"""Database persistence helpers shared by ingest workflows."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import orjson
from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Connection

from cbb.ingest.matching import best_alias_score, build_team_aliases
from cbb.ingest.models import NcaaTournamentAvailabilityPersistenceSummary
from cbb.ingest.utils import (
    parse_timestamp,
    parse_timestamp_or_none,
    to_float_or_none,
)
from cbb.team_catalog import TeamCatalog, resolve_team_id

GameUpsertValue = str | int | bool | None
MarketPayload = Mapping[str, object]
BookmakerPayload = Mapping[str, object]
DEFAULT_GAME_CONTEXT_PAYLOAD: dict[str, GameUpsertValue] = {
    "neutral_site": None,
    "conference_competition": None,
    "season_type": None,
    "season_type_slug": None,
    "tournament_id": None,
    "event_note_headline": None,
    "venue_id": None,
    "venue_name": None,
    "venue_city": None,
    "venue_state": None,
    "venue_indoor": None,
}


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
        last_score_update,
        neutral_site,
        conference_competition,
        season_type,
        season_type_slug,
        tournament_id,
        event_note_headline,
        venue_id,
        venue_name,
        venue_city,
        venue_state,
        venue_indoor
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
        :last_score_update,
        :neutral_site,
        :conference_competition,
        :season_type,
        :season_type_slug,
        :tournament_id,
        :event_note_headline,
        :venue_id,
        :venue_name,
        :venue_city,
        :venue_state,
        :venue_indoor
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
        last_score_update = excluded.last_score_update,
        neutral_site = COALESCE(excluded.neutral_site, games.neutral_site),
        conference_competition = COALESCE(
            excluded.conference_competition,
            games.conference_competition
        ),
        season_type = COALESCE(excluded.season_type, games.season_type),
        season_type_slug = COALESCE(
            excluded.season_type_slug,
            games.season_type_slug
        ),
        tournament_id = COALESCE(excluded.tournament_id, games.tournament_id),
        event_note_headline = COALESCE(
            excluded.event_note_headline,
            games.event_note_headline
        ),
        venue_id = COALESCE(excluded.venue_id, games.venue_id),
        venue_name = COALESCE(excluded.venue_name, games.venue_name),
        venue_city = COALESCE(excluded.venue_city, games.venue_city),
        venue_state = COALESCE(excluded.venue_state, games.venue_state),
        venue_indoor = COALESCE(excluded.venue_indoor, games.venue_indoor)
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

UPSERT_NCAA_TOURNAMENT_AVAILABILITY_REPORT_SQL = text(
    """
    INSERT INTO ncaa_tournament_availability_reports (
        source_name,
        source_url,
        source_report_id,
        source_dedupe_key,
        source_content_sha256,
        reported_at,
        effective_at,
        captured_at,
        imported_at,
        game_id,
        team_id,
        linkage_status,
        linkage_notes,
        raw_team_name,
        raw_opponent_name,
        raw_matchup_label,
        payload
    )
    VALUES (
        :source_name,
        :source_url,
        :source_report_id,
        :source_dedupe_key,
        :source_content_sha256,
        :reported_at,
        :effective_at,
        :captured_at,
        COALESCE(:imported_at, CURRENT_TIMESTAMP),
        :game_id,
        :team_id,
        :linkage_status,
        :linkage_notes,
        :raw_team_name,
        :raw_opponent_name,
        :raw_matchup_label,
        :payload
    )
    ON CONFLICT (source_name, source_dedupe_key) DO UPDATE SET
        source_url = excluded.source_url,
        source_report_id = excluded.source_report_id,
        source_content_sha256 = excluded.source_content_sha256,
        reported_at = excluded.reported_at,
        effective_at = excluded.effective_at,
        captured_at = excluded.captured_at,
        imported_at = excluded.imported_at,
        game_id = excluded.game_id,
        team_id = excluded.team_id,
        linkage_status = excluded.linkage_status,
        linkage_notes = excluded.linkage_notes,
        raw_team_name = excluded.raw_team_name,
        raw_opponent_name = excluded.raw_opponent_name,
        raw_matchup_label = excluded.raw_matchup_label,
        payload = excluded.payload,
        updated_at = CURRENT_TIMESTAMP
    RETURNING availability_report_id
    """
)

UPSERT_NCAA_TOURNAMENT_AVAILABILITY_PLAYER_STATUS_SQL = text(
    """
    INSERT INTO ncaa_tournament_availability_player_statuses (
        availability_report_id,
        source_item_key,
        source_content_sha256,
        row_order,
        source_player_id,
        team_id,
        raw_team_name,
        player_name,
        player_name_key,
        status_key,
        status_label,
        status_detail,
        source_updated_at,
        expected_return,
        payload
    )
    VALUES (
        :availability_report_id,
        :source_item_key,
        :source_content_sha256,
        :row_order,
        :source_player_id,
        :team_id,
        :raw_team_name,
        :player_name,
        :player_name_key,
        :status_key,
        :status_label,
        :status_detail,
        :source_updated_at,
        :expected_return,
        :payload
    )
    ON CONFLICT (availability_report_id, source_item_key) DO UPDATE SET
        source_content_sha256 = excluded.source_content_sha256,
        row_order = excluded.row_order,
        source_player_id = excluded.source_player_id,
        team_id = excluded.team_id,
        raw_team_name = excluded.raw_team_name,
        player_name = excluded.player_name,
        player_name_key = excluded.player_name_key,
        status_key = excluded.status_key,
        status_label = excluded.status_label,
        status_detail = excluded.status_detail,
        source_updated_at = excluded.source_updated_at,
        expected_return = excluded.expected_return,
        payload = excluded.payload,
        updated_at = CURRENT_TIMESTAMP
    """
)

DELETE_NCAA_TOURNAMENT_AVAILABILITY_PLAYER_STATUS_ROWS_SQL = text(
    """
    DELETE FROM ncaa_tournament_availability_player_statuses
    WHERE availability_report_id = :availability_report_id
    """
)

DELETE_STALE_NCAA_TOURNAMENT_AVAILABILITY_PLAYER_STATUS_ROWS_SQL = text(
    """
    DELETE FROM ncaa_tournament_availability_player_statuses
    WHERE availability_report_id = :availability_report_id
      AND source_item_key NOT IN :source_item_keys
    """
).bindparams(bindparam("source_item_keys", expanding=True))

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


@dataclass(frozen=True)
class NcaaTournamentAvailabilityPlayerStatusRecord:
    """Normalized player-status row for an official NCAA availability report."""

    source_item_key: str
    player_name: str
    status_key: str
    payload: object
    row_order: int | None = None
    source_player_id: str | None = None
    team_id: int | None = None
    raw_team_name: str | None = None
    player_name_key: str | None = None
    status_label: str | None = None
    status_detail: str | None = None
    source_updated_at: str | datetime | None = None
    expected_return: str | None = None
    source_content_sha256: str | None = None


@dataclass(frozen=True)
class NcaaTournamentAvailabilityReportRecord:
    """Official NCAA tournament availability report ready for persistence."""

    source_name: str
    source_dedupe_key: str
    captured_at: str | datetime
    payload: object
    player_statuses: Sequence[NcaaTournamentAvailabilityPlayerStatusRecord]
    source_url: str | None = None
    source_report_id: str | None = None
    reported_at: str | datetime | None = None
    effective_at: str | datetime | None = None
    imported_at: str | datetime | None = None
    source_content_sha256: str | None = None
    game_id: int | None = None
    team_id: int | None = None
    linkage_status: str | None = None
    linkage_notes: str | None = None
    raw_team_name: str | None = None
    raw_opponent_name: str | None = None
    raw_matchup_label: str | None = None


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
        **DEFAULT_GAME_CONTEXT_PAYLOAD,
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


def upsert_ncaa_tournament_availability_report(
    connection: Connection,
    report: NcaaTournamentAvailabilityReportRecord,
) -> NcaaTournamentAvailabilityPersistenceSummary:
    """Persist one official NCAA tournament availability report and statuses."""
    source_item_keys = _validate_source_item_keys(report.player_statuses)
    report_payload = _serialize_json_payload(
        report.payload,
        field_name="report payload",
    )
    linkage_status = _default_linkage_status(
        report.linkage_status,
        game_id=report.game_id,
        team_id=report.team_id,
    )
    availability_report_id = int(
        connection.execute(
            UPSERT_NCAA_TOURNAMENT_AVAILABILITY_REPORT_SQL,
            {
                "source_name": _require_non_empty_string(
                    report.source_name,
                    field_name="source_name",
                ),
                "source_url": _optional_string(
                    report.source_url,
                    field_name="source_url",
                ),
                "source_report_id": _optional_string(
                    report.source_report_id,
                    field_name="source_report_id",
                ),
                "source_dedupe_key": _require_non_empty_string(
                    report.source_dedupe_key,
                    field_name="source_dedupe_key",
                ),
                "source_content_sha256": _content_sha256(
                    report.source_content_sha256,
                    payload_json=report_payload,
                ),
                "reported_at": _coerce_optional_timestamp(
                    report.reported_at,
                    field_name="reported_at",
                ),
                "effective_at": _coerce_optional_timestamp(
                    report.effective_at,
                    field_name="effective_at",
                ),
                "captured_at": _coerce_required_timestamp(
                    report.captured_at,
                    field_name="captured_at",
                ),
                "imported_at": _coerce_optional_timestamp(
                    report.imported_at,
                    field_name="imported_at",
                ),
                "game_id": _as_optional_int(report.game_id),
                "team_id": _as_optional_int(report.team_id),
                "linkage_status": linkage_status,
                "linkage_notes": _optional_string(
                    report.linkage_notes,
                    field_name="linkage_notes",
                ),
                "raw_team_name": _optional_string(
                    report.raw_team_name,
                    field_name="raw_team_name",
                ),
                "raw_opponent_name": _optional_string(
                    report.raw_opponent_name,
                    field_name="raw_opponent_name",
                ),
                "raw_matchup_label": _optional_string(
                    report.raw_matchup_label,
                    field_name="raw_matchup_label",
                ),
                "payload": report_payload,
            },
        ).scalar_one()
    )

    for player_status in report.player_statuses:
        player_status_payload = _serialize_json_payload(
            player_status.payload,
            field_name="player_status payload",
        )
        connection.execute(
            UPSERT_NCAA_TOURNAMENT_AVAILABILITY_PLAYER_STATUS_SQL,
            {
                "availability_report_id": availability_report_id,
                "source_item_key": _require_non_empty_string(
                    player_status.source_item_key,
                    field_name="source_item_key",
                ),
                "source_content_sha256": _content_sha256(
                    player_status.source_content_sha256,
                    payload_json=player_status_payload,
                ),
                "row_order": _as_optional_int(player_status.row_order),
                "source_player_id": _optional_string(
                    player_status.source_player_id,
                    field_name="source_player_id",
                ),
                "team_id": _as_optional_int(player_status.team_id),
                "raw_team_name": _optional_string(
                    player_status.raw_team_name,
                    field_name="raw_team_name",
                ),
                "player_name": _require_non_empty_string(
                    player_status.player_name,
                    field_name="player_name",
                ),
                "player_name_key": _optional_string(
                    player_status.player_name_key,
                    field_name="player_name_key",
                ),
                "status_key": _require_non_empty_string(
                    player_status.status_key,
                    field_name="status_key",
                ),
                "status_label": _optional_string(
                    player_status.status_label,
                    field_name="status_label",
                ),
                "status_detail": _optional_string(
                    player_status.status_detail,
                    field_name="status_detail",
                ),
                "source_updated_at": _coerce_optional_timestamp(
                    player_status.source_updated_at,
                    field_name="source_updated_at",
                ),
                "expected_return": _optional_string(
                    player_status.expected_return,
                    field_name="expected_return",
                ),
                "payload": player_status_payload,
            },
        )

    if not source_item_keys:
        connection.execute(
            DELETE_NCAA_TOURNAMENT_AVAILABILITY_PLAYER_STATUS_ROWS_SQL,
            {"availability_report_id": availability_report_id},
        )
    else:
        connection.execute(
            DELETE_STALE_NCAA_TOURNAMENT_AVAILABILITY_PLAYER_STATUS_ROWS_SQL,
            {
                "availability_report_id": availability_report_id,
                "source_item_keys": source_item_keys,
            },
        )

    return NcaaTournamentAvailabilityPersistenceSummary(
        reports_upserted=1,
        player_status_rows_upserted=len(report.player_statuses),
        unmatched_reports_upserted=(
            1
            if linkage_status != "matched"
            or report.game_id is None
            or report.team_id is None
            else 0
        ),
    )


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


def _validate_source_item_keys(
    player_statuses: Sequence[NcaaTournamentAvailabilityPlayerStatusRecord],
) -> list[str]:
    source_item_keys = [
        _require_non_empty_string(
            player_status.source_item_key,
            field_name="source_item_key",
        )
        for player_status in player_statuses
    ]
    if len(set(source_item_keys)) != len(source_item_keys):
        raise ValueError(
            "Each availability player status must have a unique source_item_key "
            "within its report"
        )
    return source_item_keys


def _serialize_json_payload(payload: object, *, field_name: str) -> str:
    if payload is None:
        raise ValueError(f"Expected {field_name} to contain the raw source payload")
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode("utf-8")


def _content_sha256(
    explicit_value: str | None,
    *,
    payload_json: str,
) -> str:
    if explicit_value is not None:
        return _require_non_empty_string(
            explicit_value,
            field_name="source_content_sha256",
        )
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _coerce_required_timestamp(
    value: str | datetime,
    *,
    field_name: str,
) -> str:
    normalized_value = _coerce_optional_timestamp(value, field_name=field_name)
    if normalized_value is None:
        raise ValueError(f"Expected {field_name} to be provided")
    return normalized_value


def _coerce_optional_timestamp(
    value: str | datetime | None,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC).isoformat()
        return value.isoformat()
    if isinstance(value, str):
        return parse_timestamp(value).isoformat()
    raise TypeError(f"Expected {field_name} to be a string, datetime, or None")


def _default_linkage_status(
    value: str | None,
    *,
    game_id: int | None,
    team_id: int | None,
) -> str:
    if value is not None:
        return _require_non_empty_string(value, field_name="linkage_status")
    if game_id is not None and team_id is not None:
        return "matched"
    return "unresolved"


def _optional_string(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise TypeError(f"Expected {field_name} to be a string or None")


def _require_non_empty_string(value: object, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"Expected {field_name} to be a string")
    if not value.strip():
        raise ValueError(f"Expected {field_name} to be non-empty")
    return value


def _fetch_existing_game_state(
    connection: Connection,
    game_payload: Mapping[str, GameUpsertValue],
) -> ExistingGameState | None:
    row = (
        connection.execute(
            FETCH_EXISTING_GAME_STATE_SQL,
            {
                "season": game_payload["season"],
                "date": game_payload["date"],
                "team1_id": game_payload["team1_id"],
                "team2_id": game_payload["team2_id"],
            },
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    source_event_id = row.get("source_event_id")
    return ExistingGameState(
        source_event_id=(str(source_event_id) if source_event_id is not None else None),
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
        home_aliases = build_team_aliases(home_team_name)
        away_aliases = build_team_aliases(away_team_name)
        for outcome in outcomes:
            outcome_name = outcome.get("name")
            if not isinstance(outcome_name, str):
                continue
            matched_side = _match_team_outcome_side(
                outcome_name=outcome_name,
                home_aliases=home_aliases,
                away_aliases=away_aliases,
            )
            if matched_side == "home":
                fields["team1_price"] = to_float_or_none(outcome.get("price"))
                fields["team1_point"] = to_float_or_none(outcome.get("point"))
            elif matched_side == "away":
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


def _match_team_outcome_side(
    *,
    outcome_name: str,
    home_aliases: frozenset[str],
    away_aliases: frozenset[str],
) -> str | None:
    outcome_aliases = build_team_aliases(outcome_name)
    home_score = best_alias_score(home_aliases, outcome_aliases)
    away_score = best_alias_score(away_aliases, outcome_aliases)
    if home_score == 0 and away_score == 0:
        return None
    if home_score == away_score:
        return None
    return "home" if home_score > away_score else "away"


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected {key!r} to be a string")


def _as_market_list(value: object) -> list[MarketPayload]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []
