from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from math import log
from pathlib import Path
from types import SimpleNamespace

import pytest

import cbb.modeling.train as train_module
from cbb.db import AvailabilityGameSideShadow
from cbb.modeling import (
    BacktestOptions,
    BetPolicy,
    LogisticRegressionConfig,
    PredictionOptions,
    TrainingOptions,
    backtest_betting_model,
    load_artifact,
    predict_best_bets,
    train_betting_model,
)
from cbb.modeling.artifacts import (
    ModelArtifact,
    MoneylineBandModel,
    MoneylineSegmentCalibration,
    SpreadBookDepthResidualScale,
    SpreadConferenceCalibration,
    SpreadLineCalibration,
    SpreadLineResidualScale,
    SpreadSeasonPhaseCalibration,
    SpreadSeasonPhaseResidualScale,
    SpreadTimingModel,
    TrainingMetrics,
    save_artifact,
)
from cbb.modeling.backtest import (
    CandidateBlock,
    ClosingLineValueObservation,
    PolicyEvaluation,
    SpreadClosingMarketMetrics,
    SpreadTuningActivityConstraints,
    _build_spread_closing_market_metrics,
    _evaluate_policy_on_candidate_blocks,
    _select_tuned_spread_policy,
    _summarize_closing_line_value,
    _summarize_spread_segment_attribution,
)
from cbb.modeling.dataset import (
    load_live_board_game_records,
    load_upcoming_game_records,
)
from cbb.modeling.execution import build_executable_candidate_bets
from cbb.modeling.features import (
    ExecutableQuote,
    ModelExample,
    normalized_implied_probability_from_prices,
)
from cbb.modeling.infer import _load_prediction_artifacts
from cbb.modeling.policy import (
    CandidateBet,
    PlacedBet,
    apply_bankroll_limits,
    apply_bankroll_limits_with_diagnostics,
    candidate_matches_policy,
    candidate_matches_selection_policy,
    deployable_spread_policy,
    score_candidate_bet,
    score_candidate_bet_for_quote,
    select_best_candidates,
    select_best_quote_candidates,
    spread_candidate_segment_values,
)
from cbb.modeling.train import (
    DEFAULT_MONEYLINE_TRAIN_MAX_PRICE,
    DEFAULT_MONEYLINE_TRAIN_MIN_PRICE,
    SPREAD_TIMING_FEATURE_NAMES,
    _select_spread_conference_calibrations,
    _select_spread_line_calibrations,
    _select_spread_season_phase_calibrations,
    apply_platt_scaling,
    calibrate_probabilities,
    fit_platt_scaling,
    score_examples,
    select_spread_timing_model,
)


def test_train_betting_model_saves_moneyline_artifact(tmp_path: Path) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)

    summary = train_betting_model(
        TrainingOptions(
            market="moneyline",
            seasons_back=2,
            max_season=2026,
            artifact_name="unit_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=4,
            ),
        )
    )

    artifact = load_artifact(
        market="moneyline",
        artifact_name="unit_test",
        artifacts_dir=artifacts_dir,
    )
    latest_artifact = load_artifact(
        market="moneyline",
        artifact_name="latest",
        artifacts_dir=artifacts_dir,
    )

    assert summary.market == "moneyline"
    assert summary.start_season == 2025
    assert summary.end_season == 2026
    assert summary.training_examples >= 8
    assert summary.priced_examples >= 8
    assert 0.0 <= summary.market_blend_weight <= 1.0
    assert summary.max_market_probability_delta > 0.0
    assert summary.artifact_path.exists()
    assert artifact.market == "moneyline"
    assert artifact.metrics.training_examples == summary.training_examples
    assert isinstance(artifact.platt_scale, float)
    assert isinstance(artifact.platt_bias, float)
    assert artifact.market_blend_weight == summary.market_blend_weight
    assert artifact.moneyline_price_min == DEFAULT_MONEYLINE_TRAIN_MIN_PRICE
    assert artifact.moneyline_price_max == DEFAULT_MONEYLINE_TRAIN_MAX_PRICE
    assert len(artifact.moneyline_band_models) >= 1
    assert isinstance(artifact.moneyline_segment_calibrations, tuple)
    assert latest_artifact.platt_scale == artifact.platt_scale
    assert latest_artifact.platt_bias == artifact.platt_bias
    assert latest_artifact.moneyline_price_min == artifact.moneyline_price_min
    assert latest_artifact.moneyline_price_max == artifact.moneyline_price_max
    assert latest_artifact.moneyline_band_models == artifact.moneyline_band_models
    assert latest_artifact.metrics.training_examples == summary.training_examples


def test_train_betting_model_supports_spread_artifact(tmp_path: Path) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)

    summary = train_betting_model(
        TrainingOptions(
            market="spread",
            seasons_back=2,
            max_season=2026,
            artifact_name="spread_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    artifact = load_artifact(
        market="spread",
        artifact_name="spread_test",
        artifacts_dir=artifacts_dir,
    )

    assert summary.market == "spread"
    assert summary.training_examples >= 8
    assert artifact.market == "spread"
    assert len(artifact.weights) == len(artifact.feature_names)
    assert artifact.spread_modeling_mode == "margin_regression"
    assert artifact.spread_residual_scale > 0.0
    assert artifact.moneyline_price_min is None
    assert artifact.moneyline_price_max is None
    assert artifact.moneyline_segment_calibrations == ()
    assert artifact.spread_timing_model is not None


def test_backtest_betting_model_reports_bankroll_metrics(tmp_path: Path) -> None:
    database_url, _ = _create_model_test_environment(tmp_path)

    summary = backtest_betting_model(
        BacktestOptions(
            market="moneyline",
            seasons_back=2,
            evaluation_season=2026,
            starting_bankroll=1000.0,
            unit_size=25.0,
            retrain_days=30,
            database_url=database_url,
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                min_probability_edge=-1.0,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=1000.0,
            ),
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=4,
            ),
        )
    )

    assert summary.market == "moneyline"
    assert summary.evaluation_season == 2026
    assert summary.blocks >= 1
    assert summary.candidates_considered >= 1
    assert summary.bets_placed >= 1
    assert summary.total_staked > 0
    assert summary.ending_bankroll > 0
    assert summary.clv.bets_evaluated == summary.bets_placed
    assert summary.clv.average_moneyline_probability_delta == 0.0


def test_upcoming_dataset_excludes_stale_odds_only_placeholder_games(
    tmp_path: Path,
) -> None:
    database_url, _ = _create_model_test_environment(tmp_path)
    database_path = Path(database_url.removeprefix("sqlite:///"))
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        ALTER TABLE games ADD COLUMN season_type_slug TEXT;
        ALTER TABLE games ADD COLUMN tournament_id TEXT;
        ALTER TABLE games ADD COLUMN event_note_headline TEXT;
        """
    )
    connection.executemany(
        """
        INSERT INTO games (
            game_id, season, date, commence_time, team1_id, team2_id,
            result, completed, home_score, away_score, source_event_id,
            season_type_slug, tournament_id, event_note_headline
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                11,
                2026,
                "2026-03-09",
                "2026-03-09T19:30:00+00:00",
                1,
                2,
                None,
                0,
                None,
                None,
                "official-elite-eight",
                "post-season",
                "22",
                "Elite 8",
            ),
            (
                12,
                2026,
                "2026-03-09",
                "2026-03-09T19:35:00+00:00",
                2,
                3,
                None,
                0,
                None,
                None,
                "placeholder-ghost",
                None,
                None,
                None,
            ),
            (
                13,
                2026,
                "2026-03-09",
                "2026-03-09T19:40:00+00:00",
                3,
                4,
                None,
                0,
                None,
                None,
                "fresh-odds-only",
                None,
                None,
                None,
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, bookmaker_key, bookmaker_title, market_key,
            captured_at, is_closing_line, team1_price, team2_price,
            team1_point, team2_point, total_points, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                9991,
                12,
                "draftkings",
                "DraftKings",
                "h2h",
                "2026-03-07T12:00:00+00:00",
                0,
                -120.0,
                100.0,
                None,
                None,
                None,
                "{}",
            ),
            (
                9992,
                13,
                "draftkings",
                "DraftKings",
                "h2h",
                "2026-03-09T17:30:00+00:00",
                0,
                -125.0,
                105.0,
                None,
                None,
                None,
                "{}",
            ),
        ],
    )
    connection.commit()
    connection.close()

    current_time = datetime(2026, 3, 9, 18, 0, tzinfo=UTC)

    upcoming_records = load_upcoming_game_records(
        database_url=database_url,
        now=current_time,
    )
    live_board_records = load_live_board_game_records(
        database_url=database_url,
        now=current_time,
    )

    assert {record.game_id for record in upcoming_records} >= {11, 13}
    assert {record.game_id for record in live_board_records} >= {11, 13}
    assert 12 not in {record.game_id for record in upcoming_records}
    assert 12 not in {record.game_id for record in live_board_records}


def test_summarize_closing_line_value_tracks_spread_execution_metrics() -> None:
    summary = _summarize_closing_line_value(
        [
            ClosingLineValueObservation(
                market="spread",
                reference_delta=1.0,
                spread_line_delta=1.0,
                spread_price_probability_delta=0.015,
                spread_no_vig_probability_delta=0.010,
                spread_closing_expected_value=0.065,
            ),
            ClosingLineValueObservation(
                market="moneyline",
                reference_delta=0.020,
                moneyline_probability_delta=0.020,
            ),
        ]
    )

    assert summary.bets_evaluated == 2
    assert summary.positive_bets == 2
    assert summary.average_spread_line_delta == pytest.approx(1.0)
    assert summary.average_spread_price_probability_delta == pytest.approx(0.015)
    assert summary.average_spread_no_vig_probability_delta == pytest.approx(0.010)
    assert summary.average_spread_closing_expected_value == pytest.approx(0.065)
    assert summary.average_moneyline_probability_delta == pytest.approx(0.020)


def test_spread_candidate_segment_values_assign_expected_buckets() -> None:
    candidate = CandidateBet(
        game_id=91,
        commence_time="2026-01-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=-110.0,
        line_value=-11.5,
        model_probability=0.57,
        implied_probability=0.50,
        probability_edge=0.07,
        expected_value=0.05,
        stake_fraction=0.01,
        settlement="win",
        minimum_games_played=3,
        market_book_count=4,
        team_conference_key="big-ten-conference",
        same_conference_game=True,
        observation_time="2026-01-10T14:00:00+00:00",
        neutral_site=True,
        travel_distance_miles=1205.0,
        timezone_crossings=2,
    )

    assert spread_candidate_segment_values(candidate) == {
        "expected_value_bucket": "ev_4_to_6",
        "probability_edge_bucket": "edge_6_to_8",
        "season_phase": "early",
        "line_bucket": "long_line",
        "book_depth": "low_depth",
        "neutral_site": "neutral_site",
        "travel_bucket": "long_trip",
        "timezone_crossings": "two_plus_timezones",
        "same_conference": "same_conference",
        "conference_group": "power",
        "tip_window": "0_to_6h",
    }


def test_summarize_spread_segment_attribution_tracks_roi_and_close_ev() -> None:
    early_bet = PlacedBet(
        game_id=101,
        commence_time="2026-01-12T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=100.0,
        line_value=-8.5,
        model_probability=0.55,
        implied_probability=0.50,
        probability_edge=0.05,
        expected_value=0.04,
        stake_fraction=0.02,
        stake_amount=20.0,
        settlement="loss",
        minimum_games_played=2,
        market_book_count=4,
        team_conference_key="big-ten-conference",
        same_conference_game=True,
    )
    established_bet = PlacedBet(
        game_id=102,
        commence_time="2026-02-12T20:00:00+00:00",
        market="spread",
        team_name="Gamma Gulls",
        opponent_name="Delta Dogs",
        side="away",
        market_price=100.0,
        line_value=3.5,
        model_probability=0.56,
        implied_probability=0.50,
        probability_edge=0.06,
        expected_value=0.06,
        stake_fraction=0.02,
        stake_amount=20.0,
        settlement="win",
        minimum_games_played=10,
        market_book_count=9,
        team_conference_key="atlantic-10-conference",
        same_conference_game=False,
    )

    attribution = _summarize_spread_segment_attribution(
        placed_bets=[early_bet, established_bet],
        clv_observations=[
            ClosingLineValueObservation(
                market="spread",
                reference_delta=-0.02,
                spread_closing_expected_value=-0.03,
                game_id=101,
                side="home",
            ),
            ClosingLineValueObservation(
                market="spread",
                reference_delta=0.02,
                spread_closing_expected_value=0.04,
                game_id=102,
                side="away",
            ),
        ],
    )

    expected_value_summary = next(
        summary
        for summary in attribution
        if summary.dimension == "expected_value_bucket"
    )
    probability_edge_summary = next(
        summary
        for summary in attribution
        if summary.dimension == "probability_edge_bucket"
    )
    season_phase_summary = next(
        summary for summary in attribution if summary.dimension == "season_phase"
    )
    assert [segment.value for segment in expected_value_summary.segments] == [
        "ev_4_to_6",
        "ev_6_to_8",
    ]
    assert [segment.value for segment in probability_edge_summary.segments] == [
        "edge_4_to_6",
        "edge_6_to_8",
    ]
    assert [segment.value for segment in season_phase_summary.segments] == [
        "early",
        "established",
    ]
    assert season_phase_summary.segments[0].roi == pytest.approx(-1.0)
    assert season_phase_summary.segments[
        0
    ].clv.average_spread_closing_expected_value == pytest.approx(-0.03)
    assert season_phase_summary.segments[1].roi == pytest.approx(1.0)
    assert season_phase_summary.segments[
        1
    ].clv.average_spread_closing_expected_value == pytest.approx(0.04)


