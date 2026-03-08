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
from cbb.modeling import (
    BacktestOptions,
    BacktestSummary,
    BetPolicy,
    PredictionOptions,
    PredictionSummary,
    TrainingOptions,
    TrainingSummary,
)
from cbb.modeling.policy import PlacedBet
from cbb.modeling.report import BestBacktestReport, BestBacktestReportOptions
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


def test_model_train_command_reports_artifact(monkeypatch, tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifacts" / "models" / "moneyline_latest.json"
    captured: dict[str, object] = {}

    def fake_train_betting_model(options: TrainingOptions) -> TrainingSummary:
        captured["options"] = options
        return TrainingSummary(
            market="moneyline",
            start_season=2024,
            end_season=2026,
            examples=200,
            priced_examples=40,
            training_examples=180,
            accuracy=0.61,
            log_loss=0.64,
            brier_score=0.22,
            market_blend_weight=0.35,
            max_market_probability_delta=0.04,
            artifact_path=artifact_path,
        )

    monkeypatch.setattr("cbb.cli.train_betting_model", fake_train_betting_model)

    result = runner.invoke(app, ["model", "train"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, TrainingOptions)
    assert options.market == "moneyline"
    assert options.seasons_back == 3
    assert "Trained moneyline model" in result.stdout
    assert "Artifact:" in result.stdout


def test_model_backtest_command_reports_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_backtest_betting_model(options: BacktestOptions) -> BacktestSummary:
        captured["options"] = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=4,
            candidates_considered=24,
            bets_placed=8,
            wins=5,
            losses=3,
            pushes=0,
            total_staked=220.0,
            profit=46.5,
            roi=0.2114,
            units_won=1.86,
            starting_bankroll=1000.0,
            ending_bankroll=1046.5,
            max_drawdown=0.07,
            sample_bets=[
                PlacedBet(
                    game_id=12,
                    commence_time="2026-02-20T19:00:00+00:00",
                    market="moneyline",
                    team_name="Alpha Aces",
                    opponent_name="Gamma Gulls",
                    side="home",
                    market_price=-115.0,
                    line_value=-115.0,
                    model_probability=0.62,
                    implied_probability=0.535,
                    probability_edge=0.085,
                    expected_value=0.159,
                    stake_fraction=0.03,
                    stake_amount=30.0,
                    settlement="win",
                )
            ],
            policy_tuned_blocks=3,
            final_policy=BetPolicy(
                min_edge=0.015,
                min_probability_edge=0.02,
                min_games_played=12,
                max_spread_abs_line=15.0,
            ),
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["model", "backtest"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BacktestOptions)
    assert options.market == "best"
    assert options.auto_tune_spread_policy is False
    assert options.policy.max_spread_abs_line is None
    assert "Backtested best" in result.stdout
    assert "profit=$46.50" in result.stdout
    assert "Tuned Spread Policy:" in result.stdout
    assert "max_spread_abs_line=15.0" in result.stdout
    assert "Sample Bets" in result.stdout
    assert "LOCAL 2026-02-20T19:00:00+00:00" in result.stdout


def test_model_predict_command_renders_recommendations(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_predict_best_bets(options: PredictionOptions) -> PredictionSummary:
        captured["options"] = options
        return PredictionSummary(
            market="best",
            available_games=12,
            candidates_considered=5,
            bets_placed=2,
            recommendations=[
                PlacedBet(
                    game_id=20,
                    commence_time="2026-03-09T19:00:00+00:00",
                    market="moneyline",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=-115.0,
                    line_value=-115.0,
                    model_probability=0.61,
                    implied_probability=0.535,
                    probability_edge=0.075,
                    expected_value=0.140,
                    stake_fraction=0.025,
                    stake_amount=25.0,
                    settlement="pending",
                )
            ],
            applied_policy=BetPolicy(
                min_edge=0.02,
                min_probability_edge=0.015,
                min_games_played=8,
                max_spread_abs_line=10.0,
            ),
            policy_was_auto_tuned=True,
            policy_tuned_blocks=5,
        )

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["model", "predict"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, PredictionOptions)
    assert options.market == "best"
    assert options.auto_tune_spread_policy is True
    assert options.policy.max_spread_abs_line is None
    assert "Predicted best" in result.stdout
    assert "Auto-Tuned Spread Policy:" in result.stdout
    assert "max_spread_abs_line=10.0" in result.stdout
    assert "Bet Slip (1u = $25.00)" in result.stdout
    assert "1. LOCAL 2026-03-09T19:00:00+00:00" in result.stdout
    assert "Bet Alpha Aces vs Beta Bruins" in result.stdout
    assert "stake=1.00u" in result.stdout
    assert "model=0.610" not in result.stdout
    assert "LOCAL 2026-03-09T19:00:00+00:00" in result.stdout
    assert "moneyline -115" in result.stdout


def test_model_predict_command_supports_verbose_output(monkeypatch) -> None:
    def fake_predict_best_bets(_: PredictionOptions) -> PredictionSummary:
        return PredictionSummary(
            market="moneyline",
            available_games=4,
            candidates_considered=1,
            bets_placed=1,
            recommendations=[
                PlacedBet(
                    game_id=20,
                    commence_time="2026-03-09T19:00:00+00:00",
                    market="moneyline",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=-115.0,
                    line_value=-115.0,
                    model_probability=0.61,
                    implied_probability=0.535,
                    probability_edge=0.075,
                    expected_value=0.140,
                    stake_fraction=0.025,
                    stake_amount=25.0,
                    settlement="pending",
                )
            ],
            applied_policy=BetPolicy(),
        )

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["model", "predict", "--verbose"])

    assert result.exit_code == 0
    assert "Bet Slip (1u = $25.00)" in result.stdout
    assert "model=0.610" in result.stdout
    assert "implied=0.535" in result.stdout
    assert "stake=1.00u ($25.00)" in result.stdout


def test_model_predict_command_accepts_max_spread_abs_line(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_predict_best_bets(options: PredictionOptions) -> PredictionSummary:
        captured["options"] = options
        return PredictionSummary(
            market="spread",
            available_games=0,
            candidates_considered=0,
            bets_placed=0,
            recommendations=[],
        )

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)

    result = runner.invoke(
        app,
        ["model", "predict", "--max-spread-abs-line", "12.5"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, PredictionOptions)
    assert options.policy.max_spread_abs_line == 12.5


def test_model_predict_command_supports_disabling_auto_tune(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_predict_best_bets(options: PredictionOptions) -> PredictionSummary:
        captured["options"] = options
        return PredictionSummary(
            market="best",
            available_games=0,
            candidates_considered=0,
            bets_placed=0,
            recommendations=[],
            applied_policy=options.policy,
        )

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)

    result = runner.invoke(
        app,
        ["model", "predict", "--no-auto-tune-spread-policy"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, PredictionOptions)
    assert options.auto_tune_spread_policy is False


def test_model_report_command_writes_markdown_report(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}
    report_path = tmp_path / "docs" / "results" / "best-model-3y-backtest.md"

    def fake_generate_best_backtest_report(
        options: BestBacktestReportOptions,
        *,
        progress,
    ) -> BestBacktestReport:
        captured["options"] = options
        progress("Backtesting season 2026...")
        progress("Finished season 2026: bets=21, profit=+$10.67, roi=+17.75%")
        return BestBacktestReport(
            output_path=report_path,
            history_output_path=report_path.parent / "history" / "best-model-3y-backtest_20260308_120000.md",
            selected_seasons=(2024, 2025, 2026),
            summaries=(
                BacktestSummary(
                    market="best",
                    start_season=2024,
                    end_season=2026,
                    evaluation_season=2026,
                    blocks=4,
                    candidates_considered=24,
                    bets_placed=21,
                    wins=13,
                    losses=8,
                    pushes=0,
                    total_staked=60.0,
                    profit=10.67,
                    roi=0.1775,
                    units_won=0.43,
                    starting_bankroll=1000.0,
                    ending_bankroll=1010.67,
                    max_drawdown=0.0139,
                    sample_bets=[],
                    final_policy=BetPolicy(
                        min_edge=0.02,
                        min_probability_edge=0.015,
                        min_games_played=8,
                        max_spread_abs_line=10.0,
                    ),
                ),
            ),
            aggregate_bets=136,
            aggregate_profit=-35.18,
            aggregate_roi=-0.0444,
            aggregate_units=-1.41,
            max_drawdown=0.0746,
            zero_bet_seasons=(2025,),
            latest_summary=BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2026,
                evaluation_season=2026,
                blocks=4,
                candidates_considered=24,
                bets_placed=21,
                wins=13,
                losses=8,
                pushes=0,
                total_staked=60.0,
                profit=10.67,
                roi=0.1775,
                units_won=0.43,
                starting_bankroll=1000.0,
                ending_bankroll=1010.67,
                max_drawdown=0.0139,
                sample_bets=[],
                final_policy=BetPolicy(
                    min_edge=0.02,
                    min_probability_edge=0.015,
                    min_games_played=8,
                    max_spread_abs_line=10.0,
                ),
            ),
            markdown="# report",
        )

    monkeypatch.setattr(
        "cbb.cli.generate_best_backtest_report",
        fake_generate_best_backtest_report,
    )

    result = runner.invoke(app, ["model", "report"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BestBacktestReportOptions)
    assert options.seasons == 3
    assert options.max_season is None
    assert options.auto_tune_spread_policy is True
    assert "Backtesting season 2026..." in result.stdout
    assert "Generated best-model report:" in result.stdout
    assert "History copy:" in result.stdout
    assert "profit=$-35.18" in result.stdout
    assert "Latest season 2026: profit=$10.67, roi=0.1775" in result.stdout
    assert "Zero-bet seasons: 2025" in result.stdout
