from pathlib import Path

from cbb.modeling.backtest import (
    BacktestSummary,
    ClosingLineValueSummary,
    SpreadSegmentAttribution,
    SpreadSegmentSummary,
)
from cbb.modeling.policy import BetPolicy
from cbb.modeling.report import (
    BestBacktestReportOptions,
    build_best_backtest_report,
    generate_best_backtest_report,
)


def test_generate_best_backtest_report_writes_markdown(
    monkeypatch,
    tmp_path: Path,
) -> None:
    progress_messages: list[str] = []

    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2024, 2025, 2026],
    )

    def fake_backtest_betting_model(options) -> BacktestSummary:
        assert options.market == "best"
        assert options.spread_model_family == "logistic"
        assert options.use_timing_layer is False
        if options.evaluation_season == 2024:
            return BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2024,
                evaluation_season=2024,
                blocks=3,
                candidates_considered=20,
                bets_placed=10,
                wins=6,
                losses=4,
                pushes=0,
                total_staked=200.0,
                profit=-20.0,
                roi=-0.10,
                units_won=-0.80,
                starting_bankroll=1000.0,
                ending_bankroll=980.0,
                max_drawdown=0.08,
                sample_bets=[],
                clv=ClosingLineValueSummary(
                    bets_evaluated=2,
                    positive_bets=1,
                    negative_bets=1,
                    neutral_bets=0,
                    spread_bets_evaluated=2,
                    total_spread_line_delta=1.0,
                    spread_price_bets_evaluated=2,
                    total_spread_price_probability_delta=0.03,
                    spread_no_vig_bets_evaluated=2,
                    total_spread_no_vig_probability_delta=0.02,
                    spread_closing_ev_bets_evaluated=2,
                    total_spread_closing_expected_value=0.10,
                ),
                final_policy=BetPolicy(
                    min_edge=0.02,
                    min_probability_edge=0.015,
                    min_games_played=8,
                    min_positive_ev_books=2,
                    min_median_expected_value=0.01,
                    max_spread_abs_line=10.0,
                ),
            )
        if options.evaluation_season == 2025:
            return BacktestSummary(
                market="best",
                start_season=2024,
                end_season=2025,
                evaluation_season=2025,
                blocks=3,
                candidates_considered=4,
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
                final_policy=None,
            )
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=3,
            candidates_considered=8,
            bets_placed=5,
            wins=4,
            losses=1,
            pushes=0,
            total_staked=100.0,
            profit=15.0,
            roi=0.15,
            units_won=0.60,
            starting_bankroll=1000.0,
            ending_bankroll=1015.0,
            max_drawdown=0.02,
            sample_bets=[],
            clv=ClosingLineValueSummary(
                bets_evaluated=1,
                positive_bets=1,
                negative_bets=0,
                neutral_bets=0,
                moneyline_bets_evaluated=1,
                total_moneyline_probability_delta=0.01,
            ),
            final_policy=BetPolicy(
                min_edge=0.02,
                min_probability_edge=0.015,
                min_games_played=8,
                min_positive_ev_books=2,
                min_median_expected_value=0.01,
                max_spread_abs_line=10.0,
            ),
        )

    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        fake_backtest_betting_model,
    )

    report = generate_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "best-model-report.md",
            seasons=3,
            max_season=2026,
        ),
        progress=progress_messages.append,
    )

    assert report.selected_seasons == (2024, 2025, 2026)
    assert report.aggregate_bets == 15
    assert report.aggregate_profit == -5.0
    assert report.zero_bet_seasons == (2025,)
    assert report.generated_at
    assert report.output_path.exists()
    assert report.history_output_path is not None
    assert report.history_output_path.exists()
    assert "Best Model Backtest Report" in report.markdown
    assert "History Copy:" in report.markdown
    assert "Spread model family: `logistic`" in report.markdown
    assert "Auto-tuned spread policy: `disabled`" in report.markdown
    assert "Timing layer: `disabled`" in report.markdown
    assert "min_positive_ev_books=2" in report.markdown
    assert "max_bets_per_day=none" in report.markdown
    assert "min_median_expected_value=0.010" in report.markdown
    assert "Avg Spread Price CLV" in report.markdown
    assert "Avg Spread No-Vig Close Delta" in report.markdown
    assert "Avg Spread Closing EV" in report.markdown
    assert "+1.50 pp" in report.markdown
    assert "+1.00 pp" in report.markdown
    assert "+0.050" in report.markdown
    assert "## Decision Snapshot" in report.markdown
    assert "Strongest evidence:" in report.markdown
    assert "Main risk:" in report.markdown
    assert "Next action:" in report.markdown
    assert "## Close-Market Coverage" in report.markdown
    assert "2/2 (+100.00%)" in report.markdown
    assert "Spread closing EV" in report.markdown
    assert "## Closing-Line Value" in report.markdown
    assert "Aggregate CLV:" in report.markdown
    assert "Close-market coverage:" in report.markdown
    assert "`2024`" in report.markdown
    assert "`2025`" in report.markdown
    assert "`2026`" in report.markdown
    assert "`-20.00%`" not in report.markdown
    assert (
        "The current deployable path is positive in the latest season"
        in report.markdown
    )
    assert progress_messages[0] == "Backtesting season 2024..."
    assert (
        progress_messages[-1]
        == "Finished season 2026: bets=5, profit=+$15.00, roi=+15.00%"
    )


