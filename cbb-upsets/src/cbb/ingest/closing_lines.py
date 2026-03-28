"""Historical closing-odds ingest backed by The Odds API."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.engine import Connection

from cbb.db import get_engine
from cbb.ingest.clients.odds_api import DEFAULT_ODDS_REGIONS, OddsApiClient
from cbb.ingest.matching import TeamPairCandidate, match_team_pair
from cbb.ingest.models import (
    ApiQuota,
    ClosingOddsIngestSummary,
    HistoricalOddsResponse,
)
from cbb.ingest.persistence import (
    PreparedGame,
    ensure_odds_schema_extensions,
    upsert_odds_snapshots,
)
from cbb.ingest.utils import DEFAULT_CBB_SPORT, parse_timestamp, subtract_years

DEFAULT_CLOSING_ODDS_MARKET = "h2h"
DEFAULT_CLOSING_ODDS_YEARS = 5
DEFAULT_CLOSING_ODDS_SOURCE = "odds_api_historical_close"
SNAPSHOT_MATCH_WINDOW = timedelta(minutes=30)
MAX_PREVIOUS_SNAPSHOT_REPAIRS = 1

FETCH_COMPLETED_GAMES_SQL = text(
    """
    SELECT
        g.game_id,
        g.commence_time,
        home_team.name AS home_team_name,
        away_team.name AS away_team_name
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE g.completed
      AND g.commence_time IS NOT NULL
      AND g.date BETWEEN :start_date AND :end_date
    ORDER BY g.commence_time ASC, g.game_id ASC
    """
)

FETCH_MISSING_CLOSING_LINES_SQL_TEMPLATE = """
    SELECT
        g.game_id,
        g.commence_time,
        home_team.name AS home_team_name,
        away_team.name AS away_team_name
    FROM games AS g
    JOIN teams AS home_team ON home_team.team_id = g.team1_id
    JOIN teams AS away_team ON away_team.team_id = g.team2_id
    WHERE g.completed
      AND g.commence_time IS NOT NULL
      AND g.date BETWEEN :start_date AND :end_date
      AND ({missing_market_clause})
    ORDER BY g.commence_time ASC, g.game_id ASC
