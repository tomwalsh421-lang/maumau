from datetime import timedelta, timezone
from pathlib import Path

from typer.testing import CliRunner

from cbb.cli import app
from cbb.db import TeamRecentResult, TeamView, UpcomingGameView
from cbb.db_backup import DatabaseBackupArtifact, DatabaseImportArtifact
from cbb.ingest import (
    ApiQuota,
    ClosingOddsIngestOptions,
    ClosingOddsIngestSummary,
    HistoricalIngestOptions,
    HistoricalIngestSummary,
)
from cbb.verify import GameVerificationSummary, VerificationOptions

runner = CliRunner()


def test_ingest_data_command_defaults_to_three_year_backfill(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_historical_games(**kwargs: object) -> HistoricalIngestSummary:
        captured.update(kwargs)
        return HistoricalIngestSummary(
            sport="basketball_ncaab",
            start_date="2023-03-07",
            end_date="2026-03-07",
            dates_requested=100,
            dates_skipped=50,
            dates_completed=100,
            teams_seen=200,
            games_seen=300,
            games_inserted=250,
            games_skipped=12,
        )

    monkeypatch.setattr("cbb.cli.ingest_historical_games", fake_ingest_historical_games)

    result = runner.invoke(app, ["ingest", "data"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, HistoricalIngestOptions)
    assert options.years_back == 3
    assert options.start_date is None
    assert options.end_date is None
    assert options.force_refresh is False
    assert "range=2023-03-07..2026-03-07" in result.stdout
    assert "dates_requested=100" in result.stdout
    assert "games_skipped=12" in result.stdout


def test_ingest_closing_odds_command_defaults_to_one_year_backfill(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_closing_odds(**kwargs: object) -> ClosingOddsIngestSummary:
        captured.update(kwargs)
        return ClosingOddsIngestSummary(
            sport="basketball_ncaab",
            market="h2h",
            start_date="2025-03-07",
            end_date="2026-03-07",
            snapshot_slots_found=12,
            snapshot_slots_requested=4,
            snapshot_slots_skipped=6,
            snapshot_slots_deferred=2,
            games_considered=40,
            games_matched=16,
            games_unmatched=3,
            odds_snapshots_upserted=16,
            credits_spent=40,
            quota=ApiQuota(remaining=1960, used=40, last_cost=10),
        )

    monkeypatch.setattr("cbb.cli.run_ingest_closing_odds", fake_ingest_closing_odds)

    result = runner.invoke(app, ["ingest", "closing-odds"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, ClosingOddsIngestOptions)
    assert options.years_back == 1
    assert options.market == "h2h"
    assert options.max_snapshots is None
    assert "range=2025-03-07..2026-03-07" in result.stdout
    assert "snapshot_slots_requested=4" in result.stdout
    assert "credits_spent=40" in result.stdout


def test_db_audit_command_reports_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_verify_games(options: VerificationOptions) -> GameVerificationSummary:
        captured["options"] = options
        return GameVerificationSummary(
            sport="basketball_ncaab",
            start_date="2025-03-07",
            end_date="2026-03-07",
            dates_checked=366,
            upstream_games_seen=5957,
            upstream_games_skipped=12,
            completed_games_seen=5900,
            games_present=5957,
            games_verified=5956,
            games_missing=0,
            status_mismatches=1,
            score_mismatches=0,
            sample_missing_games=(),
            sample_status_mismatches=("401827053 Team A vs Team B",),
            sample_score_mismatches=(),
        )

    monkeypatch.setattr("cbb.cli.verify_games", fake_verify_games)

    result = runner.invoke(app, ["db", "audit"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, VerificationOptions)
    assert options.years_back == 3
    assert options.start_date is None
    assert options.end_date is None
    assert "dates_checked=366" in result.stdout
    assert "games_verified=5956" in result.stdout
    assert "Status Mismatch Samples" in result.stdout


def test_db_backup_command_reports_backup_path(monkeypatch, tmp_path: Path) -> None:
    backup_path = tmp_path / "backups" / "snapshot.sql"

    def fake_create_database_backup(
        *,
        backup_name: str | None = None,
    ) -> DatabaseBackupArtifact:
        assert backup_name == "snapshot"
        return DatabaseBackupArtifact(path=backup_path, size_bytes=2048)

    monkeypatch.setattr("cbb.cli.create_database_backup", fake_create_database_backup)

    result = runner.invoke(app, ["db", "backup", "--name", "snapshot"])

    assert result.exit_code == 0
    assert "Created backup:" in result.stdout
    assert "snapshot.sql" in result.stdout
    assert "(2048 bytes)" in result.stdout


def test_db_import_command_reports_imported_path(monkeypatch, tmp_path: Path) -> None:
    backup_path = tmp_path / "backups" / "snapshot.sql"

    def fake_import_database_backup(
        backup_name_or_path: str,
    ) -> DatabaseImportArtifact:
        assert backup_name_or_path == "snapshot.sql"
        return DatabaseImportArtifact(path=backup_path)

    monkeypatch.setattr("cbb.cli.import_database_backup", fake_import_database_backup)

    result = runner.invoke(app, ["db", "import", "snapshot.sql"])

    assert result.exit_code == 0
    assert "Imported backup:" in result.stdout
    assert "snapshot.sql" in result.stdout


def test_db_view_team_command_renders_recent_results(monkeypatch) -> None:
    def fake_get_team_view(team_name: str) -> TeamView:
        assert team_name == "Duke Blue Devils"
        return TeamView(
            team_name="Duke Blue Devils",
            scheduled_games=[
                UpcomingGameView(
                    commence_time="2026-03-08 18:00:00+00",
                    home_team="Duke Blue Devils",
                    away_team="Baylor Bears",
                    status="in_progress",
                    home_score=54,
                    away_score=49,
                    home_pregame_moneyline=-140.0,
                    away_pregame_moneyline=120.0,
                )
            ],
            recent_results=[
                TeamRecentResult(
                    commence_time="2026-03-07 23:30:00+00",
                    opponent_name="North Carolina Tar Heels",
                    venue_label="vs",
                    team_score=76,
                    opponent_score=61,
                    result="W",
                )
            ],
            suggestions=[],
        )

    monkeypatch.setattr("cbb.cli.get_team_view", fake_get_team_view)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["db", "view", "team", "Duke Blue Devils"])

    assert result.exit_code == 0
    assert "Team: Duke Blue Devils" in result.stdout
    assert "Current / Upcoming" in result.stdout
    assert "In Progress" in result.stdout
    assert "LOCAL 2026-03-08 18:00:00+00" in result.stdout
    assert "Duke Blue Devils (-140) 54 vs Baylor Bears (+120) 49" in result.stdout
    assert "Recent Results" in result.stdout
    assert "LOCAL 2026-03-07 23:30:00+00" in result.stdout
    assert "vs North Carolina Tar Heels | W 76-61" in result.stdout


def test_db_view_team_command_suggests_when_not_exact(monkeypatch) -> None:
    def fake_get_team_view(team_name: str) -> TeamView:
        assert team_name == "Duk Blu"
        return TeamView(
            team_name=None,
            scheduled_games=[],
            recent_results=[],
            suggestions=["Duke Blue Devils", "Drake Bulldogs"],
        )

    monkeypatch.setattr("cbb.cli.get_team_view", fake_get_team_view)

    result = runner.invoke(app, ["db", "view", "team", "Duk Blu"])

    assert result.exit_code == 1
    assert "No exact team match" in result.stdout
    assert "Did you mean:" in result.stdout
    assert "Duke Blue Devils" in result.stdout


def test_db_view_upcoming_command_renders_games(monkeypatch) -> None:
    def fake_get_upcoming_games(limit: int) -> list[UpcomingGameView]:
        assert limit == 10
        return [
            UpcomingGameView(
                commence_time="2026-03-08 18:00:00+00",
                home_team="Duke Blue Devils",
                away_team="Baylor Bears",
                status="in_progress",
                home_score=54,
                away_score=49,
                home_pregame_moneyline=-140.0,
                away_pregame_moneyline=120.0,
            ),
            UpcomingGameView(
                commence_time="2026-03-08 21:00:00+00",
                home_team="Kansas Jayhawks",
                away_team="North Carolina Tar Heels",
                status="upcoming",
                home_pregame_moneyline=-125.0,
                away_pregame_moneyline=105.0,
            ),
        ]

    monkeypatch.setattr("cbb.cli.get_upcoming_games", fake_get_upcoming_games)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["db", "view", "upcoming"])

    assert result.exit_code == 0
    assert "In Progress" in result.stdout
    assert "LOCAL 2026-03-08 18:00:00+00" in result.stdout
    assert "Duke Blue Devils (-140) 54 vs Baylor Bears (+120) 49" in result.stdout
    assert "Upcoming" in result.stdout
    assert "LOCAL 2026-03-08 21:00:00+00" in result.stdout
    assert "Kansas Jayhawks (-125) vs North Carolina Tar Heels (+105)" in result.stdout


def test_format_local_timestamp_converts_utc_to_local_timezone(monkeypatch) -> None:
    monkeypatch.setattr(
        "cbb.cli._get_local_timezone",
        lambda: timezone(timedelta(hours=-5), "EST"),
    )

    from cbb.cli import _format_local_timestamp

    formatted_value = _format_local_timestamp("2026-03-08 18:00:00+00:00")

    assert formatted_value == "2026-03-08 13:00 EST"