def test_generate_best_backtest_report_rejects_empty_window(monkeypatch) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2024, 2025, 2026],
    )

    try:
        generate_best_backtest_report(
            BestBacktestReportOptions(
                seasons=3,
                max_season=2023,
            )
        )
    except ValueError as exc:
        assert "No completed seasons match" in str(exc)
    else:
        raise AssertionError("Expected a ValueError for an empty season window")


def test_build_best_backtest_report_does_not_write_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )

    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        lambda _options: BacktestSummary(
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
            total_staked=20.0,
            profit=5.0,
            roi=0.25,
            units_won=0.20,
            starting_bankroll=1000.0,
            ending_bankroll=1005.0,
            max_drawdown=0.0,
            sample_bets=[],
        ),
    )

    report = build_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert report.output_path == tmp_path / "report.md"
    assert report.history_output_path is not None
    assert not report.output_path.exists()
    assert not report.history_output_path.exists()


def test_generate_best_backtest_report_renders_spread_segment_attribution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.report.get_available_seasons",
        lambda _database_url=None: [2026],
    )

    def fake_backtest_betting_model(options) -> BacktestSummary:
        _ = options
        return BacktestSummary(
            market="best",
            start_season=2024,
            end_season=2026,
            evaluation_season=2026,
            blocks=3,
            candidates_considered=20,
            bets_placed=10,
            wins=6,
            losses=4,
            pushes=0,
            total_staked=200.0,
            profit=15.0,
            roi=0.075,
            units_won=0.60,
            starting_bankroll=1000.0,
            ending_bankroll=1015.0,
            max_drawdown=0.03,
            sample_bets=[],
            spread_segment_attribution=(
                SpreadSegmentAttribution(
                    dimension="expected_value_bucket",
                    segments=(
                        SpreadSegmentSummary(
                            value="ev_4_to_6",
                            bets=7,
                            total_staked=140.0,
                            profit=9.0,
                            roi=0.0642857143,
                            share_of_bets=0.70,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=7,
                                positive_bets=3,
                                negative_bets=4,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=7,
                                total_spread_closing_expected_value=0.28,
                            ),
                        ),
                        SpreadSegmentSummary(
                            value="ev_6_to_8",
                            bets=3,
                            total_staked=60.0,
                            profit=6.0,
                            roi=0.10,
                            share_of_bets=0.30,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=3,
                                positive_bets=2,
                                negative_bets=1,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=3,
                                total_spread_closing_expected_value=0.15,
                            ),
                        ),
                    ),
                ),
                SpreadSegmentAttribution(
                    dimension="season_phase",
                    segments=(
                        SpreadSegmentSummary(
                            value="early",
                            bets=4,
                            total_staked=80.0,
                            profit=-8.0,
                            roi=-0.10,
                            share_of_bets=0.40,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=4,
                                positive_bets=1,
                                negative_bets=3,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=4,
                                total_spread_closing_expected_value=-0.08,
                            ),
                        ),
                        SpreadSegmentSummary(
                            value="established",
                            bets=6,
                            total_staked=120.0,
                            profit=23.0,
                            roi=0.1916666667,
                            share_of_bets=0.60,
                            clv=ClosingLineValueSummary(
                                bets_evaluated=6,
                                positive_bets=4,
                                negative_bets=2,
                                neutral_bets=0,
                                spread_closing_ev_bets_evaluated=6,
                                total_spread_closing_expected_value=0.18,
                            ),
                        ),
                    ),
                ),
            ),
        )

    monkeypatch.setattr(
        "cbb.modeling.report.backtest_betting_model",
        fake_backtest_betting_model,
    )

    report = generate_best_backtest_report(
        BestBacktestReportOptions(
            output_path=tmp_path / "best-model-report.md",
            seasons=1,
            max_season=2026,
        )
    )

    assert "## Spread Segment Attribution" in report.markdown
    assert "### Expected Value Bucket" in report.markdown
    assert "| `4% to 6%` | 7 | +70.00% | +$9.00 | +6.43% | +0.040 |" in report.markdown
    assert "### Season Phase" in report.markdown
    assert "| `Early` | 4 | +40.00% | -$8.00 | -10.00% | -0.020 |" in report.markdown
    assert (
        "| `Established` | 6 | +60.00% | +$23.00 | +19.17% | +0.030 |"
        in report.markdown
    )