"""

FETCH_HISTORICAL_ODDS_CHECKPOINTS_SQL = text(
    """
    SELECT snapshot_time
    FROM historical_odds_checkpoints
    WHERE source_name = :source_name
      AND sport_key = :sport_key
      AND market_key = :market_key
      AND filters_key = :filters_key
      AND snapshot_time BETWEEN :start_time AND :end_time
    """
)

UPSERT_HISTORICAL_ODDS_CHECKPOINT_SQL = text(
    """
    INSERT INTO historical_odds_checkpoints (
        source_name,
        sport_key,
        market_key,
        filters_key,
        snapshot_time
    )
    VALUES (
        :source_name,
        :sport_key,
        :market_key,
        :filters_key,
        :snapshot_time
    )
    ON CONFLICT (
        source_name,
        sport_key,
        market_key,
        filters_key,
        snapshot_time
    ) DO NOTHING
    """
)


@dataclass(frozen=True)
class ClosingOddsIngestOptions:
    """Runtime options for historical closing-odds ingest."""

    years_back: int = DEFAULT_CLOSING_ODDS_YEARS
    start_date: date | None = None
    end_date: date | None = None
    force_refresh: bool = False
    ignore_checkpoints: bool = False
    sport: str = DEFAULT_CBB_SPORT
    market: str = DEFAULT_CLOSING_ODDS_MARKET
    regions: str = DEFAULT_ODDS_REGIONS
    bookmakers: str | None = None
    odds_format: str = "american"
    max_snapshots: int | None = None


@dataclass(frozen=True)
class ClosingLineGameCandidate:
    """Completed game that still needs a stored closing line."""

    game_id: int
    commence_time: datetime
    home_team_name: str
    away_team_name: str


def ingest_closing_odds(
    options: ClosingOddsIngestOptions,
    database_url: str | None = None,
    client: OddsApiClient | None = None,
    today: date | None = None,
) -> ClosingOddsIngestSummary:
    """Backfill historical closing odds for completed games.

    Args:
        options: Closing-odds ingest options.
        database_url: Optional database URL override.
        client: Optional Odds API client override.
        today: Optional current-date override for tests.

    Returns:
        A summary of the completed closing-odds ingest run.

    Raises:
        ValueError: If the requested date range or limits are invalid.
    """
    if options.years_back < 1:
        raise ValueError("years_back must be at least 1")
    requested_markets = _requested_markets(options.market)
    if not requested_markets:
        raise ValueError("market must include at least one market key")
    if options.max_snapshots is not None and options.max_snapshots < 1:
        raise ValueError("max_snapshots must be at least 1")

    resolved_end = options.end_date or today or datetime.now(UTC).date()
    resolved_start = options.start_date or subtract_years(
        resolved_end,
        options.years_back,
    )
    if resolved_start > resolved_end:
        raise ValueError("start_date must be on or before end_date")

    engine = get_engine(database_url)
    odds_client = client or OddsApiClient()
    quota = ApiQuota(remaining=None, used=None, last_cost=None)
    credits_spent = 0
    games_matched = 0
    games_unmatched = 0
    odds_snapshots_upserted = 0
    response_cache: dict[datetime, HistoricalOddsResponse] = {}

    with engine.begin() as connection:
        ensure_odds_schema_extensions(connection)
        candidates = _fetch_closing_line_candidates(
            connection, options, resolved_start, resolved_end
        )
        candidates_by_time = _group_candidates_by_time(candidates)
        all_snapshot_times = sorted(candidates_by_time)
        completed_snapshot_times = _fetch_completed_snapshot_times(
            connection=connection,
            options=options,
            snapshot_times=all_snapshot_times,
        )
        pending_snapshot_times = [
            snapshot_time
            for snapshot_time in all_snapshot_times
            if _ignores_checkpoint_skips(options)
            or snapshot_time not in completed_snapshot_times
        ]
        snapshot_slots_skipped = len(all_snapshot_times) - len(pending_snapshot_times)
        snapshot_slots_deferred = 0

        if (
            options.max_snapshots is not None
            and len(pending_snapshot_times) > options.max_snapshots
        ):
            snapshot_slots_deferred = (
                len(pending_snapshot_times) - options.max_snapshots
            )
            pending_snapshot_times = pending_snapshot_times[: options.max_snapshots]

    for snapshot_time in pending_snapshot_times:
        with engine.begin() as connection:
            (
                slot_upserts,
                slot_matches,
                slot_unmatched,
                slot_credits_spent,
                quota,
            ) = _repair_snapshot_time(
                connection=connection,
                options=options,
                odds_client=odds_client,
                snapshot_time=snapshot_time,
                candidates=candidates_by_time[snapshot_time],
                response_cache=response_cache,
            )
            credits_spent += slot_credits_spent
            odds_snapshots_upserted += slot_upserts
            games_matched += slot_matches
            games_unmatched += slot_unmatched

            connection.execute(
                UPSERT_HISTORICAL_ODDS_CHECKPOINT_SQL,
                {
                    "source_name": DEFAULT_CLOSING_ODDS_SOURCE,
                    "sport_key": options.sport,
                    "market_key": _normalized_market_key(options.market),
                    "filters_key": _filters_key(options),
                    "snapshot_time": snapshot_time.isoformat(),
                },
            )

    return ClosingOddsIngestSummary(
        sport=options.sport,
        market=_normalized_market_key(options.market),
        start_date=resolved_start.isoformat(),
        end_date=resolved_end.isoformat(),
        snapshot_slots_found=len(all_snapshot_times),
        snapshot_slots_requested=len(pending_snapshot_times),
        snapshot_slots_skipped=snapshot_slots_skipped,
        snapshot_slots_deferred=snapshot_slots_deferred,
        games_considered=len(candidates),
        games_matched=games_matched,
        games_unmatched=games_unmatched,
        odds_snapshots_upserted=odds_snapshots_upserted,
        credits_spent=credits_spent,
        quota=quota,
    )


def _fetch_closing_line_candidates(
    connection: Connection,
    options: ClosingOddsIngestOptions,
    start_date: date,
    end_date: date,
) -> list[ClosingLineGameCandidate]:
    if options.force_refresh:
        query = FETCH_COMPLETED_GAMES_SQL
    else:
        query = _build_missing_closing_lines_query(_requested_markets(options.market))
    parameters: dict[str, str] = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    if not options.force_refresh:
        for index, market_key in enumerate(_requested_markets(options.market)):
            parameters[f"market_key_{index}"] = market_key

    rows = connection.execute(query, parameters).mappings()
    return [
        ClosingLineGameCandidate(
            game_id=int(row["game_id"]),
            commence_time=parse_timestamp(row["commence_time"]),
            home_team_name=str(row["home_team_name"]),
            away_team_name=str(row["away_team_name"]),
        )
        for row in rows
    ]


def _group_candidates_by_time(
    candidates: Sequence[ClosingLineGameCandidate],
) -> dict[datetime, list[ClosingLineGameCandidate]]:
    grouped_candidates: dict[datetime, list[ClosingLineGameCandidate]] = defaultdict(
        list
    )
    for candidate in candidates:
        grouped_candidates[candidate.commence_time].append(candidate)
    return dict(grouped_candidates)


def _fetch_completed_snapshot_times(
    connection: Connection,
    options: ClosingOddsIngestOptions,
    snapshot_times: Sequence[datetime],
) -> set[datetime]:
    if _ignores_checkpoint_skips(options) or not snapshot_times:
        return set()

    rows = connection.execute(
        FETCH_HISTORICAL_ODDS_CHECKPOINTS_SQL,
        {
            "source_name": DEFAULT_CLOSING_ODDS_SOURCE,
            "sport_key": options.sport,
            "market_key": _normalized_market_key(options.market),
            "filters_key": _filters_key(options),
            "start_time": snapshot_times[0].isoformat(),
            "end_time": snapshot_times[-1].isoformat(),
        },
    ).mappings()
    return {parse_timestamp(row["snapshot_time"]) for row in rows}


def _ignores_checkpoint_skips(options: ClosingOddsIngestOptions) -> bool:
    """Return whether checkpointed snapshot times should still be revisited."""
    return options.force_refresh or options.ignore_checkpoints


def _persist_snapshot_time(
    connection: Connection,
    snapshot_time: datetime,
    candidates: Sequence[ClosingLineGameCandidate],
    events: Sequence[dict[str, object]],
) -> tuple[int, int, list[ClosingLineGameCandidate]]:
    relevant_events = _events_for_snapshot_time(events, snapshot_time)
    remaining_candidates = {candidate.game_id: candidate for candidate in candidates}
    odds_snapshots_upserted = 0
    games_matched = 0

    for event in relevant_events:
        matched_candidate = _match_candidate(
            event=event,
            candidates=list(remaining_candidates.values()),
        )
        if matched_candidate is None:
            continue

        bookmakers = _as_mapping_list(event.get("bookmakers"))
        inserted = upsert_odds_snapshots(
            connection=connection,
            game_id=matched_candidate.game_id,
            prepared_game=PreparedGame(
                # Keep stored team1/team2 orientation aligned to the game row even
                # when the provider's historical home/away labels are flipped.
                home_team_name=matched_candidate.home_team_name,
                away_team_name=matched_candidate.away_team_name,
                payload={},
            ),
            bookmakers=bookmakers,
            is_closing_line=True,
        )
        if inserted == 0:
            continue

        odds_snapshots_upserted += inserted
        games_matched += 1
        remaining_candidates.pop(matched_candidate.game_id)

    return (
        odds_snapshots_upserted,
        games_matched,
        list(remaining_candidates.values()),
    )


def _events_for_snapshot_time(
    events: Sequence[dict[str, object]],
    snapshot_time: datetime,
) -> list[dict[str, object]]:
    matching_events: list[dict[str, object]] = []

    for event in events:
        event_time_value = event.get("commence_time")
        if not isinstance(event_time_value, str):
            continue
        event_time = parse_timestamp(event_time_value)
        if abs(event_time - snapshot_time) <= SNAPSHOT_MATCH_WINDOW:
            matching_events.append(event)

    return matching_events


def _repair_snapshot_time(
    *,
    connection: Connection,
    options: ClosingOddsIngestOptions,
    odds_client: OddsApiClient,
    snapshot_time: datetime,
    candidates: Sequence[ClosingLineGameCandidate],
    response_cache: dict[datetime, HistoricalOddsResponse],
) -> tuple[int, int, int, int, ApiQuota]:
    remaining_candidates = list(candidates)
    request_time = snapshot_time
    requests_remaining = MAX_PREVIOUS_SNAPSHOT_REPAIRS + 1
    odds_snapshots_upserted = 0
    games_matched = 0
    credits_spent = 0
    quota = ApiQuota(remaining=None, used=None, last_cost=None)

    while remaining_candidates and requests_remaining > 0:
        response, fetched = _fetch_historical_snapshot(
            odds_client=odds_client,
            options=options,
            request_time=request_time,
            response_cache=response_cache,
        )
        quota = response.quota
        if fetched:
            credits_spent += response.quota.last_cost or 0

        slot_upserts, slot_matches, remaining_candidates = _persist_snapshot_time(
            connection=connection,
            snapshot_time=snapshot_time,
            candidates=remaining_candidates,
            events=response.data,
        )
        odds_snapshots_upserted += slot_upserts
        games_matched += slot_matches
        requests_remaining -= 1
        if not remaining_candidates:
            break

        previous_snapshot_time = _parse_previous_snapshot_time(
            response.previous_timestamp
        )
        if previous_snapshot_time is None or previous_snapshot_time >= request_time:
            break
        request_time = previous_snapshot_time

    return (
        odds_snapshots_upserted,
        games_matched,
        len(remaining_candidates),
        credits_spent,
        quota,
    )


def _fetch_historical_snapshot(
    *,
    odds_client: OddsApiClient,
    options: ClosingOddsIngestOptions,
    request_time: datetime,
    response_cache: dict[datetime, HistoricalOddsResponse],
) -> tuple[HistoricalOddsResponse, bool]:
    cached_response = response_cache.get(request_time)
    if cached_response is not None:
        return cached_response, False

    response = odds_client.get_historical_odds(
        date=request_time,
        sport=options.sport,
        regions=options.regions,
        markets=_normalized_market_key(options.market),
        bookmakers=options.bookmakers,
        odds_format=options.odds_format,
    )
    response_cache[request_time] = response
    return response, True


def _match_candidate(
    *,
    event: Mapping[str, object],
    candidates: Sequence[ClosingLineGameCandidate],
) -> ClosingLineGameCandidate | None:
    if not candidates:
        return None

    team_candidates = [
        TeamPairCandidate(
            candidate_id=candidate.game_id,
            home_team_name=candidate.home_team_name,
            away_team_name=candidate.away_team_name,
        )
        for candidate in candidates
    ]
    event_home_team = event.get("home_team")
    event_away_team = event.get("away_team")
    if not isinstance(event_home_team, str) or not isinstance(event_away_team, str):
        return None
    candidate_id = match_team_pair(
        home_team_name=event_home_team,
        away_team_name=event_away_team,
        candidates=team_candidates,
    )
    if candidate_id is None:
        candidate_id = match_team_pair(
            home_team_name=event_home_team,
            away_team_name=event_away_team,
            candidates=[
                TeamPairCandidate(
                    candidate_id=candidate.candidate_id,
                    home_team_name=candidate.away_team_name,
                    away_team_name=candidate.home_team_name,
                )
                for candidate in team_candidates
            ],
        )
    if candidate_id is None:
        return None
    return next(
        (candidate for candidate in candidates if candidate.game_id == candidate_id),
        None,
    )


def _parse_previous_snapshot_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    return parse_timestamp(value)


def _filters_key(options: ClosingOddsIngestOptions) -> str:
    if options.bookmakers:
        return f"regions:{options.regions}|bookmakers:{options.bookmakers}"
    return f"regions:{options.regions}"


def _requested_markets(market: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            piece.strip()
            for piece in market.split(",")
            if piece.strip()
        )
    )


def _normalized_market_key(market: str) -> str:
    return ",".join(_requested_markets(market))


def _build_missing_closing_lines_query(
    requested_markets: Sequence[str],
):
    market_clause = " OR ".join(
        """
        NOT EXISTS (
            SELECT 1
            FROM odds_snapshots AS odds
            WHERE odds.game_id = g.game_id
              AND odds.market_key = :market_key_{index}
              AND odds.is_closing_line
        )
        """.strip().format(index=index)
        for index, _market_key in enumerate(requested_markets)
    )
    return text(
        FETCH_MISSING_CLOSING_LINES_SQL_TEMPLATE.format(
            missing_market_clause=market_clause
        )
    )


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected {key!r} to be a string")


def _as_mapping_list(value: object) -> list[Mapping[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []
