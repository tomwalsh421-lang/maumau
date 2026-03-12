import json
from dataclasses import replace
from pathlib import Path

from cbb.dashboard.snapshot import (
    DASHBOARD_SNAPSHOT_SCHEMA_VERSION,
    DashboardSnapshotArtifact,
    DashboardSnapshotArtifactSource,
    dashboard_snapshot_staleness_reason,
    ensure_dashboard_snapshot_fresh,
    load_dashboard_snapshot,
    write_dashboard_snapshot,
)
from cbb.db import AvailabilityShadowStatusCount, AvailabilityShadowSummary
from cbb.modeling.backtest import (
    BacktestSummary,
    ClosingLineValueObservation,
    ClosingLineValueSummary,
)
from cbb.modeling.policy import BetPolicy, PlacedBet
from cbb.modeling.report import BestBacktestReport, BestBacktestReportOptions


def test_write_dashboard_snapshot_round_trips_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "best-model-report.md"
    report_path.write_text("# report", encoding="utf-8")
    report = _sample_report(report_path)
    report_options = BestBacktestReportOptions(
        output_path=report_path,
        seasons=1,
        max_season=2026,
        write_history_copy=False,
    )
    snapshot_path = tmp_path / "best-model-dashboard-snapshot.json"

    monkeypatch.setattr(
        "cbb.dashboard.snapshot.current_dashboard_artifact_source",
        lambda artifacts_dir=None: _artifact_source("artifact-a"),
    )

    write_dashboard_snapshot(
        report,
        report_options=report_options,
        snapshot_path=snapshot_path,
    )
    snapshot = load_dashboard_snapshot(snapshot_path)

    assert snapshot.schema_version == DASHBOARD_SNAPSHOT_SCHEMA_VERSION
    assert snapshot.aggregate_summary.bets == 1
    assert snapshot.aggregate_clv.average_spread_closing_expected_value == 0.08
    assert snapshot.historical_bets[0].team_name == "Duke Blue Devils"
    assert snapshot.historical_bets[0].profit == 18.181818181818183
    assert {window.key for window in snapshot.recent_windows} == {
        "7",
        "14",
        "30",
        "90",
        "season",
    }


def test_dashboard_snapshot_staleness_detects_artifact_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report = _sample_report(tmp_path / "best-model-report.md")
    report_options = BestBacktestReportOptions(
        output_path=tmp_path / "best-model-report.md",
        seasons=1,
        max_season=2026,
        write_history_copy=False,
    )
    snapshot_path = tmp_path / "best-model-dashboard-snapshot.json"

    monkeypatch.setattr(
        "cbb.dashboard.snapshot.current_dashboard_artifact_source",
        lambda artifacts_dir=None: _artifact_source("artifact-a"),
    )
    write_dashboard_snapshot(
        report,
        report_options=report_options,
        snapshot_path=snapshot_path,
    )
    monkeypatch.setattr(
        "cbb.dashboard.snapshot.current_dashboard_artifact_source",
        lambda artifacts_dir=None: _artifact_source("artifact-b"),
    )

    reason = dashboard_snapshot_staleness_reason(
        snapshot_path=snapshot_path,
        report_options=report_options,
    )

    assert (
        reason
        == "Dashboard snapshot no longer matches the current best-path artifacts."
    )


def test_ensure_dashboard_snapshot_fresh_rebuilds_missing_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "best-model-report.md"
    report = _sample_report(report_path)
    progress_messages: list[str] = []

    monkeypatch.setattr(
        "cbb.dashboard.snapshot.generate_best_backtest_report",
        lambda options, progress=None: report,
    )
    monkeypatch.setattr(
        "cbb.dashboard.snapshot.current_dashboard_artifact_source",
        lambda artifacts_dir=None: _artifact_source("artifact-a"),
    )

    snapshot = ensure_dashboard_snapshot_fresh(
        snapshot_path=tmp_path / "best-model-dashboard-snapshot.json",
        progress=progress_messages.append,
    )

    assert snapshot.generated_at == "2026-03-12T10:30:00-04:00"
    assert progress_messages[0].startswith("Dashboard snapshot is missing.")
    assert progress_messages[-1].endswith("best-model-dashboard-snapshot.json")


def test_load_dashboard_snapshot_accepts_older_policy_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "best-model-report.md"
    report_path.write_text("# report", encoding="utf-8")
    report = _sample_report(report_path)
    report_options = BestBacktestReportOptions(
        output_path=report_path,
        seasons=1,
        max_season=2026,
        write_history_copy=False,
    )
    snapshot_path = tmp_path / "best-model-dashboard-snapshot.json"

    monkeypatch.setattr(
        "cbb.dashboard.snapshot.current_dashboard_artifact_source",
        lambda artifacts_dir=None: _artifact_source("artifact-a"),
    )

    write_dashboard_snapshot(
        report,
        report_options=report_options,
        snapshot_path=snapshot_path,
    )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    del payload["canonical_report"]["policy"]["max_bets_per_day"]
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")

    snapshot = load_dashboard_snapshot(snapshot_path)

    assert snapshot.canonical_report.policy.max_bets_per_day is None


