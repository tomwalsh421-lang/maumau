"""Historical NCAA game ingest backed by ESPN scoreboard data."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from cbb.db import get_engine
from cbb.ingest.clients.espn import EspnScoreboardClient
from cbb.ingest.models import HistoricalIngestSummary
from cbb.ingest.persistence import PreparedGame, upsert_prepared_game
from cbb.ingest.utils import (
    DEFAULT_CBB_SPORT,
    derive_cbb_season,
    determine_result,
    parse_timestamp,
    safe_int,
    subtract_years,
)
from cbb.team_catalog import TeamCatalog, load_team_catalog, seed_team_catalog

DEFAULT_HISTORICAL_YEARS = 3
DEFAULT_CHECKPOINT_SOURCE = "espn_scoreboard"

FETCH_EXISTING_GAMES_BY_SOURCE_ID_SQL = text(
    """
    SELECT source_event_id, completed
    FROM games
    WHERE source_event_id IN :source_event_ids
    """
).bindparams(bindparam("source_event_ids", expanding=True))

FETCH_INGESTED_DATES_SQL = text(
    """
    SELECT game_date
    FROM ingest_checkpoints
    WHERE source_name = :source_name
      AND sport_key = :sport_key
      AND game_date BETWEEN :start_date AND :end_date
    """
)

UPSERT_INGEST_CHECKPOINT_SQL = text(
    """
    INSERT INTO ingest_checkpoints (source_name, sport_key, game_date)
    VALUES (:source_name, :sport_key, :game_date)
    ON CONFLICT (source_name, sport_key, game_date) DO NOTHING
    """
)

ENSURE_INGEST_CHECKPOINTS_SQL = text(
    """
    CREATE TABLE IF NOT EXISTS ingest_checkpoints (
        source_name VARCHAR(64) NOT NULL,
        sport_key VARCHAR(64) NOT NULL,
        game_date DATE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(source_name, sport_key, game_date)
    )
    """
)


@dataclass(frozen=True)
class HistoricalIngestOptions:
    """Runtime options for historical game ingest."""

    years_back: int = DEFAULT_HISTORICAL_YEARS
    start_date: date | None = None
    end_date: date | None = None
    force_refresh: bool = False
    sport: str = DEFAULT_CBB_SPORT


def ingest_historical_games(
    options: HistoricalIngestOptions,
    database_url: str | None = None,
    client: EspnScoreboardClient | None = None,
    today: date | None = None,
    team_catalog: TeamCatalog | None = None,
) -> HistoricalIngestSummary:
    """Backfill NCAA Division I games from the ESPN scoreboard feed.

    Args:
        options: Historical ingest options.
        database_url: Optional database URL override.
        client: Optional ESPN client override.
        today: Optional current-date override for tests.
        team_catalog: Optional canonical team catalog override.

    Returns:
        A summary of the completed backfill run.

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
    all_dates = list(_date_range(resolved_start, resolved_end))
    teams_seen: set[str] = set()
    games_seen = 0
    games_inserted = 0
    games_skipped = 0
    dates_completed = 0

    with engine.begin() as connection:
        connection.execute(ENSURE_INGEST_CHECKPOINTS_SQL)
        resolved_team_catalog = team_catalog or load_team_catalog(scoreboard_client)
        team_ids_by_key = seed_team_catalog(connection, resolved_team_catalog)
        completed_dates = _fetch_completed_dates(
            connection=connection,
            options=options,
            start_date=resolved_start,
            end_date=resolved_end,
        )
        dates_to_fetch = [
            game_date for game_date in all_dates if game_date not in completed_dates
        ]

        for game_date in dates_to_fetch:
            events = scoreboard_client.get_scoreboard(game_date)
            existing_games_by_source_id = _fetch_existing_games_by_source_id(
                connection,
                events,
            )

            for event in events:
                games_seen += 1
                event_id = _event_id(event)
                if (
                    not options.force_refresh
                    and existing_games_by_source_id.get(event_id) is True
                ):
                    continue

                prepared_game = build_historical_game(event)
                game_id = upsert_prepared_game(
                    connection,
                    prepared_game,
                    team_catalog=resolved_team_catalog,
                    team_ids_by_key=team_ids_by_key,
                )
                if game_id is None:
                    games_skipped += 1
                    continue

                teams_seen.update(
                    [prepared_game.home_team_name, prepared_game.away_team_name]
                )
                games_inserted += 1

            connection.execute(
                UPSERT_INGEST_CHECKPOINT_SQL,
                {
                    "source_name": DEFAULT_CHECKPOINT_SOURCE,
                    "sport_key": options.sport,
                    "game_date": game_date.isoformat(),
                },
            )
            dates_completed += 1

    return HistoricalIngestSummary(
        sport=options.sport,
        start_date=resolved_start.isoformat(),
        end_date=resolved_end.isoformat(),
        dates_requested=len(dates_to_fetch),
        dates_skipped=len(all_dates) - len(dates_to_fetch),
        dates_completed=dates_completed,
        teams_seen=len(teams_seen),
        games_seen=games_seen,
        games_inserted=games_inserted,
        games_skipped=games_skipped,
    )


