import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.exc import OperationalError
from typer.testing import CliRunner

from cbb.agent import AgentSyncOptions, AgentSyncSummary
from cbb.cli import _format_fanduel_team_link, app
from cbb.db_backup import DatabaseBackupArtifact, DatabaseImportArtifact
from cbb.ingest import (
    ApiQuota,
    ClosingOddsIngestOptions,
    ClosingOddsIngestSummary,
    HistoricalIngestOptions,
    HistoricalIngestSummary,
    OddsIngestSummary,
    OfficialAvailabilityImportSummary,
)
from cbb.modeling import (
    DEFAULT_STARTING_BANKROLL,
    BacktestOptions,
    BacktestSummary,
    BetPolicy,
    PredictionOptions,
    PredictionSummary,
    TournamentBacktestOptions,
    TournamentBacktestPickSeedRoleSummary,
    TournamentBacktestRoundSummary,
    TournamentBacktestSeasonSummary,
    TournamentBacktestSeedGapSummary,
    TournamentBacktestSourceSummary,
    TournamentBacktestSummary,
    TournamentBacktestSyntheticFavoriteProbabilitySummary,
    TournamentBacktestSyntheticUpsetProbabilitySummary,
    TournamentGamePick,
    TournamentOptions,
    TournamentSummary,
    TournamentTeamAdvancement,
    TrainingOptions,
    TrainingSummary,
)
from cbb.modeling.backtest import ClosingLineValueSummary
from cbb.modeling.infer import (
    AvailabilityGameContext,
    AvailabilitySideContext,
    DeferredRecommendation,
    LiveBoardGame,
    PredictionAvailabilitySummary,
    UpcomingGamePrediction,
)
from cbb.modeling.policy import CandidateBet, PlacedBet, SupportingQuote
from cbb.modeling.report import BestBacktestReport, BestBacktestReportOptions
from cbb.verify import GameVerificationSummary, VerificationOptions

runner = CliRunner()


def _sample_agent_sync_summary() -> AgentSyncSummary:
    return AgentSyncSummary(
        started_at=datetime(2026, 3, 13, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 3, 13, 12, 0, 5, tzinfo=UTC),
        espn_resume_anchor_date=datetime(2026, 3, 10, 0, 0, tzinfo=UTC).date(),
        espn_resume_anchor_source="checkpoint",
        espn_effective_start_date=datetime(2026, 3, 11, 0, 0, tzinfo=UTC).date(),
        espn_effective_end_date=datetime(2026, 3, 13, 0, 0, tzinfo=UTC).date(),
        effective_scores_days_from=3,
        espn_summary=HistoricalIngestSummary(
            sport="basketball_ncaab",
            start_date="2026-03-11",
            end_date="2026-03-13",
            dates_requested=3,
            dates_skipped=0,
            dates_completed=3,
            teams_seen=12,
            games_seen=18,
            games_inserted=16,
            games_skipped=2,
        ),
        odds_summary=OddsIngestSummary(
            sport="basketball_ncaab",
            teams_seen=12,
            games_upserted=8,
            games_skipped=1,
            odds_snapshots_upserted=64,
            completed_games_updated=3,
            odds_quota=ApiQuota(remaining=1990, used=10, last_cost=10),
            scores_quota=ApiQuota(remaining=999, used=1, last_cost=1),
        ),
        prediction_summary=PredictionSummary(
            market="best",
            available_games=11,
            candidates_considered=4,
            bets_placed=1,
            recommendations=[
                PlacedBet(
                    game_id=99,
                    commence_time="2026-03-13T23:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    sportsbook="draftkings",
                    market_price=-110.0,
                    line_value=-3.5,
                    model_probability=0.56,
                    implied_probability=0.50,
                    probability_edge=0.06,
                    expected_value=0.08,
                    stake_fraction=0.01,
                    stake_amount=25.0,
                    settlement="win",
                    positive_ev_books=5,
                    coverage_rate=0.9,
                    min_acceptable_line=-3.0,
                    min_acceptable_price=-115.0,
                )
            ],
            live_board_games=[
                LiveBoardGame(
                    game_id=99,
                    commence_time="2026-03-13T11:00:00+00:00",
                    home_team_name="Alpha Aces",
                    away_team_name="Beta Bruins",
                    game_status="in_progress",
                    board_status="bet",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    sportsbook="draftkings",
                    market_price=-110.0,
                    line_value=-3.5,
                    home_score=54,
                    away_score=49,
                    last_score_update=datetime(
                        2026,
                        3,
                        13,
                        11,
                        58,
                        tzinfo=UTC,
                    ),
                ),
                LiveBoardGame(
                    game_id=100,
                    commence_time="2026-03-13T05:00:00+00:00",
                    home_team_name="Gamma Gulls",
                    away_team_name="Delta Dukes",
                    game_status="final",
                    board_status="pass",
                    market="spread",
                    team_name="Delta Dukes",
                    opponent_name="Gamma Gulls",
                    side="away",
                    sportsbook="fanduel",
                    market_price=-110.0,
                    line_value=4.5,
                    home_score=71,
                    away_score=64,
                    last_score_update=datetime(
                        2026,
                        3,
                        13,
                        8,
                        30,
                        tzinfo=UTC,
                    ),
                ),
                LiveBoardGame(
                    game_id=101,
                    commence_time="2026-03-12T01:00:00+00:00",
                    home_team_name="Old Owls",
                    away_team_name="Past Panthers",
                    game_status="final",
                    board_status="pass",
                    home_score=68,
                    away_score=62,
                    last_score_update=datetime(
                        2026,
                        3,
                        12,
                        18,
                        0,
                        tzinfo=UTC,
                    ),
                ),
            ],
            artifact_name="latest",
            generated_at=datetime(2026, 3, 13, 12, 0, 5, tzinfo=UTC),
            expires_at=datetime(2026, 3, 13, 12, 5, 5, tzinfo=UTC),
        ),
    )


def test_root_help_surfaces_deployable_and_setup_language() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "deployable best-path" in result.stdout
    assert "agent" in result.stdout
    assert "dashboard" in result.stdout
    assert "ingest" in result.stdout


def test_model_report_help_mentions_canonical_best_workflow() -> None:
    result = runner.invoke(app, ["model", "report", "--help"])

    assert result.exit_code == 0
    help_text = result.stdout.lower()
    assert "canonical best-path" in help_text
    assert "settled-performance" in help_text


def test_format_fanduel_team_link_normalizes_team_name() -> None:
    assert _format_fanduel_team_link("Miami (OH) RedHawks") == (
        "https://sportsbook.fanduel.com/teams/college-basketball/"
        "miami-oh-redhawks/odds"
    )


def test_ingest_data_command_defaults_to_five_year_backfill(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_historical_games(**kwargs: object) -> HistoricalIngestSummary:
        captured.update(kwargs)
        return HistoricalIngestSummary(
            sport="basketball_ncaab",
            start_date="2021-03-07",
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
    assert options.years_back == 5
    assert options.start_date is None
    assert options.end_date is None
    assert options.force_refresh is False
    assert "range=2021-03-07..2026-03-07" in result.stdout
    assert "dates_requested=100" in result.stdout
    assert "games_skipped=12" in result.stdout


def test_ingest_availability_command_reports_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    capture_path = tmp_path / "official-report.json"
    capture_path.write_text("{}", encoding="utf-8")

    def fake_ingest_official_availability_reports(
        **kwargs: object,
    ) -> OfficialAvailabilityImportSummary:
        captured.update(kwargs)
        return OfficialAvailabilityImportSummary(
            snapshots_imported=2,
            player_rows_imported=16,
            games_matched=2,
            teams_matched=4,
            rows_unmatched=1,
            duplicates_skipped=3,
        )

    monkeypatch.setattr(
        "cbb.cli.ingest_official_availability_reports",
        fake_ingest_official_availability_reports,
    )

    result = runner.invoke(app, ["ingest", "availability", str(capture_path)])

    assert result.exit_code == 0
    assert captured["paths"] == [capture_path.resolve()]
    assert "snapshots_imported=2" in result.stdout
    assert "player_rows_imported=16" in result.stdout
    assert "rows_unmatched=1" in result.stdout
    assert "duplicates_skipped=3" in result.stdout


def test_agent_command_reports_combined_summary(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_agent_sync(options: AgentSyncOptions) -> AgentSyncSummary:
        captured["options"] = options
        return _sample_agent_sync_summary()

    def fake_sleep(_: int) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("cbb.cli.run_agent_sync", fake_run_agent_sync)
    monkeypatch.setattr("cbb.cli.sleep", fake_sleep)

    result = runner.invoke(
        app,
        [
            "agent",
            "--espn-refresh-days",
            "2",
            "--regions",
            "us,uk",
            "--markets",
            "h2h,spreads",
            "--bookmakers",
            "draftkings,fanduel",
            "--scores-days-from",
            "2",
            "--delay-mins",
            "15",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, AgentSyncOptions)
    assert options.espn_refresh_days == 2
    assert options.regions == "us,uk"
    assert options.markets == "h2h,spreads"
    assert options.bookmakers == "draftkings,fanduel"
    assert options.scores_days_from == 2
    assert options.scan_bets is True
    assert options.artifact_name == "latest"
    assert "Starting agent loop:" in result.stdout
    assert "Agent iteration 1:" in result.stdout
    assert "Agent run:" in result.stdout
    assert "resume_anchor_source=checkpoint" in result.stdout
    assert "resume_anchor_date=2026-03-10" in result.stdout
    assert "espn_window=2026-03-11..2026-03-13" in result.stdout
    assert "ESPN refresh: range=2026-03-11..2026-03-13" in result.stdout
    assert "Odds refresh: games=8" in result.stdout
    assert "scores_days_from=3" in result.stdout
    assert "Odds quota: used=10, remaining=1990, last_cost=10" in result.stdout
    assert "Scores quota: used=1, remaining=999, last_cost=1" in result.stdout
    assert (
        "Bet scan: available_games=11, recommendations=1, deferred=0"
        in result.stdout
    )
    assert "Qualified bets:" in result.stdout
    assert "Alpha Aces -3.5 at draftkings -110" in result.stdout
    assert (
        "FanDuel link: https://sportsbook.fanduel.com/teams/"
        "college-basketball/alpha-aces/odds"
    ) in result.stdout
    assert "Live scores / recent finals:" in result.stdout
    assert (
        "In Progress | Bet | Alpha Aces vs Beta Bruins | Alpha Aces -3.5 | "
        "54-49 live"
    ) in result.stdout
    assert (
        "Final | Pass | Gamma Gulls vs Delta Dukes | Delta Dukes +4.5 | "
        "Final 71-64"
    ) in result.stdout
    assert "Old Owls vs Past Panthers" not in result.stdout
    assert "Sleeping for 15 minute(s) before the next run..." in result.stdout
    assert "Agent loop stopped." in result.stdout


def test_agent_command_run_once_exits_after_single_iteration(monkeypatch) -> None:
    captured: dict[str, object] = {"calls": 0, "slept": False}

    def fake_run_agent_sync(options: AgentSyncOptions) -> AgentSyncSummary:
        captured["calls"] = int(captured["calls"]) + 1
        captured["options"] = options
        return _sample_agent_sync_summary()

    def fake_sleep(_: int) -> None:
        captured["slept"] = True

    monkeypatch.setattr("cbb.cli.run_agent_sync", fake_run_agent_sync)
    monkeypatch.setattr("cbb.cli.sleep", fake_sleep)

    result = runner.invoke(app, ["agent", "--run-once"])

    assert result.exit_code == 0
    assert captured["calls"] == 1
    assert captured["slept"] is False
    options = captured["options"]
    assert isinstance(options, AgentSyncOptions)
    assert "Starting agent run-once:" in result.stdout
    assert "Agent iteration 1:" in result.stdout
    assert "Sleeping for" not in result.stdout
    assert "Agent run-once completed." in result.stdout


def test_agent_command_run_once_fails_on_single_iteration_error(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {"slept": False}

    def fake_run_agent_sync(_: AgentSyncOptions) -> AgentSyncSummary:
        raise RuntimeError("simulated refresh failure")

    def fake_sleep(_: int) -> None:
        captured["slept"] = True

    monkeypatch.setattr("cbb.cli.run_agent_sync", fake_run_agent_sync)
    monkeypatch.setattr("cbb.cli.sleep", fake_sleep)

    result = runner.invoke(app, ["agent", "--run-once"])

    assert result.exit_code == 1
    assert captured["slept"] is False
    combined_output = result.stdout + result.stderr
    assert "Starting agent run-once:" in result.stdout
    assert "Agent run failed: simulated refresh failure" in combined_output
    assert "Agent run-once completed." not in result.stdout
    assert "Sleeping for" not in combined_output


def test_agent_sync_subcommand_is_not_available() -> None:
    result = runner.invoke(app, ["agent", "sync"])

    assert result.exit_code == 2
    assert "unexpected extra argument" in result.output.lower()
    assert "sync" in result.output.lower()


def test_ingest_closing_odds_command_defaults_to_five_year_backfill(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_closing_odds(**kwargs: object) -> ClosingOddsIngestSummary:
        captured.update(kwargs)
        return ClosingOddsIngestSummary(
            sport="basketball_ncaab",
            market="h2h",
            start_date="2021-03-07",
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
    assert options.years_back == 5
    assert options.market == "h2h"
    assert options.regions == "us"
    assert options.bookmakers is None
    assert options.ignore_checkpoints is False
    assert options.max_snapshots is None
    assert "range=2021-03-07..2026-03-07" in result.stdout
    assert "snapshot_slots_requested=4" in result.stdout
    assert "credits_spent=40" in result.stdout


def test_ingest_closing_odds_command_accepts_ignore_checkpoints(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_closing_odds(**kwargs: object) -> ClosingOddsIngestSummary:
        captured.update(kwargs)
        return ClosingOddsIngestSummary(
            sport="basketball_ncaab",
            market="spreads",
            start_date="2026-03-08",
            end_date="2026-03-10",
            snapshot_slots_found=10,
            snapshot_slots_requested=10,
            snapshot_slots_skipped=0,
            snapshot_slots_deferred=0,
            games_considered=12,
            games_matched=8,
            games_unmatched=4,
            odds_snapshots_upserted=16,
            credits_spent=100,
            quota=ApiQuota(remaining=1900, used=100, last_cost=10),
        )

    monkeypatch.setattr("cbb.cli.run_ingest_closing_odds", fake_ingest_closing_odds)

    result = runner.invoke(
        app,
        [
            "ingest",
            "closing-odds",
            "--market",
            "spreads",
            "--ignore-checkpoints",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, ClosingOddsIngestOptions)
    assert options.market == "spreads"
    assert options.ignore_checkpoints is True


def test_ingest_closing_odds_command_accepts_regions_and_bookmakers(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_ingest_closing_odds(**kwargs: object) -> ClosingOddsIngestSummary:
        captured.update(kwargs)
        return ClosingOddsIngestSummary(
            sport="basketball_ncaab",
            market="spreads",
            start_date="2026-03-08",
            end_date="2026-03-10",
            snapshot_slots_found=10,
            snapshot_slots_requested=4,
            snapshot_slots_skipped=6,
            snapshot_slots_deferred=0,
            games_considered=12,
            games_matched=8,
            games_unmatched=4,
            odds_snapshots_upserted=16,
            credits_spent=40,
            quota=ApiQuota(remaining=1900, used=100, last_cost=10),
        )

    monkeypatch.setattr("cbb.cli.run_ingest_closing_odds", fake_ingest_closing_odds)

    result = runner.invoke(
        app,
        [
            "ingest",
            "closing-odds",
            "--market",
            "spreads",
            "--regions",
            "us,uk,eu",
            "--bookmakers",
            "draftkings,fanduel,betmgm,pinnacle",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, ClosingOddsIngestOptions)
    assert options.market == "spreads"
    assert options.regions == "us,uk,eu"
    assert options.bookmakers == "draftkings,fanduel,betmgm,pinnacle"


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
            context_mismatches=2,
            sample_missing_games=(),
            sample_status_mismatches=("401827053 Team A vs Team B",),
            sample_score_mismatches=(),
            sample_context_mismatches=("401827054 Team C vs Team D",),
        )

    monkeypatch.setattr("cbb.cli.verify_games", fake_verify_games)

    result = runner.invoke(app, ["db", "audit"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, VerificationOptions)
    assert options.years_back == 5
    assert options.start_date is None
    assert options.end_date is None
    assert "dates_checked=366" in result.stdout
    assert "games_verified=5956" in result.stdout
    assert "context_mismatches=2" in result.stdout
    assert "Status Mismatch Samples" in result.stdout
    assert "Context Mismatch Samples" in result.stdout


def test_dashboard_command_launches_local_ui(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_run_dashboard_server(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("cbb.ui.app.run_dashboard_server", fake_run_dashboard_server)

    result = runner.invoke(
        app,
        [
            "dashboard",
            "--host",
            "0.0.0.0",
            "--port",
            "0",
            "--no-open",
            "--window-days",
            "30",
            "--report-ttl-seconds",
            "180",
            "--prediction-ttl-seconds",
            "45",
            "--team-ttl-seconds",
            "900",
            "--prediction-source",
            "cache",
        ],
    )

    assert result.exit_code == 0
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 0
    assert captured["open_browser"] is False
    assert captured["window_days"] == 30
    assert captured["report_ttl_seconds"] == 180
    assert captured["prediction_ttl_seconds"] == 45
    assert captured["team_ttl_seconds"] == 900
    assert captured["prediction_source"] == "cache"
    assert callable(captured["announce"])


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


def test_db_view_command_is_removed() -> None:
    result = runner.invoke(app, ["db", "view", "--help"])

    assert result.exit_code == 2
    assert "No such command 'view'" in result.output


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
            model_family="logistic",
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
    assert options.model_family == "logistic"
    assert options.seasons_back == 5
    assert "Trained moneyline model" in result.stdout
    assert "family=logistic" in result.stdout
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
            clv=ClosingLineValueSummary(
                bets_evaluated=3,
                positive_bets=2,
                negative_bets=1,
                neutral_bets=0,
                spread_bets_evaluated=2,
                total_spread_line_delta=1.0,
                spread_price_bets_evaluated=2,
                total_spread_price_probability_delta=0.02,
                spread_no_vig_bets_evaluated=2,
                total_spread_no_vig_probability_delta=0.018,
                spread_closing_ev_bets_evaluated=2,
                total_spread_closing_expected_value=0.12,
                moneyline_bets_evaluated=1,
                total_moneyline_probability_delta=0.01,
            ),
            policy_tuned_blocks=3,
            final_policy=BetPolicy(
                min_edge=0.015,
                min_probability_edge=0.02,
                min_games_played=12,
                min_positive_ev_books=2,
                min_median_expected_value=0.01,
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
    assert options.spread_model_family == "logistic"
    assert options.policy.min_edge == 0.04
    assert options.policy.min_confidence == 0.518
    assert options.policy.min_probability_edge == 0.04
    assert options.policy.min_games_played == 8
    assert options.policy.max_spread_abs_line == 10.0
    assert options.policy.max_abs_rest_days_diff == 3.0
    assert "Backtested best" in result.stdout
    assert "profit=$46.50" in result.stdout
    assert "CLV:" in result.stdout
    assert "avg_spread_price_clv=+1.00 pp" in result.stdout
    assert "avg_spread_no_vig_close_delta=+0.90 pp" in result.stdout
    assert "avg_spread_closing_ev=+0.060" in result.stdout
    assert "Auto-Tuned Spread Policy:" in result.stdout
    assert "min_positive_ev_books=2" in result.stdout
    assert "min_median_expected_value=0.010" in result.stdout
    assert "max_spread_abs_line=15.0" in result.stdout
    assert "Sample Bets" in result.stdout
    assert "LOCAL 2026-02-20T19:00:00+00:00" in result.stdout


def test_model_backtest_command_accepts_timing_layer(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_backtest_betting_model(options: BacktestOptions) -> BacktestSummary:
        captured["options"] = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=0,
            bets_placed=0,
            wins=0,
            losses=0,
            pushes=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            units_won=0.0,
            starting_bankroll=1000.0,
            ending_bankroll=1000.0,
            max_drawdown=0.0,
            sample_bets=[],
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)

    result = runner.invoke(app, ["model", "backtest", "--use-timing-layer"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BacktestOptions)
    assert options.use_timing_layer is True


def test_model_backtest_command_accepts_min_positive_ev_books(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_backtest_betting_model(options: BacktestOptions) -> BacktestSummary:
        captured["options"] = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=0,
            bets_placed=0,
            wins=0,
            losses=0,
            pushes=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            units_won=0.0,
            starting_bankroll=1000.0,
            ending_bankroll=1000.0,
            max_drawdown=0.0,
            sample_bets=[],
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)

    result = runner.invoke(
        app,
        ["model", "backtest", "--min-positive-ev-books", "3"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BacktestOptions)
    assert options.policy.min_positive_ev_books == 3


def test_model_backtest_command_accepts_max_abs_rest_days_diff(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_backtest_betting_model(options: BacktestOptions) -> BacktestSummary:
        captured["options"] = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=0,
            bets_placed=0,
            wins=0,
            losses=0,
            pushes=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            units_won=0.0,
            starting_bankroll=1000.0,
            ending_bankroll=1000.0,
            max_drawdown=0.0,
            sample_bets=[],
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)

    result = runner.invoke(
        app,
        ["model", "backtest", "--max-abs-rest-days-diff", "2"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BacktestOptions)
    assert options.policy.max_abs_rest_days_diff == 2.0


def test_model_backtest_command_accepts_min_median_expected_value(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_backtest_betting_model(options: BacktestOptions) -> BacktestSummary:
        captured["options"] = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=0,
            bets_placed=0,
            wins=0,
            losses=0,
            pushes=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            units_won=0.0,
            starting_bankroll=1000.0,
            ending_bankroll=1000.0,
            max_drawdown=0.0,
            sample_bets=[],
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)

    result = runner.invoke(
        app,
        ["model", "backtest", "--min-median-expected-value", "0.01"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BacktestOptions)
    assert options.policy.min_median_expected_value == 0.01


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
                min_edge=0.03,
                min_confidence=0.52,
                min_probability_edge=0.025,
                min_games_played=4,
                min_positive_ev_books=2,
                min_median_expected_value=0.01,
                max_spread_abs_line=10.0,
            ),
            availability_summary=PredictionAvailabilitySummary(
                games_with_context=2,
                games_with_both_reports=1,
                games_with_team_only=1,
                games_with_unmatched_rows=1,
                team_sides_with_unmatched_rows=1,
                opponent_sides_with_unmatched_rows=2,
                games_with_any_out=1,
                games_with_any_questionable=2,
                source_names=("ncaa", "sec-archive"),
                latest_report_update_at="2026-03-09T17:30:00+00:00",
                closest_report_minutes_before_tip=90.0,
            ),
            policy_was_auto_tuned=False,
            policy_tuned_blocks=0,
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
    assert options.auto_tune_spread_policy is False
    assert options.policy.max_spread_abs_line == 10.0
    assert options.policy.max_abs_rest_days_diff == 3.0
    assert "Prediction Summary: market=best" in result.stdout
    assert "Applied Policy:" in result.stdout
    assert "Risk Guardrails:" in result.stdout
    assert (
        "worst_case_same_day_loss="
        f"${DEFAULT_STARTING_BANKROLL * 0.05:.2f}"
    ) in result.stdout
    assert "Uncertainty Disclosure:" in result.stdout
    assert (
        "Availability Shadow: "
        "upcoming_games_with_context=2/12, both=1, team_only=1, opponent_only=0, "
        "games_with_unmatched_rows=1, team_unmatched=1, "
        "opponent_unmatched=2, games_with_any_out=1, "
        "games_with_any_questionable=2, sources=ncaa/sec-archive, "
        "latest_report_update=2026-03-09T13:30:00-04:00, "
        "closest_report=90 min before tip"
    ) in result.stdout
    assert "blocks=0" in result.stdout
    assert "min_confidence=0.520" in result.stdout
    assert "min_positive_ev_books=2" in result.stdout
    assert "min_median_expected_value=0.010" in result.stdout
    assert "max_spread_abs_line=10.0" in result.stdout
    assert "Bet Slip (1u = $25.00)" in result.stdout
    assert "1. Alpha Aces ML at unknown -115 | 1.00u | target -115" in result.stdout


def test_model_predict_command_renders_wait_list_for_timing_layer(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_predict_best_bets(options: PredictionOptions) -> PredictionSummary:
        captured["options"] = options
        return PredictionSummary(
            market="spread",
            available_games=4,
            candidates_considered=0,
            bets_placed=0,
            recommendations=[],
            deferred_recommendations=[
                DeferredRecommendation(
                    candidate=CandidateBet(
                        game_id=20,
                        commence_time="2026-03-10T19:00:00+00:00",
                        market="spread",
                        team_name="Alpha Aces",
                        opponent_name="Beta Bruins",
                        side="home",
                        market_price=-110.0,
                        line_value=-1.5,
                        model_probability=0.59,
                        implied_probability=0.50,
                        probability_edge=0.09,
                        expected_value=0.09,
                        stake_fraction=0.02,
                        settlement="pending",
                    ),
                    favorable_close_probability=0.22,
                )
            ],
            applied_policy=BetPolicy(
                min_edge=0.027,
                min_confidence=0.518,
                min_probability_edge=0.025,
                min_games_played=4,
                min_positive_ev_books=2,
                max_spread_abs_line=10.0,
                max_abs_rest_days_diff=3.0,
            ),
        )

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(
        app,
        ["model", "predict", "--market", "spread", "--use-timing-layer"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, PredictionOptions)
    assert options.use_timing_layer is True
    assert "deferred_count=1" in result.stdout
    assert "No immediate bets qualified under the current policy." in result.stdout
    assert "Wait List" in result.stdout
    assert (
        "1. wait Alpha Aces -1.5 at unknown -110 | target -1.5 / -110"
    ) in result.stdout
    assert "min_positive_ev_books=2" in result.stdout
    assert "max_abs_rest_days_diff=3.0" in result.stdout


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
    assert "model_probability=0.610" in result.stdout
    assert "implied_probability=0.535" in result.stdout
    assert "stake_amount=$25.00 (1.00u)" in result.stdout


def test_model_predict_command_can_render_upcoming_games(monkeypatch) -> None:
    def fake_predict_best_bets(_: PredictionOptions) -> PredictionSummary:
        return PredictionSummary(
            market="best",
            available_games=3,
            candidates_considered=1,
            bets_placed=1,
            recommendations=[],
            upcoming_games=[
                UpcomingGamePrediction(
                    game_id=20,
                    commence_time="2026-03-09T19:00:00+00:00",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    status="bet",
                    market="moneyline",
                    side="home",
                    market_price=-115.0,
                    line_value=-115.0,
                    model_probability=0.61,
                    implied_probability=0.535,
                    probability_edge=0.075,
                    expected_value=0.140,
                    stake_amount=25.0,
                ),
                UpcomingGamePrediction(
                    game_id=21,
                    commence_time="2026-03-09T21:00:00+00:00",
                    team_name="Gamma Gulls",
                    opponent_name="Delta Dogs",
                    status="pass",
                    market="spread",
                    side="away",
                    market_price=-110.0,
                    line_value=4.5,
                    model_probability=0.515,
                    implied_probability=0.500,
                    probability_edge=0.015,
                    expected_value=0.010,
                    note="probability_edge",
                ),
            ],
            applied_policy=BetPolicy(),
        )

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["model", "predict", "--show-upcoming-games"])

    assert result.exit_code == 0
    assert "Upcoming Games" in result.stdout
    assert (
        "1. LOCAL 2026-03-09T19:00:00+00:00 | bet | Alpha Aces ML at unknown -115 | "
        "1.00u | target -115"
    ) in result.stdout
    assert (
        "2. LOCAL 2026-03-09T21:00:00+00:00 | pass | "
        "Gamma Gulls +4.5 at unknown -110 | "
        "reason probability_edge"
    ) in result.stdout


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


def test_model_predict_command_accepts_min_positive_ev_books(monkeypatch) -> None:
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
        ["model", "predict", "--min-positive-ev-books", "3"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, PredictionOptions)
    assert options.policy.min_positive_ev_books == 3


def test_model_predict_command_accepts_min_median_expected_value(
    monkeypatch,
) -> None:
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
        ["model", "predict", "--min-median-expected-value", "0.01"],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, PredictionOptions)
    assert options.policy.min_median_expected_value == 0.01


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


def test_model_predict_command_handles_database_connection_error(
    monkeypatch,
) -> None:
    def fake_predict_best_bets(_: PredictionOptions) -> PredictionSummary:
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)

    result = runner.invoke(app, ["model", "predict"])

    assert result.exit_code == 1
    combined_output = result.stdout + result.stderr
    assert "could not connect to PostgreSQL" in combined_output
    assert "DATABASE_URL" in combined_output


def test_model_predict_command_can_render_json_payload(monkeypatch) -> None:
    def fake_predict_best_bets(_: PredictionOptions) -> PredictionSummary:
        return PredictionSummary(
            market="best",
            available_games=3,
            candidates_considered=2,
            bets_placed=1,
            recommendations=[
                PlacedBet(
                    game_id=20,
                    commence_time="2026-03-09T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=-110.0,
                    line_value=-1.5,
                    model_probability=0.61,
                    implied_probability=0.535,
                    probability_edge=0.075,
                    expected_value=0.140,
                    stake_fraction=0.025,
                    stake_amount=25.0,
                    settlement="pending",
                    sportsbook="draftkings",
                    eligible_books=3,
                    positive_ev_books=2,
                    coverage_rate=2.0 / 3.0,
                    supporting_quotes=(
                        SupportingQuote(
                            sportsbook="fanduel",
                            line_value=-2.0,
                            market_price=-108.0,
                            expected_value=0.121,
                        ),
                    ),
                    min_acceptable_line=-2.0,
                    min_acceptable_price=-110.0,
                )
            ],
            upcoming_games=[
                UpcomingGamePrediction(
                    game_id=20,
                    commence_time="2026-03-09T19:00:00+00:00",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    status="bet",
                    market="spread",
                    side="home",
                    sportsbook="draftkings",
                    market_price=-110.0,
                    line_value=-1.5,
                    eligible_books=3,
                    positive_ev_books=2,
                    coverage_rate=2.0 / 3.0,
                    model_probability=0.61,
                    implied_probability=0.535,
                    probability_edge=0.075,
                    expected_value=0.140,
                    stake_fraction=0.025,
                    stake_amount=25.0,
                    supporting_quotes=(
                        SupportingQuote(
                            sportsbook="fanduel",
                            line_value=-2.0,
                            market_price=-108.0,
                            expected_value=0.121,
                        ),
                    ),
                    min_acceptable_line=-2.0,
                    min_acceptable_price=-110.0,
                    reason_code="qualified",
                    availability_context=AvailabilityGameContext(
                        coverage_status="both",
                        team=AvailabilitySideContext(
                            has_report=True,
                            source_name="ncaa",
                            latest_update_at="2026-03-09T17:30:00+00:00",
                            latest_minutes_before_tip=90.0,
                            any_out=True,
                            out_count=1,
                            matched_row_count=2,
                        ),
                        opponent=AvailabilitySideContext(
                            has_report=True,
                            source_name="ncaa",
                            latest_update_at="2026-03-09T17:15:00+00:00",
                            latest_minutes_before_tip=105.0,
                            any_questionable=True,
                            questionable_count=1,
                            matched_row_count=1,
                            unmatched_row_count=1,
                        ),
                    ),
                ),
                UpcomingGamePrediction(
                    game_id=21,
                    commence_time="2026-03-09T21:00:00+00:00",
                    team_name="Gamma Gulls",
                    opponent_name="Delta Dogs",
                    status="pass",
                    market="spread",
                    side="away",
                    sportsbook="betmgm",
                    market_price=-110.0,
                    line_value=4.5,
                    eligible_books=1,
                    positive_ev_books=1,
                    coverage_rate=1.0,
                    model_probability=0.515,
                    implied_probability=0.500,
                    probability_edge=0.015,
                    expected_value=0.010,
                    reason_code="probability_edge",
                    note="probability_edge",
                ),
            ],
            availability_summary=PredictionAvailabilitySummary(
                games_with_context=1,
                games_with_both_reports=1,
                games_with_unmatched_rows=1,
                team_sides_with_unmatched_rows=0,
                opponent_sides_with_unmatched_rows=1,
                games_with_any_out=1,
                games_with_any_questionable=1,
                source_names=("ncaa",),
                latest_report_update_at="2026-03-09T17:30:00+00:00",
                closest_report_minutes_before_tip=90.0,
            ),
            artifact_name="latest",
            generated_at=datetime(2026, 3, 10, 12, 0, tzinfo=UTC),
            expires_at=datetime(2026, 3, 10, 12, 15, tzinfo=UTC),
            applied_policy=BetPolicy(
                min_edge=0.027,
                min_confidence=0.518,
                min_probability_edge=0.025,
                min_games_played=4,
                min_positive_ev_books=2,
                max_spread_abs_line=10.0,
                max_abs_rest_days_diff=3.0,
            ),
        )

    monkeypatch.setattr("cbb.cli.predict_best_bets", fake_predict_best_bets)

    result = runner.invoke(app, ["model", "predict", "--output-format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "predict.v1"
    assert payload["market"] == "best"
    assert payload["summary"]["available_games"] == 3
    assert payload["summary"]["candidates_considered"] == 2
    assert payload["summary"]["recommendations_count"] == 1
    assert payload["summary"]["availability_shadow"]["games_with_context"] == 1
    assert payload["summary"]["availability_shadow"]["games_without_context"] == 2
    assert (
        payload["summary"]["availability_shadow"]["coverage_status_counts"]["both"]
        == 1
    )
    assert (
        payload["summary"]["availability_shadow"]["games_with_unmatched_rows"]
        == 1
    )
    assert (
        payload["summary"]["availability_shadow"]["side_unmatched_counts"][
            "team"
        ]
        == 0
    )
    assert (
        payload["summary"]["availability_shadow"]["side_unmatched_counts"][
            "opponent"
        ]
        == 1
    )
    assert payload["summary"]["availability_shadow"]["games_with_any_out"] == 1
    assert (
        payload["summary"]["availability_shadow"]["games_with_any_questionable"]
        == 1
    )
    assert payload["summary"]["availability_shadow"]["source_names"] == ["ncaa"]
    assert (
        payload["summary"]["availability_shadow"]["latest_report_update_at_local"]
        == "2026-03-09T13:30:00-04:00"
    )
    assert (
        payload["summary"]["availability_shadow"]["closest_report_minutes_before_tip"]
        == 90.0
    )
    assert payload["policy"]["min_edge"] == 0.027
    assert payload["risk_guardrails"]["worst_case_same_day_loss"] == (
        DEFAULT_STARTING_BANKROLL * 0.05
    )
    assert payload["recommendations"][0]["sportsbook"] == "draftkings"
    assert payload["recommendations"][0]["eligible_books"] == 3
    assert payload["recommendations"][0]["supporting_quotes"][0]["sportsbook"] == (
        "fanduel"
    )
    assert payload["recommendations"][0]["reason"] == "qualified"
    assert payload["upcoming_games"][1]["reason_code"] == "probability_edge"
    assert payload["upcoming_games"][0]["availability_context"]["coverage_status"] == (
        "both"
    )
    assert (
        payload["upcoming_games"][0]["availability_context"]["team"]["out_count"]
        == 1
    )
    assert (
        payload["upcoming_games"][0]["availability_context"]["opponent"][
            "unmatched_row_count"
        ]
        == 1
    )


def test_model_tournament_command_renders_text_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    bracket_path = tmp_path / "bracket.json"
    bracket_path.write_text("{}", encoding="utf-8")

    def fake_predict_tournament_bracket(
        options: TournamentOptions,
    ) -> TournamentSummary:
        captured["options"] = options
        return TournamentSummary(
            tournament_key="ncaa-men-2026",
            label="2026 NCAA Tournament",
            season=2026,
            generated_at=datetime(2026, 3, 18, 20, 0, tzinfo=UTC),
            artifact_name=options.artifact_name,
            bracket_picks=[
                TournamentGamePick(
                    game_key="east-r64-1",
                    round_label="Round of 64",
                    region="East",
                    scheduled_time="2026-03-19T16:15:00+00:00",
                    home_team_name="Alpha Aces",
                    home_seed=1,
                    away_team_name="Delta Dogs",
                    away_seed=16,
                    winner_name="Alpha Aces",
                    winner_seed=1,
                    winner_probability=0.882,
                    source="live_market",
                    scoring_source="moneyline_market_artifact",
                    live_game_id=101,
                ),
                TournamentGamePick(
                    game_key="title",
                    round_label="Championship",
                    region=None,
                    scheduled_time="2026-04-06T01:20:00+00:00",
                    home_team_name="Alpha Aces",
                    home_seed=1,
                    away_team_name="Beta Bruins",
                    away_seed=2,
                    winner_name="Alpha Aces",
                    winner_seed=1,
                    winner_probability=0.612,
                    source="synthetic_neutral_site",
                    scoring_source="synthetic_common_feature_artifact",
                ),
            ],
            team_advancement=[
                TournamentTeamAdvancement(
                    team_name="Alpha Aces",
                    seed=1,
                    region="East",
                    round_of_64_probability=1.0,
                    round_of_32_probability=0.882,
                    sweet_16_probability=0.731,
                    elite_8_probability=0.601,
                    final_4_probability=0.522,
                    championship_probability=0.441,
                    title_probability=0.340,
                ),
                TournamentTeamAdvancement(
                    team_name="Beta Bruins",
                    seed=2,
                    region="West",
                    round_of_64_probability=1.0,
                    round_of_32_probability=0.801,
                    sweet_16_probability=0.644,
                    elite_8_probability=0.533,
                    final_4_probability=0.451,
                    championship_probability=0.366,
                    title_probability=0.221,
                ),
            ],
            simulations=options.simulations,
        )

    monkeypatch.setattr(
        "cbb.cli.predict_tournament_bracket",
        fake_predict_tournament_bracket,
    )
    monkeypatch.setattr(
        "cbb.cli._format_local_datetime_iso",
        lambda value: f"LOCAL-DT {value.isoformat()}",
    )

    result = runner.invoke(
        app,
        [
            "model",
            "tournament",
            "--artifact-name",
            "bracket_v1",
            "--bracket-path",
            str(bracket_path),
            "--simulations",
            "2500",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, TournamentOptions)
    assert options.artifact_name == "bracket_v1"
    assert options.bracket_path == bracket_path.resolve()
    assert options.simulations == 2500
    assert "Tournament Summary: tournament=2026 NCAA Tournament" in result.stdout
    assert "Generated At: LOCAL-DT 2026-03-18T20:00:00+00:00" in result.stdout
    assert "Champion Pick: 1 Alpha Aces over 2 Beta Bruins (61.2%)" in result.stdout
    assert "Bracket Picks" in result.stdout
    assert (
        "Round of 64 | East | 1 Alpha Aces vs 16 Delta Dogs | "
        "pick 1 Alpha Aces | 88.2%"
    ) in result.stdout
    assert "Title Odds" in result.stdout
    assert (
        "1. 1 Alpha Aces (East) | title 34.0% | title game 44.1% | final four 52.2%"
    ) in result.stdout


def test_model_tournament_command_can_render_json_payload(monkeypatch) -> None:
    def fake_predict_tournament_bracket(_: TournamentOptions) -> TournamentSummary:
        return TournamentSummary(
            tournament_key="ncaa-men-2026",
            label="2026 NCAA Tournament",
            season=2026,
            generated_at=datetime(2026, 3, 18, 20, 0, tzinfo=UTC),
            artifact_name="latest",
            bracket_picks=[
                TournamentGamePick(
                    game_key="title",
                    round_label="Championship",
                    region=None,
                    scheduled_time="2026-04-06T01:20:00+00:00",
                    home_team_name="Alpha Aces",
                    home_seed=1,
                    away_team_name="Beta Bruins",
                    away_seed=2,
                    winner_name="Alpha Aces",
                    winner_seed=1,
                    winner_probability=0.612,
                    source="synthetic_neutral_site",
                    scoring_source="synthetic_common_feature_artifact",
                )
            ],
            team_advancement=[
                TournamentTeamAdvancement(
                    team_name="Alpha Aces",
                    seed=1,
                    region="East",
                    round_of_64_probability=1.0,
                    round_of_32_probability=0.882,
                    sweet_16_probability=0.731,
                    elite_8_probability=0.601,
                    final_4_probability=0.522,
                    championship_probability=0.441,
                    title_probability=0.340,
                )
            ],
            simulations=5000,
        )

    monkeypatch.setattr(
        "cbb.cli.predict_tournament_bracket",
        fake_predict_tournament_bracket,
    )
    monkeypatch.setattr(
        "cbb.cli._format_local_datetime_iso",
        lambda value: f"LOCAL-DT {value.isoformat()}",
    )
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp_iso",
        lambda value: None if value is None else f"LOCAL-TS {value}",
    )

    result = runner.invoke(app, ["model", "tournament", "--output-format", "json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "tournament.v1"
    assert payload["generated_at"] == "LOCAL-DT 2026-03-18T20:00:00+00:00"
    assert payload["tournament_key"] == "ncaa-men-2026"
    assert payload["summary"]["games"] == 1
    assert payload["summary"]["teams"] == 1
    assert payload["champion_pick"]["winner"]["name"] == "Alpha Aces"
    assert payload["champion_pick"]["winner"]["probability"] == 0.612
    assert payload["bracket_picks"][0]["scheduled_time_local"] == (
        "LOCAL-TS 2026-04-06T01:20:00+00:00"
    )
    assert payload["team_advancement"][0]["team"] == "Alpha Aces"
    assert payload["team_advancement"][0]["title_probability"] == 0.34


def test_model_tournament_backtest_command_renders_text_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_backtest_tournament_model(
        options: TournamentBacktestOptions,
    ) -> TournamentBacktestSummary:
        captured["options"] = options
        return TournamentBacktestSummary(
            generated_at=datetime(2026, 3, 18, 20, 0, tzinfo=UTC),
            season_summaries=[
                TournamentBacktestSeasonSummary(
                    tournament_key="ncaa-men-2025",
                    label="2025 NCAA Tournament",
                    season=2025,
                    training_seasons=(2023, 2024, 2025),
                    games=67,
                    correct_picks=44,
                    accuracy=44 / 67,
                    average_actual_winner_probability=0.612,
                    predicted_champion_name="Florida Gators",
                    predicted_champion_seed=1,
                    predicted_champion_probability=0.184,
                    actual_champion_name="Florida Gators",
                    actual_champion_seed=1,
                    champion_correct=True,
                    final_four_teams_correct=3,
                    round_summaries=[
                        TournamentBacktestRoundSummary(
                            round_label="Round of 64",
                            games=32,
                            correct_picks=22,
                            accuracy=22 / 32,
                            average_actual_winner_probability=0.638,
                            source_summaries=[
                                TournamentBacktestSourceSummary(
                                    source="moneyline_market_artifact",
                                    games=32,
                                    correct_picks=22,
                                    accuracy=22 / 32,
                                    average_actual_winner_probability=0.638,
                                )
                            ],
                        )
                    ],
                    source_summaries=[
                        TournamentBacktestSourceSummary(
                            source="moneyline_market_artifact",
                            games=67,
                            correct_picks=44,
                            accuracy=44 / 67,
                            average_actual_winner_probability=0.612,
                        )
                    ],
                    pick_seed_role_summaries=[
                        TournamentBacktestPickSeedRoleSummary(
                            role="favorite_pick",
                            games=51,
                            correct_picks=36,
                            accuracy=36 / 51,
                            average_actual_winner_probability=0.629,
                        ),
                        TournamentBacktestPickSeedRoleSummary(
                            role="upset_pick",
                            games=16,
                            correct_picks=8,
                            accuracy=0.5,
                            average_actual_winner_probability=0.559,
                        ),
                    ],
                    pick_seed_gap_summaries=[
                        TournamentBacktestSeedGapSummary(
                            seed_gap=5,
                            games=12,
                            correct_picks=8,
                            accuracy=8 / 12,
                            average_actual_winner_probability=0.601,
                        )
                    ],
                    synthetic_upset_probability_summaries=[
                        TournamentBacktestSyntheticUpsetProbabilitySummary(
                            bucket="prob_60_to_62",
                            games=5,
                            correct_picks=2,
                            accuracy=0.4,
                            average_actual_winner_probability=0.511,
                        )
                    ],
                    synthetic_favorite_probability_summaries=[
                        TournamentBacktestSyntheticFavoriteProbabilitySummary(
                            bucket="prob_60_to_65",
                            games=20,
                            correct_picks=15,
                            accuracy=15 / 20,
                            average_actual_winner_probability=0.701,
                        )
                    ],
                ),
                TournamentBacktestSeasonSummary(
                    tournament_key="ncaa-men-2024",
                    label="2024 NCAA Tournament",
                    season=2024,
                    training_seasons=(2023, 2024),
                    games=67,
                    correct_picks=41,
                    accuracy=41 / 67,
                    average_actual_winner_probability=0.584,
                    predicted_champion_name="Houston Cougars",
                    predicted_champion_seed=1,
                    predicted_champion_probability=0.171,
                    actual_champion_name="UConn Huskies",
                    actual_champion_seed=1,
                    champion_correct=False,
                    final_four_teams_correct=2,
                    round_summaries=[
                        TournamentBacktestRoundSummary(
                            round_label="Round of 64",
                            games=32,
                            correct_picks=20,
                            accuracy=20 / 32,
                            average_actual_winner_probability=0.594,
                            source_summaries=[
                                TournamentBacktestSourceSummary(
                                    source="moneyline_market_artifact",
                                    games=8,
                                    correct_picks=5,
                                    accuracy=5 / 8,
                                    average_actual_winner_probability=0.571,
                                ),
                                TournamentBacktestSourceSummary(
                                    source="synthetic_common_feature_artifact",
                                    games=24,
                                    correct_picks=15,
                                    accuracy=15 / 24,
                                    average_actual_winner_probability=0.602,
                                ),
                            ],
                        )
                    ],
                    source_summaries=[
                        TournamentBacktestSourceSummary(
                            source="moneyline_market_artifact",
                            games=10,
                            correct_picks=6,
                            accuracy=0.6,
                            average_actual_winner_probability=0.575,
                        ),
                        TournamentBacktestSourceSummary(
                            source="synthetic_common_feature_artifact",
                            games=57,
                            correct_picks=35,
                            accuracy=35 / 57,
                            average_actual_winner_probability=0.586,
                        ),
                    ],
                    pick_seed_role_summaries=[
                        TournamentBacktestPickSeedRoleSummary(
                            role="favorite_pick",
                            games=49,
                            correct_picks=32,
                            accuracy=32 / 49,
                            average_actual_winner_probability=0.593,
                        ),
                        TournamentBacktestPickSeedRoleSummary(
                            role="upset_pick",
                            games=18,
                            correct_picks=9,
                            accuracy=0.5,
                            average_actual_winner_probability=0.558,
                        ),
                    ],
                    pick_seed_gap_summaries=[
                        TournamentBacktestSeedGapSummary(
                            seed_gap=5,
                            games=10,
                            correct_picks=5,
                            accuracy=0.5,
                            average_actual_winner_probability=0.572,
                        )
                    ],
                    synthetic_upset_probability_summaries=[
                        TournamentBacktestSyntheticUpsetProbabilitySummary(
                            bucket="prob_60_to_62",
                            games=6,
                            correct_picks=2,
                            accuracy=2 / 6,
                            average_actual_winner_probability=0.492,
                        )
                    ],
                    synthetic_favorite_probability_summaries=[
                        TournamentBacktestSyntheticFavoriteProbabilitySummary(
                            bucket="prob_60_to_65",
                            games=18,
                            correct_picks=11,
                            accuracy=11 / 18,
                            average_actual_winner_probability=0.612,
                        )
                    ],
                ),
            ],
            games=134,
            correct_picks=85,
            accuracy=85 / 134,
            champion_hits=1,
            average_actual_winner_probability=0.598,
            round_summaries=[
                TournamentBacktestRoundSummary(
                    round_label="Round of 64",
                    games=64,
                    correct_picks=42,
                    accuracy=42 / 64,
                    average_actual_winner_probability=0.616,
                    source_summaries=[
                        TournamentBacktestSourceSummary(
                            source="moneyline_market_artifact",
                            games=40,
                            correct_picks=27,
                            accuracy=27 / 40,
                            average_actual_winner_probability=0.611,
                        ),
                        TournamentBacktestSourceSummary(
                            source="synthetic_common_feature_artifact",
                            games=24,
                            correct_picks=15,
                            accuracy=15 / 24,
                            average_actual_winner_probability=0.623,
                        ),
                    ],
                )
            ],
            source_summaries=[
                TournamentBacktestSourceSummary(
                    source="moneyline_market_artifact",
                    games=10,
                    correct_picks=6,
                    accuracy=0.6,
                    average_actual_winner_probability=0.575,
                ),
                TournamentBacktestSourceSummary(
                    source="synthetic_common_feature_artifact",
                    games=124,
                    correct_picks=79,
                    accuracy=79 / 124,
                    average_actual_winner_probability=0.599,
                ),
            ],
            pick_seed_role_summaries=[
                TournamentBacktestPickSeedRoleSummary(
                    role="favorite_pick",
                    games=100,
                    correct_picks=68,
                    accuracy=0.68,
                    average_actual_winner_probability=0.611,
                ),
                TournamentBacktestPickSeedRoleSummary(
                    role="upset_pick",
                    games=34,
                    correct_picks=17,
                    accuracy=0.5,
                    average_actual_winner_probability=0.559,
                ),
            ],
            pick_seed_gap_summaries=[
                TournamentBacktestSeedGapSummary(
                    seed_gap=5,
                    games=22,
                    correct_picks=13,
                    accuracy=13 / 22,
                    average_actual_winner_probability=0.588,
                )
            ],
            synthetic_upset_probability_summaries=[
                TournamentBacktestSyntheticUpsetProbabilitySummary(
                    bucket="prob_60_to_62",
                    games=11,
                    correct_picks=4,
                    accuracy=4 / 11,
                    average_actual_winner_probability=0.501,
                )
            ],
            synthetic_favorite_probability_summaries=[
                TournamentBacktestSyntheticFavoriteProbabilitySummary(
                    bucket="prob_60_to_65",
                    games=38,
                    correct_picks=26,
                    accuracy=26 / 38,
                    average_actual_winner_probability=0.659,
                )
            ],
        )

    monkeypatch.setattr(
        "cbb.cli.backtest_tournament_model",
        fake_backtest_tournament_model,
    )
    monkeypatch.setattr(
        "cbb.cli._format_local_datetime_iso",
        lambda value: f"LOCAL-DT {value.isoformat()}",
    )

    result = runner.invoke(
        app,
        [
            "model",
            "tournament-backtest",
            "--seasons",
            "2",
            "--max-season",
            "2025",
            "--training-seasons-back",
            "3",
            "--bracket-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, TournamentBacktestOptions)
    assert options.seasons == 2
    assert options.max_season == 2025
    assert options.training_seasons_back == 3
    assert options.bracket_dir == tmp_path.resolve()
    assert "Tournament Backtest Summary: seasons=2025, 2024" in result.stdout
    assert "Generated At: LOCAL-DT 2026-03-18T20:00:00+00:00" in result.stdout
    assert "Actual Winner Prob: 59.8%" in result.stdout
    assert "Season Results" in result.stdout
    assert "2025 | trained_on=2023,2024,2025" in result.stdout
    assert "champion miss (1 Houston Cougars vs 1 UConn Huskies)" in result.stdout
    assert "Round Accuracy" in result.stdout
    assert (
        "Round of 64 | correct 42/64 | accuracy 65.6% | actual winner prob 61.6%"
        in result.stdout
    )
    assert (
        "moneyline_market_artifact | correct 27/40 | accuracy 67.5% | "
        "actual winner prob 61.1%"
        in result.stdout
    )
    assert (
        "synthetic_common_feature_artifact | correct 15/24 | accuracy 62.5% | "
        "actual winner prob 62.3%"
        in result.stdout
    )
    assert "Scoring Source Accuracy" in result.stdout
    assert (
        "synthetic_common_feature_artifact | correct 79/124 | accuracy 63.7% | "
        "actual winner prob 59.9%"
        in result.stdout
    )
    assert "Pick Seed Role Accuracy" in result.stdout
    assert (
        "favorite pick | correct 68/100 | accuracy 68.0% | actual winner prob 61.1%"
        in result.stdout
    )
    assert (
        "upset pick | correct 17/34 | accuracy 50.0% | actual winner prob 55.9%"
        in result.stdout
    )
    assert "Pick Seed Gap Accuracy" in result.stdout
    assert (
        "seed gap 5 | correct 13/22 | accuracy 59.1% | actual winner prob 58.8%"
        in result.stdout
    )
    assert "Synthetic Upset Probability" in result.stdout
    assert (
        "60% to 62% | correct 4/11 | accuracy 36.4% | actual winner prob 50.1%"
        in result.stdout
    )
    assert "Synthetic Favorite Probability" in result.stdout
    assert (
        "60% to 65% | correct 26/38 | accuracy 68.4% | actual winner prob 65.9%"
        in result.stdout
    )


def test_model_tournament_backtest_command_can_render_json_payload(
    monkeypatch,
) -> None:
    def fake_backtest_tournament_model(
        _: TournamentBacktestOptions,
    ) -> TournamentBacktestSummary:
        return TournamentBacktestSummary(
            generated_at=datetime(2026, 3, 18, 20, 0, tzinfo=UTC),
            season_summaries=[
                TournamentBacktestSeasonSummary(
                    tournament_key="ncaa-men-2025",
                    label="2025 NCAA Tournament",
                    season=2025,
                    training_seasons=(2023, 2024, 2025),
                    games=67,
                    correct_picks=44,
                    accuracy=44 / 67,
                    average_actual_winner_probability=0.612,
                    predicted_champion_name="Florida Gators",
                    predicted_champion_seed=1,
                    predicted_champion_probability=0.184,
                    actual_champion_name="Florida Gators",
                    actual_champion_seed=1,
                    champion_correct=True,
                    final_four_teams_correct=3,
                    round_summaries=[
                        TournamentBacktestRoundSummary(
                            round_label="Championship",
                            games=1,
                            correct_picks=1,
                            accuracy=1.0,
                            average_actual_winner_probability=0.64,
                            source_summaries=[
                                TournamentBacktestSourceSummary(
                                    source="synthetic_common_feature_artifact",
                                    games=1,
                                    correct_picks=1,
                                    accuracy=1.0,
                                    average_actual_winner_probability=0.64,
                                )
                            ],
                        )
                    ],
                    source_summaries=[
                        TournamentBacktestSourceSummary(
                            source="synthetic_common_feature_artifact",
                            games=67,
                            correct_picks=44,
                            accuracy=44 / 67,
                            average_actual_winner_probability=0.612,
                        )
                    ],
                    pick_seed_role_summaries=[
                        TournamentBacktestPickSeedRoleSummary(
                            role="favorite_pick",
                            games=49,
                            correct_picks=35,
                            accuracy=35 / 49,
                            average_actual_winner_probability=0.624,
                        ),
                        TournamentBacktestPickSeedRoleSummary(
                            role="upset_pick",
                            games=18,
                            correct_picks=9,
                            accuracy=0.5,
                            average_actual_winner_probability=0.58,
                        ),
                    ],
                    pick_seed_gap_summaries=[
                        TournamentBacktestSeedGapSummary(
                            seed_gap=5,
                            games=11,
                            correct_picks=6,
                            accuracy=6 / 11,
                            average_actual_winner_probability=0.593,
                        )
                    ],
                    synthetic_upset_probability_summaries=[
                        TournamentBacktestSyntheticUpsetProbabilitySummary(
                            bucket="prob_60_to_62",
                            games=5,
                            correct_picks=2,
                            accuracy=0.4,
                            average_actual_winner_probability=0.508,
                        )
                    ],
                    synthetic_favorite_probability_summaries=[
                        TournamentBacktestSyntheticFavoriteProbabilitySummary(
                            bucket="prob_60_to_65",
                            games=21,
                            correct_picks=14,
                            accuracy=14 / 21,
                            average_actual_winner_probability=0.644,
                        )
                    ],
                )
            ],
            games=67,
            correct_picks=44,
            accuracy=44 / 67,
            champion_hits=1,
            average_actual_winner_probability=0.612,
            round_summaries=[
                TournamentBacktestRoundSummary(
                    round_label="Championship",
                    games=1,
                    correct_picks=1,
                    accuracy=1.0,
                    average_actual_winner_probability=0.64,
                    source_summaries=[
                        TournamentBacktestSourceSummary(
                            source="synthetic_common_feature_artifact",
                            games=1,
                            correct_picks=1,
                            accuracy=1.0,
                            average_actual_winner_probability=0.64,
                        )
                    ],
                )
            ],
            source_summaries=[
                TournamentBacktestSourceSummary(
                    source="synthetic_common_feature_artifact",
                    games=67,
                    correct_picks=44,
                    accuracy=44 / 67,
                    average_actual_winner_probability=0.612,
                )
            ],
            pick_seed_role_summaries=[
                TournamentBacktestPickSeedRoleSummary(
                    role="favorite_pick",
                    games=49,
                    correct_picks=35,
                    accuracy=35 / 49,
                    average_actual_winner_probability=0.624,
                ),
                TournamentBacktestPickSeedRoleSummary(
                    role="upset_pick",
                    games=18,
                    correct_picks=9,
                    accuracy=0.5,
                    average_actual_winner_probability=0.58,
                ),
            ],
            pick_seed_gap_summaries=[
                TournamentBacktestSeedGapSummary(
                    seed_gap=5,
                    games=11,
                    correct_picks=6,
                    accuracy=6 / 11,
                    average_actual_winner_probability=0.593,
                )
            ],
            synthetic_upset_probability_summaries=[
                TournamentBacktestSyntheticUpsetProbabilitySummary(
                    bucket="prob_60_to_62",
                    games=5,
                    correct_picks=2,
                    accuracy=0.4,
                    average_actual_winner_probability=0.508,
                )
            ],
            synthetic_favorite_probability_summaries=[
                TournamentBacktestSyntheticFavoriteProbabilitySummary(
                    bucket="prob_60_to_65",
                    games=21,
                    correct_picks=14,
                    accuracy=14 / 21,
                    average_actual_winner_probability=0.644,
                )
            ],
        )

    monkeypatch.setattr(
        "cbb.cli.backtest_tournament_model",
        fake_backtest_tournament_model,
    )
    monkeypatch.setattr(
        "cbb.cli._format_local_datetime_iso",
        lambda value: f"LOCAL-DT {value.isoformat()}",
    )

    result = runner.invoke(
        app,
        ["model", "tournament-backtest", "--output-format", "json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "tournament_backtest.v1"
    assert payload["generated_at"] == "LOCAL-DT 2026-03-18T20:00:00+00:00"
    assert payload["summary"]["games"] == 67
    assert payload["summary"]["champion_hits"] == 1
    assert payload["season_summaries"][0]["training_seasons"] == [2023, 2024, 2025]
    assert payload["season_summaries"][0]["predicted_champion"]["name"] == (
        "Florida Gators"
    )
    assert payload["round_summaries"][0]["round"] == "Championship"
    assert payload["round_summaries"][0]["average_actual_winner_probability"] == 0.64
    assert (
        payload["round_summaries"][0]["source_summaries"][0]["source"]
        == "synthetic_common_feature_artifact"
    )
    assert (
        payload["round_summaries"][0]["source_summaries"][0][
            "average_actual_winner_probability"
        ]
        == 0.64
    )
    assert (
        payload["source_summaries"][0]["source"]
        == "synthetic_common_feature_artifact"
    )
    assert payload["source_summaries"][0]["average_actual_winner_probability"] == 0.612
    assert payload["pick_seed_role_summaries"][0]["role"] == "favorite_pick"
    assert payload["pick_seed_role_summaries"][1]["correct_picks"] == 9
    assert payload["pick_seed_gap_summaries"][0]["seed_gap"] == 5
    assert payload["synthetic_upset_probability_summaries"][0]["bucket"] == (
        "prob_60_to_62"
    )
    assert payload["synthetic_favorite_probability_summaries"][0]["bucket"] == (
        "prob_60_to_65"
    )
    assert payload["season_summaries"][0]["source_summaries"][0]["games"] == 67
    assert (
        payload["season_summaries"][0]["pick_seed_role_summaries"][0]["games"] == 49
    )
    assert payload["season_summaries"][0]["pick_seed_gap_summaries"][0]["games"] == 11
    assert (
        payload["season_summaries"][0]["synthetic_upset_probability_summaries"][0][
            "correct_picks"
        ]
        == 2
    )
    assert (
        payload["season_summaries"][0]["synthetic_favorite_probability_summaries"][0][
            "correct_picks"
        ]
        == 14
    )
    assert (
        payload["season_summaries"][0]["round_summaries"][0]["source_summaries"][0][
            "games"
        ]
        == 1
    )
    assert (
        payload["season_summaries"][0]["round_summaries"][0][
            "average_actual_winner_probability"
        ]
        == 0.64
    )


def test_model_report_command_writes_markdown_report(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}
    report_path = tmp_path / "docs" / "results" / "best-model-5y-backtest.md"
    snapshot_path = tmp_path / "docs" / "results" / "best-model-dashboard-snapshot.json"

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
            history_output_path=report_path.parent
            / "history"
            / "best-model-5y-backtest_20260308_120000.md",
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
            generated_at="2026-03-12T10:30:00-04:00",
        )

    def fake_write_dashboard_snapshot(
        report: BestBacktestReport,
        *,
        report_options: BestBacktestReportOptions,
    ) -> Path:
        captured["snapshot_report"] = report
        captured["snapshot_options"] = report_options
        return snapshot_path

    monkeypatch.setattr(
        "cbb.cli.generate_best_backtest_report",
        fake_generate_best_backtest_report,
    )
    monkeypatch.setattr(
        "cbb.cli.write_dashboard_snapshot",
        fake_write_dashboard_snapshot,
    )

    result = runner.invoke(app, ["model", "report"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BestBacktestReportOptions)
    assert options.seasons == 5
    assert options.max_season is None
    assert options.auto_tune_spread_policy is False
    assert options.spread_model_family == "logistic"
    assert options.use_timing_layer is False
    assert options.policy.min_positive_ev_books == 4
    assert "Backtesting season 2026..." in result.stdout
    assert f"Dashboard snapshot: {snapshot_path}" in result.stdout
    assert "Generated best-model report:" in result.stdout
    assert "History copy:" in result.stdout
    assert "profit=$-35.18" in result.stdout
    assert "Aggregate CLV:" in result.stdout
    assert "Latest season CLV:" in result.stdout
    assert "Latest season 2026: profit=$10.67, roi=0.1775" in result.stdout
    assert "Zero-bet seasons: 2025" in result.stdout
    assert captured["snapshot_report"].generated_at == "2026-03-12T10:30:00-04:00"
    assert captured["snapshot_options"] is options


def test_model_report_command_accepts_timing_layer(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    report_path = tmp_path / "docs" / "results" / "best-model-5y-backtest.md"

    def fake_generate_best_backtest_report(
        options: BestBacktestReportOptions,
        *,
        progress,
    ) -> BestBacktestReport:
        captured["options"] = options
        progress("Backtesting season 2026...")
        return BestBacktestReport(
            output_path=report_path,
            history_output_path=None,
            selected_seasons=(2026,),
            summaries=(
                BacktestSummary(
                    market="best",
                    start_season=2024,
                    end_season=2026,
                    evaluation_season=2026,
                    blocks=1,
                    candidates_considered=0,
                    bets_placed=0,
                    wins=0,
                    losses=0,
                    pushes=0,
                    total_staked=0.0,
                    profit=0.0,
                    roi=0.0,
                    units_won=0.0,
                    starting_bankroll=1000.0,
                    ending_bankroll=1000.0,
                    max_drawdown=0.0,
                    sample_bets=[],
                ),
            ),
            aggregate_bets=0,
            aggregate_profit=0.0,
            aggregate_roi=0.0,
            aggregate_units=0.0,
            max_drawdown=0.0,
            zero_bet_seasons=(2026,),
            latest_summary=BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2026,
                evaluation_season=2026,
                blocks=1,
                candidates_considered=0,
                bets_placed=0,
                wins=0,
                losses=0,
                pushes=0,
                total_staked=0.0,
                profit=0.0,
                roi=0.0,
                units_won=0.0,
                starting_bankroll=1000.0,
                ending_bankroll=1000.0,
                max_drawdown=0.0,
                sample_bets=[],
            ),
            markdown="# report",
            generated_at="2026-03-12T10:30:00-04:00",
        )

    monkeypatch.setattr(
        "cbb.cli.generate_best_backtest_report",
        fake_generate_best_backtest_report,
    )
    monkeypatch.setattr(
        "cbb.cli.write_dashboard_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected")),
    )

    result = runner.invoke(app, ["model", "report", "--use-timing-layer"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BestBacktestReportOptions)
    assert options.use_timing_layer is True
    assert (
        "Dashboard snapshot: skipped because the report settings do not "
        in result.stdout
    )


def test_model_report_recent_command_reports_recent_bets(monkeypatch) -> None:
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
            bets_placed=3,
            wins=1,
            losses=2,
            pushes=0,
            total_staked=70.0,
            profit=-7.27,
            roi=-0.1039,
            units_won=-0.29,
            starting_bankroll=1000.0,
            ending_bankroll=992.73,
            max_drawdown=0.021,
            sample_bets=[],
            placed_bets=[
                PlacedBet(
                    game_id=20,
                    commence_time="2026-03-09T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=-110.0,
                    line_value=-1.5,
                    model_probability=0.590,
                    implied_probability=0.524,
                    probability_edge=0.066,
                    expected_value=0.090,
                    stake_fraction=0.020,
                    stake_amount=25.0,
                    settlement="win",
                    sportsbook="draftkings",
                    eligible_books=3,
                    positive_ev_books=2,
                    coverage_rate=2.0 / 3.0,
                ),
                PlacedBet(
                    game_id=21,
                    commence_time="2026-03-08T21:00:00+00:00",
                    market="moneyline",
                    team_name="Gamma Gulls",
                    opponent_name="Delta Dogs",
                    side="away",
                    market_price=120.0,
                    line_value=None,
                    model_probability=0.480,
                    implied_probability=0.455,
                    probability_edge=0.025,
                    expected_value=0.056,
                    stake_fraction=0.015,
                    stake_amount=20.0,
                    settlement="loss",
                    sportsbook="fanduel",
                    eligible_books=2,
                    positive_ev_books=2,
                    coverage_rate=1.0,
                ),
                PlacedBet(
                    game_id=22,
                    commence_time="2026-03-04T19:00:00+00:00",
                    market="spread",
                    team_name="Old Otters",
                    opponent_name="Past Panthers",
                    side="away",
                    market_price=-108.0,
                    line_value=2.5,
                    model_probability=0.540,
                    implied_probability=0.519,
                    probability_edge=0.021,
                    expected_value=0.040,
                    stake_fraction=0.010,
                    stake_amount=25.0,
                    settlement="loss",
                    sportsbook="betmgm",
                    eligible_books=1,
                    positive_ev_books=1,
                    coverage_rate=1.0,
                ),
            ],
            final_policy=BetPolicy(
                min_edge=0.027,
                min_confidence=0.518,
                min_probability_edge=0.025,
                min_games_played=4,
                min_positive_ev_books=2,
                max_spread_abs_line=10.0,
            ),
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["model", "report", "recent", "--days", "2"])

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BacktestOptions)
    assert options.market == "best"
    assert options.policy.min_positive_ev_books == 4
    assert options.policy.max_abs_rest_days_diff == 3.0
    assert "Recent model performance best:" in result.stdout
    assert "recent_days=2" in result.stdout
    assert "bets=2" in result.stdout
    assert "displayed=2/2" in result.stdout
    assert "profit=+$2.73" in result.stdout
    assert "Settlements: wins=1, losses=1, pushes=0" in result.stdout
    assert "Applied Spread Policy: blocks=0" in result.stdout
    assert "Recent Bets" in result.stdout
    assert "1. Alpha Aces -1.5 at draftkings -110 | 1.00u | win +$22.73" in (
        result.stdout
    )
    assert "2. Gamma Gulls ML at fanduel +120 | 0.80u | loss -$20.00" in (result.stdout)
    assert "Old Otters" not in result.stdout


def test_model_report_recent_command_supports_verbose_output(monkeypatch) -> None:
    def fake_backtest_betting_model(_: BacktestOptions) -> BacktestSummary:
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=4,
            bets_placed=1,
            wins=1,
            losses=0,
            pushes=0,
            total_staked=25.0,
            profit=22.73,
            roi=0.9092,
            units_won=0.91,
            starting_bankroll=1000.0,
            ending_bankroll=1022.73,
            max_drawdown=0.0,
            sample_bets=[],
            placed_bets=[
                PlacedBet(
                    game_id=20,
                    commence_time="2026-03-09T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=-110.0,
                    line_value=-1.5,
                    model_probability=0.590,
                    implied_probability=0.524,
                    probability_edge=0.066,
                    expected_value=0.090,
                    stake_fraction=0.020,
                    stake_amount=25.0,
                    settlement="win",
                    sportsbook="draftkings",
                    eligible_books=3,
                    positive_ev_books=2,
                    coverage_rate=2.0 / 3.0,
                )
            ],
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)
    monkeypatch.setattr(
        "cbb.cli._format_local_timestamp",
        lambda value: f"LOCAL {value}",
    )

    result = runner.invoke(app, ["model", "report", "recent", "--verbose"])

    assert result.exit_code == 0
    assert "team=Alpha Aces" in result.stdout
    assert "pnl=+$22.73" in result.stdout
    assert "model_probability=0.590" in result.stdout
    assert "coverage_rate=0.667" in result.stdout


def test_model_report_recent_command_handles_empty_results(monkeypatch) -> None:
    def fake_backtest_betting_model(_: BacktestOptions) -> BacktestSummary:
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=0,
            bets_placed=0,
            wins=0,
            losses=0,
            pushes=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            units_won=0.0,
            starting_bankroll=1000.0,
            ending_bankroll=1000.0,
            max_drawdown=0.0,
            sample_bets=[],
            placed_bets=[],
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)

    result = runner.invoke(app, ["model", "report", "recent"])

    assert result.exit_code == 0
    assert "No simulated bets were placed under the selected backtest settings." in (
        result.stdout
    )


def test_model_train_command_accepts_model_family(monkeypatch, tmp_path: Path) -> None:
    artifact_path = tmp_path / "artifacts" / "models" / "spread_latest.json"
    captured: dict[str, object] = {}

    def fake_train_betting_model(options: TrainingOptions) -> TrainingSummary:
        captured["options"] = options
        return TrainingSummary(
            market="spread",
            model_family="hist_gradient_boosting",
            start_season=2024,
            end_season=2026,
            examples=200,
            priced_examples=120,
            training_examples=180,
            accuracy=0.61,
            log_loss=0.64,
            brier_score=0.22,
            market_blend_weight=0.35,
            max_market_probability_delta=0.04,
            artifact_path=artifact_path,
        )

    monkeypatch.setattr("cbb.cli.train_betting_model", fake_train_betting_model)

    result = runner.invoke(
        app,
        [
            "model",
            "train",
            "--market",
            "spread",
            "--model-family",
            "hist_gradient_boosting",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, TrainingOptions)
    assert options.market == "spread"
    assert options.model_family == "hist_gradient_boosting"
    assert "family=hist_gradient_boosting" in result.stdout


def test_model_backtest_command_accepts_spread_model_family(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_backtest_betting_model(options: BacktestOptions) -> BacktestSummary:
        captured["options"] = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=1,
            candidates_considered=0,
            bets_placed=0,
            wins=0,
            losses=0,
            pushes=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            units_won=0.0,
            starting_bankroll=1000.0,
            ending_bankroll=1000.0,
            max_drawdown=0.0,
            sample_bets=[],
        )

    monkeypatch.setattr("cbb.cli.backtest_betting_model", fake_backtest_betting_model)

    result = runner.invoke(
        app,
        [
            "model",
            "backtest",
            "--spread-model-family",
            "hist_gradient_boosting",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BacktestOptions)
    assert options.spread_model_family == "hist_gradient_boosting"


def test_model_report_command_accepts_spread_model_family(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    report_path = tmp_path / "docs" / "results" / "best-model-5y-backtest.md"

    def fake_generate_best_backtest_report(
        options: BestBacktestReportOptions,
        *,
        progress,
    ) -> BestBacktestReport:
        captured["options"] = options
        progress("Backtesting season 2026...")
        return BestBacktestReport(
            output_path=report_path,
            history_output_path=None,
            selected_seasons=(2026,),
            summaries=(
                BacktestSummary(
                    market="best",
                    start_season=2024,
                    end_season=2026,
                    evaluation_season=2026,
                    blocks=1,
                    candidates_considered=0,
                    bets_placed=0,
                    wins=0,
                    losses=0,
                    pushes=0,
                    total_staked=0.0,
                    profit=0.0,
                    roi=0.0,
                    units_won=0.0,
                    starting_bankroll=1000.0,
                    ending_bankroll=1000.0,
                    max_drawdown=0.0,
                    sample_bets=[],
                ),
            ),
            aggregate_bets=0,
            aggregate_profit=0.0,
            aggregate_roi=0.0,
            aggregate_units=0.0,
            max_drawdown=0.0,
            zero_bet_seasons=(2026,),
            latest_summary=BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2026,
                evaluation_season=2026,
                blocks=1,
                candidates_considered=0,
                bets_placed=0,
                wins=0,
                losses=0,
                pushes=0,
                total_staked=0.0,
                profit=0.0,
                roi=0.0,
                units_won=0.0,
                starting_bankroll=1000.0,
                ending_bankroll=1000.0,
                max_drawdown=0.0,
                sample_bets=[],
            ),
            markdown="# report",
        )

    monkeypatch.setattr(
        "cbb.cli.generate_best_backtest_report",
        fake_generate_best_backtest_report,
    )

    result = runner.invoke(
        app,
        [
            "model",
            "report",
            "--spread-model-family",
            "hist_gradient_boosting",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BestBacktestReportOptions)
    assert options.spread_model_family == "hist_gradient_boosting"


def test_model_report_command_accepts_survivability_policy(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}
    report_path = tmp_path / "docs" / "results" / "best-model-5y-backtest.md"

    def fake_generate_best_backtest_report(
        options: BestBacktestReportOptions,
        *,
        progress,
    ) -> BestBacktestReport:
        captured["options"] = options
        progress("Backtesting season 2026...")
        return BestBacktestReport(
            output_path=report_path,
            history_output_path=None,
            selected_seasons=(2026,),
            summaries=(
                BacktestSummary(
                    market="best",
                    start_season=2024,
                    end_season=2026,
                    evaluation_season=2026,
                    blocks=1,
                    candidates_considered=0,
                    bets_placed=0,
                    wins=0,
                    losses=0,
                    pushes=0,
                    total_staked=0.0,
                    profit=0.0,
                    roi=0.0,
                    units_won=0.0,
                    starting_bankroll=1000.0,
                    ending_bankroll=1000.0,
                    max_drawdown=0.0,
                    sample_bets=[],
                ),
            ),
            aggregate_bets=0,
            aggregate_profit=0.0,
            aggregate_roi=0.0,
            aggregate_units=0.0,
            max_drawdown=0.0,
            zero_bet_seasons=(2026,),
            latest_summary=BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2026,
                evaluation_season=2026,
                blocks=1,
                candidates_considered=0,
                bets_placed=0,
                wins=0,
                losses=0,
                pushes=0,
                total_staked=0.0,
                profit=0.0,
                roi=0.0,
                units_won=0.0,
                starting_bankroll=1000.0,
                ending_bankroll=1000.0,
                max_drawdown=0.0,
                sample_bets=[],
            ),
            markdown="# report",
        )

    monkeypatch.setattr(
        "cbb.cli.generate_best_backtest_report",
        fake_generate_best_backtest_report,
    )

    result = runner.invoke(
        app,
        [
            "model",
            "report",
            "--min-positive-ev-books",
            "3",
            "--min-median-expected-value",
            "0.01",
        ],
    )

    assert result.exit_code == 0
    options = captured["options"]
    assert isinstance(options, BestBacktestReportOptions)
    assert options.policy.min_positive_ev_books == 3
    assert options.policy.min_median_expected_value == 0.01
