"""CLI for database setup, ingest, and betting-model workflows."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta, tzinfo
from functools import lru_cache
from pathlib import Path
from time import sleep
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer
from sqlalchemy.exc import OperationalError

from cbb.agent import AgentSyncOptions, AgentSyncSummary, run_agent_sync
from cbb.dashboard.snapshot import (
    is_canonical_dashboard_report_options,
    write_dashboard_snapshot,
)
from cbb.db import (
    GameSummary,
    OddsSnapshotSummary,
    get_database_summary,
    get_engine,
)
from cbb.db import (
    init_db as initialize_database,
)
from cbb.db_backup import (
    create_database_backup,
    import_database_backup,
)
from cbb.ingest import (
    DEFAULT_CLOSING_ODDS_MARKET,
    DEFAULT_CLOSING_ODDS_YEARS,
    DEFAULT_HISTORICAL_YEARS,
    DEFAULT_ODDS_MARKETS,
    DEFAULT_ODDS_REGIONS,
    DEFAULT_ODDS_SPORT,
    ClosingOddsIngestOptions,
    HistoricalIngestOptions,
    OddsIngestOptions,
    ingest_current_odds,
    ingest_historical_games,
    ingest_official_availability_reports,
)
from cbb.ingest import (
    ingest_closing_odds as run_ingest_closing_odds,
)
from cbb.ingest.utils import normalize_team_key
from cbb.modeling import (
    DEFAULT_ARTIFACT_NAME,
    DEFAULT_BACKTEST_RETRAIN_DAYS,
    DEFAULT_BEST_BACKTEST_REPORT_PATH,
    DEFAULT_EPOCHS,
    DEFAULT_L2_PENALTY,
    DEFAULT_LEARNING_RATE,
    DEFAULT_MIN_EXAMPLES,
    DEFAULT_MODEL_FAMILY,
    DEFAULT_MODEL_SEASONS_BACK,
    DEFAULT_SPREAD_MODEL_FAMILY,
    DEFAULT_STARTING_BANKROLL,
    DEFAULT_UNIT_SIZE,
    BacktestOptions,
    BestBacktestReportOptions,
    BetPolicy,
    LogisticRegressionConfig,
    ModelFamily,
    ModelMarket,
    PlacedBet,
    PredictionOptions,
    PredictionSummary,
    StrategyMarket,
    TrainingOptions,
    backtest_betting_model,
    generate_best_backtest_report,
    predict_best_bets,
    train_betting_model,
)
from cbb.modeling.infer import (
    AvailabilityGameContext,
    AvailabilitySideContext,
    DeferredRecommendation,
    LiveBoardGame,
    UpcomingGamePrediction,
)
from cbb.modeling.policy import (
    DEFAULT_DEPLOYABLE_SPREAD_POLICY,
    CandidateBet,
    SupportingQuote,
    settle_bet,
)
from cbb.modeling.tournament import (
    DEFAULT_TOURNAMENT_BRACKET_DIR,
    DEFAULT_TOURNAMENT_BRACKET_PATH,
    TournamentBacktestOptions,
    TournamentBacktestRoundSummary,
    TournamentBacktestSeasonSummary,
    TournamentBacktestSummary,
    TournamentGamePick,
    TournamentOptions,
    TournamentSummary,
    TournamentTeamAdvancement,
    backtest_tournament_model,
    predict_tournament_bracket,
)
from cbb.team_catalog import load_team_catalog, seed_team_catalog
from cbb.verify import (
    DEFAULT_VERIFICATION_YEARS,
    VerificationOptions,
    verify_games,
)

app = typer.Typer(
    help=(
        "CLI for NCAA men's basketball setup, ingest, deployable best-path "
        "reporting, prediction, and local dashboard workflows."
    )
)
db_app = typer.Typer(help="Database setup, inspection, backup, and audit commands.")
ingest_app = typer.Typer(
    help="Historical results and odds ingest commands. Some spend Odds API credits."
)
model_app = typer.Typer(
    help=(
        "Betting-model training, backtesting, reporting, and prediction. "
        "Use `model report` and `model predict --market best` for the "
        "current deployable path."
    )
)
report_app = typer.Typer(
    help=(
        "Canonical best-path report generation and recent settled-performance "
        "inspection commands."
    ),
    invoke_without_command=True,
    no_args_is_help=False,
)
app.add_typer(db_app, name="db")
app.add_typer(ingest_app, name="ingest")
app.add_typer(model_app, name="model")
model_app.add_typer(report_app, name="report")

AGENT_RECENT_FINAL_LOOKBACK_HOURS = 12
FANDUEL_COLLEGE_BASKETBALL_TEAM_URL = (
    "https://sportsbook.fanduel.com/teams/college-basketball/{team_key}/odds"
)


@app.command("dashboard")
def dashboard_command(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Host interface for the local dashboard server.",
    ),
    port: int = typer.Option(
        8765,
        "--port",
        min=0,
        max=65535,
        help="Port for the local dashboard server. Use 0 for an ephemeral port.",
    ),
    open_browser: bool = typer.Option(
        True,
        "--open/--no-open",
        help="Open the dashboard in the default browser after startup.",
    ),
    window_days: int = typer.Option(
        14,
        "--window-days",
        min=1,
        help="Default recent-performance window shown on the landing page.",
    ),
    report_ttl_seconds: int = typer.Option(
        300,
        "--report-ttl-seconds",
        min=0,
        help="Cache TTL for the canonical report payload.",
    ),
    prediction_ttl_seconds: int = typer.Option(
        90,
        "--prediction-ttl-seconds",
        min=0,
        help="Cache TTL for upcoming predictions.",
    ),
    team_ttl_seconds: int = typer.Option(
        600,
        "--team-ttl-seconds",
        min=0,
        help="Cache TTL for team search and detail payloads.",
    ),
) -> None:
    """Launch the local read-only dashboard for report, picks, and team review."""
    from cbb.ui.app import run_dashboard_server

    run_dashboard_server(
        host=host,
        port=port,
        open_browser=open_browser,
        window_days=window_days,
        report_ttl_seconds=report_ttl_seconds,
        prediction_ttl_seconds=prediction_ttl_seconds,
        team_ttl_seconds=team_ttl_seconds,
        announce=typer.echo,
    )


@app.command("agent")
def agent_command(
    sport: str = typer.Option(
        DEFAULT_ODDS_SPORT,
        help="Sport key for the looping live agent.",
    ),
    espn_refresh_days: int = typer.Option(
        3,
        "--espn-refresh-days",
        min=1,
        help="How many recent calendar days, including today, to re-fetch from ESPN.",
    ),
    refresh_espn: bool = typer.Option(
        True,
        "--espn/--no-espn",
        help="Refresh the recent ESPN scoreboard window.",
    ),
    refresh_odds: bool = typer.Option(
        True,
        "--odds/--no-odds",
        help="Refresh current Odds API odds and optional scores.",
    ),
    regions: str = typer.Option(
        DEFAULT_ODDS_REGIONS,
        "--regions",
        help="Comma-separated bookmaker regions for the current-odds refresh.",
    ),
    markets: str = typer.Option(
        DEFAULT_ODDS_MARKETS,
        "--markets",
        help="Comma-separated market keys for the current-odds refresh.",
    ),
    bookmakers: str | None = typer.Option(
        None,
        "--bookmakers",
        help="Optional bookmaker filter for the current-odds refresh.",
    ),
    odds_format: str = typer.Option(
        "american",
        "--odds-format",
        help="Odds format for the current-odds refresh.",
    ),
    include_scores: bool = typer.Option(
        True,
        "--include-scores/--no-include-scores",
        help="Also refresh recent scores from The Odds API current scores endpoint.",
    ),
    scores_days_from: int = typer.Option(
        3,
        "--scores-days-from",
        min=1,
        max=3,
        help="How many recent days of scores to request when scores are enabled.",
    ),
    scan_bets: bool = typer.Option(
        True,
        "--scan-bets/--no-scan-bets",
        help="Also scan the current upcoming board for best-path bets.",
    ),
    artifact_name: str = typer.Option(
        DEFAULT_ARTIFACT_NAME,
        "--artifact-name",
        help="Artifact name to use for the post-refresh bet scan.",
    ),
    bankroll: float = typer.Option(
        DEFAULT_STARTING_BANKROLL,
        "--bankroll",
        min=0.0,
        help="Bankroll scale to use for the post-refresh bet scan.",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        help="Maximum number of ranked bets to print from the post-refresh scan.",
    ),
    delay_mins: int = typer.Option(
        15,
        "--delay-mins",
        min=1,
        help="Minutes to sleep between looping agent runs.",
    ),
) -> None:
    """Run the local refresh-and-bet-scan agent loop until interrupted."""
    sync_options = _build_agent_sync_options(
        sport=sport,
        espn_refresh_days=espn_refresh_days,
        refresh_espn=refresh_espn,
        refresh_odds=refresh_odds,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
        odds_format=odds_format,
        include_scores=include_scores,
        scores_days_from=scores_days_from,
        scan_bets=scan_bets,
        artifact_name=artifact_name,
        bankroll=bankroll,
        limit=limit,
    )
    typer.echo(
        "Starting agent loop: "
        f"delay_mins={delay_mins}, "
        f"espn={'on' if refresh_espn else 'off'}, "
        f"odds={'on' if refresh_odds else 'off'}, "
        f"scan_bets={'on' if scan_bets else 'off'}"
    )
    iteration = 0
    try:
        while True:
            iteration += 1
            typer.echo(f"Agent iteration {iteration}:")
            try:
                summary = run_agent_sync(sync_options)
            except (OperationalError, RuntimeError) as exc:
                typer.echo(f"  Agent run failed: {exc}", err=True)
            else:
                _echo_agent_sync_summary(summary, scan_bets_enabled=scan_bets)
            typer.echo(
                f"  Sleeping for {delay_mins} minute(s) before the next run..."
            )
            sleep(delay_mins * 60)
    except KeyboardInterrupt:
        typer.echo("Agent loop stopped.")


def _build_agent_sync_options(
    *,
    sport: str,
    espn_refresh_days: int,
    refresh_espn: bool,
    refresh_odds: bool,
    regions: str,
    markets: str,
    bookmakers: str | None,
    odds_format: str,
    include_scores: bool,
    scores_days_from: int,
    scan_bets: bool,
    artifact_name: str,
    bankroll: float,
    limit: int,
) -> AgentSyncOptions:
    """Build one agent iteration options payload from CLI arguments."""
    return AgentSyncOptions(
        sport=sport,
        espn_refresh_days=espn_refresh_days,
        refresh_espn=refresh_espn,
        refresh_odds=refresh_odds,
        regions=regions,
        markets=markets,
        bookmakers=bookmakers,
        odds_format=odds_format,
        include_scores=include_scores,
        scores_days_from=scores_days_from,
        scan_bets=scan_bets,
        artifact_name=artifact_name,
        bankroll=bankroll,
        limit=limit,
    )


def _echo_agent_sync_summary(
    summary: AgentSyncSummary,
    *,
    scan_bets_enabled: bool,
) -> None:
    """Render one agent run summary."""
    typer.echo(
        "Agent run: "
        f"started={summary.started_at.isoformat()}, "
        f"completed={summary.completed_at.isoformat()}"
    )
    typer.echo(
        "  Catch-up state: "
        f"resume_anchor_source={summary.espn_resume_anchor_source}, "
        f"resume_anchor_date={summary.espn_resume_anchor_date}, "
        f"espn_window={summary.espn_effective_start_date}.."
        f"{summary.espn_effective_end_date}"
    )
    if summary.espn_summary is not None:
        typer.echo(
            "  ESPN refresh: "
            "range="
            f"{summary.espn_summary.start_date}..{summary.espn_summary.end_date}, "
            f"dates_requested={summary.espn_summary.dates_requested}, "
            f"dates_skipped={summary.espn_summary.dates_skipped}, "
            f"games_seen={summary.espn_summary.games_seen}, "
            f"games_inserted={summary.espn_summary.games_inserted}, "
            f"games_skipped={summary.espn_summary.games_skipped}"
        )
    else:
        typer.echo("  ESPN refresh: disabled")

    if summary.odds_summary is not None:
        typer.echo(
            "  Odds refresh: "
            f"games={summary.odds_summary.games_upserted}, "
            f"games_skipped={summary.odds_summary.games_skipped}, "
            f"completed_games={summary.odds_summary.completed_games_updated}, "
            f"odds_snapshots={summary.odds_summary.odds_snapshots_upserted}, "
            f"scores_days_from={summary.effective_scores_days_from}"
        )
        typer.echo(
            "  Odds quota: "
            f"used={summary.odds_summary.odds_quota.used}, "
            f"remaining={summary.odds_summary.odds_quota.remaining}, "
            f"last_cost={summary.odds_summary.odds_quota.last_cost}"
        )
        if summary.odds_summary.scores_quota is not None:
            typer.echo(
                "  Scores quota: "
                f"used={summary.odds_summary.scores_quota.used}, "
                f"remaining={summary.odds_summary.scores_quota.remaining}, "
                f"last_cost={summary.odds_summary.scores_quota.last_cost}"
            )
    else:
        typer.echo("  Odds refresh: disabled")

    if not scan_bets_enabled:
        typer.echo("  Bet scan: disabled")
    elif summary.prediction_error is not None:
        typer.echo(f"  Bet scan: skipped ({summary.prediction_error})")
    elif summary.prediction_summary is not None:
        prediction_summary = summary.prediction_summary
        typer.echo(
            "  Bet scan: "
            f"available_games={prediction_summary.available_games}, "
            f"recommendations={prediction_summary.bets_placed}, "
            f"deferred={len(prediction_summary.deferred_recommendations)}, "
            f"artifact={prediction_summary.artifact_name}, "
            "generated="
            f"{_format_optional_datetime_iso(prediction_summary.generated_at)}, "
            f"expires={_format_optional_datetime_iso(prediction_summary.expires_at)}"
        )
        if prediction_summary.recommendations:
            typer.echo("  Qualified bets:")
            _echo_agent_betting_recommendations(
                prediction_summary.recommendations,
                unit_size=DEFAULT_UNIT_SIZE,
            )
        elif prediction_summary.deferred_recommendations:
            typer.echo("  Wait list:")
            _echo_simple_deferred_recommendations(
                prediction_summary.deferred_recommendations
            )
        tracked_games = _select_agent_scoreboard_games(
            prediction_summary.live_board_games,
            reference_time=prediction_summary.generated_at or summary.completed_at,
        )
        if tracked_games:
            typer.echo("  Live scores / recent finals:")
            _echo_agent_scoreboard_games(tracked_games)
    else:
        typer.echo("  Bet scan: no summary returned")


@db_app.command("init")
def init_db_command() -> None:
    """Initialize the PostgreSQL schema from ``sql/schema.sql``."""
    schema_path = initialize_database()
    team_catalog = load_team_catalog()
    with get_engine().begin() as connection:
        team_ids_by_key = seed_team_catalog(connection, team_catalog)
    typer.echo(
        f"Initialized database schema from {schema_path} and seeded "
        f"{len(team_ids_by_key)} canonical D1 teams"
    )


@db_app.command("summary")
def db_summary_command() -> None:
    """Show a concise summary of the currently loaded database contents."""
    summary = get_database_summary()

    typer.echo("Counts")
    typer.echo(f"  teams: {summary.teams}")
    typer.echo(f"  games: {summary.games}")
    typer.echo(f"  completed_games: {summary.completed_games}")
    typer.echo(f"  upcoming_games: {summary.upcoming_games}")
    typer.echo(f"  odds_snapshots: {summary.odds_snapshots}")
    typer.echo("")
    typer.echo("Date Range")
    typer.echo(f"  first_game_time: {summary.first_game_time}")
    typer.echo(f"  last_game_time: {summary.last_game_time}")
    typer.echo("")
    typer.echo("Completed Samples")
    _echo_game_samples(summary.completed_samples, include_scores=True)
    typer.echo("")
    typer.echo("Upcoming Samples")
    _echo_game_samples(summary.upcoming_samples, include_scores=False)
    typer.echo("")
    typer.echo("Odds Samples")
    _echo_odds_samples(summary.odds_samples)


@ingest_app.command("odds")
def ingest_odds_command(
    sport: str = typer.Option(
        DEFAULT_ODDS_SPORT,
        "--sport",
        help="Sport key, e.g. basketball_ncaab.",
    ),
    regions: str = typer.Option(
        DEFAULT_ODDS_REGIONS,
        "--regions",
        help="Comma-separated bookmaker regions.",
    ),
    markets: str = typer.Option(
        DEFAULT_ODDS_MARKETS,
        "--markets",
        help="Comma-separated market keys.",
    ),
    bookmakers: str | None = typer.Option(
        None, "--bookmakers", help="Optional bookmaker key filter."
    ),
    odds_format: str = typer.Option(
        "american", "--odds-format", help="american or decimal."
    ),
    include_scores: bool = typer.Option(
        True,
        "--include-scores/--no-include-scores",
        help="Also sync live/recent scores from the scores endpoint.",
    ),
    days_from: int = typer.Option(
        3,
        "--days-from",
        min=1,
        max=3,
        help=(
            "How many days of completed scores to sync when include-scores is enabled."
        ),
    ),
):
    """Load current odds, events, and optional scores from The Odds API."""
    summary = ingest_current_odds(
        options=OddsIngestOptions(
            sport=sport,
            regions=regions,
            markets=markets,
            bookmakers=bookmakers,
            odds_format=odds_format,
            include_scores=include_scores,
            days_from=days_from,
        )
    )
    typer.echo(
        f"Ingested {summary.sport}: "
        f"teams={summary.teams_seen}, "
        f"games={summary.games_upserted}, "
        f"games_skipped={summary.games_skipped}, "
        f"completed_games={summary.completed_games_updated}, "
        f"odds_snapshots={summary.odds_snapshots_upserted}"
    )
    typer.echo(
        f"Odds quota: used={summary.odds_quota.used}, "
        f"remaining={summary.odds_quota.remaining}, "
        f"last_cost={summary.odds_quota.last_cost}"
    )
    if summary.scores_quota:
        typer.echo(
            f"Scores quota: used={summary.scores_quota.used}, "
            f"remaining={summary.scores_quota.remaining}, "
            f"last_cost={summary.scores_quota.last_cost}"
        )


@ingest_app.command("data")
def ingest_data_command(
    years_back: int = typer.Option(
        DEFAULT_HISTORICAL_YEARS,
        "--years-back",
        min=1,
        help="Rolling historical backfill window in years.",
    ),
    start_date: str | None = typer.Option(
        None,
        "--start-date",
        help="Optional ISO date override (YYYY-MM-DD).",
    ),
    end_date: str | None = typer.Option(
        None,
        "--end-date",
        help="Optional ISO date override (YYYY-MM-DD). Defaults to today.",
    ),
    force_refresh: bool = typer.Option(
        False,
        "--force-refresh",
        help="Re-fetch dates even if they were already checkpointed.",
    ),
):
    """Backfill historical NCAA Division I game results."""
    summary = ingest_historical_games(
        options=HistoricalIngestOptions(
            years_back=years_back,
            start_date=_parse_date_option(start_date, "start-date"),
            end_date=_parse_date_option(end_date, "end-date"),
            force_refresh=force_refresh,
        )
    )
    typer.echo(
        f"Ingested historical {summary.sport}: "
        f"range={summary.start_date}..{summary.end_date}, "
        f"dates_requested={summary.dates_requested}, "
        f"dates_skipped={summary.dates_skipped}, "
        f"games_seen={summary.games_seen}, "
        f"games_inserted={summary.games_inserted}, "
        f"games_skipped={summary.games_skipped}, "
        f"teams={summary.teams_seen}"
    )


@ingest_app.command("availability")
def ingest_availability_command(
    paths: list[Path] = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help=(
            "One or more local JSON files or directories containing captured "
            "official availability capture payloads."
        ),
    ),
) -> None:
    """Import captured official availability reports from local JSON files."""
    try:
        summary = ingest_official_availability_reports(paths=paths)
    except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        "Imported official NCAA availability: "
        f"snapshots_imported={summary.snapshots_imported}, "
        f"player_rows_imported={summary.player_rows_imported}, "
        f"games_matched={summary.games_matched}, "
        f"teams_matched={summary.teams_matched}, "
        f"rows_unmatched={summary.rows_unmatched}, "
        f"duplicates_skipped={summary.duplicates_skipped}"
    )


@db_app.command("audit")
def db_audit_command(
    years_back: int = typer.Option(
        DEFAULT_VERIFICATION_YEARS,
        "--years-back",
        min=1,
        help="Rolling verification window in years.",
    ),
    start_date: str | None = typer.Option(
        None,
        "--start-date",
        help="Optional ISO date override (YYYY-MM-DD).",
    ),
    end_date: str | None = typer.Option(
        None,
        "--end-date",
        help="Optional ISO date override (YYYY-MM-DD). Defaults to today.",
    ),
):
    """Verify stored D1 games against ESPN coverage, scores, and context."""
    summary = verify_games(
        VerificationOptions(
            years_back=years_back,
            start_date=_parse_date_option(start_date, "start-date"),
            end_date=_parse_date_option(end_date, "end-date"),
        )
    )
    typer.echo(
        f"Verified {summary.sport}: "
        f"range={summary.start_date}..{summary.end_date}, "
        f"dates_checked={summary.dates_checked}, "
        f"upstream_games={summary.upstream_games_seen}, "
        f"upstream_games_skipped={summary.upstream_games_skipped}, "
        f"games_present={summary.games_present}, "
        f"games_verified={summary.games_verified}, "
        f"games_missing={summary.games_missing}, "
        f"status_mismatches={summary.status_mismatches}, "
        f"score_mismatches={summary.score_mismatches}, "
        f"context_mismatches={summary.context_mismatches}"
    )
    _echo_samples("Missing Samples", summary.sample_missing_games)
    _echo_samples("Status Mismatch Samples", summary.sample_status_mismatches)
    _echo_samples("Score Mismatch Samples", summary.sample_score_mismatches)
    _echo_samples("Context Mismatch Samples", summary.sample_context_mismatches)


@db_app.command("backup")
def db_backup_command(
    name: str | None = typer.Option(
        None,
        "--name",
        help="Optional backup file name. The dump is stored under backups/.",
    ),
) -> None:
    """Create a repo-local SQL backup of the configured Postgres database."""
    try:
        artifact = create_database_backup(backup_name=name)
    except (FileExistsError, RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Created backup: {_format_repo_path(artifact.path)} "
        f"({artifact.size_bytes} bytes)"
    )


@db_app.command("import")
def db_import_command(
    backup_name_or_path: str = typer.Argument(
        ...,
        help="Backup file name from backups/ or a path to a .sql dump.",
    ),
) -> None:
    """Replace the configured Postgres contents with a SQL backup."""
    try:
        artifact = import_database_backup(backup_name_or_path)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Imported backup: {_format_repo_path(artifact.path)}")


@ingest_app.command("closing-odds")
def ingest_closing_odds_command(
    years_back: int = typer.Option(
        DEFAULT_CLOSING_ODDS_YEARS,
        "--years-back",
        min=1,
        help="Rolling historical backfill window in years.",
    ),
    start_date: str | None = typer.Option(
        None,
        "--start-date",
        help="Optional ISO date override (YYYY-MM-DD).",
    ),
    end_date: str | None = typer.Option(
        None,
        "--end-date",
        help="Optional ISO date override (YYYY-MM-DD). Defaults to today.",
    ),
    market: str = typer.Option(
        DEFAULT_CLOSING_ODDS_MARKET,
        "--market",
        help=(
            "Historical market key or comma-separated keys. Start with h2h for "
            "moneyline closes, or use h2h,spreads,totals for a combined pass."
        ),
    ),
    regions: str = typer.Option(
        "us",
        "--regions",
        help="Comma-separated bookmaker regions for historical featured markets.",
    ),
    bookmakers: str | None = typer.Option(
        None,
        "--bookmakers",
        help=(
            "Optional comma-separated bookmaker key filter. When set, this "
            "overrides broad region selection at the API layer."
        ),
    ),
    force_refresh: bool = typer.Option(
        False,
        "--force-refresh",
        help="Re-fetch slots even if they were already checkpointed.",
    ),
    ignore_checkpoints: bool = typer.Option(
        False,
        "--ignore-checkpoints",
        help=(
            "Revisit checkpointed snapshot times while still limiting the run "
            "to games missing a closing line."
        ),
    ),
    max_snapshots: int | None = typer.Option(
        None,
        "--max-snapshots",
        min=1,
        help="Optional cap on historical snapshot requests for the run.",
    ),
):
    """Backfill historical closing odds for completed games."""
    summary = run_ingest_closing_odds(
        options=ClosingOddsIngestOptions(
            years_back=years_back,
            start_date=_parse_date_option(start_date, "start-date"),
            end_date=_parse_date_option(end_date, "end-date"),
            market=market,
            regions=regions,
            bookmakers=bookmakers,
            force_refresh=force_refresh,
            ignore_checkpoints=ignore_checkpoints,
            max_snapshots=max_snapshots,
        )
    )
    typer.echo(
        f"Ingested closing odds {summary.sport}/{summary.market}: "
        f"range={summary.start_date}..{summary.end_date}, "
        f"snapshot_slots_found={summary.snapshot_slots_found}, "
        f"snapshot_slots_requested={summary.snapshot_slots_requested}, "
        f"snapshot_slots_skipped={summary.snapshot_slots_skipped}, "
        f"snapshot_slots_deferred={summary.snapshot_slots_deferred}, "
        f"games_considered={summary.games_considered}, "
        f"games_matched={summary.games_matched}, "
        f"games_unmatched={summary.games_unmatched}, "
        f"odds_snapshots={summary.odds_snapshots_upserted}, "
        f"credits_spent={summary.credits_spent}"
    )
    typer.echo(
        f"Odds quota: used={summary.quota.used}, "
        f"remaining={summary.quota.remaining}, "
        f"last_cost={summary.quota.last_cost}"
    )


@model_app.command("train")
def model_train_command(
    market: str = typer.Option(
        "moneyline",
        "--market",
        help="Model market to train: moneyline or spread.",
    ),
    seasons_back: int = typer.Option(
        DEFAULT_MODEL_SEASONS_BACK,
        "--seasons-back",
        min=1,
        help="Rolling season window used for training.",
    ),
    max_season: int | None = typer.Option(
        None,
        "--max-season",
        help="Optional latest season to include in training.",
    ),
    artifact_name: str = typer.Option(
        DEFAULT_ARTIFACT_NAME,
        "--artifact-name",
        help="Artifact name written under artifacts/models/.",
    ),
    model_family: str = typer.Option(
        DEFAULT_MODEL_FAMILY,
        "--model-family",
        help="Underlying model family: logistic or hist_gradient_boosting.",
    ),
    epochs: int = typer.Option(
        DEFAULT_EPOCHS,
        "--epochs",
        min=1,
        help="Gradient-descent epochs for the baseline logistic model.",
    ),
    learning_rate: float = typer.Option(
        DEFAULT_LEARNING_RATE,
        "--learning-rate",
        min=0.0001,
        help="Gradient-descent learning rate.",
    ),
    l2_penalty: float = typer.Option(
        DEFAULT_L2_PENALTY,
        "--l2-penalty",
        min=0.0,
        help="L2 regularization penalty.",
    ),
    min_examples: int = typer.Option(
        DEFAULT_MIN_EXAMPLES,
        "--min-examples",
        min=1,
        help="Minimum training examples required before fitting.",
    ),
) -> None:
    """Train one betting-model artifact from stored game data."""
    try:
        summary = train_betting_model(
            TrainingOptions(
                market=_parse_model_market(market),
                seasons_back=seasons_back,
                max_season=max_season,
                artifact_name=artifact_name,
                model_family=_parse_model_family(model_family),
                config=LogisticRegressionConfig(
                    learning_rate=learning_rate,
                    epochs=epochs,
                    l2_penalty=l2_penalty,
                    min_examples=min_examples,
                ),
            )
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Trained {summary.market} model: "
        f"family={summary.model_family}, "
        f"seasons={summary.start_season}..{summary.end_season}, "
        f"examples={summary.examples}, "
        f"priced_examples={summary.priced_examples}, "
        f"training_examples={summary.training_examples}, "
        f"log_loss={summary.log_loss:.4f}, "
        f"brier_score={summary.brier_score:.4f}, "
        f"accuracy={summary.accuracy:.4f}, "
        f"blend={summary.market_blend_weight:.2f}, "
        f"max_delta={summary.max_market_probability_delta:.2f}"
    )
    typer.echo(f"Artifact: {_format_repo_path(summary.artifact_path)}")


def _build_backtest_options(
    *,
    market: str,
    seasons_back: int,
    evaluation_season: int | None,
    starting_bankroll: float,
    unit_size: float,
    retrain_days: int,
    auto_tune_spread_policy: bool,
    use_timing_layer: bool,
    spread_model_family: str,
    min_edge: float,
    min_confidence: float,
    min_probability_edge: float,
    min_games_played: int,
    kelly_fraction: float,
    max_bet_fraction: float,
    max_daily_exposure_fraction: float,
    min_moneyline_price: float,
    max_moneyline_price: float,
    max_spread_abs_line: float | None,
    max_abs_rest_days_diff: float | None,
    min_positive_ev_books: int,
    min_median_expected_value: float | None,
    epochs: int,
    learning_rate: float,
    l2_penalty: float,
    min_examples: int,
) -> BacktestOptions:
    """Build one backtest options object from shared CLI arguments."""
    parsed_market = _parse_strategy_market(market)
    return BacktestOptions(
        market=parsed_market,
        seasons_back=seasons_back,
        evaluation_season=evaluation_season,
        starting_bankroll=starting_bankroll,
        unit_size=unit_size,
        retrain_days=retrain_days,
        auto_tune_spread_policy=auto_tune_spread_policy,
        use_timing_layer=use_timing_layer,
        spread_model_family=_parse_model_family(spread_model_family),
        policy=BetPolicy(
            min_edge=min_edge,
            min_confidence=min_confidence,
            min_probability_edge=min_probability_edge,
            uncertainty_probability_buffer=(
                DEFAULT_DEPLOYABLE_SPREAD_POLICY.uncertainty_probability_buffer
                if parsed_market in {"spread", "best"}
                else BetPolicy().uncertainty_probability_buffer
            ),
            min_games_played=min_games_played,
            kelly_fraction=kelly_fraction,
            max_bet_fraction=max_bet_fraction,
            max_daily_exposure_fraction=max_daily_exposure_fraction,
            max_bets_per_day=(
                DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_bets_per_day
                if parsed_market in {"spread", "best"}
                else BetPolicy().max_bets_per_day
            ),
            min_moneyline_price=min_moneyline_price,
            max_moneyline_price=max_moneyline_price,
            max_spread_abs_line=max_spread_abs_line,
            max_abs_rest_days_diff=max_abs_rest_days_diff,
            min_positive_ev_books=min_positive_ev_books,
            min_median_expected_value=min_median_expected_value,
        ),
        config=LogisticRegressionConfig(
            learning_rate=learning_rate,
            epochs=epochs,
            l2_penalty=l2_penalty,
            min_examples=min_examples,
        ),
    )


@model_app.command("backtest")
def model_backtest_command(
    market: str = typer.Option(
        "best",
        "--market",
        help="Strategy market: moneyline, spread, or best.",
    ),
    seasons_back: int = typer.Option(
        DEFAULT_MODEL_SEASONS_BACK,
        "--seasons-back",
        min=1,
        help="Rolling season window available for walk-forward training.",
    ),
    evaluation_season: int | None = typer.Option(
        None,
        "--evaluation-season",
        help="Optional evaluation season. Defaults to the latest loaded season.",
    ),
    starting_bankroll: float = typer.Option(
        DEFAULT_STARTING_BANKROLL,
        "--starting-bankroll",
        min=0.01,
        help="Starting bankroll used for the simulation.",
    ),
    unit_size: float = typer.Option(
        25.0,
        "--unit-size",
        min=0.01,
        help="Dollar unit used when reporting units won.",
    ),
    retrain_days: int = typer.Option(
        DEFAULT_BACKTEST_RETRAIN_DAYS,
        "--retrain-days",
        min=1,
        help="How many days of games to score before refitting the model.",
    ),
    auto_tune_spread_policy: bool = typer.Option(
        False,
        "--auto-tune-spread-policy/--no-auto-tune-spread-policy",
        help="Tune spread deployment filters on prior walk-forward blocks only.",
    ),
    use_timing_layer: bool = typer.Option(
        False,
        "--use-timing-layer/--no-use-timing-layer",
        help=(
            "For spread bets, only keep early candidates when the closing-line "
            "layer expects the market to move in your favor."
        ),
    ),
    spread_model_family: str = typer.Option(
        DEFAULT_SPREAD_MODEL_FAMILY,
        "--spread-model-family",
        help="Spread model family used during walk-forward training blocks.",
    ),
    min_edge: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_edge,
        "--min-edge",
        help="Minimum expected value required to place a bet.",
    ),
    min_confidence: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_confidence,
        "--min-confidence",
        min=0.0,
        max=1.0,
        help="Minimum model probability required to place a bet.",
    ),
    min_probability_edge: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_probability_edge,
        "--min-probability-edge",
        help="Minimum model-minus-market probability edge required to place a bet.",
    ),
    min_games_played: int = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_games_played,
        "--min-games-played",
        min=0,
        help="Minimum prior games each team must have before the model can bet.",
    ),
    kelly_fraction: float = typer.Option(
        0.10,
        "--kelly-fraction",
        min=0.0,
        help="Fraction of full Kelly stake to use.",
    ),
    max_bet_fraction: float = typer.Option(
        0.02,
        "--max-bet-fraction",
        min=0.0,
        help="Maximum stake per bet as a fraction of bankroll.",
    ),
    max_daily_exposure_fraction: float = typer.Option(
        0.05,
        "--max-daily-exposure-fraction",
        min=0.0,
        help="Maximum total daily exposure as a fraction of bankroll.",
    ),
    min_moneyline_price: float = typer.Option(
        BetPolicy().min_moneyline_price,
        "--min-moneyline-price",
        help="Lowest moneyline price eligible for betting.",
    ),
    max_moneyline_price: float = typer.Option(
        BetPolicy().max_moneyline_price,
        "--max-moneyline-price",
        help="Highest moneyline price eligible for betting.",
    ),
    max_spread_abs_line: float | None = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_spread_abs_line,
        "--max-spread-abs-line",
        min=0.0,
        help="Maximum absolute spread line eligible for betting.",
    ),
    max_abs_rest_days_diff: float | None = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_abs_rest_days_diff,
        "--max-abs-rest-days-diff",
        min=0.0,
        help="Maximum allowed rest-days gap for deployable spread picks.",
    ),
    min_positive_ev_books: int = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_positive_ev_books,
        "--min-positive-ev-books",
        min=1,
        help="Minimum number of books that must show positive EV on one side.",
    ),
    min_median_expected_value: float | None = typer.Option(
        BetPolicy().min_median_expected_value,
        "--min-median-expected-value",
        help=(
            "Minimum median expected value across eligible books on one side. "
            "Disabled by default."
        ),
    ),
    epochs: int = typer.Option(
        DEFAULT_EPOCHS,
        "--epochs",
        min=1,
        help="Gradient-descent epochs for each walk-forward refit.",
    ),
    learning_rate: float = typer.Option(
        DEFAULT_LEARNING_RATE,
        "--learning-rate",
        min=0.0001,
        help="Gradient-descent learning rate for each walk-forward refit.",
    ),
    l2_penalty: float = typer.Option(
        DEFAULT_L2_PENALTY,
        "--l2-penalty",
        min=0.0,
        help="L2 regularization penalty for each walk-forward refit.",
    ),
    min_examples: int = typer.Option(
        DEFAULT_MIN_EXAMPLES,
        "--min-examples",
        min=1,
        help="Minimum training examples required before each refit.",
    ),
) -> None:
    """Run a walk-forward bankroll backtest on stored completed games."""
    try:
        summary = backtest_betting_model(
            _build_backtest_options(
                market=market,
                seasons_back=seasons_back,
                evaluation_season=evaluation_season,
                starting_bankroll=starting_bankroll,
                unit_size=unit_size,
                retrain_days=retrain_days,
                auto_tune_spread_policy=auto_tune_spread_policy,
                use_timing_layer=use_timing_layer,
                spread_model_family=spread_model_family,
                min_edge=min_edge,
                min_confidence=min_confidence,
                min_probability_edge=min_probability_edge,
                min_games_played=min_games_played,
                kelly_fraction=kelly_fraction,
                max_bet_fraction=max_bet_fraction,
                max_daily_exposure_fraction=max_daily_exposure_fraction,
                min_moneyline_price=min_moneyline_price,
                max_moneyline_price=max_moneyline_price,
                max_spread_abs_line=max_spread_abs_line,
                max_abs_rest_days_diff=max_abs_rest_days_diff,
                min_positive_ev_books=min_positive_ev_books,
                min_median_expected_value=min_median_expected_value,
                epochs=epochs,
                learning_rate=learning_rate,
                l2_penalty=l2_penalty,
                min_examples=min_examples,
            )
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Backtested {summary.market}: "
        f"seasons={summary.start_season}..{summary.end_season}, "
        f"evaluation_season={summary.evaluation_season}, "
        f"blocks={summary.blocks}, "
        f"candidates={summary.candidates_considered}, "
        f"bets={summary.bets_placed}"
    )
    typer.echo(
        f"Bankroll: start=${summary.starting_bankroll:.2f}, "
        f"end=${summary.ending_bankroll:.2f}, "
        f"profit=${summary.profit:.2f}, "
        f"roi={summary.roi:.4f}, "
        f"units_won={summary.units_won:.2f}, "
        f"max_drawdown={summary.max_drawdown:.4f}"
    )
    typer.echo(
        f"Settlements: wins={summary.wins}, "
        f"losses={summary.losses}, "
        f"pushes={summary.pushes}, "
        f"total_staked=${summary.total_staked:.2f}"
    )
    typer.echo(f"CLV: {_format_backtest_clv_summary(summary.clv)}")
    if summary.final_policy is not None:
        policy_label = (
            "Auto-Tuned Spread Policy"
            if summary.policy_tuned_blocks > 0
            else "Applied Spread Policy"
        )
        typer.echo(
            f"{policy_label}: "
            f"blocks={summary.policy_tuned_blocks}, "
            f"{_format_policy_controls(summary.final_policy)}"
        )
    if summary.sample_bets:
        typer.echo("")
        typer.echo("Sample Bets")
        _echo_betting_recommendations(summary.sample_bets)


@report_app.command("recent")
def model_report_recent_command(
    market: str = typer.Option(
        "best",
        "--market",
        help="Strategy market: moneyline, spread, or best.",
    ),
    days: int = typer.Option(
        7,
        "--days",
        min=1,
        help="Show simulated bets from the trailing N days anchored to the latest bet.",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        min=1,
        help="Maximum number of recent simulated bets to display.",
    ),
    seasons_back: int = typer.Option(
        DEFAULT_MODEL_SEASONS_BACK,
        "--seasons-back",
        min=1,
        help="Rolling season window available for walk-forward training.",
    ),
    evaluation_season: int | None = typer.Option(
        None,
        "--evaluation-season",
        help="Optional evaluation season. Defaults to the latest loaded season.",
    ),
    starting_bankroll: float = typer.Option(
        DEFAULT_STARTING_BANKROLL,
        "--starting-bankroll",
        min=0.01,
        help="Starting bankroll used for the simulation.",
    ),
    unit_size: float = typer.Option(
        DEFAULT_UNIT_SIZE,
        "--unit-size",
        min=0.01,
        help="Dollar unit used when reporting recent simulated bets.",
    ),
    retrain_days: int = typer.Option(
        DEFAULT_BACKTEST_RETRAIN_DAYS,
        "--retrain-days",
        min=1,
        help="How many days of games to score before refitting the model.",
    ),
    auto_tune_spread_policy: bool = typer.Option(
        False,
        "--auto-tune-spread-policy/--no-auto-tune-spread-policy",
        help="Tune spread deployment filters on prior walk-forward blocks only.",
    ),
    use_timing_layer: bool = typer.Option(
        False,
        "--use-timing-layer/--no-use-timing-layer",
        help=(
            "For spread bets, only keep early candidates when the closing-line "
            "layer expects the market to move in your favor."
        ),
    ),
    spread_model_family: str = typer.Option(
        DEFAULT_SPREAD_MODEL_FAMILY,
        "--spread-model-family",
        help="Spread model family used during walk-forward training blocks.",
    ),
    min_edge: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_edge,
        "--min-edge",
        help="Minimum expected value required to place a bet.",
    ),
    min_confidence: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_confidence,
        "--min-confidence",
        min=0.0,
        max=1.0,
        help="Minimum model probability required to place a bet.",
    ),
    min_probability_edge: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_probability_edge,
        "--min-probability-edge",
        help="Minimum model-minus-market probability edge required to place a bet.",
    ),
    min_games_played: int = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_games_played,
        "--min-games-played",
        min=0,
        help="Minimum prior games each team must have before the model can bet.",
    ),
    kelly_fraction: float = typer.Option(
        0.10,
        "--kelly-fraction",
        min=0.0,
        help="Fraction of full Kelly stake to use.",
    ),
    max_bet_fraction: float = typer.Option(
        0.02,
        "--max-bet-fraction",
        min=0.0,
        help="Maximum stake per bet as a fraction of bankroll.",
    ),
    max_daily_exposure_fraction: float = typer.Option(
        0.05,
        "--max-daily-exposure-fraction",
        min=0.0,
        help="Maximum total daily exposure as a fraction of bankroll.",
    ),
    min_moneyline_price: float = typer.Option(
        BetPolicy().min_moneyline_price,
        "--min-moneyline-price",
        help="Lowest moneyline price eligible for betting.",
    ),
    max_moneyline_price: float = typer.Option(
        BetPolicy().max_moneyline_price,
        "--max-moneyline-price",
        help="Highest moneyline price eligible for betting.",
    ),
    max_spread_abs_line: float | None = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_spread_abs_line,
        "--max-spread-abs-line",
        min=0.0,
        help="Maximum absolute spread line eligible for betting.",
    ),
    max_abs_rest_days_diff: float | None = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_abs_rest_days_diff,
        "--max-abs-rest-days-diff",
        min=0.0,
        help="Maximum allowed rest-days gap for deployable spread picks.",
    ),
    min_positive_ev_books: int = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_positive_ev_books,
        "--min-positive-ev-books",
        min=1,
        help="Minimum number of books that must show positive EV on one side.",
    ),
    min_median_expected_value: float | None = typer.Option(
        BetPolicy().min_median_expected_value,
        "--min-median-expected-value",
        help=(
            "Minimum median expected value across eligible books on one side. "
            "Disabled by default."
        ),
    ),
    epochs: int = typer.Option(
        DEFAULT_EPOCHS,
        "--epochs",
        min=1,
        help="Gradient-descent epochs for each walk-forward refit.",
    ),
    learning_rate: float = typer.Option(
        DEFAULT_LEARNING_RATE,
        "--learning-rate",
        min=0.0001,
        help="Gradient-descent learning rate for each walk-forward refit.",
    ),
    l2_penalty: float = typer.Option(
        DEFAULT_L2_PENALTY,
        "--l2-penalty",
        min=0.0,
        help="L2 regularization penalty for each walk-forward refit.",
    ),
    min_examples: int = typer.Option(
        DEFAULT_MIN_EXAMPLES,
        "--min-examples",
        min=1,
        help="Minimum training examples required before each refit.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show full model, market, and stake details for each simulated bet.",
    ),
) -> None:
    """Show recent simulated placed bets from a walk-forward backtest."""
    try:
        summary = backtest_betting_model(
            _build_backtest_options(
                market=market,
                seasons_back=seasons_back,
                evaluation_season=evaluation_season,
                starting_bankroll=starting_bankroll,
                unit_size=unit_size,
                retrain_days=retrain_days,
                auto_tune_spread_policy=auto_tune_spread_policy,
                use_timing_layer=use_timing_layer,
                spread_model_family=spread_model_family,
                min_edge=min_edge,
                min_confidence=min_confidence,
                min_probability_edge=min_probability_edge,
                min_games_played=min_games_played,
                kelly_fraction=kelly_fraction,
                max_bet_fraction=max_bet_fraction,
                max_daily_exposure_fraction=max_daily_exposure_fraction,
                min_moneyline_price=min_moneyline_price,
                max_moneyline_price=max_moneyline_price,
                max_spread_abs_line=max_spread_abs_line,
                max_abs_rest_days_diff=max_abs_rest_days_diff,
                min_positive_ev_books=min_positive_ev_books,
                min_median_expected_value=min_median_expected_value,
                epochs=epochs,
                learning_rate=learning_rate,
                l2_penalty=l2_penalty,
                min_examples=min_examples,
            )
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    recent_bets, earliest_bet_time, latest_bet_time = _recent_backtest_bets(
        summary.placed_bets,
        days=days,
    )
    if not recent_bets:
        typer.echo(
            "No simulated bets were placed under the selected backtest settings."
        )
        return

    displayed_bets = recent_bets[:limit]
    recent_profit = sum(settle_bet(bet) for bet in recent_bets)
    recent_total_staked = sum(bet.stake_amount for bet in recent_bets)
    recent_roi = recent_profit / recent_total_staked if recent_total_staked > 0 else 0.0
    recent_units_won = recent_profit / unit_size if unit_size > 0 else 0.0
    recent_wins = sum(1 for bet in recent_bets if bet.settlement == "win")
    recent_losses = sum(1 for bet in recent_bets if bet.settlement == "loss")
    recent_pushes = sum(1 for bet in recent_bets if bet.settlement == "push")

    typer.echo(
        f"Recent model performance {summary.market}: "
        f"evaluation_season={summary.evaluation_season}, "
        f"recent_days={days}, "
        f"bets={len(recent_bets)}"
    )
    typer.echo(
        "Window: "
        f"first_bet={_format_local_timestamp(earliest_bet_time)}, "
        f"latest_bet={_format_local_timestamp(latest_bet_time)}, "
        f"displayed={len(displayed_bets)}/{len(recent_bets)}"
    )
    typer.echo(
        f"Performance: total_staked=${recent_total_staked:.2f}, "
        f"profit={_format_signed_currency(recent_profit)}, "
        f"roi={recent_roi:.4f}, "
        f"units_won={recent_units_won:+.2f}"
    )
    typer.echo(
        f"Settlements: wins={recent_wins}, "
        f"losses={recent_losses}, "
        f"pushes={recent_pushes}"
    )
    if summary.final_policy is not None:
        policy_label = (
            "Auto-Tuned Spread Policy"
            if summary.policy_tuned_blocks > 0
            else "Applied Spread Policy"
        )
        typer.echo(
            f"{policy_label}: "
            f"blocks={summary.policy_tuned_blocks}, "
            f"{_format_policy_controls(summary.final_policy)}"
        )

    typer.echo("")
    typer.echo("Recent Bets")
    _echo_recent_betting_results(
        displayed_bets,
        unit_size=unit_size,
        verbose=verbose,
    )


@model_app.command("predict")
def model_predict_command(
    market: str = typer.Option(
        "best",
        "--market",
        help="Prediction market: moneyline, spread, or best.",
    ),
    artifact_name: str = typer.Option(
        DEFAULT_ARTIFACT_NAME,
        "--artifact-name",
        help="Artifact name loaded from artifacts/models/.",
    ),
    bankroll: float = typer.Option(
        DEFAULT_STARTING_BANKROLL,
        "--bankroll",
        min=0.01,
        help="Current bankroll used for stake sizing.",
    ),
    unit_size: float = typer.Option(
        DEFAULT_UNIT_SIZE,
        "--unit-size",
        min=0.01,
        help="Dollar size of one betting unit in the displayed bet slip.",
    ),
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        help="Maximum number of ranked recommendations to display.",
    ),
    auto_tune_spread_policy: bool = typer.Option(
        False,
        "--auto-tune-spread-policy/--no-auto-tune-spread-policy",
        help="Auto-apply the best walk-forward tuned spread policy to live picks.",
    ),
    use_timing_layer: bool = typer.Option(
        False,
        "--use-timing-layer/--no-use-timing-layer",
        help=(
            "For spread bets, defer early plays unless the closing-line layer "
            "expects the market to move in your favor."
        ),
    ),
    min_edge: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_edge,
        "--min-edge",
        help="Minimum expected value required to place a bet.",
    ),
    min_confidence: float = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_confidence,
        "--min-confidence",
        min=0.0,
        max=1.0,
        help="Minimum model probability required to place a bet.",
    ),
    min_probability_edge: float = typer.Option(
        0.025,
        "--min-probability-edge",
        help="Minimum model-minus-market probability edge required to place a bet.",
    ),
    min_games_played: int = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_games_played,
        "--min-games-played",
        min=0,
        help="Minimum prior games each team must have before the model can bet.",
    ),
    kelly_fraction: float = typer.Option(
        0.10,
        "--kelly-fraction",
        min=0.0,
        help="Fraction of full Kelly stake to use.",
    ),
    max_bet_fraction: float = typer.Option(
        0.02,
        "--max-bet-fraction",
        min=0.0,
        help="Maximum stake per bet as a fraction of bankroll.",
    ),
    max_daily_exposure_fraction: float = typer.Option(
        0.05,
        "--max-daily-exposure-fraction",
        min=0.0,
        help="Maximum total daily exposure as a fraction of bankroll.",
    ),
    min_moneyline_price: float = typer.Option(
        BetPolicy().min_moneyline_price,
        "--min-moneyline-price",
        help="Lowest moneyline price eligible for betting.",
    ),
    max_moneyline_price: float = typer.Option(
        BetPolicy().max_moneyline_price,
        "--max-moneyline-price",
        help="Highest moneyline price eligible for betting.",
    ),
    max_spread_abs_line: float | None = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_spread_abs_line,
        "--max-spread-abs-line",
        min=0.0,
        help="Maximum absolute spread line eligible for betting.",
    ),
    min_positive_ev_books: int = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_positive_ev_books,
        "--min-positive-ev-books",
        min=1,
        help="Minimum number of books that must show positive EV on one side.",
    ),
    max_abs_rest_days_diff: float | None = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_abs_rest_days_diff,
        "--max-abs-rest-days-diff",
        min=0.0,
        help="Maximum allowed rest-days gap for deployable spread picks.",
    ),
    min_median_expected_value: float | None = typer.Option(
        BetPolicy().min_median_expected_value,
        "--min-median-expected-value",
        help=(
            "Minimum median expected value across eligible books on one side. "
            "Disabled by default."
        ),
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show full model, market, and edge details for each recommendation.",
    ),
    show_upcoming_games: bool = typer.Option(
        False,
        "--show-upcoming-games/--no-show-upcoming-games",
        help=(
            "Show one row per upcoming game with the best current model angle, "
            "including bets, waits, and passes."
        ),
    ),
    output_format: str = typer.Option(
        "text",
        "--output-format",
        help="Prediction output format: text or json.",
    ),
) -> None:
    """Rank current upcoming betting opportunities from trained artifacts."""
    try:
        normalized_output_format = output_format.strip().lower()
        if normalized_output_format not in {"text", "json"}:
            raise typer.BadParameter("output format must be one of: text, json")
        parsed_market = _parse_strategy_market(market)
        summary = predict_best_bets(
            PredictionOptions(
                market=parsed_market,
                artifact_name=artifact_name,
                bankroll=bankroll,
                limit=limit,
                auto_tune_spread_policy=auto_tune_spread_policy,
                use_timing_layer=use_timing_layer,
                policy=BetPolicy(
                    min_edge=min_edge,
                    min_confidence=min_confidence,
                    min_probability_edge=min_probability_edge,
                    uncertainty_probability_buffer=(
                        DEFAULT_DEPLOYABLE_SPREAD_POLICY.uncertainty_probability_buffer
                        if parsed_market in {"spread", "best"}
                        else BetPolicy().uncertainty_probability_buffer
                    ),
                    min_games_played=min_games_played,
                    kelly_fraction=kelly_fraction,
                    max_bet_fraction=max_bet_fraction,
                    max_daily_exposure_fraction=max_daily_exposure_fraction,
                    max_bets_per_day=(
                        DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_bets_per_day
                        if parsed_market in {"spread", "best"}
                        else BetPolicy().max_bets_per_day
                    ),
                    min_moneyline_price=min_moneyline_price,
                    max_moneyline_price=max_moneyline_price,
                    max_spread_abs_line=max_spread_abs_line,
                    max_abs_rest_days_diff=max_abs_rest_days_diff,
                    min_positive_ev_books=min_positive_ev_books,
                    min_median_expected_value=min_median_expected_value,
                ),
            )
        )
    except OperationalError as exc:
        typer.echo(
            "Error: could not connect to PostgreSQL. "
            "Start the local cluster and port-forward Postgres, or point "
            "`DATABASE_URL` at a reachable database.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if normalized_output_format == "json":
        typer.echo(
            json.dumps(
                _prediction_summary_payload(
                    summary=summary,
                    bankroll=bankroll,
                ),
                indent=2,
            )
        )
        return

    typer.echo(
        "Prediction Summary: "
        f"market={summary.market}, "
        f"available_games={summary.available_games}, "
        f"candidates_considered={summary.candidates_considered}, "
        f"deferred_count={len(summary.deferred_recommendations)}, "
        f"recommendations_count={summary.bets_placed}"
    )
    if summary.generated_at is not None:
        typer.echo(
            "Freshness: "
            f"generated_at={_format_local_datetime_iso(summary.generated_at)}, "
            "expires_at="
            f"{_format_optional_datetime_iso(summary.expires_at)}"
        )
    if summary.applied_policy is not None:
        policy_label = "Applied Policy"
        if summary.market in {"spread", "best"}:
            policy_label = (
                "Auto-Tuned Spread Policy"
                if summary.policy_was_auto_tuned
                else "Applied Policy"
            )
        typer.echo(
            f"{policy_label}: "
            f"blocks={summary.policy_tuned_blocks}, "
            f"{_format_policy_controls(summary.applied_policy)}"
        )
    if summary.applied_policy is not None:
        worst_case_same_day_loss = (
            bankroll * summary.applied_policy.max_daily_exposure_fraction
        )
        typer.echo(
            "Risk Guardrails: "
            f"fractional_kelly={summary.applied_policy.kelly_fraction:.2f}, "
            f"max_bet={summary.applied_policy.max_bet_fraction * 100.0:.1f}%, "
            "max_daily_exposure="
            f"{summary.applied_policy.max_daily_exposure_fraction * 100.0:.1f}%, "
            f"worst_case_same_day_loss=${worst_case_same_day_loss:.2f}"
        )
    else:
        typer.echo("Risk Guardrails: unavailable")
    typer.echo(
        "Uncertainty Disclosure: no direct player-availability, roster, or "
        "coaching/news feed is modeled; predictions rely on team form, market "
        "structure, and offseason proxy features."
    )
    typer.echo(
        "Availability Shadow: "
        f"{_prediction_availability_summary_text(summary=summary)}"
    )
    if not summary.recommendations:
        if not summary.deferred_recommendations:
            typer.echo("No bets qualified under the current policy.")
            if not show_upcoming_games or not summary.upcoming_games:
                return
        else:
            typer.echo("No immediate bets qualified under the current policy.")
    else:
        typer.echo("")
        typer.echo(f"Bet Slip (1u = ${unit_size:.2f})")
        if verbose:
            _echo_betting_recommendations(
                summary.recommendations,
                unit_size=unit_size,
            )
        else:
            _echo_simple_betting_recommendations(
                summary.recommendations,
                unit_size=unit_size,
            )

    if summary.deferred_recommendations:
        typer.echo("")
        typer.echo("Wait List")
        if verbose:
            _echo_deferred_recommendations(summary.deferred_recommendations)
        else:
            _echo_simple_deferred_recommendations(summary.deferred_recommendations)

    if not show_upcoming_games or not summary.upcoming_games:
        return

    typer.echo("")
    typer.echo("Upcoming Games")
    if verbose:
        _echo_upcoming_game_predictions(
            summary.upcoming_games,
            unit_size=unit_size,
        )
        return
    _echo_simple_upcoming_game_predictions(
        summary.upcoming_games,
        unit_size=unit_size,
    )


@model_app.command("tournament")
def model_tournament_command(
    artifact_name: str = typer.Option(
        DEFAULT_ARTIFACT_NAME,
        "--artifact-name",
        help="Moneyline artifact name loaded from artifacts/models/.",
    ),
    bracket_path: Path = typer.Option(
        DEFAULT_TOURNAMENT_BRACKET_PATH,
        "--bracket-path",
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Tracked local tournament bracket specification JSON.",
    ),
    simulations: int = typer.Option(
        TournamentOptions().simulations,
        "--simulations",
        min=1,
        help="Monte Carlo tournament simulations used for advancement odds.",
    ),
    output_format: str = typer.Option(
        "text",
        "--output-format",
        help="Tournament output format: text or json.",
    ),
) -> None:
    """Generate a full tournament bracket from the moneyline model."""
    try:
        normalized_output_format = output_format.strip().lower()
        if normalized_output_format not in {"text", "json"}:
            raise typer.BadParameter("output format must be one of: text, json")
        summary = predict_tournament_bracket(
            TournamentOptions(
                artifact_name=artifact_name,
                bracket_path=bracket_path,
                simulations=simulations,
            )
        )
    except OperationalError as exc:
        typer.echo(
            "Error: could not connect to PostgreSQL. "
            "Start the local cluster and port-forward Postgres, or point "
            "`DATABASE_URL` at a reachable database.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (FileNotFoundError, OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if normalized_output_format == "json":
        typer.echo(json.dumps(_tournament_summary_payload(summary=summary), indent=2))
        return

    _echo_tournament_summary(summary=summary)


@model_app.command("tournament-backtest")
def model_tournament_backtest_command(
    seasons: int = typer.Option(
        TournamentBacktestOptions().seasons,
        "--seasons",
        min=1,
        help=(
            "How many completed tournament seasons to evaluate. "
            "On 2026-03-18, the default window is 2021-2025."
        ),
    ),
    max_season: int | None = typer.Option(
        None,
        "--max-season",
        min=1,
        help="Optional last evaluation season to include.",
    ),
    training_seasons_back: int = typer.Option(
        TournamentBacktestOptions().training_seasons_back,
        "--training-seasons-back",
        min=1,
        help=(
            "How many seasons of completed games to train each evaluation "
            "bracket on, including the evaluation season up to tournament tip."
        ),
    ),
    bracket_dir: Path = typer.Option(
        DEFAULT_TOURNAMENT_BRACKET_DIR,
        "--bracket-dir",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        resolve_path=True,
        help="Tracked local directory of tournament bracket specification JSON files.",
    ),
    output_format: str = typer.Option(
        "text",
        "--output-format",
        help="Tournament backtest output format: text or json.",
    ),
) -> None:
    """Backtest the tournament bracket path on completed prior seasons."""
    try:
        normalized_output_format = output_format.strip().lower()
        if normalized_output_format not in {"text", "json"}:
            raise typer.BadParameter("output format must be one of: text, json")
        summary = backtest_tournament_model(
            TournamentBacktestOptions(
                seasons=seasons,
                max_season=max_season,
                training_seasons_back=training_seasons_back,
                bracket_dir=bracket_dir,
            )
        )
    except OperationalError as exc:
        typer.echo(
            "Error: could not connect to PostgreSQL. "
            "Start the local cluster and port-forward Postgres, or point "
            "`DATABASE_URL` at a reachable database.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except (FileNotFoundError, OSError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if normalized_output_format == "json":
        typer.echo(
            json.dumps(
                _tournament_backtest_summary_payload(summary=summary),
                indent=2,
            )
        )
        return

    _echo_tournament_backtest_summary(summary=summary)


@report_app.callback()
def model_report_command(
    ctx: typer.Context,
    output: Path = typer.Option(
        DEFAULT_BEST_BACKTEST_REPORT_PATH,
        "--output",
        help="Markdown report path. Defaults to docs/results/best-model-5y-backtest.md",
    ),
    seasons: int = typer.Option(
        DEFAULT_MODEL_SEASONS_BACK,
        "--seasons",
        min=1,
        help="How many loaded seasons to include in the report window.",
    ),
    max_season: int | None = typer.Option(
        None,
        "--max-season",
        help="Optional latest season to include in the report window.",
    ),
    starting_bankroll: float = typer.Option(
        DEFAULT_STARTING_BANKROLL,
        "--starting-bankroll",
        min=0.01,
        help="Starting bankroll used for each seasonal backtest.",
    ),
    unit_size: float = typer.Option(
        DEFAULT_UNIT_SIZE,
        "--unit-size",
        min=0.01,
        help="Dollar unit used when reporting units won.",
    ),
    retrain_days: int = typer.Option(
        DEFAULT_BACKTEST_RETRAIN_DAYS,
        "--retrain-days",
        min=1,
        help="How many days of games to score before refitting the model.",
    ),
    auto_tune_spread_policy: bool = typer.Option(
        False,
        "--auto-tune-spread-policy/--no-auto-tune-spread-policy",
        help="Use the current spread auto-tuning path when reporting `best`.",
    ),
    use_timing_layer: bool = typer.Option(
        False,
        "--use-timing-layer/--no-use-timing-layer",
        help=(
            "For spread bets, report the early-only timing layer that keeps "
            "candidates only when favorable closing-line movement is expected."
        ),
    ),
    spread_model_family: str = typer.Option(
        DEFAULT_SPREAD_MODEL_FAMILY,
        "--spread-model-family",
        help="Spread model family used during report backtests.",
    ),
    min_positive_ev_books: int = typer.Option(
        DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_positive_ev_books,
        "--min-positive-ev-books",
        min=1,
        help="Minimum number of books that must show positive EV on one side.",
    ),
    min_median_expected_value: float | None = typer.Option(
        BetPolicy().min_median_expected_value,
        "--min-median-expected-value",
        help=(
            "Minimum median expected value across eligible books on one side. "
            "Disabled by default."
        ),
    ),
) -> None:
    """Write the canonical best-path Markdown report for the deployable window."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        report_policy = BetPolicy(
            min_edge=DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_edge,
            min_confidence=DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_confidence,
            min_probability_edge=DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_probability_edge,
            uncertainty_probability_buffer=(
                DEFAULT_DEPLOYABLE_SPREAD_POLICY.uncertainty_probability_buffer
            ),
            min_games_played=DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_games_played,
            kelly_fraction=DEFAULT_DEPLOYABLE_SPREAD_POLICY.kelly_fraction,
            max_bet_fraction=DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_bet_fraction,
            max_daily_exposure_fraction=(
                DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_daily_exposure_fraction
            ),
            max_bets_per_day=DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_bets_per_day,
            min_moneyline_price=DEFAULT_DEPLOYABLE_SPREAD_POLICY.min_moneyline_price,
            max_moneyline_price=DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_moneyline_price,
            max_spread_abs_line=DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_spread_abs_line,
            max_abs_rest_days_diff=(
                DEFAULT_DEPLOYABLE_SPREAD_POLICY.max_abs_rest_days_diff
            ),
            min_positive_ev_books=min_positive_ev_books,
            min_median_expected_value=min_median_expected_value,
        )
        report_options = BestBacktestReportOptions(
            output_path=output,
            seasons=seasons,
            max_season=max_season,
            starting_bankroll=starting_bankroll,
            unit_size=unit_size,
            retrain_days=retrain_days,
            auto_tune_spread_policy=auto_tune_spread_policy,
            use_timing_layer=use_timing_layer,
            spread_model_family=_parse_model_family(spread_model_family),
            policy=report_policy,
        )
        report = generate_best_backtest_report(report_options, progress=typer.echo)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if is_canonical_dashboard_report_options(report_options):
        snapshot_path = write_dashboard_snapshot(
            report,
            report_options=report_options,
        )
        typer.echo(f"Dashboard snapshot: {_format_repo_path(snapshot_path)}")
    else:
        typer.echo(
            "Dashboard snapshot: skipped because the report settings do not "
            "match the canonical best workflow."
        )

    typer.echo(f"Generated best-model report: {_format_repo_path(report.output_path)}")
    if report.history_output_path is not None:
        typer.echo(f"History copy: {_format_repo_path(report.history_output_path)}")
    typer.echo(
        f"Aggregate: seasons={len(report.selected_seasons)}, "
        f"bets={report.aggregate_bets}, "
        f"profit=${report.aggregate_profit:.2f}, "
        f"roi={report.aggregate_roi:.4f}"
    )
    typer.echo(f"Aggregate CLV: {_format_backtest_clv_summary(report.aggregate_clv)}")
    typer.echo(
        f"Latest season {report.latest_summary.evaluation_season}: "
        f"profit=${report.latest_summary.profit:.2f}, "
        f"roi={report.latest_summary.roi:.4f}"
    )
    typer.echo(
        f"Latest season CLV: {_format_backtest_clv_summary(report.latest_summary.clv)}"
    )
    typer.echo(
        "Zero-bet seasons: "
        + (
            ", ".join(str(season) for season in report.zero_bet_seasons)
            if report.zero_bet_seasons
            else "none"
        )
    )


