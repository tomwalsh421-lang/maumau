"""Current odds ingest backed by The Odds API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cbb.db import get_engine
from cbb.ingest.clients.odds_api import (
    DEFAULT_ODDS_MARKETS,
    DEFAULT_ODDS_REGIONS,
    DEFAULT_ODDS_SPORT,
    OddsApiClient,
)
from cbb.ingest.models import ApiQuota, OddsIngestSummary
from cbb.ingest.persistence import (
    BookmakerPayload,
    PreparedGame,
    ensure_odds_schema_extensions,
    upsert_odds_snapshots,
    upsert_prepared_game,
)
from cbb.ingest.utils import (
    derive_cbb_season,
    determine_result,
    parse_timestamp,
    parse_timestamp_or_none,
    safe_int,
)
from cbb.team_catalog import TeamCatalog, load_team_catalog, seed_team_catalog

SCORE_EVENT_FIELDS = {
    "id",
    "sport_key",
    "sport_title",
    "commence_time",
    "home_team",
    "away_team",
    "scores",
    "completed",
    "last_update",
}


@dataclass(frozen=True)
class OddsIngestOptions:
    """Runtime options for current odds ingest."""

    sport: str = DEFAULT_ODDS_SPORT
    regions: str = DEFAULT_ODDS_REGIONS
    markets: str = DEFAULT_ODDS_MARKETS
    bookmakers: str | None = None
    odds_format: str = "american"
    include_scores: bool = True
    days_from: int = 3


@dataclass(frozen=True)
class OddsPersistenceInput:
    """Normalized API payloads ready for database persistence."""

    sport: str
    odds_events: Sequence[dict[str, object]]
    score_events: Sequence[dict[str, object]]
    odds_quota: ApiQuota | None = None
    scores_quota: ApiQuota | None = None


def ingest_current_odds(
    options: OddsIngestOptions,
    database_url: str | None = None,
    client: OddsApiClient | None = None,
    team_catalog: TeamCatalog | None = None,
) -> OddsIngestSummary:
    """Fetch current odds and optional scores, then persist them.

    Args:
        options: Odds ingest options.
        database_url: Optional database URL override.
        client: Optional Odds API client override.
        team_catalog: Optional canonical team catalog override.

    Returns:
        A summary of inserted or updated records.
    """
    odds_client = client or OddsApiClient()
    odds_response = odds_client.get_odds(
        sport=options.sport,
        regions=options.regions,
        markets=options.markets,
        bookmakers=options.bookmakers,
        odds_format=options.odds_format,
    )
    scores_response = (
        odds_client.get_scores(sport=options.sport, days_from=options.days_from)
        if options.include_scores
        else None
    )

    return persist_odds_data(
        payload=OddsPersistenceInput(
            sport=options.sport,
            odds_events=_ensure_event_list(odds_response.data),
            score_events=(
                _ensure_event_list(scores_response.data)
                if scores_response is not None
                else []
            ),
            odds_quota=odds_response.quota,
            scores_quota=(
                scores_response.quota if scores_response is not None else None
            ),
        ),
        database_url=database_url,
        team_catalog=team_catalog,
    )


def persist_odds_data(
    payload: OddsPersistenceInput,
    database_url: str | None = None,
    team_catalog: TeamCatalog | None = None,
) -> OddsIngestSummary:
    """Persist current odds and scores into the database.

    Args:
        payload: Normalized odds and score payload bundle.
        database_url: Optional database URL override.
        team_catalog: Optional canonical team catalog override.

    Returns:
        A summary of inserted or updated records.
    """
    engine = get_engine(database_url)
    odds_by_id = {_event_id(event): event for event in payload.odds_events}
    scores_by_id = {_event_id(event): event for event in payload.score_events}
    team_names_seen: set[str] = set()
    games_upserted = 0
    games_skipped = 0
    odds_snapshots_upserted = 0
    completed_games_updated = 0

    with engine.begin() as connection:
        ensure_odds_schema_extensions(connection)
        resolved_team_catalog = team_catalog or load_team_catalog()
        team_ids_by_key = seed_team_catalog(connection, resolved_team_catalog)
        for event_id in sorted(set(odds_by_id) | set(scores_by_id)):
            odds_event = odds_by_id.get(event_id)
            score_event = scores_by_id.get(event_id)
            prepared_game = build_odds_game(
                event=_merge_event_data(odds_event, score_event),
                score_event=score_event,
            )
            game_id = upsert_prepared_game(
                connection,
                prepared_game,
                team_catalog=resolved_team_catalog,
                team_ids_by_key=team_ids_by_key,
                preserve_existing_completed=True,
            )
            if game_id is None:
                games_skipped += 1
                continue

            team_names_seen.update(
                [prepared_game.home_team_name, prepared_game.away_team_name]
            )
            games_upserted += 1
            if prepared_game.payload["completed"]:
                completed_games_updated += 1

            if odds_event is not None:
                bookmakers = _as_mapping_list(odds_event.get("bookmakers"))
                odds_snapshots_upserted += upsert_odds_snapshots(
                    connection=connection,
                    game_id=game_id,
                    prepared_game=prepared_game,
                    bookmakers=bookmakers,
                )

    return OddsIngestSummary(
        sport=payload.sport,
        teams_seen=len(team_names_seen),
        games_upserted=games_upserted,
        games_skipped=games_skipped,
        odds_snapshots_upserted=odds_snapshots_upserted,
        completed_games_updated=completed_games_updated,
        odds_quota=payload.odds_quota or ApiQuota(None, None, None),
        scores_quota=payload.scores_quota,
    )


def build_odds_game(
    event: Mapping[str, object],
    score_event: Mapping[str, object] | None,
) -> PreparedGame:
    """Normalize an Odds API event into a prepared game payload.

    Args:
        event: Merged odds and score payload.
        score_event: Optional score payload.

    Returns:
        A normalized game payload ready for database upsert.
    """
    commence_time = parse_timestamp(_required_string(event, "commence_time"))
    home_team_name = _required_string(event, "home_team")
    away_team_name = _required_string(event, "away_team")
    home_score, away_score = extract_team_scores(
        score_event=score_event,
        home_team=home_team_name,
        away_team=away_team_name,
    )
    completed = bool(score_event and score_event.get("completed"))

    return PreparedGame(
        home_team_name=home_team_name,
        away_team_name=away_team_name,
        payload={
            "season": derive_cbb_season(commence_time),
            "date": commence_time.date().isoformat(),
            "commence_time": commence_time.isoformat(),
            "round": None,
            "source_event_id": _event_id(event),
            "sport_key": _optional_string(event.get("sport_key")),
            "sport_title": _optional_string(event.get("sport_title")),
            "result": determine_result(home_score, away_score, completed),
            "completed": completed,
            "home_score": home_score,
            "away_score": away_score,
            "last_score_update": parse_timestamp_or_none(
                score_event.get("last_update") if score_event is not None else None
            ),
        },
    )


def extract_team_scores(
    score_event: Mapping[str, object] | None,
    home_team: str,
    away_team: str,
) -> tuple[int | None, int | None]:
    """Extract home and away scores from a score payload.

    Args:
        score_event: Optional score payload from The Odds API.
        home_team: Home team name.
        away_team: Away team name.

    Returns:
        A ``(home_score, away_score)`` tuple.
    """
    if score_event is None:
        return None, None

    scores = {
        _required_string(entry, "name"): safe_int(entry.get("score"))
        for entry in _as_mapping_list(score_event.get("scores"))
    }
    return scores.get(home_team), scores.get(away_team)


def _merge_event_data(
    odds_event: Mapping[str, object] | None,
    score_event: Mapping[str, object] | None,
) -> dict[str, object]:
    event: dict[str, object] = {}
    if odds_event is not None:
        event.update(odds_event)
    if score_event is not None:
        event.update(
            {
                key: value
                for key, value in score_event.items()
                if key in SCORE_EVENT_FIELDS
            }
        )
    return event


def _ensure_event_list(data: object) -> list[dict[str, object]]:
    if isinstance(data, list):
        return [event for event in data if isinstance(event, dict)]
    raise TypeError("Expected a list response from The Odds API.")


def _event_id(event: Mapping[str, object]) -> str:
    return _required_string(event, "id")


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected {key!r} to be a string")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected optional string value, got {type(value).__name__}")


def _as_mapping_list(value: object) -> list[BookmakerPayload]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []
