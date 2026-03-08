"""Verification helpers for historical ESPN game coverage."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from cbb.db import get_engine
from cbb.ingest.clients.espn import EspnScoreboardClient
from cbb.ingest.historical import build_historical_game
from cbb.ingest.utils import DEFAULT_CBB_SPORT, subtract_years
from cbb.team_catalog import TeamCatalog, load_team_catalog

DEFAULT_VERIFICATION_YEARS = 3
SAMPLE_LIMIT = 5
SKIPPED_EVENT_STATES = {"STATUS_CANCELED", "STATUS_POSTPONED"}

FETCH_GAMES_BY_SOURCE_ID_SQL = text(
    """
    SELECT source_event_id, completed, home_score, away_score
    FROM games
    WHERE source_event_id IN :source_event_ids
    """
).bindparams(bindparam("source_event_ids", expanding=True))


@dataclass(frozen=True)
class VerificationOptions:
    """Runtime options for game verification."""

    years_back: int = DEFAULT_VERIFICATION_YEARS
    start_date: date | None = None
    end_date: date | None = None
    sport: str = DEFAULT_CBB_SPORT


@dataclass(frozen=True)
class GameVerificationSummary:
    """Summary of an ESPN-to-database verification run."""

    sport: str
    start_date: str
    end_date: str
    dates_checked: int
    upstream_games_seen: int
    upstream_games_skipped: int
    completed_games_seen: int
    games_present: int
    games_verified: int
    games_missing: int
    status_mismatches: int
    score_mismatches: int
    sample_missing_games: tuple[str, ...]
    sample_status_mismatches: tuple[str, ...]
    sample_score_mismatches: tuple[str, ...]


@dataclass(frozen=True)
class StoredGame:
    """Stored game values used during source-event verification."""

    completed: bool
    home_score: int | None
    away_score: int | None


@dataclass(frozen=True)
class ExpectedGame:
    """Expected game values derived from the ESPN scoreboard feed."""

    source_event_id: str
    home_team_name: str
    away_team_name: str
    completed: bool
    home_score: int | None
    away_score: int | None


def verify_games(
    options: VerificationOptions,
    database_url: str | None = None,
    client: EspnScoreboardClient | None = None,
    today: date | None = None,
    team_catalog: TeamCatalog | None = None,
) -> GameVerificationSummary:
    """Verify stored D1 games against ESPN scoreboard events.

    Args:
        options: Verification date-window options.
        database_url: Optional database URL override.
        client: Optional ESPN client override.
        today: Optional current-date override for tests.
        team_catalog: Optional canonical team catalog override.

    Returns:
        A summary of coverage, status, and score verification results.

    Raises:
        ValueError: If the requested date range is invalid.
    """
    if options.years_back < 1:
        raise ValueError("years_back must be at least 1")

    resolved_end = options.end_date or today or datetime.now(UTC).date()
    resolved_start = options.start_date or subtract_years(
        resolved_end,
        options.years_back,
    )
    if resolved_start > resolved_end:
        raise ValueError("start_date must be on or before end_date")

    engine = get_engine(database_url)
    scoreboard_client = client or EspnScoreboardClient()
    resolved_team_catalog = team_catalog or load_team_catalog(scoreboard_client)
    sample_missing_games: list[str] = []
    sample_status_mismatches: list[str] = []
    sample_score_mismatches: list[str] = []
    upstream_games_seen = 0
    upstream_games_skipped = 0
    completed_games_seen = 0
    games_present = 0
    games_verified = 0
    games_missing = 0
    status_mismatches = 0
    score_mismatches = 0
    all_dates = _date_range(resolved_start, resolved_end)

    with engine.connect() as connection:
        for game_date in all_dates:
            expected_games, skipped_games = _prepare_expected_games(
                scoreboard_client.get_scoreboard(game_date),
                resolved_team_catalog,
            )
            upstream_games_skipped += skipped_games
            stored_games_by_source_id = _fetch_stored_games_by_source_id(
                connection,
                expected_games,
            )

            for expected_game in expected_games:
                upstream_games_seen += 1
                if expected_game.completed:
                    completed_games_seen += 1

                stored_game = stored_games_by_source_id.get(
                    expected_game.source_event_id
                )
                if stored_game is None:
                    games_missing += 1
                    _append_sample(
                        sample_missing_games,
                        _describe_expected_game(expected_game),
                    )
                    continue

                games_present += 1
                if stored_game.completed != expected_game.completed:
                    status_mismatches += 1
                    _append_sample(
                        sample_status_mismatches,
                        _describe_expected_game(expected_game),
                    )
                    continue

                if expected_game.completed and (
                    stored_game.home_score != expected_game.home_score
                    or stored_game.away_score != expected_game.away_score
                ):
                    score_mismatches += 1
                    _append_sample(
                        sample_score_mismatches,
                        _describe_expected_game(expected_game),
                    )
                    continue

                games_verified += 1

    return GameVerificationSummary(
        sport=options.sport,
        start_date=resolved_start.isoformat(),
        end_date=resolved_end.isoformat(),
        dates_checked=len(all_dates),
        upstream_games_seen=upstream_games_seen,
        upstream_games_skipped=upstream_games_skipped,
        completed_games_seen=completed_games_seen,
        games_present=games_present,
        games_verified=games_verified,
        games_missing=games_missing,
        status_mismatches=status_mismatches,
        score_mismatches=score_mismatches,
        sample_missing_games=tuple(sample_missing_games),
        sample_status_mismatches=tuple(sample_status_mismatches),
        sample_score_mismatches=tuple(sample_score_mismatches),
    )


def _prepare_expected_games(
    events: list[dict[str, object]],
    team_catalog: TeamCatalog,
) -> tuple[list[ExpectedGame], int]:
    expected_games: list[ExpectedGame] = []
    skipped_games = 0

    for event in events:
        if _should_skip_event(event):
            skipped_games += 1
            continue

        prepared_game = build_historical_game(event)
        if team_catalog.resolve_team_name(prepared_game.home_team_name) is None:
            skipped_games += 1
            continue
        if team_catalog.resolve_team_name(prepared_game.away_team_name) is None:
            skipped_games += 1
            continue

        source_event_id = prepared_game.payload.get("source_event_id")
        if not isinstance(source_event_id, str):
            raise RuntimeError("Expected source_event_id to be a string")

        expected_games.append(
            ExpectedGame(
                source_event_id=source_event_id,
                home_team_name=prepared_game.home_team_name,
                away_team_name=prepared_game.away_team_name,
                completed=bool(prepared_game.payload["completed"]),
                home_score=_coerce_optional_int(prepared_game.payload["home_score"]),
                away_score=_coerce_optional_int(prepared_game.payload["away_score"]),
            )
        )

    return expected_games, skipped_games


def _fetch_stored_games_by_source_id(
    connection: Connection,
    expected_games: list[ExpectedGame],
) -> dict[str, StoredGame]:
    source_event_ids = [game.source_event_id for game in expected_games]
    if not source_event_ids:
        return {}

    rows = connection.execute(
        FETCH_GAMES_BY_SOURCE_ID_SQL,
        {"source_event_ids": source_event_ids},
    ).mappings()
    return {
        str(row["source_event_id"]): StoredGame(
            completed=bool(row["completed"]),
            home_score=_coerce_optional_int(row["home_score"]),
            away_score=_coerce_optional_int(row["away_score"]),
        )
        for row in rows
    }


def _describe_expected_game(expected_game: ExpectedGame) -> str:
    return (
        f"{expected_game.source_event_id} "
        f"{expected_game.home_team_name} vs {expected_game.away_team_name}"
    )


def _append_sample(samples: list[str], value: str) -> None:
    if len(samples) < SAMPLE_LIMIT:
        samples.append(value)


def _should_skip_event(event: Mapping[str, object]) -> bool:
    status_name = _event_status_name(event)
    return status_name in SKIPPED_EVENT_STATES


def _event_status_name(event: Mapping[str, object]) -> str | None:
    competition_status = _status_name(_first_competition(event))
    if competition_status is not None:
        return competition_status
    return _status_name(event.get("status"))


def _first_competition(event: Mapping[str, object]) -> Mapping[str, object] | None:
    competitions = event.get("competitions")
    if not isinstance(competitions, list) or not competitions:
        return None
    first_competition = competitions[0]
    if isinstance(first_competition, Mapping):
        return first_competition
    return None


def _status_name(status_payload: object) -> str | None:
    if not isinstance(status_payload, Mapping):
        return None
    type_payload = status_payload.get("type")
    if not isinstance(type_payload, Mapping):
        return None
    name = type_payload.get("name")
    if isinstance(name, str):
        return name
    return None


def _date_range(start_date: date, end_date: date) -> list[date]:
    day_count = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(day_count + 1)]


def _coerce_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"Expected int-compatible value, got {type(value).__name__}")