def test_build_spread_closing_market_metrics_scores_close_quote(monkeypatch) -> None:
    artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("spread_line",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("spread_line",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    record = SimpleNamespace(
        game_id=42,
        spread_close=SimpleNamespace(
            team1_point=-3.5,
            team2_point=3.5,
            team1_price=-115.0,
            team2_price=-105.0,
            team1_implied_probability=0.54,
            team2_implied_probability=0.46,
        ),
        current_spread_quotes=(
            SimpleNamespace(team1_price=-110.0, team2_price=-110.0),
            SimpleNamespace(team1_price=-120.0, team2_price=100.0),
        ),
        home_spread_price=-115.0,
        away_spread_price=-105.0,
    )
    example = ModelExample(
        game_id=42,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={
            "spread_line": -3.0,
            "spread_abs_line": 3.0,
            "spread_total_interaction": -4.5,
            "total_close_points": 150.0,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=-3.0,
    )

    monkeypatch.setattr(
        "cbb.modeling.backtest.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest.score_spread_probability_at_line",
        lambda **_: 0.57,
    )

    metrics = _build_spread_closing_market_metrics(
        training_records=[],
        completed_records=[record],
        artifact=artifact,
    )

    assert set(metrics) == {(42, "home")}
    closing_metrics = metrics[(42, "home")]
    assert closing_metrics.closing_line == -3.5
    assert closing_metrics.closing_price_probability == pytest.approx(
        0.5346,
        abs=1e-4,
    )
    assert closing_metrics.closing_no_vig_probability == 0.54
    assert closing_metrics.closing_expected_value == pytest.approx(
        0.0657,
        abs=1e-4,
    )


def test_predict_best_bets_uses_trained_artifact(tmp_path: Path) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)
    train_betting_model(
        TrainingOptions(
            market="moneyline",
            seasons_back=2,
            max_season=2026,
            artifact_name="predict_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="best",
            artifact_name="predict_test",
            bankroll=1000.0,
            limit=5,
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            now=datetime(2026, 3, 9, 18, 45, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                min_probability_edge=-1.0,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=1000.0,
            ),
        )
    )

    assert summary.market == "best"
    assert summary.available_games == 2
    assert summary.availability_summary.games_with_context == 0
    assert summary.availability_summary.latest_report_update_at is None
    assert summary.availability_summary.closest_report_minutes_before_tip is None
    assert summary.candidates_considered >= 1
    assert summary.bets_placed >= 1
    assert summary.recommendations[0].market in {"moneyline", "spread"}
    assert summary.recommendations[0].stake_amount > 0


def test_predict_best_bets_uses_best_executable_quote(monkeypatch) -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=9,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={"feature": 1.0},
        label=None,
        settlement="pending",
        market_price=-115.0,
        market_implied_probability=0.51,
        minimum_games_played=10,
        line_value=-115.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=-115.0,
                market_implied_probability=0.51,
                line_value=-115.0,
            ),
            ExecutableQuote(
                bookmaker_key="fanduel",
                market_price=100.0,
                market_implied_probability=0.50,
                line_value=100.0,
            ),
        ),
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [
            SimpleNamespace(
                game_id=9,
                commence_time=datetime(2026, 3, 10, 20, 0, tzinfo=UTC),
                home_team_name="Alpha Aces",
                away_team_name="Beta Bruins",
            )
        ],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.load_completed_game_records",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer._load_prediction_artifacts",
        lambda **_: [("moneyline", artifact)],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_examples",
        lambda **_: [0.55],
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="moneyline",
            bankroll=1000.0,
            limit=5,
            now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                min_probability_edge=-1.0,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=125.0,
            ),
        )
    )

    assert summary.candidates_considered == 1
    assert summary.bets_placed == 1
    assert summary.recommendations[0].market_price == 100.0


def test_predict_best_bets_keeps_in_policy_quote_when_better_quote_is_capped(
    monkeypatch,
) -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=10,
        season=2026,
        commence_time="2026-03-10T21:00:00+00:00",
        market="moneyline",
        team_name="Gamma Gulls",
        opponent_name="Delta Dogs",
        side="away",
        features={"feature": 1.0},
        label=None,
        settlement="pending",
        market_price=115.0,
        market_implied_probability=0.46,
        minimum_games_played=10,
        line_value=115.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=130.0,
                market_implied_probability=0.43,
                line_value=130.0,
            ),
            ExecutableQuote(
                bookmaker_key="fanduel",
                market_price=120.0,
                market_implied_probability=0.45,
                line_value=120.0,
            ),
        ),
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [
            SimpleNamespace(
                game_id=10,
                commence_time=datetime(2026, 3, 10, 21, 0, tzinfo=UTC),
                home_team_name="Gamma Gulls",
                away_team_name="Delta Dogs",
            )
        ],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.load_completed_game_records",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer._load_prediction_artifacts",
        lambda **_: [("moneyline", artifact)],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_examples",
        lambda **_: [0.55],
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="moneyline",
            bankroll=1000.0,
            limit=5,
            now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                min_probability_edge=-1.0,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=125.0,
            ),
        )
    )

    assert summary.candidates_considered == 1
    assert summary.bets_placed == 1
    assert summary.recommendations[0].market_price == 120.0


def test_predict_best_bets_tracks_upcoming_games_with_pass_metrics(
    monkeypatch,
) -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=11,
        season=2026,
        commence_time="2026-03-10T22:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=100.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=100.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=100.0,
                market_implied_probability=0.50,
                line_value=100.0,
            ),
        ),
    )
    upcoming_record = SimpleNamespace(
        game_id=11,
        commence_time=datetime(2026, 3, 10, 22, 0, tzinfo=UTC),
        home_team_name="Alpha Aces",
        away_team_name="Beta Bruins",
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [upcoming_record],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.load_completed_game_records",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer._load_prediction_artifacts",
        lambda **_: [("moneyline", artifact)],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_examples",
        lambda **_: [0.52],
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="moneyline",
            bankroll=1000.0,
            limit=5,
            now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=0.02,
                min_confidence=0.0,
                min_probability_edge=0.025,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=125.0,
            ),
        )
    )

    assert summary.recommendations == []
    assert len(summary.upcoming_games) == 1
    assert summary.upcoming_games[0].status == "pass"
    assert summary.upcoming_games[0].market == "moneyline"
    assert summary.upcoming_games[0].probability_edge == pytest.approx(0.02)
    assert summary.upcoming_games[0].note == "probability_edge"
    assert len(summary.live_board_games) == 1
    assert summary.live_board_games[0].board_status == "pass"
    assert summary.live_board_games[0].game_status == "upcoming"


def test_predict_best_bets_attaches_availability_context_to_board_rows(
    monkeypatch,
) -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=11,
        season=2026,
        commence_time="2026-03-10T22:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=100.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=100.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=100.0,
                market_implied_probability=0.50,
                line_value=100.0,
            ),
        ),
    )
    upcoming_record = SimpleNamespace(
        game_id=11,
        commence_time=datetime(2026, 3, 10, 22, 0, tzinfo=UTC),
        home_team_name="Alpha Aces",
        away_team_name="Beta Bruins",
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [upcoming_record],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.load_completed_game_records",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_availability_game_side_shadows",
        lambda _database_url=None: (
            AvailabilityGameSideShadow(
                game_id=11,
                season=2026,
                commence_time="2026-03-10T22:00:00+00:00",
                side="home",
                team_id=1,
                team_name="Alpha Aces",
                opponent_team_id=2,
                opponent_name="Beta Bruins",
                source_name="ncaa",
                has_official_report=True,
                opponent_has_official_report=True,
                team_any_out=True,
                team_any_questionable=False,
                opponent_any_out=True,
                opponent_any_questionable=True,
                team_out_count=1,
                team_questionable_count=0,
                opponent_out_count=1,
                opponent_questionable_count=1,
                matched_row_count=2,
                unmatched_row_count=0,
                latest_update_at="2026-03-10T20:30:00+00:00",
                latest_minutes_before_tip=90.0,
            ),
            AvailabilityGameSideShadow(
                game_id=11,
                season=2026,
                commence_time="2026-03-10T22:00:00+00:00",
                side="away",
                team_id=2,
                team_name="Beta Bruins",
                opponent_team_id=1,
                opponent_name="Alpha Aces",
                source_name="ncaa",
                has_official_report=True,
                opponent_has_official_report=True,
                team_any_out=True,
                team_any_questionable=True,
                opponent_any_out=True,
                opponent_any_questionable=False,
                team_out_count=1,
                team_questionable_count=1,
                opponent_out_count=1,
                opponent_questionable_count=0,
                matched_row_count=3,
                unmatched_row_count=1,
                latest_update_at="2026-03-10T20:15:00+00:00",
                latest_minutes_before_tip=105.0,
            ),
        ),
    )
    monkeypatch.setattr(
        "cbb.modeling.infer._load_prediction_artifacts",
        lambda **_: [("moneyline", artifact)],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_examples",
        lambda **_: [0.52],
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="moneyline",
            bankroll=1000.0,
            limit=5,
            now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=0.02,
                min_confidence=0.0,
                min_probability_edge=0.025,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=125.0,
            ),
        )
    )

    upcoming_context = summary.upcoming_games[0].availability_context
    assert upcoming_context is not None
    assert upcoming_context.coverage_status == "both"
    assert upcoming_context.team.source_name == "ncaa"
    assert upcoming_context.team.out_count == 1
    assert upcoming_context.opponent.questionable_count == 1

    live_board_context = summary.live_board_games[0].availability_context
    assert live_board_context is not None
    assert live_board_context.team.latest_minutes_before_tip == pytest.approx(90.0)
    assert live_board_context.opponent.unmatched_row_count == 1
    assert summary.availability_summary.games_with_context == 1
    assert summary.availability_summary.games_with_both_reports == 1
    assert summary.availability_summary.games_with_team_only == 0
    assert summary.availability_summary.games_with_opponent_only == 0
    assert summary.availability_summary.games_with_unmatched_rows == 1
    assert summary.availability_summary.team_sides_with_unmatched_rows == 0
    assert summary.availability_summary.opponent_sides_with_unmatched_rows == 1
    assert summary.availability_summary.games_with_any_out == 1
    assert summary.availability_summary.games_with_any_questionable == 1
    assert summary.availability_summary.source_names == ("ncaa",)
    assert (
        summary.availability_summary.latest_report_update_at
        == "2026-03-10T20:30:00+00:00"
    )
    assert summary.availability_summary.closest_report_minutes_before_tip == (
        pytest.approx(90.0)
    )


def test_predict_best_bets_tracks_cross_book_survivability_in_pass_note(
    monkeypatch,
) -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=14,
        season=2026,
        commence_time="2026-03-10T23:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=100.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=100.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=100.0,
                market_implied_probability=0.50,
                line_value=100.0,
            ),
            ExecutableQuote(
                bookmaker_key="fanduel",
                market_price=-130.0,
                market_implied_probability=0.565,
                line_value=-130.0,
            ),
        ),
    )
    upcoming_record = SimpleNamespace(
        game_id=14,
        commence_time=datetime(2026, 3, 10, 23, 0, tzinfo=UTC),
        home_team_name="Alpha Aces",
        away_team_name="Beta Bruins",
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [upcoming_record],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.load_completed_game_records",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer._load_prediction_artifacts",
        lambda **_: [("moneyline", artifact)],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_examples",
        lambda **_: [0.55],
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="moneyline",
            bankroll=1000.0,
            limit=5,
            now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=0.02,
                min_confidence=0.0,
                min_probability_edge=0.0,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=125.0,
                min_positive_ev_books=2,
            ),
        )
    )

    assert summary.recommendations == []
    assert len(summary.upcoming_games) == 1
    assert summary.upcoming_games[0].status == "pass"
    assert summary.upcoming_games[0].expected_value == pytest.approx(0.1)
    assert summary.upcoming_games[0].note == "positive_ev_books=1/2"


