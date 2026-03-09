from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cbb.modeling.dataset import GameOddsRecord, MarketSnapshotAggregate
from cbb.modeling.features import build_training_examples


def test_build_training_examples_adds_totals_features_to_spread_examples() -> None:
    total_open = MarketSnapshotAggregate(
        bookmaker_count=3,
        team1_price=None,
        team2_price=None,
        team1_point=None,
        team2_point=None,
        total_points=147.5,
        team1_implied_probability=None,
        team2_implied_probability=None,
        team1_probability_range=None,
        team2_probability_range=None,
        team1_point_range=None,
        team2_point_range=None,
        total_points_range=1.5,
    )
    total_close = MarketSnapshotAggregate(
        bookmaker_count=3,
        team1_price=None,
        team2_price=None,
        team1_point=None,
        team2_point=None,
        total_points=149.5,
        team1_implied_probability=None,
        team2_implied_probability=None,
        team1_probability_range=None,
        team2_probability_range=None,
        team1_point_range=None,
        team2_point_range=None,
        total_points_range=3.0,
    )
    h2h_open = MarketSnapshotAggregate(
        bookmaker_count=3,
        team1_price=-140.0,
        team2_price=120.0,
        team1_point=None,
        team2_point=None,
        total_points=None,
        team1_implied_probability=0.57,
        team2_implied_probability=0.43,
        team1_probability_range=0.02,
        team2_probability_range=0.02,
        team1_point_range=None,
        team2_point_range=None,
        total_points_range=None,
    )
    h2h_close = MarketSnapshotAggregate(
        bookmaker_count=3,
        team1_price=-150.0,
        team2_price=130.0,
        team1_point=None,
        team2_point=None,
        total_points=None,
        team1_implied_probability=0.60,
        team2_implied_probability=0.40,
        team1_probability_range=0.03,
        team2_probability_range=0.03,
        team1_point_range=None,
        team2_point_range=None,
        total_points_range=None,
    )
    spread_open = MarketSnapshotAggregate(
        bookmaker_count=3,
        team1_price=-110.0,
        team2_price=-110.0,
        team1_point=-3.5,
        team2_point=3.5,
        total_points=None,
        team1_implied_probability=0.51,
        team2_implied_probability=0.49,
        team1_probability_range=0.01,
        team2_probability_range=0.01,
        team1_point_range=0.5,
        team2_point_range=0.5,
        total_points_range=None,
    )
    spread_close = MarketSnapshotAggregate(
        bookmaker_count=3,
        team1_price=-110.0,
        team2_price=-110.0,
        team1_point=-4.5,
        team2_point=4.5,
        total_points=None,
        team1_implied_probability=0.52,
        team2_implied_probability=0.48,
        team1_probability_range=0.02,
        team2_probability_range=0.02,
        team1_point_range=0.5,
        team2_point_range=0.5,
        total_points_range=None,
    )
    record = GameOddsRecord(
        game_id=1,
        season=2026,
        game_date="2026-03-08",
        commence_time=datetime(2026, 3, 8, 18, 0, tzinfo=UTC),
        completed=True,
        home_score=78,
        away_score=70,
        home_team_id=10,
        home_team_name="Alpha Aces",
        away_team_id=20,
        away_team_name="Beta Bruins",
        home_h2h_price=-150.0,
        away_h2h_price=130.0,
        home_spread_line=-4.5,
        away_spread_line=4.5,
        home_spread_price=-110.0,
        away_spread_price=-110.0,
        total_points=149.5,
        h2h_open=h2h_open,
        h2h_close=h2h_close,
        spread_open=spread_open,
        spread_close=spread_close,
        total_open=total_open,
        total_close=total_close,
    )

    examples = build_training_examples(
        game_records=[record],
        market="spread",
        target_seasons={2026},
    )

    assert len(examples) == 2
    home_example = examples[0]
    away_example = examples[1]

    assert home_example.features["total_open_points"] == 147.5
    assert home_example.features["total_close_points"] == 149.5
    assert home_example.features["total_points_move"] == 2.0
    assert home_example.features["total_consensus_dispersion"] == 3.0
    assert home_example.features["total_books"] == 3.0
    assert home_example.features["total_move_abs"] == 2.0
    assert home_example.features["spread_line_move"] == pytest.approx(-1.0)
    assert home_example.features["spread_total_interaction"] == pytest.approx(
        -4.5 * 1.495
    )

    assert away_example.features["total_open_points"] == 147.5
    assert away_example.features["total_close_points"] == 149.5
    assert away_example.features["total_points_move"] == 2.0
    assert away_example.features["spread_total_interaction"] == pytest.approx(
        4.5 * 1.495
    )


def test_build_training_examples_sets_spread_margin_residual_target() -> None:
    record = GameOddsRecord(
        game_id=2,
        season=2026,
        game_date="2026-03-09",
        commence_time=datetime(2026, 3, 9, 18, 0, tzinfo=UTC),
        completed=True,
        home_score=78,
        away_score=70,
        home_team_id=10,
        home_team_name="Alpha Aces",
        away_team_id=20,
        away_team_name="Beta Bruins",
        home_h2h_price=-150.0,
        away_h2h_price=130.0,
        home_spread_line=-4.5,
        away_spread_line=4.5,
        home_spread_price=-110.0,
        away_spread_price=-110.0,
        total_points=149.5,
        h2h_open=None,
        h2h_close=None,
        spread_open=None,
        spread_close=None,
        total_open=None,
        total_close=None,
    )

    examples = build_training_examples(
        game_records=[record],
        market="spread",
        target_seasons={2026},
    )

    assert len(examples) == 2
    home_example = examples[0]
    away_example = examples[1]

    assert home_example.label == 1
    assert home_example.regression_target == pytest.approx(3.5)
    assert home_example.settlement == "win"

    assert away_example.label == 0
    assert away_example.regression_target == pytest.approx(-3.5)
    assert away_example.settlement == "loss"
