"""CLI for database setup, ingest, and betting-model workflows."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, tzinfo
from functools import lru_cache
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import typer

from cbb.db import (
    GameSummary,
    OddsSnapshotSummary,
    TeamRecentResult,
    UpcomingGameView,
    get_database_summary,
    get_engine,
    get_team_view,
    get_upcoming_games,
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
)
from cbb.ingest import (
    ingest_closing_odds as run_ingest_closing_odds,
)
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
    DEFAULT_UNIT_SIZE,
    BacktestOptions,
    BestBacktestReportOptions,
    BetPolicy,
    LogisticRegressionConfig,
    ModelFamily,
    ModelMarket,
    PlacedBet,
    PredictionOptions,
    StrategyMarket,
    TrainingOptions,
    backtest_betting_model,
    generate_best_backtest_report,
    predict_best_bets,
    train_betting_model,
)
from cbb.team_catalog import load_team_catalog, seed_team_catalog
from cbb.verify import (
    DEFAULT_VERIFICATION_YEARS,
    VerificationOptions,
    verify_games,
)

app = typer.Typer(
    help="CLI for NCAA men's basketball data ingest and local Postgres management."
)
db_app = typer.Typer(help="Database setup, inspection, and audit commands.")
db_view_app = typer.Typer(help="Database-backed read-only views.")
ingest_app = typer.Typer(help="Data ingest commands.")
model_app = typer.Typer(
    help="Betting-model training, backtesting, reporting, and prediction."
)
app.add_typer(db_app, name="db")
db_app.add_typer(db_view_app, name="view")
app.add_typer(ingest_app, name="ingest")
app.add_typer(model_app, name="model")


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
    """Verify stored D1 games against ESPN scoreboard coverage and scores."""
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
        f"score_mismatches={summary.score_mismatches}"
    )
    _echo_samples("Missing Samples", summary.sample_missing_games)
    _echo_samples("Status Mismatch Samples", summary.sample_status_mismatches)
    _echo_samples("Score Mismatch Samples", summary.sample_score_mismatches)


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


@db_view_app.command("team")
def db_view_team_command(
    team_name: str = typer.Argument(..., help="Canonical team name or exact alias."),
) -> None:
    """Show the five most recent completed results for one team."""
    view = get_team_view(team_name)
    if view.team_name is None:
        typer.echo(f"No exact team match for {team_name!r}.")
        _echo_suggestions(view.suggestions)
        raise typer.Exit(code=1)

    typer.echo(f"Team: {view.team_name}")
    if view.scheduled_games:
        typer.echo("Current / Upcoming")
        _echo_upcoming_games(view.scheduled_games)
        typer.echo("")
    typer.echo("Recent Results")
    _echo_team_recent_results(view.recent_results)


@db_view_app.command("upcoming")
def db_view_upcoming_command(
    limit: int = typer.Option(
        10,
        "--limit",
        min=1,
        help=(
            "Maximum number of future upcoming games to show. In-progress "
            "games are always all shown."
        ),
    ),
) -> None:
    """Show current in-progress and upcoming games from the DB."""
    games = get_upcoming_games(limit=limit)
    _echo_upcoming_games(games)


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
        help="Historical market key. Start with h2h for moneyline closes.",
    ),
    force_refresh: bool = typer.Option(
        False,
        "--force-refresh",
        help="Re-fetch slots even if they were already checkpointed.",
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
            force_refresh=force_refresh,
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
        1000.0,
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
    spread_model_family: str = typer.Option(
        DEFAULT_SPREAD_MODEL_FAMILY,
        "--spread-model-family",
        help="Spread model family used during walk-forward training blocks.",
    ),
    min_edge: float = typer.Option(
        0.02,
        "--min-edge",
        help="Minimum expected value required to place a bet.",
    ),
    min_confidence: float = typer.Option(
        0.0,
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
        8,
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
        BetPolicy().max_spread_abs_line,
        "--max-spread-abs-line",
        min=0.0,
        help="Maximum absolute spread line eligible for betting.",
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
            BacktestOptions(
                market=_parse_strategy_market(market),
                seasons_back=seasons_back,
                evaluation_season=evaluation_season,
                starting_bankroll=starting_bankroll,
                unit_size=unit_size,
                retrain_days=retrain_days,
                auto_tune_spread_policy=auto_tune_spread_policy,
                spread_model_family=_parse_model_family(spread_model_family),
                policy=BetPolicy(
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
                ),
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
    if summary.final_policy is not None:
        typer.echo(
            "Tuned Spread Policy: "
            f"blocks={summary.policy_tuned_blocks}, "
            f"min_edge={summary.final_policy.min_edge:.3f}, "
            f"min_probability_edge={summary.final_policy.min_probability_edge:.3f}, "
            f"min_games_played={summary.final_policy.min_games_played}, "
            f"max_spread_abs_line={_format_optional_float(summary.final_policy.max_spread_abs_line)}"
        )
    if summary.sample_bets:
        typer.echo("")
        typer.echo("Sample Bets")
        _echo_betting_recommendations(summary.sample_bets)


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
        1000.0,
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
        True,
        "--auto-tune-spread-policy/--no-auto-tune-spread-policy",
        help="Auto-apply the best walk-forward tuned spread policy to live picks.",
    ),
    min_edge: float = typer.Option(
        0.02,
        "--min-edge",
        help="Minimum expected value required to place a bet.",
    ),
    min_confidence: float = typer.Option(
        0.0,
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
        8,
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
        BetPolicy().max_spread_abs_line,
        "--max-spread-abs-line",
        min=0.0,
        help="Maximum absolute spread line eligible for betting.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show full model, market, and edge details for each recommendation.",
    ),
) -> None:
    """Rank current upcoming betting opportunities from trained artifacts."""
    try:
        summary = predict_best_bets(
            PredictionOptions(
                market=_parse_strategy_market(market),
                artifact_name=artifact_name,
                bankroll=bankroll,
                limit=limit,
                auto_tune_spread_policy=auto_tune_spread_policy,
                policy=BetPolicy(
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
                ),
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Predicted {summary.market}: "
        f"available_games={summary.available_games}, "
        f"candidates={summary.candidates_considered}, "
        f"recommendations={summary.bets_placed}"
    )
    if summary.policy_was_auto_tuned and summary.applied_policy is not None:
        typer.echo(
            "Auto-Tuned Spread Policy: "
            f"min_edge={summary.applied_policy.min_edge:.3f}, "
            f"min_probability_edge={summary.applied_policy.min_probability_edge:.3f}, "
            f"min_games_played={summary.applied_policy.min_games_played}, "
            f"max_spread_abs_line={_format_optional_float(summary.applied_policy.max_spread_abs_line)}"
        )
    if not summary.recommendations:
        typer.echo("No bets qualified under the current policy.")
        return

    typer.echo("")
    typer.echo(f"Bet Slip (1u = ${unit_size:.2f})")
    if verbose:
        _echo_betting_recommendations(
            summary.recommendations,
            unit_size=unit_size,
        )
        return
    _echo_simple_betting_recommendations(
        summary.recommendations,
        unit_size=unit_size,
    )


@model_app.command("report")
def model_report_command(
    output: Path = typer.Option(
        DEFAULT_BEST_BACKTEST_REPORT_PATH,
        "--output",
        help="Markdown report path. Defaults to docs/results/best-model-3y-backtest.md",
    ),
    seasons: int = typer.Option(
        3,
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
        1000.0,
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
        True,
        "--auto-tune-spread-policy/--no-auto-tune-spread-policy",
        help="Use the current spread auto-tuning path when reporting `best`.",
    ),
    spread_model_family: str = typer.Option(
        DEFAULT_SPREAD_MODEL_FAMILY,
        "--spread-model-family",
        help="Spread model family used during report backtests.",
    ),
) -> None:
    """Write a Markdown report for the current deployable best-model window."""
    try:
        report = generate_best_backtest_report(
            BestBacktestReportOptions(
                output_path=output,
                seasons=seasons,
                max_season=max_season,
                starting_bankroll=starting_bankroll,
                unit_size=unit_size,
                retrain_days=retrain_days,
                auto_tune_spread_policy=auto_tune_spread_policy,
                spread_model_family=_parse_model_family(spread_model_family),
            ),
            progress=typer.echo,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(
        f"Generated best-model report: {_format_repo_path(report.output_path)}"
    )
    if report.history_output_path is not None:
        typer.echo(
            f"History copy: {_format_repo_path(report.history_output_path)}"
        )
    typer.echo(
        f"Aggregate: seasons={len(report.selected_seasons)}, "
        f"bets={report.aggregate_bets}, "
        f"profit=${report.aggregate_profit:.2f}, "
        f"roi={report.aggregate_roi:.4f}"
    )
    typer.echo(
        f"Latest season {report.latest_summary.evaluation_season}: "
        f"profit=${report.latest_summary.profit:.2f}, "
        f"roi={report.latest_summary.roi:.4f}"
    )
    typer.echo(
        "Zero-bet seasons: "
        + (
            ", ".join(str(season) for season in report.zero_bet_seasons)
            if report.zero_bet_seasons
            else "none"
        )
    )


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


def _echo_team_recent_results(results: list[TeamRecentResult]) -> None:
    """Render recent results for a resolved team."""
    if not results:
        typer.echo("  (no completed games)")
        return

    for result in results:
        typer.echo(
            f"  {_format_local_timestamp(result.commence_time)} | {result.venue_label} "
            f"{result.opponent_name} | {result.result} "
            f"{result.team_score}-{result.opponent_score}"
        )


def _echo_upcoming_games(games: list[UpcomingGameView]) -> None:
    """Render upcoming and in-progress games."""
    if not games:
        typer.echo("  (no current upcoming or in-progress games)")
        return

    in_progress_games = [game for game in games if game.status == "in_progress"]
    upcoming_games = [game for game in games if game.status != "in_progress"]

    if in_progress_games:
        typer.echo("  In Progress")
        for game in in_progress_games:
            typer.echo(
                f"    {_format_local_timestamp(game.commence_time)} | "
                f"{_format_upcoming_matchup(game)}"
            )

    if upcoming_games:
        if in_progress_games:
            typer.echo("")
        typer.echo("  Upcoming")
        for game in upcoming_games:
            typer.echo(
                f"    {_format_local_timestamp(game.commence_time)} | "
                f"{_format_upcoming_matchup(game)}"
            )


def _format_upcoming_matchup(game: UpcomingGameView) -> str:
    """Render one upcoming or in-progress matchup with moneylines and scores."""
    home_score = game.home_score if game.status == "in_progress" else None
    away_score = game.away_score if game.status == "in_progress" else None
    home_team = _format_upcoming_team(
        game.home_team,
        game.home_pregame_moneyline,
        home_score,
    )
    away_team = _format_upcoming_team(
        game.away_team,
        game.away_pregame_moneyline,
        away_score,
    )
    return f"{home_team} vs {away_team}"


def _format_upcoming_team(
    team_name: str,
    pregame_moneyline: float | None,
    score: int | None,
) -> str:
    """Render one team with pregame ML next to the name and live score when present."""
    parts = [team_name]
    moneyline = _format_moneyline(pregame_moneyline)
    if moneyline is not None:
        parts.append(f"({moneyline})")
    if score is not None:
        parts.append(str(score))
    return " ".join(parts)


def _echo_betting_recommendations(
    recommendations: list[PlacedBet],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
) -> None:
    """Render ranked betting recommendations or settled sample bets."""
    for recommendation in recommendations:
        typer.echo(
            f"  {_format_local_timestamp(recommendation.commence_time)} | "
            f"{recommendation.team_name} vs {recommendation.opponent_name} | "
            f"{_format_betting_market(recommendation)} | "
            f"model={recommendation.model_probability:.3f} | "
            f"implied={recommendation.implied_probability:.3f} | "
            f"prob_edge={recommendation.probability_edge:.3f} | "
            f"edge={recommendation.expected_value:.3f} | "
            f"stake={_format_unit_stake(recommendation.stake_amount, unit_size)} "
            f"(${recommendation.stake_amount:.2f}) "
            f"({recommendation.stake_fraction:.3f})"
        )


def _echo_simple_betting_recommendations(
    recommendations: list[PlacedBet],
    *,
    unit_size: float = DEFAULT_UNIT_SIZE,
) -> None:
    """Render a compact bet-slip style list for current predictions."""
    for index, recommendation in enumerate(recommendations, start=1):
        typer.echo(
            f"  {index}. {_format_local_timestamp(recommendation.commence_time)} | "
            f"Bet {recommendation.team_name} vs {recommendation.opponent_name} | "
            f"{_format_betting_market(recommendation)} | "
            f"stake={_format_unit_stake(recommendation.stake_amount, unit_size)}"
        )


def _format_betting_market(recommendation: PlacedBet) -> str:
    """Render one bet's market and pricing information."""
    price = _format_moneyline(recommendation.market_price)
    if recommendation.market == "spread":
        line_value = recommendation.line_value or 0.0
        return f"spread {line_value:+.1f} @ {price}"
    return f"moneyline {price}"


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


def _format_local_timestamp(value: str | None) -> str:
    """Render one stored timestamp in the machine's local timezone."""
    if value is None:
        return "unknown"

    timestamp = _parse_timestamp(value)
    local_timestamp = timestamp.astimezone(_get_local_timezone())
    return local_timestamp.strftime("%Y-%m-%d %H:%M %Z")


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