def test_predict_best_bets_tracks_median_ev_survivability_in_pass_note(
    monkeypatch,
) -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=17,
        season=2026,
        commence_time="2026-03-10T23:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=100.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=100.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=100.0,
                market_implied_probability=0.50,
                line_value=100.0,
            ),
            ExecutableQuote(
                bookmaker_key="fanduel",
                market_price=-130.0,
                market_implied_probability=0.565,
                line_value=-130.0,
            ),
        ),
    )
    upcoming_record = SimpleNamespace(
        game_id=17,
        commence_time=datetime(2026, 3, 10, 23, 0, tzinfo=UTC),
        home_team_name="Alpha Aces",
        away_team_name="Beta Bruins",
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [upcoming_record],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.load_completed_game_records",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer._load_prediction_artifacts",
        lambda **_: [("moneyline", artifact)],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_examples",
        lambda **_: [0.52],
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="moneyline",
            bankroll=1000.0,
            limit=5,
            now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                min_probability_edge=-1.0,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
                min_moneyline_price=-1000.0,
                max_moneyline_price=125.0,
                min_positive_ev_books=1,
                min_median_expected_value=0.0,
            ),
        )
    )

    assert summary.recommendations == []
    assert len(summary.upcoming_games) == 1
    assert summary.upcoming_games[0].status == "pass"
    assert summary.upcoming_games[0].note == "median_expected_value=-0.020/0.000"


def test_predict_best_bets_without_upcoming_games_uses_deployable_spread_policy(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [],
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="best",
            now=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        )
    )

    assert summary.available_games == 0
    assert summary.applied_policy == deployable_spread_policy(BetPolicy())


def test_deployable_spread_policy_uses_fixed_positive_baseline() -> None:
    policy = deployable_spread_policy(BetPolicy())

    assert policy.min_edge == 0.04
    assert policy.min_confidence == 0.518
    assert policy.min_probability_edge == 0.04
    assert policy.min_games_played == 8
    assert policy.max_spread_abs_line == 10.0
    assert policy.max_abs_rest_days_diff == 3.0
    assert policy.min_positive_ev_books == 4
    assert policy.max_bets_per_day == 5


def test_apply_bankroll_limits_can_cap_bets_per_day() -> None:
    candidates = [
        CandidateBet(
            game_id=100 + offset,
            commence_time="2026-02-14T19:00:00+00:00",
            market="spread",
            team_name=f"Team {offset}",
            opponent_name=f"Opponent {offset}",
            side="home",
            sportsbook="draftkings",
            market_price=-110.0,
            line_value=-3.5,
            model_probability=0.55,
            implied_probability=0.50,
            probability_edge=0.05,
            expected_value=0.08 - (offset * 0.01),
            stake_fraction=0.01,
            settlement="win",
            minimum_games_played=8,
        )
        for offset in range(4)
    ]

    placed_bets = apply_bankroll_limits(
        bankroll=1000.0,
        policy=BetPolicy(max_bets_per_day=2),
        candidate_bets=candidates,
    )

    assert [bet.game_id for bet in placed_bets] == [100, 101]


def test_apply_bankroll_limits_with_diagnostics_tracks_capped_stakes() -> None:
    candidates = [
        CandidateBet(
            game_id=100 + offset,
            commence_time="2026-02-14T19:00:00+00:00",
            market="spread",
            team_name=f"Team {offset}",
            opponent_name=f"Opponent {offset}",
            side="home",
            sportsbook="draftkings",
            market_price=-110.0,
            line_value=-3.5,
            model_probability=0.55,
            implied_probability=0.50,
            probability_edge=0.05,
            expected_value=0.08 - (offset * 0.01),
            stake_fraction=0.03,
            settlement="win",
            minimum_games_played=8,
            positive_ev_books=4,
            coverage_rate=1.0,
            median_expected_value=0.02,
        )
        for offset in range(2)
    ]

    result = apply_bankroll_limits_with_diagnostics(
        bankroll=1000.0,
        policy=BetPolicy(
            max_daily_exposure_fraction=0.05,
            max_bets_per_day=5,
        ),
        candidate_bets=candidates,
    )

    assert [bet.stake_amount for bet in result.placed_bets] == [30.0, 20.0]
    assert [bet.requested_stake_amount for bet in result.placed_bets] == [30.0, 30.0]
    assert result.placed_bets[0].stake_was_capped is False
    assert result.placed_bets[1].stake_was_capped is True
    assert result.diagnostics.active_days == 1
    assert result.diagnostics.bets_requested == 2
    assert result.diagnostics.bets_placed == 2
    assert result.diagnostics.requested_stake_total == pytest.approx(60.0)
    assert result.diagnostics.placed_stake_total == pytest.approx(50.0)
    assert result.diagnostics.clipped_bets == 1
    assert result.diagnostics.days_hitting_exposure_cap == 1


def test_candidate_matches_selection_policy_respects_survivability_fields() -> None:
    candidate = CandidateBet(
        game_id=10,
        commence_time="2026-02-14T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        sportsbook="draftkings",
        market_price=-110.0,
        line_value=-3.5,
        model_probability=0.55,
        implied_probability=0.50,
        probability_edge=0.05,
        expected_value=0.08,
        stake_fraction=0.01,
        settlement="win",
        minimum_games_played=8,
        eligible_books=4,
        positive_ev_books=3,
        coverage_rate=0.75,
        median_expected_value=0.009,
    )
    policy = BetPolicy(
        min_edge=0.0,
        min_confidence=0.0,
        min_probability_edge=0.0,
        min_games_played=0,
        min_positive_ev_books=4,
        min_median_expected_value=0.01,
    )

    assert candidate_matches_policy(candidate=candidate, policy=policy) is True
    assert (
        candidate_matches_selection_policy(candidate=candidate, policy=policy)
        is False
    )


def test_evaluate_policy_on_candidate_blocks_uses_selection_support_filters() -> None:
    approved_candidate = CandidateBet(
        game_id=10,
        commence_time="2026-02-14T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        sportsbook="draftkings",
        market_price=-110.0,
        line_value=-3.5,
        model_probability=0.55,
        implied_probability=0.50,
        probability_edge=0.05,
        expected_value=0.08,
        stake_fraction=0.01,
        settlement="win",
        minimum_games_played=8,
        eligible_books=5,
        positive_ev_books=4,
        coverage_rate=0.8,
        median_expected_value=0.012,
    )
    filtered_candidate = CandidateBet(
        game_id=11,
        commence_time="2026-02-14T21:00:00+00:00",
        market="spread",
        team_name="Gamma Gulls",
        opponent_name="Delta Ducks",
        side="home",
        sportsbook="fanduel",
        market_price=-110.0,
        line_value=-2.5,
        model_probability=0.56,
        implied_probability=0.50,
        probability_edge=0.06,
        expected_value=0.09,
        stake_fraction=0.01,
        settlement="win",
        minimum_games_played=8,
        eligible_books=4,
        positive_ev_books=3,
        coverage_rate=0.75,
        median_expected_value=0.008,
    )

    evaluation = _evaluate_policy_on_candidate_blocks(
        candidate_blocks=[
            CandidateBlock(
                commence_time="2026-02-14T19:00:00+00:00",
                candidates=(approved_candidate, filtered_candidate),
            )
        ],
        policy=BetPolicy(
            min_edge=0.0,
            min_confidence=0.0,
            min_probability_edge=0.0,
            min_games_played=0,
            max_daily_exposure_fraction=1.0,
            min_positive_ev_books=4,
            min_median_expected_value=0.01,
        ),
        starting_bankroll=1000.0,
        activity_constraints=SpreadTuningActivityConstraints(
            min_active_blocks=1,
            min_bets=1,
            min_total_staked=1.0,
        ),
    )

    assert evaluation.bets_placed == 1
    assert evaluation.total_staked == pytest.approx(10.0)


def test_apply_bankroll_limits_with_diagnostics_reports_cap_hits() -> None:
    candidates = [
        CandidateBet(
            game_id=300 + offset,
            commence_time="2026-02-14T19:00:00+00:00",
            market="spread",
            team_name=f"Team {offset}",
            opponent_name=f"Opponent {offset}",
            side="home",
            sportsbook="draftkings",
            market_price=-110.0,
            line_value=-3.5,
            model_probability=0.55,
            implied_probability=0.50,
            probability_edge=0.05,
            expected_value=0.08 - (offset * 0.005),
            stake_fraction=0.03,
            settlement="win",
            minimum_games_played=8,
            positive_ev_books=4 - offset,
            coverage_rate=0.80 - (offset * 0.10),
        )
        for offset in range(3)
    ]

    result = apply_bankroll_limits_with_diagnostics(
        bankroll=1000.0,
        policy=BetPolicy(max_bets_per_day=2, max_daily_exposure_fraction=0.05),
        candidate_bets=candidates,
    )

    assert [bet.game_id for bet in result.placed_bets] == [300, 301]
    assert result.diagnostics.days_evaluated == 1
    assert result.diagnostics.active_days == 1
    assert result.diagnostics.bets_requested == 3
    assert result.diagnostics.bets_placed == 2
    assert result.diagnostics.skipped_by_bet_cap == 1
    assert result.diagnostics.days_hitting_bet_cap == 1
    assert result.diagnostics.days_hitting_exposure_cap == 1
    assert result.diagnostics.clipped_bets == 1
    assert [bet.game_id for bet in result.placed_bets_on_capped_days] == [300, 301]
    assert [
        candidate.game_id for candidate in result.skipped_by_bet_cap_candidates
    ] == [302]
    assert result.placed_bets[1].stake_was_capped is True
    assert result.placed_bets[1].requested_stake_amount == pytest.approx(30.0)
    assert result.placed_bets[1].stake_amount == pytest.approx(20.0)


def test_apply_bankroll_limits_with_diagnostics_can_use_support_aware_day_sort(
) -> None:
    candidates = [
        CandidateBet(
            game_id=400,
            commence_time="2026-02-14T19:00:00+00:00",
            market="spread",
            team_name="Low Support High EV",
            opponent_name="Opponent A",
            side="home",
            sportsbook="draftkings",
            market_price=-110.0,
            line_value=-3.5,
            model_probability=0.57,
            implied_probability=0.50,
            probability_edge=0.07,
            expected_value=0.09,
            stake_fraction=0.02,
            settlement="win",
            minimum_games_played=8,
            positive_ev_books=4,
            coverage_rate=0.80,
        ),
        CandidateBet(
            game_id=401,
            commence_time="2026-02-14T20:00:00+00:00",
            market="spread",
            team_name="High Support Lower EV",
            opponent_name="Opponent B",
            side="home",
            sportsbook="fanduel",
            market_price=-110.0,
            line_value=-2.5,
            model_probability=0.55,
            implied_probability=0.50,
            probability_edge=0.05,
            expected_value=0.08,
            stake_fraction=0.02,
            settlement="win",
            minimum_games_played=8,
            positive_ev_books=7,
            coverage_rate=0.95,
        ),
    ]

    incumbent = apply_bankroll_limits_with_diagnostics(
        bankroll=1000.0,
        policy=BetPolicy(max_bets_per_day=1, max_daily_exposure_fraction=0.10),
        candidate_bets=candidates,
    )
    challenger = apply_bankroll_limits_with_diagnostics(
        bankroll=1000.0,
        policy=BetPolicy(max_bets_per_day=1, max_daily_exposure_fraction=0.10),
        candidate_bets=candidates,
        daily_cap_sort_order="support_aware",
    )

    assert [bet.game_id for bet in incumbent.placed_bets] == [400]
    assert [bet.game_id for bet in challenger.placed_bets] == [401]
    assert [
        candidate.game_id for candidate in challenger.skipped_by_bet_cap_candidates
    ] == [400]


def test_predict_best_bets_auto_tunes_spread_policy(
    tmp_path: Path, monkeypatch
) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)
    train_betting_model(
        TrainingOptions(
            market="spread",
            seasons_back=2,
            max_season=2026,
            artifact_name="spread_predict_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    tuned_policy = BetPolicy(
        min_edge=-1.0,
        min_confidence=0.0,
        min_probability_edge=-1.0,
        min_games_played=0,
        kelly_fraction=0.25,
        max_bet_fraction=0.05,
        max_daily_exposure_fraction=0.20,
        max_spread_abs_line=10.0,
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.derive_latest_spread_policy_from_records",
        lambda **_: PolicyEvaluation(
            policy=tuned_policy,
            blocks_evaluated=4,
            blocks_with_bets=3,
            profitable_blocks=2,
            bets_placed=5,
            total_staked=50.0,
            profit=5.0,
            roi=0.10,
            active_block_rate=0.75,
            profitable_block_rate=0.5,
            worst_block_roi=-0.05,
            block_roi_stddev=0.04,
            stability_score=0.05,
            max_drawdown=0.02,
            meets_activity_constraints=True,
            activity_score=1.0,
        ),
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="spread",
            artifact_name="spread_predict_test",
            bankroll=1000.0,
            limit=5,
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            now=datetime(2026, 3, 9, 18, 45, tzinfo=UTC),
            auto_tune_spread_policy=True,
            policy=BetPolicy(
                min_edge=-1.0,
                min_confidence=0.0,
                min_probability_edge=-1.0,
                min_games_played=0,
                kelly_fraction=0.25,
                max_bet_fraction=0.05,
                max_daily_exposure_fraction=0.20,
            ),
        )
    )

    assert summary.market == "spread"
    assert summary.policy_was_auto_tuned is True
    assert summary.policy_tuned_blocks == 4
    assert summary.applied_policy == tuned_policy