def _recent_backtest_bets(
    placed_bets: list[PlacedBet],
    *,
    days: int,
) -> tuple[list[PlacedBet], str | None, str | None]:
    """Filter settled backtest bets to a trailing window anchored to the latest bet."""
    if not placed_bets:
        return [], None, None

    sorted_bets = sorted(
        placed_bets,
        key=lambda bet: (
            _parse_timestamp(bet.commence_time),
            bet.game_id,
            bet.market,
            bet.team_name,
        ),
        reverse=True,
    )
    latest_bet_time = _parse_timestamp(sorted_bets[0].commence_time)
    cutoff_time = latest_bet_time - timedelta(days=days)
    recent_bets = [
        bet for bet in sorted_bets if _parse_timestamp(bet.commence_time) >= cutoff_time
    ]
    earliest_bet_time = min(_parse_timestamp(bet.commence_time) for bet in recent_bets)
    return recent_bets, earliest_bet_time.isoformat(), latest_bet_time.isoformat()


def _echo_game_samples(samples: list[GameSummary], include_scores: bool) -> None:
    """Render a list of game samples for CLI output."""
    if not samples:
        typer.echo("  (no rows)")
        return

    for sample in samples:
        if include_scores:
            score_line = (
                f"{sample.commence_time} | {sample.home_team} vs {sample.away_team}"
            )
            typer.echo(
                f"  {score_line} | "
                f"{sample.home_score}-{sample.away_score} | result={sample.result}"
            )
            continue
        typer.echo(
            f"  {sample.commence_time} | {sample.home_team} vs {sample.away_team}"
        )


