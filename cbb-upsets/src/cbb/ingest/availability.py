"""File-based import workflow for wrapped official availability captures."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import orjson
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from cbb.db import get_engine
from cbb.ingest.clients.availability_loader import (
    expand_official_availability_capture_paths,
    load_official_availability_captures,
)
from cbb.ingest.clients.availability_types import (
    OfficialAvailabilityGame,
    OfficialAvailabilityReport,
    OfficialAvailabilityRow,
    OfficialAvailabilityTeam,
)
from cbb.ingest.persistence import (
    NcaaTournamentAvailabilityPlayerStatusRecord,
    NcaaTournamentAvailabilityReportRecord,
    upsert_ncaa_tournament_availability_report,
)
from cbb.ingest.utils import derive_cbb_season, normalize_team_key, parse_timestamp

_COMMON_TEAM_KEY_ALIASES = {
    "arizona-st": "arizona-state",
    "iowa-st": "iowa-state",
    "kansas-st": "kansas-state",
    "michigan-st": "michigan-state",
    "northwestern-st": "northwestern-state",
    "ohio-st": "ohio-state",
    "oklahoma-st": "oklahoma-state",
    "oregon-st": "oregon-state",
    "penn-st": "penn-state",
    "wichita-st": "wichita-state",
}

FETCH_TEAMS_FOR_AVAILABILITY_SQL = text(
    """
    SELECT team_id, team_key, name, ncaa_team_code
    FROM teams
    ORDER BY team_id
    """
)

FETCH_TEAM_ALIASES_FOR_AVAILABILITY_SQL = text(
    """
    SELECT team_id, alias_key, alias_name
    FROM team_aliases
    ORDER BY team_alias_id
    """
)

FETCH_GAMES_BY_SOURCE_IDS_SQL = text(
    """
    SELECT game_id
    FROM games
    WHERE (
        :source_event_id IS NOT NULL
        AND source_event_id = :source_event_id
    )
       OR (
        :ncaa_game_code IS NOT NULL
        AND ncaa_game_code = :ncaa_game_code
    )
    ORDER BY game_id
    """
)

FETCH_GAMES_BY_TEAM_CONTEXT_SQL = text(
    """
    SELECT game_id
    FROM games
    WHERE season = :season
      AND date = :game_date
      AND team1_id = :home_team_id
      AND team2_id = :away_team_id
    ORDER BY game_id
    """
)


@dataclass(frozen=True)
class OfficialAvailabilityImportSummary:
    """Deterministic summary returned by the availability import workflow."""

    snapshots_imported: int
    player_rows_imported: int
    games_matched: int
    teams_matched: int
    rows_unmatched: int
    duplicates_skipped: int


class OfficialAvailabilityPersistenceWriter(Protocol):
    """Callable persistence contract for normalized availability reports."""

    def __call__(
        self,
        reports: Sequence[OfficialAvailabilityReport],
        *,
        database_url: str | None = None,
    ) -> OfficialAvailabilityImportSummary: ...


@dataclass(frozen=True)
class _AvailabilityTeamLookup:
    """Preloaded local lookup state used to match official report teams."""

    team_ids_by_key: dict[str, int]
    team_ids_by_ncaa_code: dict[str, int]


@dataclass(frozen=True)
class _NormalizedAvailabilityReport:
    """One normalized availability report plus import-time summary fields."""

    record: NcaaTournamentAvailabilityReportRecord
    matched_game: bool
    matched_team_ids: frozenset[int]
    unmatched_row_count: int


def ingest_official_availability_reports(
    paths: Sequence[Path | str],
    *,
    database_url: str | None = None,
    persist_reports: OfficialAvailabilityPersistenceWriter | None = None,
) -> OfficialAvailabilityImportSummary:
    """Load one or more local capture files and persist them into the database."""

    capture_paths = expand_official_availability_capture_paths(paths)
    reports = tuple(
        report
        for path in capture_paths
        for report in load_official_availability_captures(path)
    )
    persistence_writer = (
        persist_reports or persist_official_ncaa_availability_reports
    )
    return persistence_writer(reports, database_url=database_url)


def persist_official_ncaa_availability_reports(
    reports: Sequence[OfficialAvailabilityReport],
    *,
    database_url: str | None = None,
) -> OfficialAvailabilityImportSummary:
    """Persist normalized availability reports into the configured DB."""

    engine = get_engine(database_url)
    with engine.begin() as connection:
        _validate_availability_schema(connection)
        team_lookup = _load_team_lookup(connection)
        summary = OfficialAvailabilityImportSummary(
            snapshots_imported=0,
            player_rows_imported=0,
            games_matched=0,
            teams_matched=0,
            rows_unmatched=0,
            duplicates_skipped=0,
        )
        for report in reports:
            normalized = _normalize_report(
                connection,
                report=report,
                team_lookup=team_lookup,
            )
            if _is_duplicate_report(connection, normalized.record):
                summary = OfficialAvailabilityImportSummary(
                    snapshots_imported=summary.snapshots_imported,
                    player_rows_imported=summary.player_rows_imported,
                    games_matched=summary.games_matched,
                    teams_matched=summary.teams_matched,
                    rows_unmatched=summary.rows_unmatched,
                    duplicates_skipped=summary.duplicates_skipped + 1,
                )
                continue

            persisted = upsert_ncaa_tournament_availability_report(
                connection,
                normalized.record,
            )
            summary = OfficialAvailabilityImportSummary(
                snapshots_imported=(
                    summary.snapshots_imported + persisted.reports_upserted
                ),
                player_rows_imported=(
                    summary.player_rows_imported
                    + persisted.player_status_rows_upserted
                ),
                games_matched=summary.games_matched + int(normalized.matched_game),
                teams_matched=(
                    summary.teams_matched + len(normalized.matched_team_ids)
                ),
                rows_unmatched=(
                    summary.rows_unmatched + normalized.unmatched_row_count
                ),
                duplicates_skipped=summary.duplicates_skipped,
            )
        return summary


def _validate_availability_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    required_tables = {
        "ncaa_tournament_availability_reports",
        "ncaa_tournament_availability_player_statuses",
        "games",
        "teams",
    }
    missing_tables = sorted(required_tables - table_names)
    if not missing_tables:
        return
    raise RuntimeError(
        "Availability import requires the initialized database schema. Missing "
        f"tables: {', '.join(missing_tables)}. Run `cbb db init` first."
    )


def _load_team_lookup(connection: Connection) -> _AvailabilityTeamLookup:
    team_ids_by_key: dict[str, int] = {}
    team_ids_by_ncaa_code: dict[str, int] = {}

    for row in connection.execute(FETCH_TEAMS_FOR_AVAILABILITY_SQL).mappings():
        team_id = int(row["team_id"])
        team_key = str(row["team_key"])
        team_ids_by_key[team_key] = team_id
        team_ids_by_key.setdefault(normalize_team_key(str(row["name"])), team_id)
        ncaa_team_code = row.get("ncaa_team_code")
        if isinstance(ncaa_team_code, str) and ncaa_team_code.strip():
            team_ids_by_ncaa_code[ncaa_team_code.strip()] = team_id

    if inspect(connection).has_table("team_aliases"):
        for row in connection.execute(
            FETCH_TEAM_ALIASES_FOR_AVAILABILITY_SQL
        ).mappings():
            team_id = int(row["team_id"])
            alias_key = str(row["alias_key"])
            team_ids_by_key.setdefault(alias_key, team_id)
            alias_name = str(row["alias_name"])
            team_ids_by_key.setdefault(normalize_team_key(alias_name), team_id)

    return _AvailabilityTeamLookup(
        team_ids_by_key=team_ids_by_key,
        team_ids_by_ncaa_code=team_ids_by_ncaa_code,
    )


def _normalize_report(
    connection: Connection,
    *,
    report: OfficialAvailabilityReport,
    team_lookup: _AvailabilityTeamLookup,
) -> _NormalizedAvailabilityReport:
    home_team_id = _resolve_team_id(report.game.home_team, team_lookup)
    away_team_id = _resolve_team_id(report.game.away_team, team_lookup)
    game_id, linkage_notes = _resolve_game_id(
        connection,
        game=report.game,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
    )

    player_statuses: list[NcaaTournamentAvailabilityPlayerStatusRecord] = []
    matched_team_ids: set[int] = set()
    unmatched_row_count = 0
    for row in report.rows:
        row_team_id = _resolve_team_id(row.team, team_lookup)
        if row_team_id is not None:
            matched_team_ids.add(row_team_id)
        if row_team_id is None or game_id is None:
            unmatched_row_count += 1
        player_statuses.append(
            _build_player_status_record(
                row=row,
                row_team_id=row_team_id,
            )
        )

    report_team = report.rows[0].team if report.rows else report.game.home_team
    primary_team_id = _resolve_team_id(report_team, team_lookup)
    primary_team_name: str | None
    primary_opponent_name: str | None
    if primary_team_id == home_team_id:
        primary_team_name = report.game.home_team.name
        primary_opponent_name = report.game.away_team.name
    elif primary_team_id == away_team_id:
        primary_team_name = report.game.away_team.name
        primary_opponent_name = report.game.home_team.name
    else:
        primary_team_name = report_team.name if primary_team_id is not None else None
        primary_opponent_name = (
            report.game.away_team.name
            if primary_team_name == report.game.home_team.name
            else report.game.home_team.name
        )
    linkage_status = (
        "matched"
        if game_id is not None and primary_team_id is not None
        else "unresolved"
    )

    return _NormalizedAvailabilityReport(
        record=NcaaTournamentAvailabilityReportRecord(
            source_name=report.source_name,
            source_url=report.source_url,
            source_report_id=report.game.source_event_id
            or report.game.ncaa_game_code,
            source_dedupe_key=_report_dedupe_key(report),
            reported_at=report.published_at,
            effective_at=report.effective_at,
            captured_at=report.captured_at,
            game_id=game_id,
            team_id=primary_team_id,
            linkage_status=linkage_status,
            linkage_notes=linkage_notes,
            raw_team_name=primary_team_name,
            raw_opponent_name=primary_opponent_name,
            raw_matchup_label=(
                f"{report.game.away_team.name} at {report.game.home_team.name}"
            ),
            payload=report.raw_payload,
            player_statuses=tuple(player_statuses),
        ),
        matched_game=game_id is not None,
        matched_team_ids=frozenset(matched_team_ids),
        unmatched_row_count=unmatched_row_count,
    )


def _build_player_status_record(
    *,
    row: OfficialAvailabilityRow,
    row_team_id: int | None,
) -> NcaaTournamentAvailabilityPlayerStatusRecord:
    player_name_key = normalize_team_key(row.player_name)
    return NcaaTournamentAvailabilityPlayerStatusRecord(
        source_item_key=_source_item_key(row),
        source_player_id=None,
        player_name=row.player_name,
        player_name_key=player_name_key,
        team_id=row_team_id,
        raw_team_name=row.team.name,
        status_key=row.status,
        status_label=row.status.title(),
        status_detail=row.note,
        source_updated_at=row.updated_at,
        expected_return=None,
        payload=dict(row.raw_payload),
        row_order=row.row_number,
    )


def _resolve_team_id(
    team: OfficialAvailabilityTeam,
    team_lookup: _AvailabilityTeamLookup,
) -> int | None:
    if team.ncaa_team_code is not None:
        matched_team_id = team_lookup.team_ids_by_ncaa_code.get(team.ncaa_team_code)
        if matched_team_id is not None:
            return matched_team_id
    team_key = normalize_team_key(team.name)
    matched_team_id = team_lookup.team_ids_by_key.get(team_key)
    if matched_team_id is not None:
        return matched_team_id
    alias_key = _COMMON_TEAM_KEY_ALIASES.get(team_key)
    if alias_key is not None:
        return team_lookup.team_ids_by_key.get(alias_key)
    return None


def _resolve_game_id(
    connection: Connection,
    *,
    game: OfficialAvailabilityGame,
    home_team_id: int | None,
    away_team_id: int | None,
) -> tuple[int | None, str | None]:
    source_rows = []
    if game.source_event_id is not None or game.ncaa_game_code is not None:
        source_rows = list(
            connection.execute(
                FETCH_GAMES_BY_SOURCE_IDS_SQL,
                {
                    "source_event_id": game.source_event_id,
                    "ncaa_game_code": game.ncaa_game_code,
                },
            ).mappings()
        )
        if len(source_rows) == 1:
            return int(source_rows[0]["game_id"]), None
        if len(source_rows) > 1:
            return None, "Multiple stored games matched the official source ID."

    if home_team_id is None or away_team_id is None:
        return None, "Could not resolve both report teams to canonical team IDs."

    season = derive_cbb_season(game.scheduled_start)
    game_date = parse_timestamp(game.scheduled_start).date().isoformat()
    exact_rows = list(
        connection.execute(
            FETCH_GAMES_BY_TEAM_CONTEXT_SQL,
            {
                "season": season,
                "game_date": game_date,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
            },
        ).mappings()
    )
    if len(exact_rows) == 1:
        return int(exact_rows[0]["game_id"]), None
    if len(exact_rows) > 1:
        return None, "Multiple stored games matched the team/date fallback."

    swapped_rows = list(
        connection.execute(
            FETCH_GAMES_BY_TEAM_CONTEXT_SQL,
            {
                "season": season,
                "game_date": game_date,
                "home_team_id": away_team_id,
                "away_team_id": home_team_id,
            },
        ).mappings()
    )
    if len(swapped_rows) == 1:
        return (
            int(swapped_rows[0]["game_id"]),
            "Matched by team/date fallback after swapping home and away teams.",
        )
    if len(swapped_rows) > 1:
        return None, "Multiple stored games matched the swapped team/date fallback."

    if source_rows:
        return None, "Official source ID did not match a unique stored game."
    return None, "No stored game matched the official report context."


def _source_item_key(row: OfficialAvailabilityRow) -> str:
    team_part = row.team.ncaa_team_code or normalize_team_key(row.team.name)
    player_part = normalize_team_key(row.player_name)
    return f"{team_part}:{player_part}:{row.row_number}"


def _report_dedupe_key(report: OfficialAvailabilityReport) -> str:
    event_id = report.game.source_event_id or report.game.ncaa_game_code or "unknown"
    home_key = normalize_team_key(report.game.home_team.name)
    away_key = normalize_team_key(report.game.away_team.name)
    effective_at = report.effective_at or "none"
    return (
        f"{event_id}:{report.published_at}:{effective_at}:{home_key}:{away_key}"
    )


def _is_duplicate_report(
    connection: Connection,
    report: NcaaTournamentAvailabilityReportRecord,
) -> bool:
    row = (
        connection.execute(
            text(
                """
                SELECT source_content_sha256
                FROM ncaa_tournament_availability_reports
                WHERE source_name = :source_name
                  AND source_dedupe_key = :source_dedupe_key
                """
            ),
            {
                "source_name": report.source_name,
                "source_dedupe_key": report.source_dedupe_key,
            },
        )
        .mappings()
        .first()
    )
    if row is None:
        return False
    return row["source_content_sha256"] == _payload_sha256(report.payload)


def _payload_sha256(payload: object) -> str:
    payload_json = orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)
    return hashlib.sha256(payload_json).hexdigest()


__all__ = [
    "OfficialAvailabilityImportSummary",
    "OfficialAvailabilityPersistenceWriter",
    "ingest_official_availability_reports",
    "persist_official_ncaa_availability_reports",
]