def test_dashboard_snapshot_round_trips_availability_shadow_summary(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "best-model-report.md"
    report_path.write_text("# report", encoding="utf-8")
    report = replace(
        _sample_report(report_path),
        availability_shadow_summary=_availability_shadow_summary(),
    )
    report_options = BestBacktestReportOptions(
        output_path=report_path,
        seasons=1,
        max_season=2026,
        write_history_copy=False,
    )
    snapshot_path = tmp_path / "best-model-dashboard-snapshot.json"

    monkeypatch.setattr(
        "cbb.dashboard.snapshot.current_dashboard_artifact_source",
        lambda artifacts_dir=None: _artifact_source("artifact-a"),
    )

    write_dashboard_snapshot(
        report,
        report_options=report_options,
        snapshot_path=snapshot_path,
    )
    snapshot = load_dashboard_snapshot(snapshot_path)

    assert snapshot.availability_shadow_summary.games_covered == 2
    assert snapshot.availability_shadow_summary.unmatched_player_rows == 2
    assert (
        snapshot.to_report().availability_shadow_summary
        == _availability_shadow_summary()
    )


def test_load_dashboard_snapshot_accepts_missing_availability_shadow_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    report_path = tmp_path / "best-model-report.md"
    report_path.write_text("# report", encoding="utf-8")
    report = replace(
        _sample_report(report_path),
        availability_shadow_summary=_availability_shadow_summary(),
    )
    report_options = BestBacktestReportOptions(
        output_path=report_path,
        seasons=1,
        max_season=2026,
        write_history_copy=False,
    )
    snapshot_path = tmp_path / "best-model-dashboard-snapshot.json"

    monkeypatch.setattr(
        "cbb.dashboard.snapshot.current_dashboard_artifact_source",
        lambda artifacts_dir=None: _artifact_source("artifact-a"),
    )

    write_dashboard_snapshot(
        report,
        report_options=report_options,
        snapshot_path=snapshot_path,
    )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    del payload["availability_shadow_summary"]
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")

    snapshot = load_dashboard_snapshot(snapshot_path)

    assert snapshot.availability_shadow_summary == AvailabilityShadowSummary()


def _sample_report(report_path: Path) -> BestBacktestReport:
    bet = PlacedBet(
        game_id=401,
        commence_time="2026-03-11T19:00:00+00:00",
        market="spread",
        team_name="Duke Blue Devils",
        opponent_name="Virginia Cavaliers",
        side="home",
        sportsbook="draftkings",
        market_price=-110.0,
        line_value=-4.5,
        model_probability=0.542,
        implied_probability=0.5,
        probability_edge=0.042,
        expected_value=0.05,
        stake_fraction=0.02,
        stake_amount=20.0,
        settlement="win",
        minimum_games_played=8,
        eligible_books=5,
        positive_ev_books=3,
        coverage_rate=0.8,
    )
    clv_observation = ClosingLineValueObservation(
        market="spread",
        reference_delta=-0.1,
        spread_line_delta=-0.1,
        spread_price_probability_delta=0.01,
        spread_no_vig_probability_delta=0.008,
        spread_closing_expected_value=0.08,
        game_id=401,
        side="home",
    )
    summary = BacktestSummary(
        market="best",
        start_season=2024,
        end_season=2026,
        evaluation_season=2026,
        blocks=12,
        candidates_considered=48,
        bets_placed=1,
        wins=1,
        losses=0,
        pushes=0,
        total_staked=20.0,
        profit=18.0,
        roi=0.9,
        units_won=0.72,
        starting_bankroll=1000.0,
        ending_bankroll=1018.0,
        max_drawdown=0.02,
        sample_bets=[bet],
        placed_bets=[bet],
        clv_observations=[clv_observation],
        clv=ClosingLineValueSummary(
            bets_evaluated=1,
            positive_bets=1,
            spread_bets_evaluated=1,
            total_spread_line_delta=-0.1,
            spread_price_bets_evaluated=1,
            total_spread_price_probability_delta=0.01,
            spread_no_vig_bets_evaluated=1,
            total_spread_no_vig_probability_delta=0.008,
            spread_closing_ev_bets_evaluated=1,
            total_spread_closing_expected_value=0.08,
        ),
        final_policy=BetPolicy(min_edge=0.04, min_probability_edge=0.04),
    )
    return BestBacktestReport(
        output_path=report_path,
        history_output_path=None,
        selected_seasons=(2026,),
        summaries=(summary,),
        aggregate_bets=1,
        aggregate_profit=18.0,
        aggregate_roi=0.9,
        aggregate_units=0.72,
        max_drawdown=0.02,
        zero_bet_seasons=(),
        latest_summary=summary,
        markdown="# report",
        generated_at="2026-03-12T10:30:00-04:00",
        aggregate_clv=summary.clv,
    )


def _artifact_source(signature: str) -> DashboardSnapshotArtifactSource:
    return DashboardSnapshotArtifactSource(
        active_best_market="spread",
        entries=(
            DashboardSnapshotArtifact(
                market="spread",
                artifact_name="latest",
                path="artifacts/models/spread_latest.json",
                sha256=signature,
                model_family="logistic",
                trained_at="2026-03-12T09:00:00-04:00",
                start_season=2024,
                end_season=2026,
            ),
        ),
        signature=signature,
    )


def _availability_shadow_summary() -> AvailabilityShadowSummary:
    return AvailabilityShadowSummary(
        reports_loaded=3,
        player_rows_loaded=11,
        games_covered=2,
        matched_player_rows=9,
        unmatched_player_rows=2,
        latest_update_at="2026-03-11T18:05:00+00:00",
        average_minutes_before_tip=82.0,
        latest_minutes_before_tip=85.0,
        seasons=(2026,),
        scope_labels=("postseason",),
        source_labels=("ncaa",),
        status_counts=(
            AvailabilityShadowStatusCount(status="available", row_count=6),
            AvailabilityShadowStatusCount(status="out", row_count=3),
        ),
    )