def test_predict_best_bets_skips_inactive_auto_tuned_spread_policy(
    tmp_path: Path, monkeypatch
) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)
    train_betting_model(
        TrainingOptions(
            market="spread",
            seasons_back=2,
            max_season=2026,
            artifact_name="spread_predict_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    base_policy = BetPolicy(
        min_edge=-1.0,
        min_confidence=0.0,
        min_probability_edge=-1.0,
        min_games_played=0,
        kelly_fraction=0.25,
        max_bet_fraction=0.05,
        max_daily_exposure_fraction=0.20,
    )
    tuned_policy = BetPolicy(
        min_edge=-1.0,
        min_confidence=0.0,
        min_probability_edge=-1.0,
        min_games_played=0,
        kelly_fraction=0.25,
        max_bet_fraction=0.05,
        max_daily_exposure_fraction=0.20,
        max_spread_abs_line=10.0,
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.derive_latest_spread_policy_from_records",
        lambda **_: PolicyEvaluation(
            policy=tuned_policy,
            blocks_evaluated=4,
            blocks_with_bets=1,
            profitable_blocks=1,
            bets_placed=1,
            total_staked=10.0,
            profit=2.0,
            roi=0.20,
            active_block_rate=0.25,
            profitable_block_rate=1.0,
            worst_block_roi=0.20,
            block_roi_stddev=0.0,
            stability_score=0.18,
            max_drawdown=0.0,
            meets_activity_constraints=False,
            activity_score=0.33,
        ),
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="spread",
            artifact_name="spread_predict_test",
            bankroll=1000.0,
            limit=5,
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            now=datetime(2026, 3, 9, 18, 45, tzinfo=UTC),
            auto_tune_spread_policy=True,
            policy=base_policy,
        )
    )

    assert summary.market == "spread"
    assert summary.policy_was_auto_tuned is False
    assert summary.policy_tuned_blocks == 0
    assert summary.applied_policy == base_policy


def test_predict_best_bets_skips_low_quality_auto_tuned_spread_policy(
    tmp_path: Path, monkeypatch
) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)
    train_betting_model(
        TrainingOptions(
            market="spread",
            seasons_back=2,
            max_season=2026,
            artifact_name="spread_predict_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            config=LogisticRegressionConfig(
                epochs=250,
                min_examples=8,
            ),
        )
    )

    base_policy = BetPolicy(
        min_edge=-1.0,
        min_confidence=0.0,
        min_probability_edge=-1.0,
        min_games_played=0,
        kelly_fraction=0.25,
        max_bet_fraction=0.05,
        max_daily_exposure_fraction=0.20,
    )
    tuned_policy = BetPolicy(
        min_edge=-1.0,
        min_confidence=0.0,
        min_probability_edge=-1.0,
        min_games_played=0,
        kelly_fraction=0.25,
        max_bet_fraction=0.05,
        max_daily_exposure_fraction=0.20,
        max_spread_abs_line=10.0,
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.derive_latest_spread_policy_from_records",
        lambda **_: PolicyEvaluation(
            policy=tuned_policy,
            blocks_evaluated=4,
            blocks_with_bets=4,
            profitable_blocks=4,
            bets_placed=8,
            total_staked=80.0,
            profit=12.0,
            roi=0.15,
            active_block_rate=1.0,
            profitable_block_rate=1.0,
            worst_block_roi=0.05,
            block_roi_stddev=0.01,
            stability_score=0.20,
            max_drawdown=0.0,
            meets_activity_constraints=True,
            meets_close_quality_constraints=False,
            activity_score=1.0,
        ),
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="spread",
            artifact_name="spread_predict_test",
            bankroll=1000.0,
            limit=5,
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            now=datetime(2026, 3, 9, 18, 45, tzinfo=UTC),
            auto_tune_spread_policy=True,
            policy=base_policy,
        )
    )

    assert summary.market == "spread"
    assert summary.policy_was_auto_tuned is False
    assert summary.policy_tuned_blocks == 0
    assert summary.applied_policy == base_policy


