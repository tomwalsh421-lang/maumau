"""CLI for database setup, inspection, and ingest workflows."""

from __future__ import annotations

from datetime import date

import typer

from cbb.db import (
    GameSummary,
    OddsSnapshotSummary,
    get_database_summary,
    init_db as initialize_database,
)
from cbb.ingest import (
    DEFAULT_HISTORICAL_YEARS,
    DEFAULT_ODDS_MARKETS,
    DEFAULT_ODDS_REGIONS,
    DEFAULT_ODDS_SPORT,
    HistoricalIngestOptions,
    OddsIngestOptions,
    ingest_current_odds,
    ingest_historical_games,
)

app = typer.Typer(
    help="CLI for NCAA men's basketball data ingest and local Postgres management."
)


@app.command("init-db")
def init_db():
    """Initialize the PostgreSQL schema from ``sql/schema.sql``."""
    schema_path = initialize_database()
    typer.echo(f"Initialized database schema from {schema_path}")


@app.command("db-summary")
def db_summary():
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


@app.command()
def ingest_odds(
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
        help="How many days of completed scores to sync when include-scores is enabled.",
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


@app.command()
def ingest_data(
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
        f"teams={summary.teams_seen}"
    )


def _echo_game_samples(samples: list[GameSummary], include_scores: bool) -> None:
    """Render a list of game samples for CLI output."""
    if not samples:
        typer.echo("  (no rows)")
        return

    for sample in samples:
        if include_scores:
            typer.echo(
                f"  {sample.commence_time} | {sample.home_team} vs {sample.away_team} | "
                f"{sample.home_score}-{sample.away_score} | result={sample.result}"
            )
            continue
        typer.echo(
            f"  {sample.commence_time} | {sample.home_team} vs {sample.away_team}"
        )


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


def _parse_date_option(value: str | None, option_name: str) -> date | None:
    """Parse an ISO date option for CLI commands."""
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(
            f"{option_name} must be in YYYY-MM-DD format"
        ) from exc


if __name__ == "__main__":
    app()