def _format_optional_float(value: float | None) -> str:
    """Format optional float values for concise CLI output."""
    if value is None:
        return "none"
    return f"{value:.1f}"


def _format_optional_int(value: int | None) -> str:
    """Format optional integer values for concise CLI output."""
    if value is None:
        return "none"
    return str(value)


def _format_optional_edge(value: float | None) -> str:
    """Format optional EV thresholds for concise CLI output."""
    if value is None:
        return "none"
    return f"{value:.3f}"


def _format_policy_controls(policy: BetPolicy) -> str:
    """Render one spread policy in a stable CLI-friendly format."""
    parts = [
        f"min_edge={policy.min_edge:.3f}, min_confidence={policy.min_confidence:.3f}, ",
        f"min_probability_edge={policy.min_probability_edge:.3f}, ",
        f"uncertainty_probability_buffer={policy.uncertainty_probability_buffer:.4f}, ",
        f"min_games_played={policy.min_games_played}, ",
        f"min_positive_ev_books={policy.min_positive_ev_books}, ",
        f"max_bets_per_day={_format_optional_int(policy.max_bets_per_day)}, ",
        "min_median_expected_value="
        f"{_format_optional_edge(policy.min_median_expected_value)}, ",
        f"max_spread_abs_line={_format_optional_float(policy.max_spread_abs_line)}, ",
        "max_abs_rest_days_diff="
        f"{_format_optional_float(policy.max_abs_rest_days_diff)}",
    ]
    return "".join(parts)