def test_predict_best_bets_defers_spread_candidates_with_timing_layer(
    monkeypatch,
) -> None:
    timing_model = SpreadTimingModel(
        feature_names=SPREAD_TIMING_FEATURE_NAMES,
        means=tuple(0.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        scales=tuple(1.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        weights=tuple(0.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        bias=0.0,
        min_favorable_probability=0.5,
        min_hours_to_tip=6.0,
    )
    artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
        spread_timing_model=timing_model,
    )
    example = ModelExample(
        game_id=9,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={"feature": 1.0},
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=-1.5,
        observation_time="2026-03-09T12:00:00+00:00",
    )
    candidate = CandidateBet(
        game_id=9,
        commence_time="2026-03-10T20:00:00+00:00",
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
        minimum_games_played=10,
    )

    monkeypatch.setattr(
        "cbb.modeling.infer.load_live_board_game_records",
        lambda **_: [
            SimpleNamespace(
                game_id=9,
                commence_time=datetime(2026, 3, 10, 20, 0, tzinfo=UTC),
                home_team_name="Alpha Aces",
                away_team_name="Beta Bruins",
            )
        ],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.load_completed_game_records",
        lambda **_: [],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer._load_prediction_artifacts",
        lambda **_: [("spread", artifact)],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_prediction_examples",
        lambda **_: [example],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_examples",
        lambda **_: [0.59],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.build_executable_candidate_bets",
        lambda **_: [candidate],
    )
    monkeypatch.setattr(
        "cbb.modeling.infer.score_spread_timing_probability",
        lambda **_: 0.22,
    )

    summary = predict_best_bets(
        PredictionOptions(
            market="spread",
            bankroll=1000.0,
            limit=5,
            now=datetime(2026, 3, 9, 12, 0, tzinfo=UTC),
            use_timing_layer=True,
        )
    )

    assert summary.candidates_considered == 1
    assert summary.bets_placed == 0
    assert summary.recommendations == []
    assert len(summary.deferred_recommendations) == 1
    assert summary.deferred_recommendations[0].candidate == candidate
    assert summary.deferred_recommendations[0].favorable_close_probability == 0.22


def test_select_spread_timing_model_prefers_profile_specific_model() -> None:
    global_timing_model = SpreadTimingModel(
        feature_names=SPREAD_TIMING_FEATURE_NAMES,
        means=tuple(0.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        scales=tuple(1.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        weights=tuple(0.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        bias=0.0,
        profile_key="global",
    )
    low_profile_timing_model = SpreadTimingModel(
        feature_names=SPREAD_TIMING_FEATURE_NAMES,
        means=tuple(0.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        scales=tuple(1.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        weights=tuple(0.0 for _ in SPREAD_TIMING_FEATURE_NAMES),
        bias=0.0,
        profile_key="low_profile",
    )
    artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
        spread_timing_model=global_timing_model,
        spread_timing_models=(low_profile_timing_model,),
    )
    example = ModelExample(
        game_id=9,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={
            "spread_books": 4.0,
            "h2h_books": 4.0,
            "total_books": 4.0,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=-1.5,
        observation_time="2026-03-09T12:00:00+00:00",
    )

    selected_model = select_spread_timing_model(
        artifact=artifact,
        example=example,
    )

    assert selected_model == low_profile_timing_model


def test_load_prediction_artifacts_for_best_prefers_spread_only(
    tmp_path: Path,
) -> None:
    artifacts_dir = tmp_path / "artifacts"
    metrics = TrainingMetrics(
        examples=10,
        priced_examples=10,
        training_examples=10,
        feature_names=("feature",),
        log_loss=0.5,
        brier_score=0.2,
        accuracy=0.6,
        start_season=2024,
        end_season=2026,
        trained_at="2026-03-08T12:00:00Z",
    )
    save_artifact(
        ModelArtifact(
            market="spread",
            model_family="logistic",
            feature_names=("feature",),
            means=(0.0,),
            scales=(1.0,),
            weights=(0.1,),
            bias=0.0,
            metrics=metrics,
        ),
        artifact_name="unit_test",
        artifacts_dir=artifacts_dir,
    )
    save_artifact(
        ModelArtifact(
            market="moneyline",
            model_family="logistic",
            feature_names=("feature",),
            means=(0.0,),
            scales=(1.0,),
            weights=(0.2,),
            bias=0.0,
            metrics=metrics,
        ),
        artifact_name="unit_test",
        artifacts_dir=artifacts_dir,
    )

    loaded_artifacts = _load_prediction_artifacts(
        market="best",
        artifact_name="unit_test",
        artifacts_dir=artifacts_dir,
    )

    assert [market for market, _artifact in loaded_artifacts] == ["spread"]


def test_normalized_implied_probability_removes_vig() -> None:
    assert (
        normalized_implied_probability_from_prices(
            side_american_price=-110.0,
            opponent_american_price=-110.0,
        )
        == 0.5
    )


def test_score_candidate_bet_rejects_extreme_moneyline_and_low_history() -> None:
    example = ModelExample(
        game_id=99,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="away",
        features={},
        label=None,
        settlement="pending",
        market_price=450.0,
        market_implied_probability=0.20,
        minimum_games_played=3,
        line_value=450.0,
    )

    candidate = score_candidate_bet(
        example=example,
        probability=0.28,
        policy=BetPolicy(),
    )

    assert candidate is None


def test_score_candidate_bet_rejects_spread_above_max_abs_line() -> None:
    example = ModelExample(
        game_id=100,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={
            "elo_diff": -120.0,
            "spread_books": 10.0,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=15.5,
    )

    candidate = score_candidate_bet(
        example=example,
        probability=0.56,
        policy=BetPolicy(max_spread_abs_line=10.0),
    )

    assert candidate is None


def test_score_candidate_bet_rejects_spread_above_max_abs_rest_days_diff() -> None:
    example = ModelExample(
        game_id=101,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={
            "rest_days_diff": 4.5,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=4.5,
    )

    candidate = score_candidate_bet(
        example=example,
        probability=0.56,
        policy=BetPolicy(max_abs_rest_days_diff=3.0),
    )

    assert candidate is None


def test_fit_platt_scaling_improves_miscalibrated_probabilities() -> None:
    raw_probabilities = [0.92, 0.88, 0.84, 0.80, 0.76, 0.72, 0.68, 0.64]
    labels = [1, 1, 0, 0, 0, 0, 0, 0]

    baseline_log_loss = _test_log_loss(raw_probabilities, labels)
    platt_scale, platt_bias = fit_platt_scaling(
        raw_probabilities=raw_probabilities,
        labels=labels,
    )
    calibrated_probabilities = apply_platt_scaling(
        raw_probabilities=raw_probabilities,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
    )

    assert _test_log_loss(calibrated_probabilities, labels) < baseline_log_loss


def test_select_best_candidates_prefers_spread_over_moneyline() -> None:
    moneyline_candidate = CandidateBet(
        game_id=7,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=180.0,
        line_value=180.0,
        model_probability=0.42,
        implied_probability=0.35,
        probability_edge=0.07,
        expected_value=0.18,
        stake_fraction=0.02,
        settlement="win",
    )
    spread_candidate = CandidateBet(
        game_id=7,
        commence_time="2026-03-09T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=-110.0,
        line_value=4.5,
        model_probability=0.54,
        implied_probability=0.50,
        probability_edge=0.04,
        expected_value=0.03,
        stake_fraction=0.02,
        settlement="win",
    )

    selected_candidates = select_best_candidates(
        [moneyline_candidate, spread_candidate]
    )

    assert selected_candidates == [spread_candidate]


def test_select_best_candidates_keeps_moneyline_for_games_without_spread() -> None:
    moneyline_candidate = CandidateBet(
        game_id=7,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=180.0,
        line_value=180.0,
        model_probability=0.42,
        implied_probability=0.35,
        probability_edge=0.07,
        expected_value=0.18,
        stake_fraction=0.02,
        settlement="win",
    )
    spread_candidate = CandidateBet(
        game_id=9,
        commence_time="2026-03-10T19:00:00+00:00",
        market="spread",
        team_name="Gamma Gulls",
        opponent_name="Delta Dogs",
        side="away",
        market_price=-110.0,
        line_value=4.5,
        model_probability=0.54,
        implied_probability=0.50,
        probability_edge=0.04,
        expected_value=0.03,
        stake_fraction=0.02,
        settlement="win",
    )

    selected_candidates = select_best_candidates(
        [moneyline_candidate, spread_candidate]
    )

    assert selected_candidates == [moneyline_candidate, spread_candidate]


def test_select_best_quote_candidates_prefers_highest_ev_for_same_side() -> None:
    shorter_price_candidate = CandidateBet(
        game_id=12,
        commence_time="2026-03-10T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=100.0,
        line_value=100.0,
        model_probability=0.55,
        implied_probability=0.50,
        probability_edge=0.05,
        expected_value=0.10,
        stake_fraction=0.02,
        settlement="win",
    )
    better_price_candidate = CandidateBet(
        game_id=12,
        commence_time="2026-03-10T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=110.0,
        line_value=110.0,
        model_probability=0.55,
        implied_probability=0.48,
        probability_edge=0.07,
        expected_value=0.16,
        stake_fraction=0.02,
        settlement="win",
    )

    selected_candidates = select_best_quote_candidates(
        [shorter_price_candidate, better_price_candidate]
    )

    assert selected_candidates == [better_price_candidate]


def test_select_best_quote_candidates_prefers_coverage_before_ev() -> None:
    lower_coverage_higher_ev = CandidateBet(
        game_id=12,
        commence_time="2026-03-10T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=120.0,
        line_value=120.0,
        model_probability=0.55,
        implied_probability=0.45,
        probability_edge=0.10,
        expected_value=0.21,
        stake_fraction=0.02,
        settlement="win",
        sportsbook="draftkings",
        eligible_books=2,
        positive_ev_books=1,
        coverage_rate=0.5,
    )
    higher_coverage_lower_ev = CandidateBet(
        game_id=12,
        commence_time="2026-03-10T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        market_price=110.0,
        line_value=110.0,
        model_probability=0.54,
        implied_probability=0.47,
        probability_edge=0.07,
        expected_value=0.15,
        stake_fraction=0.02,
        settlement="win",
        sportsbook="fanduel",
        eligible_books=3,
        positive_ev_books=2,
        coverage_rate=2.0 / 3.0,
    )

    selected_candidates = select_best_quote_candidates(
        [lower_coverage_higher_ev, higher_coverage_lower_ev]
    )

    assert selected_candidates == [higher_coverage_lower_ev]


def test_build_executable_candidate_bets_reprices_spread_quotes(monkeypatch) -> None:
    artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("spread_line",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("spread_line",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=13,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="away",
        features={
            "spread_line": 4.0,
            "spread_abs_line": 4.0,
            "spread_total_interaction": 6.0,
            "total_close_points": 150.0,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=4.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=-120.0,
                market_implied_probability=0.52,
                line_value=3.5,
            ),
            ExecutableQuote(
                bookmaker_key="fanduel",
                market_price=-150.0,
                market_implied_probability=0.60,
                line_value=4.5,
            ),
        ),
    )

    monkeypatch.setattr(
        "cbb.modeling.execution.score_spread_probability_at_line",
        lambda **kwargs: 0.55 if kwargs["line_value"] == 3.5 else 0.603,
    )

    candidates = build_executable_candidate_bets(
        artifact=artifact,
        example=example,
        probability=0.53,
        policy=BetPolicy(
            min_edge=-1.0,
            min_confidence=0.0,
            min_probability_edge=-1.0,
            min_games_played=0,
            max_bet_fraction=0.05,
            min_positive_ev_books=2,
        ),
    )

    assert [
        (
            candidate.line_value,
            candidate.market_price,
            round(candidate.expected_value, 4),
        )
        for candidate in candidates
    ] == [
        (3.5, -120.0, 0.0083),
        (4.5, -150.0, 0.005),
    ]
    assert select_best_quote_candidates(candidates) == [candidates[0]]


def test_build_executable_candidate_bets_requires_cross_book_survivability() -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=15,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={"feature": 1.0},
        label=None,
        settlement="pending",
        market_price=100.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=100.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=100.0,
                market_implied_probability=0.50,
                line_value=100.0,
            ),
            ExecutableQuote(
                bookmaker_key="fanduel",
                market_price=-130.0,
                market_implied_probability=0.565,
                line_value=-130.0,
            ),
        ),
    )

    candidates = build_executable_candidate_bets(
        artifact=artifact,
        example=example,
        probability=0.55,
        policy=BetPolicy(
            min_edge=-1.0,
            min_confidence=0.0,
            min_probability_edge=-1.0,
            min_games_played=0,
            max_bet_fraction=0.05,
            min_positive_ev_books=2,
        ),
    )

    assert candidates == []


def test_score_candidate_bet_for_quote_applies_spread_uncertainty_buffer() -> None:
    example = ModelExample(
        game_id=17,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={
            "rest_days_diff": 3.0,
            "min_season_games_played": 8.0,
            "spread_abs_line": 9.0,
            "spread_consensus_dispersion": 2.25,
            "spread_books": 4.0,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=8,
        line_value=-9.0,
    )

    candidate = score_candidate_bet_for_quote(
        example=example,
        probability=0.57,
        policy=BetPolicy(
            min_edge=0.0,
            min_confidence=0.0,
            min_probability_edge=0.0,
            uncertainty_probability_buffer=0.02,
            min_games_played=0,
        ),
        sportsbook="draftkings",
        market_price=-110.0,
        implied_probability=0.50,
        line_value=-9.0,
    )

    assert candidate is not None
    assert candidate.model_probability == pytest.approx(0.57)
    assert candidate.probability_edge == pytest.approx(0.05425)
    assert candidate.expected_value == pytest.approx(0.0581136364)
    assert candidate.stake_fraction == pytest.approx(0.0063925)


def test_spread_uncertainty_buffer_can_block_raw_positive_ev_candidate() -> None:
    example = ModelExample(
        game_id=18,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="spread",
        team_name="Gamma Gulls",
        opponent_name="Delta Dogs",
        side="away",
        features={
            "rest_days_diff": 3.0,
            "min_season_games_played": 8.0,
            "spread_abs_line": 9.0,
            "spread_consensus_dispersion": 2.25,
            "spread_books": 4.0,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=8,
        line_value=9.0,
    )
    policy = BetPolicy(
        min_edge=0.04,
        min_confidence=0.0,
        min_probability_edge=0.04,
        uncertainty_probability_buffer=0.02,
        min_games_played=0,
    )

    candidate = score_candidate_bet_for_quote(
        example=example,
        probability=0.545,
        policy=policy,
        sportsbook="fanduel",
        market_price=-110.0,
        implied_probability=0.50,
        line_value=9.0,
    )

    assert candidate is not None
    assert candidate.probability_edge == pytest.approx(0.02925)
    assert candidate.expected_value == pytest.approx(0.0103863636)
    assert candidate_matches_policy(candidate=candidate, policy=policy) is False
    assert (
        score_candidate_bet(
            example=example,
            probability=0.545,
            policy=policy,
        )
        is None
    )


def test_build_executable_candidate_bets_can_require_positive_median_ev() -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=0.0,
        metrics=TrainingMetrics(
            examples=10,
            priced_examples=10,
            training_examples=10,
            feature_names=("feature",),
            log_loss=0.5,
            brier_score=0.2,
            accuracy=0.6,
            start_season=2024,
            end_season=2026,
            trained_at="2026-03-08T12:00:00+00:00",
        ),
    )
    example = ModelExample(
        game_id=16,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={"feature": 1.0},
        label=None,
        settlement="pending",
        market_price=100.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=100.0,
        executable_quotes=(
            ExecutableQuote(
                bookmaker_key="draftkings",
                market_price=100.0,
                market_implied_probability=0.50,
                line_value=100.0,
            ),
            ExecutableQuote(
                bookmaker_key="fanduel",
                market_price=-130.0,
                market_implied_probability=0.565,
                line_value=-130.0,
            ),
        ),
    )

    candidates = build_executable_candidate_bets(
        artifact=artifact,
        example=example,
        probability=0.52,
        policy=BetPolicy(
            min_edge=-1.0,
            min_confidence=0.0,
            min_probability_edge=-1.0,
            min_games_played=0,
            max_bet_fraction=0.05,
            min_positive_ev_books=1,
            min_median_expected_value=0.0,
        ),
    )

    assert candidates == []


def test_calibrate_probabilities_shrinks_extreme_moneyline_prices_toward_market() -> (
    None
):
    extreme_example = ModelExample(
        game_id=1,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="away",
        features={},
        label=None,
        settlement="pending",
        market_price=5000.0,
        market_implied_probability=0.02,
        minimum_games_played=10,
        line_value=5000.0,
    )
    centered_example = ModelExample(
        game_id=2,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Gamma Gulls",
        opponent_name="Delta Dogs",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=-110.0,
    )

    probabilities = calibrate_probabilities(
        raw_probabilities=[0.08, 0.58],
        examples=[extreme_example, centered_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=1.0,
        max_market_probability_delta=0.10,
    )

    assert 0.02 < probabilities[0] < 0.03
    assert round(probabilities[1], 5) == 0.58


def test_calibrate_probabilities_uses_spread_line_bucket_override() -> None:
    tight_spread_example = ModelExample(
        game_id=3,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=-3.5,
    )

    probabilities = calibrate_probabilities(
        raw_probabilities=[0.60],
        examples=[tight_spread_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=0.2,
        max_market_probability_delta=0.04,
        spread_line_calibrations=(
            SpreadLineCalibration(
                bucket_key="tight",
                abs_line_min=0.0,
                abs_line_max=4.5,
                market_blend_weight=1.0,
                max_market_probability_delta=0.20,
            ),
        ),
    )

    assert probabilities == [0.60]


def test_calibrate_probabilities_layers_spread_conference_override() -> None:
    sec_example = ModelExample(
        game_id=31,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=-5.5,
        team_conference_key="sec",
    )

    default_probabilities = calibrate_probabilities(
        raw_probabilities=[0.60],
        examples=[sec_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=0.2,
        max_market_probability_delta=0.04,
    )
    conference_probabilities = calibrate_probabilities(
        raw_probabilities=[0.60],
        examples=[sec_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=0.2,
        max_market_probability_delta=0.04,
        spread_conference_calibrations=(
            SpreadConferenceCalibration(
                conference_key="sec",
                market_blend_weight=1.0,
                max_market_probability_delta=0.20,
            ),
        ),
    )

    assert default_probabilities == [0.52]
    assert conference_probabilities == [0.54]


def test_calibrate_probabilities_layers_spread_season_phase_override() -> None:
    early_season_example = ModelExample(
        game_id=32,
        season=2026,
        commence_time="2026-11-15T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={"min_season_games_played": 3.0},
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=3,
        line_value=-5.5,
        team_conference_key="sec",
    )

    default_probabilities = calibrate_probabilities(
        raw_probabilities=[0.60],
        examples=[early_season_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=0.2,
        max_market_probability_delta=0.04,
    )
    phase_probabilities = calibrate_probabilities(
        raw_probabilities=[0.60],
        examples=[early_season_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=0.2,
        max_market_probability_delta=0.04,
        spread_season_phase_calibrations=(
            SpreadSeasonPhaseCalibration(
                phase_key="early",
                min_games_played_min=1,
                min_games_played_max=5,
                market_blend_weight=1.0,
                max_market_probability_delta=0.20,
            ),
        ),
    )

    assert default_probabilities == [0.52]
    assert phase_probabilities == [0.54]


def test_select_spread_line_calibrations_rejects_holdout_loser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_feature_raw_probabilities_for_spread_calibration(monkeypatch)
    calibration_examples = _build_specialized_spread_calibration_examples(
        labels=[1] * 40 + [0] * 40,
        raw_probability=0.80,
        line_value=-3.5,
    )

    calibrations = _select_spread_line_calibrations(
        means=(),
        scales=(),
        weights=(),
        bias=0.0,
        feature_names=(),
        calibration_examples=calibration_examples,
        spread_residual_scale=1.0,
        platt_scale=1.0,
        platt_bias=0.0,
        default_market_blend_weight=0.2,
        default_max_market_probability_delta=0.04,
    )

    assert calibrations == ()


def test_select_spread_conference_calibrations_keeps_holdout_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_feature_raw_probabilities_for_spread_calibration(monkeypatch)
    calibration_examples = _build_specialized_spread_calibration_examples(
        labels=[1] * 80,
        raw_probability=0.80,
        line_value=-5.5,
        team_conference_key="sec",
    )

    calibrations = _select_spread_conference_calibrations(
        means=(),
        scales=(),
        weights=(),
        bias=0.0,
        feature_names=(),
        calibration_examples=calibration_examples,
        spread_residual_scale=1.0,
        platt_scale=1.0,
        platt_bias=0.0,
        default_market_blend_weight=0.2,
        default_max_market_probability_delta=0.04,
    )

    assert len(calibrations) == 1
    assert calibrations[0].conference_key == "sec"
    assert calibrations[0].market_blend_weight > 0.2


def test_select_spread_season_phase_calibrations_keeps_holdout_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_feature_raw_probabilities_for_spread_calibration(monkeypatch)
    calibration_examples = _build_specialized_spread_calibration_examples(
        labels=[1] * 80,
        raw_probability=0.80,
        line_value=-5.5,
        min_season_games_played=3.0,
    )

    calibrations = _select_spread_season_phase_calibrations(
        means=(),
        scales=(),
        weights=(),
        bias=0.0,
        feature_names=(),
        calibration_examples=calibration_examples,
        spread_residual_scale=1.0,
        platt_scale=1.0,
        platt_bias=0.0,
        default_market_blend_weight=0.2,
        default_max_market_probability_delta=0.04,
    )

    assert len(calibrations) == 1
    assert calibrations[0].phase_key == "early"
    assert calibrations[0].market_blend_weight > 0.2


def test_calibrate_probabilities_uses_moneyline_segment_override() -> None:
    balanced_example = ModelExample(
        game_id=4,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=110.0,
    )

    default_probabilities = calibrate_probabilities(
        raw_probabilities=[0.60],
        examples=[balanced_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=0.2,
        max_market_probability_delta=0.04,
    )
    segment_probabilities = calibrate_probabilities(
        raw_probabilities=[0.60],
        examples=[balanced_example],
        platt_scale=1.0,
        platt_bias=0.0,
        market_blend_weight=0.2,
        max_market_probability_delta=0.04,
        moneyline_segment_calibrations=(
            MoneylineSegmentCalibration(
                segment_key="balanced",
                market_blend_weight=1.0,
                max_market_probability_delta=0.20,
            ),
        ),
    )

    assert default_probabilities == [0.52]
    assert segment_probabilities == [0.60]


def test_score_examples_dispatches_moneyline_band_models_by_price() -> None:
    artifact = ModelArtifact(
        market="moneyline",
        model_family="logistic",
        feature_names=(),
        means=(),
        scales=(),
        weights=(),
        bias=-2.0,
        metrics=TrainingMetrics(
            examples=0,
            priced_examples=0,
            training_examples=0,
            feature_names=(),
            log_loss=0.0,
            brier_score=0.0,
            accuracy=0.0,
            start_season=2026,
            end_season=2026,
            trained_at="2026-03-08T00:00:00+00:00",
        ),
        moneyline_band_models=(
            MoneylineBandModel(
                band_key="short_dog",
                price_min=126.0,
                price_max=175.0,
                means=(),
                scales=(),
                weights=(),
                bias=2.0,
            ),
        ),
    )
    core_example = ModelExample(
        game_id=1,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={},
        label=None,
        settlement="pending",
        market_price=110.0,
        market_implied_probability=None,
        minimum_games_played=10,
        line_value=110.0,
    )
    short_dog_example = ModelExample(
        game_id=2,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="moneyline",
        team_name="Gamma Gulls",
        opponent_name="Delta Dogs",
        side="away",
        features={},
        label=None,
        settlement="pending",
        market_price=150.0,
        market_implied_probability=None,
        minimum_games_played=10,
        line_value=150.0,
    )

    probabilities = score_examples(
        artifact=artifact,
        examples=[core_example, short_dog_example],
    )

    assert probabilities[0] < 0.2
    assert probabilities[1] > 0.8


def test_train_betting_model_supports_hist_gradient_boosting_spread(
    tmp_path: Path,
) -> None:
    database_url, artifacts_dir = _create_model_test_environment(tmp_path)

    summary = train_betting_model(
        TrainingOptions(
            market="spread",
            seasons_back=2,
            max_season=2026,
            artifact_name="spread_tree_test",
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            model_family="hist_gradient_boosting",
            config=LogisticRegressionConfig(
                min_examples=8,
            ),
        )
    )

    artifact = load_artifact(
        market="spread",
        artifact_name="spread_tree_test",
        artifacts_dir=artifacts_dir,
    )

    assert summary.market == "spread"
    assert summary.model_family == "hist_gradient_boosting"
    assert artifact.model_family == "hist_gradient_boosting"
    assert artifact.spread_modeling_mode == "cover_classifier"
    assert artifact.serialized_model_base64 is not None
    assert artifact.weights == ()
    assert artifact.means == ()
    assert artifact.scales == ()


def test_select_tuned_spread_policy_prefers_tighter_spread_cap() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time="2026-01-01T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=1,
                    commence_time="2026-01-01T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=-110.0,
                    line_value=14.5,
                    model_probability=0.56,
                    implied_probability=0.50,
                    probability_edge=0.06,
                    expected_value=0.07,
                    stake_fraction=0.02,
                    settlement="loss",
                    minimum_games_played=10,
                ),
                CandidateBet(
                    game_id=2,
                    commence_time="2026-01-02T19:00:00+00:00",
                    market="spread",
                    team_name="Gamma Gulls",
                    opponent_name="Delta Dogs",
                    side="away",
                    market_price=-110.0,
                    line_value=5.5,
                    model_probability=0.57,
                    implied_probability=0.50,
                    probability_edge=0.07,
                    expected_value=0.09,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        )
    ]

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=BetPolicy(),
        starting_bankroll=1000.0,
    )

    assert evaluation.policy.max_spread_abs_line is not None
    assert evaluation.policy.max_spread_abs_line < 14.5
    assert evaluation.profit > 0
    assert evaluation.meets_activity_constraints is False


def _make_spread_candidate(
    *,
    game_id: int,
    commence_time: str,
    expected_value: float,
    model_probability: float,
    settlement: str,
    line_value: float,
    implied_probability: float = 0.50,
    minimum_games_played: int = 10,
    market_book_count: int = 8,
    same_conference_game: bool | None = None,
    team_conference_key: str | None = None,
    observation_time: str | None = None,
) -> CandidateBet:
    return CandidateBet(
        game_id=game_id,
        commence_time=commence_time,
        market="spread",
        team_name=f"Team {game_id}",
        opponent_name=f"Opponent {game_id}",
        side="home",
        market_price=100.0,
        line_value=line_value,
        model_probability=model_probability,
        implied_probability=implied_probability,
        probability_edge=model_probability - implied_probability,
        expected_value=expected_value,
        stake_fraction=0.02,
        settlement=settlement,
        minimum_games_played=minimum_games_played,
        market_book_count=market_book_count,
        same_conference_game=same_conference_game,
        team_conference_key=team_conference_key,
        observation_time=observation_time,
    )


def _make_spread_close_record(*, game_id: int, line_value: float) -> SimpleNamespace:
    return SimpleNamespace(
        game_id=game_id,
        spread_close=SimpleNamespace(
            team1_point=line_value,
            team2_point=-line_value,
            team1_price=100.0,
            team2_price=100.0,
            team1_implied_probability=0.50,
            team2_implied_probability=0.50,
        ),
        current_spread_quotes=(),
        home_spread_price=100.0,
        away_spread_price=100.0,
        home_spread_line=line_value,
        away_spread_line=-line_value,
    )


def test_select_tuned_spread_policy_prefers_profit_over_roi() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time="2026-01-01T19:00:00+00:00",
            candidates=(
                _make_spread_candidate(
                    game_id=11,
                    commence_time="2026-01-01T19:00:00+00:00",
                    expected_value=0.04,
                    model_probability=0.60,
                    settlement="win",
                    line_value=3.5,
                ),
                _make_spread_candidate(
                    game_id=12,
                    commence_time="2026-01-01T20:00:00+00:00",
                    expected_value=0.018,
                    model_probability=0.56,
                    settlement="win",
                    line_value=4.0,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-08T19:00:00+00:00",
            candidates=(
                _make_spread_candidate(
                    game_id=13,
                    commence_time="2026-01-08T19:00:00+00:00",
                    expected_value=0.04,
                    model_probability=0.60,
                    settlement="win",
                    line_value=4.5,
                ),
                _make_spread_candidate(
                    game_id=14,
                    commence_time="2026-01-08T20:00:00+00:00",
                    expected_value=0.018,
                    model_probability=0.56,
                    settlement="win",
                    line_value=5.0,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-15T19:00:00+00:00",
            candidates=(
                _make_spread_candidate(
                    game_id=15,
                    commence_time="2026-01-15T19:00:00+00:00",
                    expected_value=0.04,
                    model_probability=0.60,
                    settlement="win",
                    line_value=5.5,
                ),
                _make_spread_candidate(
                    game_id=16,
                    commence_time="2026-01-15T20:00:00+00:00",
                    expected_value=0.018,
                    model_probability=0.56,
                    settlement="loss",
                    line_value=6.0,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-22T19:00:00+00:00",
            candidates=(
                _make_spread_candidate(
                    game_id=17,
                    commence_time="2026-01-22T19:00:00+00:00",
                    expected_value=0.04,
                    model_probability=0.60,
                    settlement="win",
                    line_value=6.5,
                ),
            ),
        ),
    ]

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=BetPolicy(),
        starting_bankroll=1000.0,
    )

    assert evaluation.policy.min_edge == pytest.approx(0.015)
    assert evaluation.meets_activity_constraints is True
    assert evaluation.meets_tuning_constraints is True
    assert evaluation.roi > 0.0
    assert evaluation.profit > 0


def test_select_tuned_spread_policy_rejects_negative_closing_ev() -> None:
    candidate_blocks = []
    for block_index, commence_time in enumerate(
        (
            "2026-01-01T19:00:00+00:00",
            "2026-01-08T19:00:00+00:00",
            "2026-01-15T19:00:00+00:00",
            "2026-01-22T19:00:00+00:00",
        ),
        start=1,
    ):
        good_game_id = 100 + (block_index * 2)
        bad_game_id = good_game_id + 1
        good_line_value = -3.5 - block_index
        bad_line_value = -2.5 - block_index
        candidate_blocks.append(
            CandidateBlock(
                commence_time=commence_time,
                candidates=(
                    _make_spread_candidate(
                        game_id=good_game_id,
                        commence_time=commence_time,
                        expected_value=0.04,
                        model_probability=0.53,
                        settlement="win",
                        line_value=good_line_value,
                    ),
                    _make_spread_candidate(
                        game_id=bad_game_id,
                        commence_time=commence_time.replace("19:00:00", "20:00:00"),
                        expected_value=0.08,
                        model_probability=0.51,
                        implied_probability=0.47,
                        settlement="win",
                        line_value=bad_line_value,
                    ),
                ),
                completed_records=(
                    _make_spread_close_record(
                        game_id=good_game_id,
                        line_value=good_line_value,
                    ),
                    _make_spread_close_record(
                        game_id=bad_game_id,
                        line_value=bad_line_value,
                    ),
                ),
                spread_closing_metrics=(
                    (
                        (good_game_id, "home"),
                        SpreadClosingMarketMetrics(
                            closing_line=good_line_value,
                            closing_no_vig_probability=0.50,
                            closing_expected_value=0.03,
                        ),
                    ),
                    (
                        (bad_game_id, "home"),
                        SpreadClosingMarketMetrics(
                            closing_line=bad_line_value,
                            closing_no_vig_probability=0.50,
                            closing_expected_value=-0.04,
                        ),
                    ),
                ),
            )
        )

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=BetPolicy(),
        starting_bankroll=1000.0,
    )

    assert evaluation.policy.min_confidence in {0.515, 0.52, 0.525}
    assert evaluation.meets_activity_constraints is True
    assert evaluation.meets_close_quality_constraints is True
    assert evaluation.meets_tuning_constraints is True
    assert evaluation.clv.average_spread_closing_expected_value == pytest.approx(0.03)


def test_select_tuned_spread_policy_can_raise_min_confidence() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time="2026-01-01T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=31,
                    commence_time="2026-01-01T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=100.0,
                    line_value=6.5,
                    model_probability=0.51,
                    implied_probability=0.47,
                    probability_edge=0.04,
                    expected_value=0.04,
                    stake_fraction=0.02,
                    settlement="loss",
                    minimum_games_played=10,
                ),
                CandidateBet(
                    game_id=32,
                    commence_time="2026-01-01T20:00:00+00:00",
                    market="spread",
                    team_name="Gamma Gulls",
                    opponent_name="Delta Dogs",
                    side="away",
                    market_price=100.0,
                    line_value=6.0,
                    model_probability=0.54,
                    implied_probability=0.50,
                    probability_edge=0.04,
                    expected_value=0.08,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-08T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=33,
                    commence_time="2026-01-08T19:00:00+00:00",
                    market="spread",
                    team_name="Iota Iguanas",
                    opponent_name="Kappa Knights",
                    side="home",
                    market_price=100.0,
                    line_value=7.0,
                    model_probability=0.51,
                    implied_probability=0.47,
                    probability_edge=0.04,
                    expected_value=0.04,
                    stake_fraction=0.02,
                    settlement="loss",
                    minimum_games_played=10,
                ),
                CandidateBet(
                    game_id=34,
                    commence_time="2026-01-08T20:00:00+00:00",
                    market="spread",
                    team_name="Lambda Lions",
                    opponent_name="Mu Mustangs",
                    side="away",
                    market_price=100.0,
                    line_value=6.0,
                    model_probability=0.54,
                    implied_probability=0.50,
                    probability_edge=0.04,
                    expected_value=0.08,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-15T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=35,
                    commence_time="2026-01-15T19:00:00+00:00",
                    market="spread",
                    team_name="Nu Knights",
                    opponent_name="Omicron Owls",
                    side="home",
                    market_price=100.0,
                    line_value=7.5,
                    model_probability=0.51,
                    implied_probability=0.47,
                    probability_edge=0.04,
                    expected_value=0.04,
                    stake_fraction=0.02,
                    settlement="loss",
                    minimum_games_played=10,
                ),
                CandidateBet(
                    game_id=36,
                    commence_time="2026-01-15T20:00:00+00:00",
                    market="spread",
                    team_name="Pi Panthers",
                    opponent_name="Rho Ravens",
                    side="away",
                    market_price=100.0,
                    line_value=6.5,
                    model_probability=0.54,
                    implied_probability=0.50,
                    probability_edge=0.04,
                    expected_value=0.08,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-22T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=37,
                    commence_time="2026-01-22T19:00:00+00:00",
                    market="spread",
                    team_name="Sigma Sharks",
                    opponent_name="Tau Tigers",
                    side="home",
                    market_price=100.0,
                    line_value=7.0,
                    model_probability=0.51,
                    implied_probability=0.47,
                    probability_edge=0.04,
                    expected_value=0.04,
                    stake_fraction=0.02,
                    settlement="loss",
                    minimum_games_played=10,
                ),
                CandidateBet(
                    game_id=38,
                    commence_time="2026-01-22T20:00:00+00:00",
                    market="spread",
                    team_name="Upsilon United",
                    opponent_name="Phi Foxes",
                    side="away",
                    market_price=100.0,
                    line_value=6.5,
                    model_probability=0.54,
                    implied_probability=0.50,
                    probability_edge=0.04,
                    expected_value=0.08,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        ),
    ]

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=BetPolicy(),
        starting_bankroll=1000.0,
    )

    assert evaluation.policy.min_confidence in {0.515, 0.52, 0.525}
    assert evaluation.meets_activity_constraints is True
    assert evaluation.bets_placed == 4
    assert evaluation.profit > 0.0


def test_select_tuned_spread_policy_preserves_base_rest_gap_guard() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time="2026-01-01T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=41,
                    commence_time="2026-01-01T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=100.0,
                    line_value=4.5,
                    model_probability=0.58,
                    implied_probability=0.50,
                    probability_edge=0.08,
                    expected_value=0.08,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                    abs_rest_days_diff=5.0,
                ),
            ),
        )
    ]

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=BetPolicy(
            min_edge=0.027,
            min_confidence=0.518,
            min_probability_edge=0.025,
            min_games_played=4,
            max_spread_abs_line=10.0,
            max_abs_rest_days_diff=3.0,
            min_positive_ev_books=2,
            min_median_expected_value=0.01,
        ),
        starting_bankroll=1000.0,
    )

    assert evaluation.policy.max_abs_rest_days_diff == 3.0
    assert evaluation.policy.min_positive_ev_books == 2
    assert evaluation.policy.min_median_expected_value == 0.01
    assert evaluation.bets_placed == 0
    assert evaluation.profit == 0.0


def test_backtest_betting_model_skips_inactive_auto_tuned_spread_policy(
    monkeypatch,
) -> None:
    base_policy = BetPolicy(
        min_edge=0.02,
        min_probability_edge=0.025,
        min_games_played=8,
    )
    tuned_policy = BetPolicy(
        min_edge=0.015,
        min_probability_edge=0.015,
        min_games_played=4,
        max_spread_abs_line=10.0,
    )
    evaluation_record = SimpleNamespace(
        game_id=1,
        season=2026,
        commence_time=datetime(2026, 1, 15, 19, 0, tzinfo=UTC),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "cbb.modeling.backtest.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest.resolve_training_seasons",
        lambda **_: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest.load_completed_game_records",
        lambda **_: [evaluation_record],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest._build_evaluation_blocks",
        lambda **_: [[evaluation_record]],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest.tune_spread_policy_from_records",
        lambda **_: PolicyEvaluation(
            policy=tuned_policy,
            blocks_evaluated=1,
            blocks_with_bets=0,
            profitable_blocks=0,
            bets_placed=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            active_block_rate=0.0,
            profitable_block_rate=0.0,
            worst_block_roi=0.0,
            block_roi_stddev=0.0,
            stability_score=0.0,
            max_drawdown=0.0,
            meets_activity_constraints=False,
            activity_score=0.0,
        ),
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest._train_block_artifacts",
        lambda **_: {"spread": object()},
    )

    def fake_score_block_candidates(*, selection_policy, **_):
        captured["selection_policy"] = selection_policy
        return []

    monkeypatch.setattr(
        "cbb.modeling.backtest._score_block_candidates",
        fake_score_block_candidates,
    )

    summary = backtest_betting_model(
        BacktestOptions(
            market="spread",
            seasons_back=1,
            evaluation_season=2026,
            auto_tune_spread_policy=True,
            starting_bankroll=1000.0,
            unit_size=25.0,
            retrain_days=30,
            database_url="sqlite://",
            policy=base_policy,
        )
    )

    assert captured["selection_policy"] == deployable_spread_policy(base_policy)
    assert summary.policy_tuned_blocks == 0
    assert summary.final_policy == deployable_spread_policy(base_policy)


def test_backtest_betting_model_timing_layer_skips_moneyline_fallback(
    monkeypatch,
) -> None:
    evaluation_record = SimpleNamespace(
        game_id=1,
        season=2026,
        commence_time=datetime(2026, 1, 15, 19, 0, tzinfo=UTC),
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "cbb.modeling.backtest.get_available_seasons",
        lambda _database_url=None: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest.resolve_training_seasons",
        lambda **_: [2026],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest.load_completed_game_records",
        lambda **_: [evaluation_record],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest._build_evaluation_blocks",
        lambda **_: [[evaluation_record]],
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest._train_block_artifacts",
        lambda **_: {"moneyline": object()},
    )
    monkeypatch.setattr(
        "cbb.modeling.backtest._derive_timing_decision_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("timing records should not be built for moneyline fallback")
        ),
    )

    def fake_score_block_candidates(*, evaluation_block, **_):
        captured["evaluation_block"] = evaluation_block
        return []

    monkeypatch.setattr(
        "cbb.modeling.backtest._score_block_candidates",
        fake_score_block_candidates,
    )

    summary = backtest_betting_model(
        BacktestOptions(
            market="best",
            seasons_back=1,
            evaluation_season=2026,
            use_timing_layer=True,
            database_url="sqlite://",
        )
    )

    assert captured["evaluation_block"] == [evaluation_record]
    assert summary.market == "best"
    assert summary.bets_placed == 0


def test_select_tuned_spread_policy_rejects_inactive_high_roi_policy() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time="2026-01-01T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=21,
                    commence_time="2026-01-01T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=100.0,
                    line_value=3.5,
                    model_probability=0.62,
                    implied_probability=0.50,
                    probability_edge=0.12,
                    expected_value=0.24,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
                CandidateBet(
                    game_id=22,
                    commence_time="2026-01-01T20:00:00+00:00",
                    market="spread",
                    team_name="Gamma Gulls",
                    opponent_name="Delta Dogs",
                    side="away",
                    market_price=100.0,
                    line_value=5.5,
                    model_probability=0.56,
                    implied_probability=0.50,
                    probability_edge=0.06,
                    expected_value=0.018,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-08T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=23,
                    commence_time="2026-01-08T19:00:00+00:00",
                    market="spread",
                    team_name="Iota Iguanas",
                    opponent_name="Kappa Knights",
                    side="home",
                    market_price=100.0,
                    line_value=4.5,
                    model_probability=0.56,
                    implied_probability=0.50,
                    probability_edge=0.06,
                    expected_value=0.018,
                    stake_fraction=0.02,
                    settlement="loss",
                    minimum_games_played=10,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-15T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=24,
                    commence_time="2026-01-15T19:00:00+00:00",
                    market="spread",
                    team_name="Lambda Lions",
                    opponent_name="Mu Mustangs",
                    side="away",
                    market_price=100.0,
                    line_value=6.5,
                    model_probability=0.56,
                    implied_probability=0.50,
                    probability_edge=0.06,
                    expected_value=0.018,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        ),
        CandidateBlock(
            commence_time="2026-01-22T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=25,
                    commence_time="2026-01-22T19:00:00+00:00",
                    market="spread",
                    team_name="Nu Knights",
                    opponent_name="Omicron Owls",
                    side="home",
                    market_price=100.0,
                    line_value=2.5,
                    model_probability=0.56,
                    implied_probability=0.50,
                    probability_edge=0.06,
                    expected_value=0.018,
                    stake_fraction=0.02,
                    settlement="win",
                    minimum_games_played=10,
                ),
            ),
        ),
    ]

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=BetPolicy(),
        starting_bankroll=1000.0,
    )

    assert evaluation.meets_activity_constraints is True
    assert evaluation.bets_placed >= 3
    assert evaluation.active_block_rate >= 0.25
    assert evaluation.policy.min_edge < 0.03


