"""One-iteration live refresh workflow for recent ESPN and current odds data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from cbb.db import get_latest_completed_game_date, get_latest_ingest_checkpoint_date
from cbb.ingest import (
    DEFAULT_ODDS_MARKETS,
    DEFAULT_ODDS_REGIONS,
    DEFAULT_ODDS_SPORT,
    HistoricalIngestOptions,
    OddsIngestOptions,
    ingest_current_odds,
    ingest_historical_games,
)
from cbb.ingest.models import HistoricalIngestSummary, OddsIngestSummary
from cbb.modeling import (
    DEFAULT_ARTIFACT_NAME,
    DEFAULT_STARTING_BANKROLL,
    PredictionOptions,
    PredictionSummary,
    predict_best_bets,
)

DEFAULT_AGENT_INGEST_CHECKPOINT_SOURCE = "espn_scoreboard"


@dataclass(frozen=True)
class AgentSyncOptions:
    """One live refresh-and-scan iteration configuration."""

    sport: str = DEFAULT_ODDS_SPORT
    espn_refresh_days: int = 3
    refresh_espn: bool = True
    refresh_odds: bool = True
    regions: str = DEFAULT_ODDS_REGIONS
    markets: str = DEFAULT_ODDS_MARKETS
    bookmakers: str | None = None
    odds_format: str = "american"
    include_scores: bool = True
    scores_days_from: int = 3
    scan_bets: bool = True
    artifact_name: str = DEFAULT_ARTIFACT_NAME
    bankroll: float = DEFAULT_STARTING_BANKROLL
    limit: int = 10


@dataclass(frozen=True)
class AgentSyncSummary:
    """Outcome of one live refresh cycle."""

    started_at: datetime
    completed_at: datetime
    espn_resume_anchor_date: date | None = None
    espn_resume_anchor_source: str = "recent_window"
    espn_effective_start_date: date | None = None
    espn_effective_end_date: date | None = None
    effective_scores_days_from: int | None = None
    espn_summary: HistoricalIngestSummary | None = None
    odds_summary: OddsIngestSummary | None = None
    prediction_summary: PredictionSummary | None = None
    prediction_error: str | None = None


def run_agent_sync(
    options: AgentSyncOptions,
    *,
    today: date | None = None,
    database_url: str | None = None,
) -> AgentSyncSummary:
    """Run one live refresh-and-scan iteration.

    The workflow stays single-iteration so the CLI can own the loop behavior.
    It refreshes a small recent ESPN window with ``force_refresh=True`` and
    optionally updates current odds and scores from The Odds API, then can
    scan the current upcoming board for best-path bets.
    """
    if not options.refresh_espn and not options.refresh_odds:
        raise ValueError("At least one live refresh source must be enabled.")
    if options.espn_refresh_days < 1:
        raise ValueError("espn_refresh_days must be at least 1.")
    if options.limit < 1:
        raise ValueError("limit must be at least 1.")
    if options.bankroll < 0:
        raise ValueError("bankroll must be non-negative.")

    started_at = datetime.now(UTC)
    resolved_today = today or started_at.date()
    recent_refresh_start = resolved_today - timedelta(
        days=options.espn_refresh_days - 1
    )
    latest_checkpoint_date = get_latest_ingest_checkpoint_date(
        source_name=DEFAULT_AGENT_INGEST_CHECKPOINT_SOURCE,
        sport_key=options.sport,
        database_url=database_url,
    )
    latest_completed_game_date = None
    resume_anchor_source = "checkpoint"
    resume_anchor_date = latest_checkpoint_date
    if resume_anchor_date is None:
        latest_completed_game_date = get_latest_completed_game_date(
            sport_key=options.sport,
            database_url=database_url,
        )
        resume_anchor_date = latest_completed_game_date
        resume_anchor_source = (
            "completed_game"
            if latest_completed_game_date is not None
            else "recent_window"
        )
    catch_up_start = (
        resume_anchor_date + timedelta(days=1)
        if resume_anchor_date is not None and resume_anchor_date < resolved_today
        else None
    )
    effective_start_date = (
        min(recent_refresh_start, catch_up_start)
        if catch_up_start is not None
        else recent_refresh_start
    )
    effective_scores_days_from = min(
        3,
        max(
            options.scores_days_from,
            (resolved_today - effective_start_date).days + 1,
        ),
    )

    espn_summary: HistoricalIngestSummary | None = None
    if options.refresh_espn:
        espn_summary = ingest_historical_games(
            HistoricalIngestOptions(
                years_back=1,
                start_date=effective_start_date,
                end_date=resolved_today,
                force_refresh=True,
                sport=options.sport,
            ),
            database_url=database_url,
        )

    odds_summary: OddsIngestSummary | None = None
    if options.refresh_odds:
        odds_summary = ingest_current_odds(
            OddsIngestOptions(
                sport=options.sport,
                regions=options.regions,
                markets=options.markets,
                bookmakers=options.bookmakers,
                odds_format=options.odds_format,
                include_scores=options.include_scores,
                days_from=effective_scores_days_from,
            ),
            database_url=database_url,
        )

    prediction_summary: PredictionSummary | None = None
    prediction_error: str | None = None
    if options.scan_bets:
        try:
            prediction_summary = predict_best_bets(
                PredictionOptions(
                    market="best",
                    artifact_name=options.artifact_name,
                    bankroll=options.bankroll,
                    limit=options.limit,
                    database_url=database_url,
                    now=datetime.now(UTC),
                )
            )
        except (FileNotFoundError, ValueError) as exc:
            prediction_error = str(exc)

    return AgentSyncSummary(
        started_at=started_at,
        completed_at=datetime.now(UTC),
        espn_resume_anchor_date=resume_anchor_date,
        espn_resume_anchor_source=resume_anchor_source,
        espn_effective_start_date=effective_start_date,
        espn_effective_end_date=resolved_today,
        effective_scores_days_from=effective_scores_days_from,
        espn_summary=espn_summary,
        odds_summary=odds_summary,
        prediction_summary=prediction_summary,
        prediction_error=prediction_error,
    )