def _format_backtest_clv_summary(summary) -> str:
    """Render a concise closing-line-value summary for CLI output."""
    if summary.bets_evaluated == 0:
        return "tracked=0"
    parts = [
        f"tracked={summary.bets_evaluated}",
        f"positive={summary.positive_bets}",
        f"neutral={summary.neutral_bets}",
        f"negative={summary.negative_bets}",
        f"positive_rate={summary.positive_rate:.4f}",
    ]
    if summary.average_spread_line_delta is not None:
        parts.append(
            f"avg_spread_line_clv={summary.average_spread_line_delta:+.2f} pts"
        )
    if summary.average_spread_price_probability_delta is not None:
        parts.append(
            "avg_spread_price_clv="
            f"{summary.average_spread_price_probability_delta * 100.0:+.2f} pp"
        )
    if summary.average_spread_no_vig_probability_delta is not None:
        parts.append(
            "avg_spread_no_vig_close_delta="
            f"{summary.average_spread_no_vig_probability_delta * 100.0:+.2f} pp"
        )
    if summary.average_spread_closing_expected_value is not None:
        parts.append(
            "avg_spread_closing_ev="
            f"{summary.average_spread_closing_expected_value:+.3f}"
        )
    if summary.average_moneyline_probability_delta is not None:
        parts.append(
            "avg_moneyline_clv="
            f"{summary.average_moneyline_probability_delta * 100.0:+.2f} pp"
        )
    return ", ".join(parts)