def test_score_examples_supports_margin_regression_spread_artifact() -> None:
    positive_example = ModelExample(
        game_id=31,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={"feature": 0.0},
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=-4.5,
    )
    negative_example = ModelExample(
        game_id=32,
        season=2026,
        commence_time="2026-03-09T19:00:00+00:00",
        market="spread",
        team_name="Gamma Gulls",
        opponent_name="Delta Dogs",
        side="away",
        features={"feature": 0.0},
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=10,
        line_value=4.5,
    )

    positive_artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=4.0,
        spread_modeling_mode="margin_regression",
        spread_residual_scale=2.0,
        metrics=TrainingMetrics(
            examples=0,
            priced_examples=0,
            training_examples=0,
            feature_names=("feature",),
            log_loss=0.0,
            brier_score=0.0,
            accuracy=0.0,
            start_season=2026,
            end_season=2026,
            trained_at="2026-03-08T00:00:00+00:00",
        ),
        market_blend_weight=1.0,
        max_market_probability_delta=1.0,
    )
    negative_artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=-4.0,
        spread_modeling_mode="margin_regression",
        spread_residual_scale=2.0,
        metrics=TrainingMetrics(
            examples=0,
            priced_examples=0,
            training_examples=0,
            feature_names=("feature",),
            log_loss=0.0,
            brier_score=0.0,
            accuracy=0.0,
            start_season=2026,
            end_season=2026,
            trained_at="2026-03-08T00:00:00+00:00",
        ),
        market_blend_weight=1.0,
        max_market_probability_delta=1.0,
    )

    positive_probability = score_examples(
        artifact=positive_artifact,
        examples=[positive_example],
    )[0]
    negative_probability = score_examples(
        artifact=negative_artifact,
        examples=[negative_example],
    )[0]

    assert positive_probability > 0.8
    assert negative_probability < 0.2


