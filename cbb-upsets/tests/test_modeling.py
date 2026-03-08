from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from math import log
from pathlib import Path

from cbb.modeling.artifacts import (
    ModelArtifact,
    MoneylineBandModel,
    TrainingMetrics,
    save_artifact,
)
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
from cbb.modeling.features import (
    ModelExample,
    normalized_implied_probability_from_prices,
)
from cbb.modeling.infer import _load_prediction_artifacts
from cbb.modeling.policy import CandidateBet, score_candidate_bet, select_best_candidates
from cbb.modeling.backtest import (
    CandidateBlock,
    PolicyEvaluation,
    _select_tuned_spread_policy,
)
from cbb.modeling.train import (
    DEFAULT_MONEYLINE_TRAIN_MAX_PRICE,
    DEFAULT_MONEYLINE_TRAIN_MIN_PRICE,
    apply_platt_scaling,
    calibrate_probabilities,
    fit_platt_scaling,
    score_examples,
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
                min_examples=8,
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
    assert artifact.moneyline_price_min is None
    assert artifact.moneyline_price_max is None
    assert artifact.moneyline_segment_calibrations == ()


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
    assert summary.candidates_considered >= 1
    assert summary.bets_placed >= 1
    assert summary.recommendations[0].market in {"moneyline", "spread"}
    assert summary.recommendations[0].stake_amount > 0


def test_predict_best_bets_auto_tunes_spread_policy(tmp_path: Path, monkeypatch) -> None:
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
            profitable_block_rate=0.5,
            worst_block_roi=-0.05,
            block_roi_stddev=0.04,
            stability_score=0.05,
            max_drawdown=0.02,
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


def test_load_prediction_artifacts_for_best_keeps_spread_and_moneyline(
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

    assert [market for market, _artifact in loaded_artifacts] == [
        "spread",
        "moneyline",
    ]


def test_normalized_implied_probability_removes_vig() -> None:
    assert normalized_implied_probability_from_prices(
        side_american_price=-110.0,
        opponent_american_price=-110.0,
    ) == 0.5


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
        features={},
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


def test_calibrate_probabilities_shrinks_extreme_moneyline_prices_toward_market() -> None:
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


def test_score_examples_dispatches_moneyline_band_models_by_price() -> None:
    artifact = ModelArtifact(
        market="moneyline",
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

    assert evaluation.policy.max_spread_abs_line == 10.0
    assert evaluation.profit > 0


def test_select_tuned_spread_policy_prefers_roi_stability_over_raw_profit() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time="2026-01-01T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=11,
                    commence_time="2026-01-01T19:00:00+00:00",
                    market="spread",
                    team_name="Alpha Aces",
                    opponent_name="Beta Bruins",
                    side="home",
                    market_price=100.0,
                    line_value=3.5,
                    model_probability=0.60,
                    implied_probability=0.50,
                    probability_edge=0.10,
                    expected_value=0.03,
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
                    game_id=12,
                    commence_time="2026-01-08T19:00:00+00:00",
                    market="spread",
                    team_name="Gamma Gulls",
                    opponent_name="Delta Dogs",
                    side="away",
                    market_price=100.0,
                    line_value=4.5,
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
            commence_time="2026-01-15T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=13,
                    commence_time="2026-01-15T19:00:00+00:00",
                    market="spread",
                    team_name="Iota Iguanas",
                    opponent_name="Kappa Knights",
                    side="home",
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
            commence_time="2026-01-22T19:00:00+00:00",
            candidates=(
                CandidateBet(
                    game_id=14,
                    commence_time="2026-01-22T19:00:00+00:00",
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
                    settlement="loss",
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

    assert evaluation.policy.min_edge >= 0.02
    assert evaluation.roi == 1.0
    assert evaluation.profit > 0


def _create_model_test_environment(tmp_path: Path) -> tuple[str, Path]:
    database_path = tmp_path / "modeling.sqlite"
    artifacts_dir = tmp_path / "artifacts"
    _create_model_test_db(database_path)
    return f"sqlite:///{database_path}", artifacts_dir


def _create_model_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE teams (
            team_id INTEGER PRIMARY KEY,
            team_key TEXT NOT NULL UNIQUE,
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
        "INSERT INTO teams (team_id, team_key, name) VALUES (?, ?, ?)",
        [
            (1, "alpha-aces", "Alpha Aces"),
            (2, "beta-bruins", "Beta Bruins"),
            (3, "gamma-gulls", "Gamma Gulls"),
            (4, "delta-dogs", "Delta Dogs"),
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
            )
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
    game_lines = [
        (1, "2024-11-05T18:30:00+00:00", -130.0, 110.0, -3.5, 3.5, 146.5),
        (2, "2024-11-10T19:30:00+00:00", -125.0, 105.0, -2.5, 2.5, 142.5),
        (3, "2025-01-15T18:30:00+00:00", 145.0, -165.0, 4.5, -4.5, 144.5),
        (4, "2025-01-20T18:30:00+00:00", 135.0, -155.0, 3.5, -3.5, 141.5),
        (5, "2025-11-05T18:30:00+00:00", -120.0, 100.0, -2.5, 2.5, 145.5),
        (6, "2025-11-10T19:30:00+00:00", -110.0, -110.0, -1.5, 1.5, 143.5),
        (7, "2026-02-20T18:30:00+00:00", 145.0, -165.0, 4.5, -4.5, 147.5),
        (8, "2026-02-25T19:30:00+00:00", 140.0, -160.0, 4.0, -4.0, 144.0),
        (9, "2026-03-09T18:30:00+00:00", -115.0, -105.0, -1.5, 1.5, 145.0),
        (10, "2026-03-10T19:30:00+00:00", 105.0, -125.0, 1.5, -1.5, 140.5),
    ]
    for (
        game_id,
        captured_at,
        home_price,
        away_price,
        home_spread,
        away_spread,
        total,
    ) in game_lines:
        rows.append(
            (
                odds_id,
                game_id,
                "draftkings",
                "DraftKings",
                "h2h",
                captured_at,
                1,
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
                1,
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
                1,
                -110.0,
                -110.0,
                None,
                None,
                total,
                "{}",
            )
        )
        odds_id += 1
    return rows


def _test_log_loss(probabilities: list[float], labels: list[int]) -> float:
    losses = [
        -(
            float(label) * log(min(max(probability, 1e-6), 1.0 - 1e-6))
            + (1.0 - float(label))
            * log(min(max(1.0 - probability, 1e-6), 1.0 - 1e-6))
        )
        for probability, label in zip(probabilities, labels, strict=True)
    ]
    return sum(losses) / len(losses)
