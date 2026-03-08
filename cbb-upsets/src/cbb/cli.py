"""CLI for database setup, inspection, and ingest workflows."""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, tzinfo
from functools import lru_cache
from pathlib import Path
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
app.add_typer(db_app, name="db")
db_app.add_typer(db_view_app, name="view")
app.add_typer(ingest_app, name="ingest")


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