def test_score_examples_uses_heteroskedastic_spread_residual_scales() -> None:
    volatile_example = ModelExample(
        game_id=205,
        season=2026,
        commence_time="2026-01-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={
            "feature": 0.0,
            "min_season_games_played": 3.0,
            "spread_books": 3.0,
            "spread_consensus_dispersion": 1.5,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.50,
        minimum_games_played=3,
        line_value=-11.5,
    )
    baseline_artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=4.0,
        spread_modeling_mode="margin_regression",
        spread_residual_scale=1.0,
        metrics=TrainingMetrics(
            examples=0,
            priced_examples=0,
            training_examples=0,
            feature_names=("feature",),
            log_loss=0.0,
            brier_score=0.0,
            accuracy=0.0,
            start_season=2026,
            end_season=2026,
            trained_at="2026-03-08T00:00:00+00:00",
        ),
        market_blend_weight=1.0,
        max_market_probability_delta=1.0,
    )
    heteroskedastic_artifact = ModelArtifact(
        market="spread",
        model_family="logistic",
        feature_names=("feature",),
        means=(0.0,),
        scales=(1.0,),
        weights=(0.0,),
        bias=4.0,
        spread_modeling_mode="margin_regression",
        spread_residual_scale=1.0,
        spread_line_residual_scales=(
            SpreadLineResidualScale(
                bucket_key="long_line",
                abs_line_min=10.5,
                abs_line_max=None,
                residual_scale=4.0,
            ),
        ),
        spread_season_phase_residual_scales=(
            SpreadSeasonPhaseResidualScale(
                phase_key="early",
                min_games_played_min=1,
                min_games_played_max=5,
                residual_scale=3.0,
            ),
        ),
        spread_book_depth_residual_scales=(
            SpreadBookDepthResidualScale(
                bucket_key="low_depth",
                min_books=0,
                max_books=4,
                residual_scale=5.0,
            ),
        ),
        metrics=TrainingMetrics(
            examples=0,
            priced_examples=0,
            training_examples=0,
            feature_names=("feature",),
            log_loss=0.0,
            brier_score=0.0,
            accuracy=0.0,
            start_season=2026,
            end_season=2026,
            trained_at="2026-03-08T00:00:00+00:00",
        ),
        market_blend_weight=1.0,
        max_market_probability_delta=1.0,
    )

    baseline_probability = score_examples(
        artifact=baseline_artifact,
        examples=[volatile_example],
    )[0]
    heteroskedastic_probability = score_examples(
        artifact=heteroskedastic_artifact,
        examples=[volatile_example],
    )[0]

    assert baseline_probability > heteroskedastic_probability
    assert baseline_probability == pytest.approx(0.98201379)
    assert heteroskedastic_probability == pytest.approx(0.77395318)