def _echo_odds_samples(samples: list[OddsSnapshotSummary]) -> None:
    """Render a list of odds snapshot samples for CLI output."""
    if not samples:
        typer.echo("  (no rows)")
        return

    for sample in samples:
        typer.echo(
            f"  {sample.captured_at} | {sample.bookmaker_key}/{sample.market_key} | "
            f"{sample.home_team} vs {sample.away_team} | "
            f"team1_price={sample.team1_price} | team2_price={sample.team2_price} | "
            f"total_points={sample.total_points}"
        )


def _format_repo_path(path: Path) -> str:
    """Render a path relative to the current working tree when possible."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _echo_betting_recommendations(
    recommendations: list[PlacedBet],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
) -> None:
    """Render ranked betting recommendations or settled sample bets."""
    for index, recommendation in enumerate(recommendations, start=1):
        typer.echo(
            "  "
            + _format_bet_row(
                recommendation=recommendation,
                rank=index,
                unit_size=unit_size,
            )
        )


def _echo_recent_betting_results(
    recommendations: list[PlacedBet],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
    verbose: bool,
) -> None:
    """Render recent settled backtest bets with realized PnL."""
    for index, recommendation in enumerate(recommendations, start=1):
        typer.echo(
            "  "
            + _format_recent_bet_row(
                recommendation=recommendation,
                rank=index,
                unit_size=unit_size,
                verbose=verbose,
            )
        )


def _echo_simple_betting_recommendations(
    recommendations: list[PlacedBet],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
) -> None:
    """Render a compact bet-slip style list for current predictions."""
    for index, recommendation in enumerate(recommendations, start=1):
        typer.echo(
            "  "
            + _format_compact_bet_row(
                recommendation=recommendation,
                rank=index,
                unit_size=unit_size,
            )
        )


def _echo_agent_betting_recommendations(
    recommendations: list[PlacedBet],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
) -> None:
    """Render agent-mode bets plus one separate FanDuel link each."""
    for index, recommendation in enumerate(recommendations, start=1):
        typer.echo(
            "  "
            + _format_compact_bet_row(
                recommendation=recommendation,
                rank=index,
                unit_size=unit_size,
            )
        )
        fanduel_link = _format_fanduel_team_link(recommendation.team_name)
        if fanduel_link is not None:
            typer.echo(f"    FanDuel link: {fanduel_link}")


def _echo_deferred_recommendations(
    recommendations: list[DeferredRecommendation],
) -> None:
    """Render deferred spread candidates with timing-layer context."""
    for index, recommendation in enumerate(recommendations, start=1):
        typer.echo(
            "  "
            + _format_wait_row(
                recommendation=recommendation,
                rank=index,
            )
        )


def _echo_simple_deferred_recommendations(
    recommendations: list[DeferredRecommendation],
) -> None:
    """Render a compact wait list for deferred spread candidates."""
    for index, recommendation in enumerate(recommendations, start=1):
        typer.echo(
            "  "
            + _format_compact_wait_row(
                recommendation=recommendation,
                rank=index,
            )
        )


def _echo_upcoming_game_predictions(
    predictions: list[UpcomingGamePrediction],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
) -> None:
    """Render the full upcoming slate with per-game model metrics."""
    for index, prediction in enumerate(predictions, start=1):
        typer.echo(
            "  "
            + _format_upcoming_prediction_row(
                prediction=prediction,
                rank=index,
                unit_size=unit_size,
            )
        )


def _echo_simple_upcoming_game_predictions(
    predictions: list[UpcomingGamePrediction],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
) -> None:
    """Render a compact upcoming-game slate with status and core metrics."""
    for index, prediction in enumerate(predictions, start=1):
        typer.echo(
            "  "
            + _format_compact_upcoming_prediction_row(
                prediction=prediction,
                rank=index,
                unit_size=unit_size,
            )
        )


def _echo_agent_scoreboard_games(games: list[LiveBoardGame]) -> None:
    """Render live scores plus recently completed board games."""
    for index, game in enumerate(games, start=1):
        typer.echo("  " + _format_agent_scoreboard_row(game=game, rank=index))


def _select_agent_scoreboard_games(
    games: list[LiveBoardGame],
    *,
    reference_time: datetime,
) -> list[LiveBoardGame]:
    """Keep in-progress games plus finals updated within the recent cutoff."""
    recent_final_cutoff = reference_time - timedelta(
        hours=AGENT_RECENT_FINAL_LOOKBACK_HOURS
    )
    selected_games: list[LiveBoardGame] = []
    for game in games:
        score_timestamp = _agent_game_score_timestamp(game)
        if game.game_status == "in_progress":
            selected_games.append(game)
            continue
        if (
            game.game_status == "final"
            and score_timestamp is not None
            and score_timestamp >= recent_final_cutoff
        ):
            selected_games.append(game)
    return sorted(
        selected_games,
        key=_agent_scoreboard_sort_key,
    )


def _format_agent_scoreboard_row(*, game: LiveBoardGame, rank: int) -> str:
    """Render one compact live-score row for the agent loop."""
    matchup = f"{game.home_team_name} vs {game.away_team_name}"
    parts = [
        f"{rank}. {_format_local_timestamp(game.commence_time)}",
        game.game_status.replace("_", " ").title(),
        game.board_status.replace("_", " ").title(),
        matchup,
        _format_agent_score_label(game),
    ]
    tracked_side = _format_agent_tracked_side(game)
    if tracked_side is not None:
        parts.insert(4, tracked_side)
    return " | ".join(parts)


def _format_agent_tracked_side(game: LiveBoardGame) -> str | None:
    """Render the tracked side for one live-board row when available."""
    if game.team_name is None:
        return None
    if game.market == "spread" and game.line_value is not None:
        return f"{game.team_name} {game.line_value:+.1f}"
    if game.market == "moneyline":
        return f"{game.team_name} ML"
    return game.team_name


def _format_agent_score_label(game: LiveBoardGame) -> str:
    """Render a short live/final score label for agent output."""
    if game.home_score is None or game.away_score is None:
        return "Score pending"
    score_label = f"{game.home_score}-{game.away_score}"
    if game.game_status == "in_progress":
        return f"{score_label} live"
    return f"Final {score_label}"


def _agent_game_score_timestamp(game: LiveBoardGame) -> datetime | None:
    """Return the best available score-update timestamp for one board row."""
    if game.last_score_update is not None:
        return game.last_score_update
    if not game.commence_time:
        return None
    return _parse_timestamp(game.commence_time)


def _agent_scoreboard_sort_key(game: LiveBoardGame) -> tuple[int, float, int]:
    """Sort live games before finals, newest score updates first."""
    score_timestamp = _agent_game_score_timestamp(game)
    return (
        0 if game.game_status == "in_progress" else 1,
        -(
            score_timestamp.timestamp()
            if score_timestamp is not None
            else float("-inf")
        ),
        game.game_id,
    )


def _format_betting_market(recommendation: PlacedBet) -> str:
    """Render one bet's market and pricing information."""
    return _format_market_label(
        market=recommendation.market,
        line_value=recommendation.line_value,
        market_price=recommendation.market_price,
    )