def build_historical_game(event: Mapping[str, object]) -> PreparedGame:
    """Normalize an ESPN scoreboard event into a prepared game payload.

    Args:
        event: Raw ESPN event payload.

    Returns:
        A normalized game payload ready for database upsert.
    """
    competition = _first_mapping(event.get("competitions"))
    competitors = _as_mapping_list(competition.get("competitors"))
    home_competitor = _find_competitor(competitors, "home")
    away_competitor = _find_competitor(competitors, "away")

    commence_time = parse_timestamp(_required_string(event, "date"))
    home_team_name = _team_display_name(home_competitor)
    away_team_name = _team_display_name(away_competitor)
    completed = bool(
        _dig(competition, "status", "type", "completed")
        or _dig(event, "status", "type", "completed")
    )
    home_score = safe_int(home_competitor.get("score"))
    away_score = safe_int(away_competitor.get("score"))

    return PreparedGame(
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        payload={
            "season": derive_cbb_season(commence_time),
            "date": commence_time.date().isoformat(),
            "commence_time": commence_time.isoformat(),
            "round": None,
            "source_event_id": _event_id(event),
            "sport_key": DEFAULT_CBB_SPORT,
            "sport_title": "NCAAM",
            "result": determine_result(home_score, away_score, completed),
            "completed": completed,
            "home_score": home_score,
            "away_score": away_score,
            "last_score_update": (commence_time.isoformat() if completed else None),
        },
    )


def _fetch_completed_dates(
    connection: Connection,
    options: HistoricalIngestOptions,
    start_date: date,
    end_date: date,
) -> set[date]:
    if options.force_refresh:
        return set()

    rows = connection.execute(
        FETCH_INGESTED_DATES_SQL,
        {
            "source_name": DEFAULT_CHECKPOINT_SOURCE,
            "sport_key": options.sport,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
    ).mappings()
    return {_coerce_date(row["game_date"]) for row in rows}


def _fetch_existing_games_by_source_id(
    connection: Connection,
    events: list[dict[str, object]],
) -> dict[str, bool]:
    source_ids = [_event_id(event) for event in events]
    if not source_ids:
        return {}

    rows = connection.execute(
        FETCH_EXISTING_GAMES_BY_SOURCE_ID_SQL,
        {"source_event_ids": source_ids},
    ).mappings()
    return {str(row["source_event_id"]): bool(row["completed"]) for row in rows}


def _event_id(event: Mapping[str, object]) -> str:
    return _required_string(event, "id")


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected {key!r} to be a string")


def _date_range(start_date: date, end_date: date) -> list[date]:
    day_count = (end_date - start_date).days
    return [start_date + timedelta(days=offset) for offset in range(day_count + 1)]


def _coerce_date(value: object) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    raise TypeError(f"Expected date-compatible value, got {type(value).__name__}")


def _first_mapping(value: object) -> Mapping[str, object]:
    items = _as_mapping_list(value)
    if not items:
        raise RuntimeError("Expected at least one competition in ESPN event payload")
    return items[0]


def _find_competitor(
    competitors: list[Mapping[str, object]],
    home_away: str,
) -> Mapping[str, object]:
    for competitor in competitors:
        if competitor.get("homeAway") == home_away:
            return competitor
    raise RuntimeError(f"Expected {home_away} competitor in ESPN event payload")


def _team_display_name(competitor: Mapping[str, object]) -> str:
    team = competitor.get("team")
    if isinstance(team, Mapping):
        display_name = team.get("displayName")
        if isinstance(display_name, str):
            return display_name
    raise RuntimeError("Expected competitor.team.displayName in ESPN event payload")


def _as_mapping_list(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _dig(value: object, *keys: str) -> object | None:
    current = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current