def _create_model_test_environment(tmp_path: Path) -> tuple[str, Path]:
    database_path = tmp_path / "modeling.sqlite"
    artifacts_dir = tmp_path / "artifacts"
    _create_model_test_db(database_path)
    return f"sqlite:///{database_path}", artifacts_dir


def _use_feature_raw_probabilities_for_spread_calibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _stub_score_raw_spread_margin_probabilities(*, examples, **kwargs):
        return [float(example.features["raw_probability"]) for example in examples]

    monkeypatch.setattr(
        train_module,
        "_score_raw_spread_margin_probabilities",
        _stub_score_raw_spread_margin_probabilities,
    )


def _build_specialized_spread_calibration_examples(
    *,
    labels: list[int],
    raw_probability: float,
    line_value: float,
    team_conference_key: str | None = None,
    min_season_games_played: float = 8.0,
) -> list[ModelExample]:
    base_time = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        ModelExample(
            game_id=5000 + index,
            season=2026,
            commence_time=(base_time + timedelta(days=index)).isoformat(),
            market="spread",
            team_name=f"Team {index}",
            opponent_name=f"Opponent {index}",
            side="home",
            features={
                "raw_probability": raw_probability,
                "min_season_games_played": min_season_games_played,
            },
            label=label,
            settlement="win" if label else "loss",
            market_price=-110.0,
            market_implied_probability=0.50,
            minimum_games_played=int(min_season_games_played),
            line_value=line_value,
            team_conference_key=team_conference_key,
        )
        for index, label in enumerate(labels)
    ]


def _create_model_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_key TEXT NOT NULL UNIQUE,
            conference_key TEXT,
            conference_name TEXT,
            name TEXT NOT NULL
        );

        CREATE TABLE games (
            game_id INTEGER PRIMARY KEY,
            season INTEGER NOT NULL,
            date TEXT NOT NULL,
            commence_time TEXT,
            team1_id INTEGER NOT NULL,
            team2_id INTEGER NOT NULL,
            result TEXT,
            completed INTEGER NOT NULL DEFAULT 0,
            home_score INTEGER,
            away_score INTEGER,
            source_event_id TEXT UNIQUE
        );

        CREATE TABLE odds_snapshots (
            odds_id INTEGER PRIMARY KEY,
            game_id INTEGER NOT NULL,
            bookmaker_key TEXT NOT NULL,
            bookmaker_title TEXT NOT NULL,
            market_key TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            is_closing_line INTEGER NOT NULL DEFAULT 0,
            team1_price REAL,
            team2_price REAL,
            team1_point REAL,
            team2_point REAL,
            total_points REAL,
            payload TEXT NOT NULL
        );
        """
    )
    connection.executemany(
        """
        INSERT INTO teams (
            team_id,
            team_key,
            conference_key,
            conference_name,
            name
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "alpha-aces", "sec", "SEC", "Alpha Aces"),
            (2, "beta-bruins", "acc", "ACC", "Beta Bruins"),
            (3, "gamma-gulls", "big-ten", "Big Ten", "Gamma Gulls"),
            (4, "delta-dogs", "mvc", "MVC", "Delta Dogs"),
        ],
    )
    connection.executemany(
        """
        INSERT INTO games (
            game_id, season, date, commence_time, team1_id, team2_id,
            result, completed, home_score, away_score, source_event_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                1,
                2025,
                "2024-11-05",
                "2024-11-05T19:00:00+00:00",
                1,
                4,
                "W",
                1,
                80,
                60,
                "evt-1",
            ),
            (
                2,
                2025,
                "2024-11-10",
                "2024-11-10T20:00:00+00:00",
                2,
                3,
                "W",
                1,
                75,
                67,
                "evt-2",
            ),
            (
                3,
                2025,
                "2025-01-15",
                "2025-01-15T19:00:00+00:00",
                3,
                1,
                "L",
                1,
                65,
                79,
                "evt-3",
            ),
            (
                4,
                2025,
                "2025-01-20",
                "2025-01-20T19:00:00+00:00",
                4,
                2,
                "L",
                1,
                64,
                72,
                "evt-4",
            ),
            (
                5,
                2026,
                "2025-11-05",
                "2025-11-05T19:00:00+00:00",
                1,
                3,
                "W",
                1,
                81,
                70,
                "evt-5",
            ),
            (
                6,
                2026,
                "2025-11-10",
                "2025-11-10T20:00:00+00:00",
                2,
                4,
                "W",
                1,
                77,
                68,
                "evt-6",
            ),
            (
                7,
                2026,
                "2026-02-20",
                "2026-02-20T19:00:00+00:00",
                4,
                1,
                "L",
                1,
                69,
                82,
                "evt-7",
            ),
            (
                8,
                2026,
                "2026-02-25",
                "2026-02-25T20:00:00+00:00",
                3,
                2,
                "L",
                1,
                66,
                74,
                "evt-8",
            ),
            (
                9,
                2026,
                "2026-03-09",
                "2026-03-09T19:00:00+00:00",
                1,
                2,
                None,
                0,
                None,
                None,
                "evt-9",
            ),
            (
                10,
                2026,
                "2026-03-10",
                "2026-03-10T20:00:00+00:00",
                4,
                3,
                None,
                0,
                None,
                None,
                "evt-10",
            ),
        ],
    )
    connection.executemany(
        """
        INSERT INTO odds_snapshots (
            odds_id, game_id, bookmaker_key, bookmaker_title, market_key,
            captured_at, is_closing_line, team1_price, team2_price,
            team1_point, team2_point, total_points, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _odds_snapshot_rows(),
    )
    connection.commit()
    connection.close()


def _odds_snapshot_rows() -> list[tuple[object, ...]]:
    rows: list[tuple[object, ...]] = []
    odds_id = 1
    snapshot_specs = [
        (1, "2024-11-02T18:00:00+00:00", 0, -140.0, 120.0, -4.5, 4.5, 146.5),
        (1, "2024-11-04T19:00:00+00:00", 0, -135.0, 115.0, -4.0, 4.0, 146.0),
        (1, "2024-11-05T18:30:00+00:00", 1, -130.0, 110.0, -3.5, 3.5, 145.5),
        (2, "2024-11-07T20:00:00+00:00", 0, -118.0, 102.0, -1.5, 1.5, 142.5),
        (2, "2024-11-09T20:00:00+00:00", 0, -122.0, 104.0, -2.0, 2.0, 142.0),
        (2, "2024-11-10T19:30:00+00:00", 1, -125.0, 105.0, -2.5, 2.5, 141.5),
        (3, "2025-01-12T18:00:00+00:00", 0, 160.0, -180.0, 5.5, -5.5, 145.5),
        (3, "2025-01-14T18:00:00+00:00", 0, 150.0, -170.0, 5.0, -5.0, 145.0),
        (3, "2025-01-15T18:30:00+00:00", 1, 145.0, -165.0, 4.5, -4.5, 144.5),
        (4, "2025-01-17T19:00:00+00:00", 0, 125.0, -145.0, 2.5, -2.5, 142.5),
        (4, "2025-01-19T19:00:00+00:00", 0, 130.0, -150.0, 3.0, -3.0, 142.0),
        (4, "2025-01-20T18:30:00+00:00", 1, 135.0, -155.0, 3.5, -3.5, 141.5),
        (5, "2025-11-02T18:00:00+00:00", 0, -110.0, -110.0, -1.5, 1.5, 146.5),
        (5, "2025-11-04T18:00:00+00:00", 0, -115.0, -105.0, -2.0, 2.0, 146.0),
        (5, "2025-11-05T18:30:00+00:00", 1, -120.0, 100.0, -2.5, 2.5, 145.5),
        (6, "2025-11-07T20:00:00+00:00", 0, -105.0, -115.0, -0.5, 0.5, 144.5),
        (6, "2025-11-09T20:00:00+00:00", 0, -108.0, -112.0, -1.0, 1.0, 144.0),
        (6, "2025-11-10T19:30:00+00:00", 1, -110.0, -110.0, -1.5, 1.5, 143.5),
        (7, "2026-02-17T19:00:00+00:00", 0, 155.0, -175.0, 5.0, -5.0, 148.5),
        (7, "2026-02-19T19:00:00+00:00", 0, 150.0, -170.0, 4.75, -4.75, 148.0),
        (7, "2026-02-20T18:30:00+00:00", 1, 145.0, -165.0, 4.5, -4.5, 147.5),
        (8, "2026-02-22T20:00:00+00:00", 0, 130.0, -150.0, 3.0, -3.0, 145.0),
        (8, "2026-02-24T20:00:00+00:00", 0, 135.0, -155.0, 3.5, -3.5, 144.5),
        (8, "2026-02-25T19:30:00+00:00", 1, 140.0, -160.0, 4.0, -4.0, 144.0),
        (9, "2026-03-08T18:00:00+00:00", 0, -110.0, -110.0, -1.0, 1.0, 145.5),
        (9, "2026-03-09T18:30:00+00:00", 0, -115.0, -105.0, -1.5, 1.5, 145.0),
        (10, "2026-03-08T20:00:00+00:00", 0, 110.0, -130.0, 2.0, -2.0, 141.0),
        (10, "2026-03-09T17:00:00+00:00", 0, 105.0, -125.0, 1.5, -1.5, 140.5),
    ]

    def append_market_rows(
        *,
        game_id: int,
        captured_at: str,
        is_closing_line: int,
        home_price: float,
        away_price: float,
        home_spread: float,
        away_spread: float,
        total_points: float,
    ) -> None:
        nonlocal odds_id
        rows.append(
            (
                odds_id,
                game_id,
                "draftkings",
                "DraftKings",
                "h2h",
                captured_at,
                is_closing_line,
                home_price,
                away_price,
                None,
                None,
                None,
                "{}",
            )
        )
        odds_id += 1
        rows.append(
            (
                odds_id,
                game_id,
                "draftkings",
                "DraftKings",
                "spreads",
                captured_at,
                is_closing_line,
                -110.0,
                -110.0,
                home_spread,
                away_spread,
                None,
                "{}",
            )
        )
        odds_id += 1
        rows.append(
            (
                odds_id,
                game_id,
                "draftkings",
                "DraftKings",
                "totals",
                captured_at,
                is_closing_line,
                -110.0,
                -110.0,
                None,
                None,
                total_points,
                "{}",
            )
        )
        odds_id += 1

    for (
        game_id,
        captured_at,
        is_closing_line,
        home_price,
        away_price,
        home_spread,
        away_spread,
        total_points,
    ) in snapshot_specs:
        append_market_rows(
            game_id=game_id,
            captured_at=captured_at,
            is_closing_line=is_closing_line,
            home_price=home_price,
            away_price=away_price,
            home_spread=home_spread,
            away_spread=away_spread,
            total_points=total_points,
        )
    return rows


def _test_log_loss(probabilities: list[float], labels: list[int]) -> float:
    losses = [
        -(
            float(label) * log(min(max(probability, 1e-6), 1.0 - 1e-6))
            + (1.0 - float(label)) * log(min(max(1.0 - probability, 1e-6), 1.0 - 1e-6))
        )
        for probability, label in zip(probabilities, labels, strict=True)
    ]
    return sum(losses) / len(losses)