def _format_recent_bet_row(
    *,
    recommendation: PlacedBet,
    rank: int,
    unit_size: float,
    verbose: bool,
) -> str:
    """Render one settled backtest bet with realized outcome fields."""
    if not verbose:
        return _format_compact_recent_bet_row(
            recommendation=recommendation,
            rank=rank,
            unit_size=unit_size,
        )

    parts = [
        f"rank={rank}",
        f"game_id={recommendation.game_id}",
        f"commence_time_local={_format_local_timestamp(recommendation.commence_time)}",
        f"team={recommendation.team_name}",
        f"opponent={recommendation.opponent_name}",
        f"sportsbook={recommendation.sportsbook or 'unknown'}",
        f"market={_format_betting_market(recommendation)}",
        "stake_amount="
        f"${recommendation.stake_amount:.2f} "
        f"({_format_unit_stake(recommendation.stake_amount, unit_size)})",
        f"settlement={recommendation.settlement}",
        f"pnl={_format_signed_currency(settle_bet(recommendation))}",
    ]
    if verbose:
        parts.extend(
            [
                f"model_probability={recommendation.model_probability:.3f}",
                f"implied_probability={recommendation.implied_probability:.3f}",
                f"probability_edge={recommendation.probability_edge:.3f}",
                f"expected_value={recommendation.expected_value:.3f}",
                f"stake_fraction={recommendation.stake_fraction:.3f}",
                f"eligible_books={recommendation.eligible_books}",
                f"positive_ev_books={recommendation.positive_ev_books}",
                f"coverage_rate={recommendation.coverage_rate:.3f}",
            ]
        )
    return " | ".join(parts)


def _format_compact_recent_bet_row(
    *,
    recommendation: PlacedBet,
    rank: int,
    unit_size: float,
) -> str:
    """Render one compact settled-bet row for default recent-report output."""
    settled_pnl = _format_signed_currency(settle_bet(recommendation))
    return " | ".join(
        [
            f"{rank}. {_format_explicit_bet_instruction(recommendation)}",
            _format_unit_stake(recommendation.stake_amount, unit_size),
            f"{recommendation.settlement} {settled_pnl}",
        ]
    )


def _format_candidate_market(candidate: CandidateBet) -> str:
    """Render one deferred candidate's market and pricing information."""
    return _format_market_label(
        market=candidate.market,
        line_value=candidate.line_value,
        market_price=candidate.market_price,
    )


def _format_upcoming_market(prediction: UpcomingGamePrediction) -> str:
    """Render one upcoming game's market label when available."""
    if prediction.market is None or prediction.market_price is None:
        return "no market"
    return _format_market_label(
        market=prediction.market,
        line_value=prediction.line_value,
        market_price=prediction.market_price,
    )


def _format_explicit_bet_instruction(recommendation: PlacedBet) -> str:
    """Render the exact bet to place in a compact human-readable form."""
    price = _format_moneyline(recommendation.market_price) or str(
        recommendation.market_price
    )
    sportsbook = recommendation.sportsbook or "unknown"
    if recommendation.market == "spread":
        return (
            f"{recommendation.team_name} "
            f"{(recommendation.line_value or 0.0):+.1f} "
            f"at {sportsbook} {price}"
        )
    return f"{recommendation.team_name} ML at {sportsbook} {price}"


def _format_compact_target(
    *,
    market: ModelMarket,
    line_value: float | None,
    market_price: float | None,
) -> str:
    """Render a short execution target with American odds."""
    target_price = _format_moneyline(market_price)
    if market == "spread" and line_value is not None:
        if target_price is None:
            return f"{line_value:+.1f}"
        return f"{line_value:+.1f} / {target_price}"
    return target_price or "none"


def _format_compact_bet_row(
    *,
    recommendation: PlacedBet,
    rank: int,
    unit_size: float,
) -> str:
    """Render one compact actionable bet row for default text output."""
    target = _format_compact_target(
        market=recommendation.market,
        line_value=(
            recommendation.min_acceptable_line
            if recommendation.min_acceptable_line is not None
            else recommendation.line_value
        ),
        market_price=(
            recommendation.min_acceptable_price
            if recommendation.min_acceptable_price is not None
            else recommendation.market_price
        ),
    )
    return " | ".join(
        [
            f"{rank}. {_format_explicit_bet_instruction(recommendation)}",
            _format_unit_stake(recommendation.stake_amount, unit_size),
            f"target {target}",
        ]
    )


def _format_bet_row(
    *,
    recommendation: PlacedBet,
    rank: int,
    unit_size: float,
) -> str:
    parts = [
        f"rank={rank}",
        f"bet={_format_explicit_bet_instruction(recommendation)}",
        f"game_id={recommendation.game_id}",
        f"commence_time_local={_format_local_timestamp(recommendation.commence_time)}",
        f"team={recommendation.team_name}",
        f"opponent={recommendation.opponent_name}",
        f"market={recommendation.market}",
        f"side={recommendation.side}",
        f"sportsbook={recommendation.sportsbook or 'unknown'}",
        f"line_value={_format_optional_number(recommendation.line_value)}",
        f"market_price={recommendation.market_price:.1f}",
        f"eligible_books={recommendation.eligible_books}",
        f"positive_ev_books={recommendation.positive_ev_books}",
        f"coverage_rate={recommendation.coverage_rate:.3f}",
        f"model_probability={recommendation.model_probability:.3f}",
        f"implied_probability={recommendation.implied_probability:.3f}",
        f"probability_edge={recommendation.probability_edge:.3f}",
        f"expected_value={recommendation.expected_value:.3f}",
        f"stake_fraction={recommendation.stake_fraction:.3f}",
        "stake_amount="
        f"${recommendation.stake_amount:.2f} "
        f"({_format_unit_stake(recommendation.stake_amount, unit_size)})",
        "reason=qualified",
    ]
    if recommendation.min_acceptable_line is not None:
        parts.append(
            "min_acceptable_line="
            f"{_format_optional_number(recommendation.min_acceptable_line)}"
        )
    if recommendation.min_acceptable_price is not None:
        parts.append(f"min_acceptable_price={recommendation.min_acceptable_price:.1f}")
    return " | ".join(parts)


def _format_compact_wait_row(
    *,
    recommendation: DeferredRecommendation,
    rank: int,
) -> str:
    """Render one compact wait-list row for default text output."""
    candidate = recommendation.candidate
    price = _format_moneyline(candidate.market_price) or str(candidate.market_price)
    sportsbook = candidate.sportsbook or "unknown"
    target = _format_compact_target(
        market=candidate.market,
        line_value=(
            candidate.min_acceptable_line
            if candidate.min_acceptable_line is not None
            else candidate.line_value
        ),
        market_price=(
            candidate.min_acceptable_price
            if candidate.min_acceptable_price is not None
            else candidate.market_price
        ),
    )
    return " | ".join(
        [
            (
                f"{rank}. wait {candidate.team_name} "
                f"{(candidate.line_value or 0.0):+.1f} "
                f"at {sportsbook} {price}"
            ),
            f"target {target}",
        ]
    )


def _format_wait_row(
    *,
    recommendation: DeferredRecommendation,
    rank: int,
) -> str:
    candidate = recommendation.candidate
    parts = [
        f"rank={rank}",
        f"game_id={candidate.game_id}",
        f"commence_time_local={_format_local_timestamp(candidate.commence_time)}",
        f"team={candidate.team_name}",
        f"opponent={candidate.opponent_name}",
        f"market={candidate.market}",
        f"side={candidate.side}",
        f"sportsbook={candidate.sportsbook or 'unknown'}",
        f"line_value={_format_optional_number(candidate.line_value)}",
        f"market_price={candidate.market_price:.1f}",
        f"eligible_books={candidate.eligible_books}",
        f"positive_ev_books={candidate.positive_ev_books}",
        f"coverage_rate={candidate.coverage_rate:.3f}",
        f"model_probability={candidate.model_probability:.3f}",
        f"implied_probability={candidate.implied_probability:.3f}",
        f"probability_edge={candidate.probability_edge:.3f}",
        f"expected_value={candidate.expected_value:.3f}",
        f"stake_fraction={candidate.stake_fraction:.3f}",
        f"favorable_close_probability={recommendation.favorable_close_probability:.3f}",
        "reason=timing_wait",
    ]
    if candidate.min_acceptable_line is not None:
        parts.append(
            "min_acceptable_line="
            f"{_format_optional_number(candidate.min_acceptable_line)}"
        )
    if candidate.min_acceptable_price is not None:
        parts.append(f"min_acceptable_price={candidate.min_acceptable_price:.1f}")
    return " | ".join(parts)


def _format_upcoming_prediction_row(
    *,
    prediction: UpcomingGamePrediction,
    rank: int,
    unit_size: float,
) -> str:
    parts = [
        f"rank={rank}",
        f"game_id={prediction.game_id}",
        f"commence_time_local={_format_local_timestamp(prediction.commence_time)}",
        f"status={prediction.status}",
        f"team={prediction.team_name}",
        f"opponent={prediction.opponent_name}",
    ]
    if prediction.market is not None:
        parts.append(f"market={prediction.market}")
    if prediction.side is not None:
        parts.append(f"side={prediction.side}")
    if prediction.sportsbook is not None:
        parts.append(f"sportsbook={prediction.sportsbook or 'unknown'}")
    if prediction.line_value is not None:
        parts.append(f"line_value={_format_optional_number(prediction.line_value)}")
    if prediction.market_price is not None:
        parts.append(f"market_price={prediction.market_price:.1f}")
    parts.extend(
        [
            f"eligible_books={prediction.eligible_books}",
            f"positive_ev_books={prediction.positive_ev_books}",
            f"coverage_rate={prediction.coverage_rate:.3f}",
        ]
    )
    if prediction.model_probability is not None:
        parts.append(f"model_probability={prediction.model_probability:.3f}")
    if prediction.implied_probability is not None:
        parts.append(f"implied_probability={prediction.implied_probability:.3f}")
    if prediction.probability_edge is not None:
        parts.append(f"probability_edge={prediction.probability_edge:.3f}")
    if prediction.expected_value is not None:
        parts.append(f"expected_value={prediction.expected_value:.3f}")
    if prediction.stake_fraction is not None:
        parts.append(f"stake_fraction={prediction.stake_fraction:.3f}")
    if prediction.stake_amount is not None:
        parts.append(
            "stake_amount="
            f"${prediction.stake_amount:.2f} "
            f"({_format_unit_stake(prediction.stake_amount, unit_size)})"
        )
    if prediction.favorable_close_probability is not None:
        parts.append(
            f"favorable_close_probability={prediction.favorable_close_probability:.3f}"
        )
    if prediction.reason_code is not None:
        parts.append(f"reason_code={prediction.reason_code}")
    if prediction.note is not None and prediction.note != prediction.reason_code:
        parts.append(f"note={prediction.note}")
    return " | ".join(parts)


def _format_compact_upcoming_prediction_row(
    *,
    prediction: UpcomingGamePrediction,
    rank: int,
    unit_size: float,
) -> str:
    """Render one compact upcoming-game row for default text output."""
    parts = [
        f"{rank}. {_format_local_timestamp(prediction.commence_time)}",
        prediction.status,
    ]
    if prediction.market is not None and prediction.market_price is not None:
        sportsbook = prediction.sportsbook or "unknown"
        price = _format_moneyline(prediction.market_price) or str(
            prediction.market_price
        )
        if prediction.market == "spread":
            parts.append(
                f"{prediction.team_name} "
                f"{(prediction.line_value or 0.0):+.1f} "
                f"at {sportsbook} {price}"
            )
        else:
            parts.append(f"{prediction.team_name} ML at {sportsbook} {price}")
    else:
        parts.append(prediction.team_name)
    if prediction.status == "bet" and prediction.stake_amount is not None:
        parts.append(_format_unit_stake(prediction.stake_amount, unit_size))
        parts.append(
            "target "
            + _format_compact_target(
                market=prediction.market or "moneyline",
                line_value=(
                    prediction.min_acceptable_line
                    if prediction.min_acceptable_line is not None
                    else prediction.line_value
                ),
                market_price=(
                    prediction.min_acceptable_price
                    if prediction.min_acceptable_price is not None
                    else prediction.market_price
                ),
            )
        )
    elif prediction.status == "wait":
        parts.append(
            "target "
            + _format_compact_target(
                market=prediction.market or "moneyline",
                line_value=(
                    prediction.min_acceptable_line
                    if prediction.min_acceptable_line is not None
                    else prediction.line_value
                ),
                market_price=(
                    prediction.min_acceptable_price
                    if prediction.min_acceptable_price is not None
                    else prediction.market_price
                ),
            )
        )
    elif prediction.reason_code is not None:
        parts.append(f"reason {prediction.reason_code}")
    elif prediction.note is not None:
        parts.append(f"reason {prediction.note}")
    return " | ".join(parts)


def _format_market_label(
    *,
    market: ModelMarket,
    line_value: float | None,
    market_price: float,
) -> str:
    """Render one market's line and price in a shared format."""
    price = _format_moneyline(market_price)
    if market == "spread":
        return f"spread {(line_value or 0.0):+.1f} @ {price}"
    return f"moneyline {price}"


def _format_upcoming_metrics(
    prediction: UpcomingGamePrediction,
    *,
    unit_size: float,
) -> str:
    """Render the model metrics attached to one upcoming game."""
    if (
        prediction.model_probability is None
        or prediction.implied_probability is None
        or prediction.probability_edge is None
        or prediction.expected_value is None
    ):
        return f"note={prediction.note or 'none'}"

    parts = [
        f"model={prediction.model_probability:.3f}",
        f"implied={prediction.implied_probability:.3f}",
        f"prob_edge={prediction.probability_edge:.3f}",
        f"edge={prediction.expected_value:.3f}",
    ]
    if prediction.stake_amount is not None:
        parts.append(f"stake={_format_unit_stake(prediction.stake_amount, unit_size)}")
    if prediction.favorable_close_probability is not None:
        parts.append(
            f"favorable_close_prob={prediction.favorable_close_probability:.3f}"
        )
    if prediction.note is not None:
        parts.append(f"note={prediction.note}")
    return " | ".join(parts)


def _format_optional_number(value: float | None) -> str:
    """Format optional numeric quote fields for CLI output."""
    if value is None:
        return "none"
    return f"{value:.1f}"


def _format_moneyline(value: float | None) -> str | None:
    """Format an American moneyline value for CLI output."""
    if value is None:
        return None

    rounded_value = int(round(value))
    if abs(value - rounded_value) < 1e-9:
        if rounded_value > 0:
            return f"+{rounded_value}"
        return str(rounded_value)
    if value > 0:
        return f"+{value:.1f}"
    return f"{value:.1f}"


def _format_unit_stake(stake_amount: float, unit_size: float) -> str:
    """Render a stake amount in betting units."""
    if unit_size <= 0:
        return f"${stake_amount:.2f}"
    return f"{stake_amount / unit_size:.2f}u"


def _format_fanduel_team_link(team_name: str) -> str | None:
    """Build a deterministic FanDuel college-basketball team-page URL."""
    try:
        team_key = normalize_team_key(team_name)
    except ValueError:
        return None
    return FANDUEL_COLLEGE_BASKETBALL_TEAM_URL.format(team_key=team_key)


def _format_signed_currency(value: float) -> str:
    """Render a signed currency amount for bankroll and realized PnL output."""
    sign = "+" if value >= 0 else "-"
    return f"{sign}${abs(value):.2f}"


def _format_local_timestamp(value: str | None) -> str:
    """Render one stored timestamp in the machine's local timezone."""
    if value is None:
        return "unknown"

    timestamp = _parse_timestamp(value)
    local_timestamp = timestamp.astimezone(_get_local_timezone())
    return local_timestamp.strftime("%Y-%m-%d %H:%M %Z")


def _format_local_timestamp_iso(value: str | None) -> str | None:
    """Render one stored timestamp as local ISO-8601."""
    if value is None:
        return None
    timestamp = _parse_timestamp(value)
    return timestamp.astimezone(_get_local_timezone()).isoformat()


def _format_local_datetime_iso(value: datetime) -> str:
    """Render one aware datetime as local ISO-8601."""
    return value.astimezone(_get_local_timezone()).isoformat()


def _format_optional_datetime_iso(value: datetime | None) -> str:
    """Render an optional datetime as local ISO-8601."""
    if value is None:
        return "none"
    return _format_local_datetime_iso(value)


def _prediction_availability_summary_payload(
    *,
    summary: PredictionSummary,
) -> dict[str, object]:
    games_with_context = summary.availability_summary.games_with_context
    games_without_context = max(summary.available_games - games_with_context, 0)
    return {
        "games_with_context": games_with_context,
        "games_without_context": games_without_context,
        "coverage_status_counts": {
            "both": summary.availability_summary.games_with_both_reports,
            "team_only": summary.availability_summary.games_with_team_only,
            "opponent_only": (
                summary.availability_summary.games_with_opponent_only
            ),
        },
        "latest_report_update_at_local": _format_local_timestamp_iso(
            summary.availability_summary.latest_report_update_at
        ),
        "closest_report_minutes_before_tip": (
            summary.availability_summary.closest_report_minutes_before_tip
        ),
    }


def _prediction_availability_summary_text(
    *,
    summary: PredictionSummary,
) -> str:
    parts = [
        "upcoming_games_with_context="
        f"{summary.availability_summary.games_with_context}/{summary.available_games}",
        f"both={summary.availability_summary.games_with_both_reports}",
        f"team_only={summary.availability_summary.games_with_team_only}",
        "opponent_only="
        f"{summary.availability_summary.games_with_opponent_only}",
    ]
    latest_report_update_at = _format_local_timestamp_iso(
        summary.availability_summary.latest_report_update_at
    )
    if latest_report_update_at is not None:
        parts.append(f"latest_report_update={latest_report_update_at}")
    if summary.availability_summary.closest_report_minutes_before_tip is not None:
        parts.append(
            "closest_report="
            + _format_minutes_before_tip(
                summary.availability_summary.closest_report_minutes_before_tip
            )
        )
    return ", ".join(parts)


def _format_minutes_before_tip(value: float) -> str:
    rounded_value = round(value)
    return f"{rounded_value} min before tip"


def _prediction_summary_payload(
    *,
    summary: PredictionSummary,
    bankroll: float,
) -> dict[str, object]:
    policy = summary.applied_policy or BetPolicy()
    return {
        "schema_version": "predict.v1",
        "generated_at": (
            _format_local_datetime_iso(summary.generated_at)
            if summary.generated_at is not None
            else None
        ),
        "expires_at": (
            _format_local_datetime_iso(summary.expires_at)
            if summary.expires_at is not None
            else None
        ),
        "market": summary.market,
        "artifact_name": summary.artifact_name,
        "summary": {
            "available_games": summary.available_games,
            "candidates_considered": summary.candidates_considered,
            "deferred_count": len(summary.deferred_recommendations),
            "recommendations_count": summary.bets_placed,
            "availability_shadow": _prediction_availability_summary_payload(
                summary=summary
            ),
        },
        "policy": _prediction_policy_payload(policy),
        "risk_guardrails": {
            "worst_case_same_day_loss": (bankroll * policy.max_daily_exposure_fraction),
        },
        "recommendations": [
            _placed_bet_payload(recommendation=bet, rank=index)
            for index, bet in enumerate(summary.recommendations, start=1)
        ],
        "wait_list": [
            _deferred_recommendation_payload(recommendation=wait, rank=index)
            for index, wait in enumerate(summary.deferred_recommendations, start=1)
        ],
        "upcoming_games": [
            _upcoming_prediction_payload(prediction=prediction, rank=index)
            for index, prediction in enumerate(summary.upcoming_games, start=1)
        ],
    }


def _echo_tournament_summary(*, summary: TournamentSummary) -> None:
    """Render one tournament bracket summary for CLI text output."""
    champion_pick = _tournament_champion_pick(summary)
    champion_label = (
        _format_tournament_seeded_team(
            champion_pick.winner_name,
            champion_pick.winner_seed,
        )
        if champion_pick is not None
        else None
    )
    runner_up_label = (
        _format_tournament_seeded_team(
            _tournament_pick_loser_name(champion_pick),
            _tournament_pick_loser_seed(champion_pick),
        )
        if champion_pick is not None
        else None
    )
    typer.echo(
        "Tournament Summary: "
        f"tournament={summary.label}, "
        f"season={summary.season}, "
        f"artifact={summary.artifact_name}, "
        f"simulations={summary.simulations}, "
        f"games={len(summary.bracket_picks)}, "
        f"teams={len(summary.team_advancement)}"
    )
    typer.echo(f"Generated At: {_format_local_datetime_iso(summary.generated_at)}")
    if champion_pick is not None:
        typer.echo(
            "Champion Pick: "
            f"{champion_label} over {runner_up_label} "
            f"({champion_pick.winner_probability * 100.0:.1f}%)"
        )

    typer.echo("")
    typer.echo("Bracket Picks")
    _echo_tournament_bracket_picks(summary.bracket_picks)

    typer.echo("")
    typer.echo("Title Odds")
    _echo_tournament_title_odds(summary.team_advancement)


def _echo_tournament_bracket_picks(picks: list[TournamentGamePick]) -> None:
    """Render one compact bracket-picks section."""
    for pick in picks:
        typer.echo(f"  {_format_tournament_pick_row(pick)}")


def _echo_tournament_title_odds(teams: list[TournamentTeamAdvancement]) -> None:
    """Render the top title contenders for quick bracket reference."""
    if not teams:
        typer.echo("  (no rows)")
        return
    for index, team in enumerate(teams[:10], start=1):
        typer.echo(f"  {_format_tournament_title_odds_row(team=team, rank=index)}")


def _echo_tournament_backtest_summary(*, summary: TournamentBacktestSummary) -> None:
    """Render one prior-years tournament backtest summary."""
    seasons = ", ".join(str(item.season) for item in summary.season_summaries)
    typer.echo(
        "Tournament Backtest Summary: "
        f"seasons={seasons}, "
        f"games={summary.games}, "
        f"correct={summary.correct_picks}, "
        f"accuracy={summary.accuracy * 100.0:.1f}%, "
        f"champion_hits={summary.champion_hits}/{len(summary.season_summaries)}"
    )
    typer.echo(f"Generated At: {_format_local_datetime_iso(summary.generated_at)}")
    typer.echo(
        "Actual Winner Prob: "
        f"{summary.average_actual_winner_probability * 100.0:.1f}%"
    )
    typer.echo("")
    typer.echo("Season Results")
    for season_summary in summary.season_summaries:
        typer.echo(f"  {_format_tournament_backtest_season_row(season_summary)}")
    typer.echo("")
    typer.echo("Round Accuracy")
    for round_summary in summary.round_summaries:
        typer.echo(f"  {_format_tournament_backtest_round_row(round_summary)}")


def _format_tournament_pick_row(pick: TournamentGamePick) -> str:
    """Render one compact bracket pick row."""
    parts = [pick.round_label]
    if pick.region is not None:
        parts.append(pick.region)
    matchup_label = (
        f"{_format_tournament_seeded_team(pick.home_team_name, pick.home_seed)} "
        f"vs {_format_tournament_seeded_team(pick.away_team_name, pick.away_seed)}"
    )
    winner_label = _format_tournament_seeded_team(pick.winner_name, pick.winner_seed)
    parts.extend(
        [
            matchup_label,
            f"pick {winner_label}",
            f"{pick.winner_probability * 100.0:.1f}%",
        ]
    )
    return " | ".join(parts)


def _format_tournament_title_odds_row(
    *,
    team: TournamentTeamAdvancement,
    rank: int,
) -> str:
    """Render one compact title-odds row."""
    seeded_team_label = _format_tournament_seeded_team(team.team_name, team.seed)
    return " | ".join(
        [
            f"{rank}. {seeded_team_label} ({team.region})",
            f"title {team.title_probability * 100.0:.1f}%",
            f"title game {team.championship_probability * 100.0:.1f}%",
            f"final four {team.final_4_probability * 100.0:.1f}%",
        ]
    )


def _format_tournament_seeded_team(team_name: str, seed: int) -> str:
    """Render one seeded team label for bracket output."""
    return f"{seed} {team_name}"


def _format_tournament_backtest_season_row(
    summary: TournamentBacktestSeasonSummary,
) -> str:
    """Render one compact season-level tournament backtest row."""
    champion_label = (
        _format_tournament_seeded_team(
            summary.predicted_champion_name,
            summary.predicted_champion_seed,
        )
        if (
            summary.predicted_champion_name is not None
            and summary.predicted_champion_seed is not None
        )
        else "n/a"
    )
    actual_champion_label = (
        _format_tournament_seeded_team(
            summary.actual_champion_name,
            summary.actual_champion_seed,
        )
        if (
            summary.actual_champion_name is not None
            and summary.actual_champion_seed is not None
        )
        else "n/a"
    )
    training_seasons = ",".join(str(season) for season in summary.training_seasons)
    return " | ".join(
        [
            str(summary.season),
            f"trained_on={training_seasons}",
            f"correct {summary.correct_picks}/{summary.games}",
            f"accuracy {summary.accuracy * 100.0:.1f}%",
            (
                "champion hit"
                if summary.champion_correct
                else f"champion miss ({champion_label} vs {actual_champion_label})"
            ),
            f"final four {summary.final_four_teams_correct}/4",
            (
                "actual winner prob "
                f"{summary.average_actual_winner_probability * 100.0:.1f}%"
            ),
        ]
    )


def _format_tournament_backtest_round_row(
    summary: TournamentBacktestRoundSummary,
) -> str:
    """Render one compact round-level accuracy row."""
    return " | ".join(
        [
            summary.round_label,
            f"correct {summary.correct_picks}/{summary.games}",
            f"accuracy {summary.accuracy * 100.0:.1f}%",
        ]
    )


def _tournament_champion_pick(summary: TournamentSummary) -> TournamentGamePick | None:
    """Return the championship pick from one tournament summary."""
    for pick in reversed(summary.bracket_picks):
        if pick.round_label == "Championship":
            return pick
    if not summary.bracket_picks:
        return None
    return summary.bracket_picks[-1]


def _tournament_pick_loser_name(pick: TournamentGamePick) -> str:
    """Return the losing team's name for one picked game."""
    if pick.winner_name == pick.home_team_name:
        return pick.away_team_name
    return pick.home_team_name


def _tournament_pick_loser_seed(pick: TournamentGamePick) -> int:
    """Return the losing team's seed for one picked game."""
    if pick.winner_name == pick.home_team_name:
        return pick.away_seed
    return pick.home_seed


def _tournament_summary_payload(*, summary: TournamentSummary) -> dict[str, object]:
    """Render the tournament summary in a stable machine-readable shape."""
    champion_pick = _tournament_champion_pick(summary)
    return {
        "schema_version": "tournament.v1",
        "generated_at": _format_local_datetime_iso(summary.generated_at),
        "tournament_key": summary.tournament_key,
        "label": summary.label,
        "season": summary.season,
        "artifact_name": summary.artifact_name,
        "simulations": summary.simulations,
        "summary": {
            "games": len(summary.bracket_picks),
            "teams": len(summary.team_advancement),
        },
        "champion_pick": (
            _tournament_pick_payload(pick=champion_pick)
            if champion_pick is not None
            else None
        ),
        "bracket_picks": [
            _tournament_pick_payload(pick=pick) for pick in summary.bracket_picks
        ],
        "team_advancement": [
            _tournament_team_advancement_payload(team=team)
            for team in summary.team_advancement
        ],
    }


def _tournament_backtest_summary_payload(
    *,
    summary: TournamentBacktestSummary,
) -> dict[str, object]:
    """Render the tournament backtest summary in a stable JSON shape."""
    return {
        "schema_version": "tournament_backtest.v1",
        "generated_at": _format_local_datetime_iso(summary.generated_at),
        "summary": {
            "seasons": len(summary.season_summaries),
            "games": summary.games,
            "correct_picks": summary.correct_picks,
            "accuracy": summary.accuracy,
            "champion_hits": summary.champion_hits,
            "average_actual_winner_probability": (
                summary.average_actual_winner_probability
            ),
        },
        "season_summaries": [
            _tournament_backtest_season_payload(item)
            for item in summary.season_summaries
        ],
        "round_summaries": [
            _tournament_backtest_round_payload(item)
            for item in summary.round_summaries
        ],
    }


def _tournament_pick_payload(*, pick: TournamentGamePick) -> dict[str, object]:
    """Render one picked tournament game in a stable JSON shape."""
    return {
        "game_key": pick.game_key,
        "round": pick.round_label,
        "region": pick.region,
        "scheduled_time_local": _format_local_timestamp_iso(pick.scheduled_time),
        "source": pick.source,
        "live_game_id": pick.live_game_id,
        "home_team": {
            "name": pick.home_team_name,
            "seed": pick.home_seed,
        },
        "away_team": {
            "name": pick.away_team_name,
            "seed": pick.away_seed,
        },
        "winner": {
            "name": pick.winner_name,
            "seed": pick.winner_seed,
            "probability": pick.winner_probability,
        },
    }


def _tournament_team_advancement_payload(
    *,
    team: TournamentTeamAdvancement,
) -> dict[str, object]:
    """Render one team's tournament advancement probabilities."""
    return {
        "team": team.team_name,
        "seed": team.seed,
        "region": team.region,
        "round_of_64_probability": team.round_of_64_probability,
        "round_of_32_probability": team.round_of_32_probability,
        "sweet_16_probability": team.sweet_16_probability,
        "elite_8_probability": team.elite_8_probability,
        "final_4_probability": team.final_4_probability,
        "championship_probability": team.championship_probability,
        "title_probability": team.title_probability,
    }


def _tournament_backtest_season_payload(
    summary: TournamentBacktestSeasonSummary,
) -> dict[str, object]:
    """Render one season of tournament backtest output."""
    return {
        "tournament_key": summary.tournament_key,
        "label": summary.label,
        "season": summary.season,
        "training_seasons": list(summary.training_seasons),
        "games": summary.games,
        "correct_picks": summary.correct_picks,
        "accuracy": summary.accuracy,
        "average_actual_winner_probability": summary.average_actual_winner_probability,
        "predicted_champion": (
            {
                "name": summary.predicted_champion_name,
                "seed": summary.predicted_champion_seed,
                "probability": summary.predicted_champion_probability,
            }
            if summary.predicted_champion_name is not None
            else None
        ),
        "actual_champion": (
            {
                "name": summary.actual_champion_name,
                "seed": summary.actual_champion_seed,
            }
            if summary.actual_champion_name is not None
            else None
        ),
        "champion_correct": summary.champion_correct,
        "final_four_teams_correct": summary.final_four_teams_correct,
        "round_summaries": [
            _tournament_backtest_round_payload(item)
            for item in summary.round_summaries
        ],
    }


def _tournament_backtest_round_payload(
    summary: TournamentBacktestRoundSummary,
) -> dict[str, object]:
    """Render one round-level tournament backtest row."""
    return {
        "round": summary.round_label,
        "games": summary.games,
        "correct_picks": summary.correct_picks,
        "accuracy": summary.accuracy,
    }


def _prediction_policy_payload(policy: BetPolicy) -> dict[str, object]:
    """Render the predict policy in a stable machine-readable shape."""
    payload: dict[str, object] = {
        "min_edge": policy.min_edge,
        "min_confidence": policy.min_confidence,
        "min_probability_edge": policy.min_probability_edge,
        "uncertainty_probability_buffer": policy.uncertainty_probability_buffer,
        "min_games_played": policy.min_games_played,
        "min_moneyline_price": policy.min_moneyline_price,
        "max_moneyline_price": policy.max_moneyline_price,
        "min_positive_ev_books": policy.min_positive_ev_books,
        "min_median_expected_value": policy.min_median_expected_value,
        "kelly_fraction": policy.kelly_fraction,
        "max_bet_fraction": policy.max_bet_fraction,
        "max_daily_exposure_fraction": policy.max_daily_exposure_fraction,
        "max_bets_per_day": policy.max_bets_per_day,
        "max_spread_abs_line": policy.max_spread_abs_line,
        "max_abs_rest_days_diff": policy.max_abs_rest_days_diff,
    }
    return payload


def _placed_bet_payload(
    *,
    recommendation: PlacedBet,
    rank: int,
) -> dict[str, object]:
    return {
        "rank": rank,
        "game_id": recommendation.game_id,
        "commence_time_local": _format_local_timestamp_iso(
            recommendation.commence_time
        ),
        "team": recommendation.team_name,
        "opponent": recommendation.opponent_name,
        "market": recommendation.market,
        "side": recommendation.side,
        "sportsbook": recommendation.sportsbook or None,
        "line_value": recommendation.line_value,
        "market_price": recommendation.market_price,
        "eligible_books": recommendation.eligible_books,
        "positive_ev_books": recommendation.positive_ev_books,
        "coverage_rate": recommendation.coverage_rate,
        "model_probability": recommendation.model_probability,
        "implied_probability": recommendation.implied_probability,
        "probability_edge": recommendation.probability_edge,
        "expected_value": recommendation.expected_value,
        "stake_fraction": recommendation.stake_fraction,
        "stake_amount": recommendation.stake_amount,
        "supporting_quotes": _supporting_quotes_payload(
            recommendation.supporting_quotes
        ),
        "min_acceptable_line": recommendation.min_acceptable_line,
        "min_acceptable_price": recommendation.min_acceptable_price,
        "reason": "qualified",
    }


def _deferred_recommendation_payload(
    *,
    recommendation: DeferredRecommendation,
    rank: int,
) -> dict[str, object]:
    candidate = recommendation.candidate
    return {
        "rank": rank,
        "game_id": candidate.game_id,
        "commence_time_local": _format_local_timestamp_iso(candidate.commence_time),
        "team": candidate.team_name,
        "opponent": candidate.opponent_name,
        "market": candidate.market,
        "side": candidate.side,
        "sportsbook": candidate.sportsbook or None,
        "line_value": candidate.line_value,
        "market_price": candidate.market_price,
        "eligible_books": candidate.eligible_books,
        "positive_ev_books": candidate.positive_ev_books,
        "coverage_rate": candidate.coverage_rate,
        "model_probability": candidate.model_probability,
        "implied_probability": candidate.implied_probability,
        "probability_edge": candidate.probability_edge,
        "expected_value": candidate.expected_value,
        "stake_fraction": candidate.stake_fraction,
        "favorable_close_probability": recommendation.favorable_close_probability,
        "supporting_quotes": _supporting_quotes_payload(candidate.supporting_quotes),
        "min_acceptable_line": candidate.min_acceptable_line,
        "min_acceptable_price": candidate.min_acceptable_price,
        "reason": "timing_wait",
    }


def _upcoming_prediction_payload(
    *,
    prediction: UpcomingGamePrediction,
    rank: int,
) -> dict[str, object]:
    return {
        "rank": rank,
        "game_id": prediction.game_id,
        "commence_time_local": _format_local_timestamp_iso(prediction.commence_time),
        "status": prediction.status,
        "team": prediction.team_name,
        "opponent": prediction.opponent_name,
        "market": prediction.market,
        "side": prediction.side,
        "sportsbook": prediction.sportsbook,
        "line_value": prediction.line_value,
        "market_price": prediction.market_price,
        "eligible_books": prediction.eligible_books,
        "positive_ev_books": prediction.positive_ev_books,
        "coverage_rate": prediction.coverage_rate,
        "model_probability": prediction.model_probability,
        "implied_probability": prediction.implied_probability,
        "probability_edge": prediction.probability_edge,
        "expected_value": prediction.expected_value,
        "stake_fraction": prediction.stake_fraction,
        "stake_amount": prediction.stake_amount,
        "favorable_close_probability": prediction.favorable_close_probability,
        "supporting_quotes": _supporting_quotes_payload(prediction.supporting_quotes),
        "min_acceptable_line": prediction.min_acceptable_line,
        "min_acceptable_price": prediction.min_acceptable_price,
        "reason_code": prediction.reason_code,
        "note": prediction.note,
        "availability_context": _availability_game_context_payload(
            prediction.availability_context
        ),
    }


def _availability_game_context_payload(
    context: AvailabilityGameContext | None,
) -> dict[str, object] | None:
    if context is None:
        return None
    return {
        "coverage_status": context.coverage_status,
        "team": _availability_side_context_payload(context.team),
        "opponent": _availability_side_context_payload(context.opponent),
    }


def _availability_side_context_payload(
    context: AvailabilitySideContext,
) -> dict[str, object]:
    return {
        "has_report": context.has_report,
        "source_name": context.source_name,
        "latest_update_at_local": _format_local_timestamp_iso(
            context.latest_update_at
        ),
        "latest_minutes_before_tip": context.latest_minutes_before_tip,
        "any_out": context.any_out,
        "any_questionable": context.any_questionable,
        "out_count": context.out_count,
        "questionable_count": context.questionable_count,
        "matched_row_count": context.matched_row_count,
        "unmatched_row_count": context.unmatched_row_count,
    }


def _supporting_quotes_payload(
    quotes: tuple[SupportingQuote, ...],
) -> list[dict[str, object]]:
    """Render supporting quotes in a stable, short machine-readable shape."""
    return [
        {
            "sportsbook": quote.sportsbook or None,
            "line_value": quote.line_value,
            "market_price": quote.market_price,
            "expected_value": quote.expected_value,
        }
        for quote in quotes
    ]


def _echo_suggestions(suggestions: list[str]) -> None:
    """Render fallback team suggestions when exact lookup fails."""
    if not suggestions:
        return

    typer.echo("Did you mean:")
    for suggestion in suggestions:
        typer.echo(f"  {suggestion}")


def _echo_samples(header: str, samples: tuple[str, ...]) -> None:
    """Render a titled sample block when verification finds issues."""
    if not samples:
        return

    typer.echo("")
    typer.echo(header)
    for sample in samples:
        typer.echo(f"  {sample}")


def _parse_date_option(value: str | None, option_name: str) -> date | None:
    """Parse an ISO date option for CLI commands."""
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"{option_name} must be in YYYY-MM-DD format") from exc


def _parse_model_market(value: str) -> ModelMarket:
    """Validate a model market CLI option."""
    normalized_value = value.strip().lower()
    if normalized_value in {"moneyline", "spread"}:
        return cast(ModelMarket, normalized_value)
    raise typer.BadParameter("market must be one of: moneyline, spread")


def _parse_strategy_market(value: str) -> StrategyMarket:
    """Validate a strategy market CLI option."""
    normalized_value = value.strip().lower()
    if normalized_value in {"moneyline", "spread", "best"}:
        return cast(StrategyMarket, normalized_value)
    raise typer.BadParameter("market must be one of: moneyline, spread, best")


def _parse_model_family(value: str) -> ModelFamily:
    """Validate a model-family CLI option."""
    normalized_value = value.strip().lower()
    if normalized_value in {"logistic", "hist_gradient_boosting"}:
        return cast(ModelFamily, normalized_value)
    raise typer.BadParameter(
        "model family must be one of: logistic, hist_gradient_boosting"
    )


def _parse_timestamp(value: str) -> datetime:
    """Parse a stored ISO-like timestamp into an aware datetime."""
    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value


@lru_cache(maxsize=1)
def _get_local_timezone() -> tzinfo:
    """Resolve the machine's local timezone for CLI display."""
    tz_name = os.environ.get("TZ", "").strip()
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except ZoneInfoNotFoundError:
            pass

    localtime_path = Path("/etc/localtime")
    try:
        resolved_path = localtime_path.resolve()
    except OSError:
        resolved_path = localtime_path

    parts = resolved_path.parts
    if "zoneinfo" in parts:
        zoneinfo_index = parts.index("zoneinfo")
        zone_key = "/".join(parts[zoneinfo_index + 1 :])
        if zone_key:
            try:
                return ZoneInfo(zone_key)
            except ZoneInfoNotFoundError:
                pass

    fallback_timezone = datetime.now().astimezone().tzinfo
    if fallback_timezone is None:
        return UTC
    return fallback_timezone


if __name__ == "__main__":
    app()
