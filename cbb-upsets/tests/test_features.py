from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cbb.modeling.dataset import (
    GameOddsRecord,
    MarketSnapshotAggregate,
    OddsSnapshotRecord,
)
from cbb.modeling.features import (
    ModelExample,
    build_training_examples,
    normalized_implied_probability_from_prices,
    repriced_spread_example,
)


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


def test_build_training_examples_adds_same_conference_feature_and_metadata() -> None:
    record = GameOddsRecord(
        game_id=22,
        season=2026,
        game_date="2026-03-10",
        commence_time=datetime(2026, 3, 10, 18, 0, tzinfo=UTC),
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
        home_conference_key="sec",
        home_conference_name="SEC",
        away_conference_key="sec",
        away_conference_name="SEC",
    )

    examples = build_training_examples(
        game_records=[record],
        market="spread",
        target_seasons={2026},
    )

    assert len(examples) == 2
    assert examples[0].features["same_conference_game"] == 1.0
    assert examples[0].team_conference_key == "sec"
    assert examples[0].opponent_conference_key == "sec"
    assert examples[1].features["same_conference_game"] == 1.0


def test_build_training_examples_carries_executable_quotes_per_book() -> None:
    record = GameOddsRecord(
        game_id=3,
        season=2026,
        game_date="2026-03-10",
        commence_time=datetime(2026, 3, 10, 18, 0, tzinfo=UTC),
        completed=True,
        home_score=76,
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
        current_h2h_quotes=(
            OddsSnapshotRecord(
                game_id=3,
                bookmaker_key="draftkings",
                market_key="h2h",
                captured_at=datetime(2026, 3, 10, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-150.0,
                team2_price=130.0,
                team1_point=None,
                team2_point=None,
                total_points=None,
            ),
            OddsSnapshotRecord(
                game_id=3,
                bookmaker_key="fanduel",
                market_key="h2h",
                captured_at=datetime(2026, 3, 10, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-145.0,
                team2_price=135.0,
                team1_point=None,
                team2_point=None,
                total_points=None,
            ),
        ),
        current_spread_quotes=(
            OddsSnapshotRecord(
                game_id=3,
                bookmaker_key="draftkings",
                market_key="spreads",
                captured_at=datetime(2026, 3, 10, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-110.0,
                team2_price=-110.0,
                team1_point=-4.5,
                team2_point=4.5,
                total_points=None,
            ),
            OddsSnapshotRecord(
                game_id=3,
                bookmaker_key="fanduel",
                market_key="spreads",
                captured_at=datetime(2026, 3, 10, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-105.0,
                team2_price=-115.0,
                team1_point=-4.0,
                team2_point=4.0,
                total_points=None,
            ),
        ),
    )

    moneyline_examples = build_training_examples(
        game_records=[record],
        market="moneyline",
        target_seasons={2026},
    )
    spread_examples = build_training_examples(
        game_records=[record],
        market="spread",
        target_seasons={2026},
    )

    assert [
        quote.market_price for quote in moneyline_examples[0].executable_quotes
    ] == [-150.0, -145.0]
    assert [
        quote.market_price for quote in moneyline_examples[1].executable_quotes
    ] == [130.0, 135.0]
    assert [
        (quote.line_value, quote.market_price)
        for quote in spread_examples[0].executable_quotes
    ] == [(-4.5, -110.0), (-4.0, -105.0)]
    assert [
        (quote.line_value, quote.market_price)
        for quote in spread_examples[1].executable_quotes
    ] == [(4.5, -110.0), (4.0, -115.0)]


def test_repriced_spread_example_updates_line_features() -> None:
    example = ModelExample(
        game_id=11,
        season=2026,
        commence_time="2026-03-10T20:00:00+00:00",
        market="spread",
        team_name="Alpha Aces",
        opponent_name="Beta Bruins",
        side="home",
        features={
            "spread_line": -4.5,
            "spread_abs_line": 4.5,
            "spread_total_interaction": -6.75,
            "total_close_points": 150.0,
        },
        label=None,
        settlement="pending",
        market_price=-110.0,
        market_implied_probability=0.5,
        minimum_games_played=10,
        line_value=-4.5,
    )

    repriced_example = repriced_spread_example(
        example=example,
        line_value=-3.5,
    )

    assert repriced_example.line_value == -3.5
    assert repriced_example.features["spread_line"] == -3.5
    assert repriced_example.features["spread_abs_line"] == 3.5
    assert repriced_example.features["spread_total_interaction"] == pytest.approx(
        -5.25
    )


def test_build_training_examples_resets_team_form_at_season_boundary() -> None:
    prior_season_record = GameOddsRecord(
        game_id=12,
        season=2025,
        game_date="2025-03-01",
        commence_time=datetime(2025, 3, 1, 18, 0, tzinfo=UTC),
        completed=True,
        home_score=80,
        away_score=70,
        home_team_id=10,
        home_team_name="Alpha Aces",
        away_team_id=20,
        away_team_name="Beta Bruins",
        home_h2h_price=-140.0,
        away_h2h_price=120.0,
        home_spread_line=-4.0,
        away_spread_line=4.0,
        home_spread_price=-110.0,
        away_spread_price=-110.0,
        total_points=148.5,
        h2h_open=None,
        h2h_close=None,
        spread_open=None,
        spread_close=None,
        total_open=None,
        total_close=None,
    )
    new_season_record = GameOddsRecord(
        game_id=13,
        season=2026,
        game_date="2026-11-10",
        commence_time=datetime(2026, 11, 10, 18, 0, tzinfo=UTC),
        completed=True,
        home_score=75,
        away_score=72,
        home_team_id=10,
        home_team_name="Alpha Aces",
        away_team_id=20,
        away_team_name="Beta Bruins",
        home_h2h_price=-135.0,
        away_h2h_price=115.0,
        home_spread_line=-3.5,
        away_spread_line=3.5,
        home_spread_price=-110.0,
        away_spread_price=-110.0,
        total_points=146.5,
        h2h_open=None,
        h2h_close=None,
        spread_open=None,
        spread_close=None,
        total_open=None,
        total_close=None,
    )

    examples = build_training_examples(
        game_records=[prior_season_record, new_season_record],
        market="spread",
        target_seasons={2026},
    )

    assert len(examples) == 2
    home_example = examples[0]
    away_example = examples[1]

    assert home_example.features["side_games_played"] == 0.0
    assert home_example.features["opponent_games_played"] == 0.0
    assert home_example.features["min_season_games_played"] == 0.0
    assert home_example.features["season_opener"] == 1.0
    assert home_example.features["early_season"] == 1.0
    assert home_example.features["season_elo_shift_diff"] == 0.0
    assert home_example.features["carryover_elo_diff"] > 0.0

    assert away_example.features["season_opener"] == 1.0
    assert away_example.features["carryover_elo_diff"] < 0.0


def test_build_training_examples_adds_bookmaker_quality_features() -> None:
    prior_record = GameOddsRecord(
        game_id=20,
        season=2025,
        game_date="2025-03-01",
        commence_time=datetime(2025, 3, 1, 18, 0, tzinfo=UTC),
        completed=True,
        home_score=80,
        away_score=75,
        home_team_id=10,
        home_team_name="Alpha Aces",
        away_team_id=20,
        away_team_name="Beta Bruins",
        home_h2h_price=-150.0,
        away_h2h_price=130.0,
        home_spread_line=-5.0,
        away_spread_line=5.0,
        home_spread_price=-110.0,
        away_spread_price=-110.0,
        total_points=148.5,
        h2h_open=None,
        h2h_close=None,
        spread_open=None,
        spread_close=None,
        total_open=None,
        total_close=None,
        current_h2h_quotes=(
            OddsSnapshotRecord(
                game_id=20,
                bookmaker_key="draftkings",
                market_key="h2h",
                captured_at=datetime(2025, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-150.0,
                team2_price=130.0,
                team1_point=None,
                team2_point=None,
                total_points=None,
            ),
            OddsSnapshotRecord(
                game_id=20,
                bookmaker_key="fanduel",
                market_key="h2h",
                captured_at=datetime(2025, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=130.0,
                team2_price=-150.0,
                team1_point=None,
                team2_point=None,
                total_points=None,
            ),
        ),
        current_spread_quotes=(
            OddsSnapshotRecord(
                game_id=20,
                bookmaker_key="draftkings",
                market_key="spreads",
                captured_at=datetime(2025, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-110.0,
                team2_price=-110.0,
                team1_point=-5.0,
                team2_point=5.0,
                total_points=None,
            ),
            OddsSnapshotRecord(
                game_id=20,
                bookmaker_key="fanduel",
                market_key="spreads",
                captured_at=datetime(2025, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-110.0,
                team2_price=-110.0,
                team1_point=-2.0,
                team2_point=2.0,
                total_points=None,
            ),
        ),
    )
    target_record = GameOddsRecord(
        game_id=21,
        season=2026,
        game_date="2026-03-01",
        commence_time=datetime(2026, 3, 1, 18, 0, tzinfo=UTC),
        completed=True,
        home_score=77,
        away_score=74,
        home_team_id=10,
        home_team_name="Alpha Aces",
        away_team_id=20,
        away_team_name="Beta Bruins",
        home_h2h_price=-105.0,
        away_h2h_price=-115.0,
        home_spread_line=-3.0,
        away_spread_line=3.0,
        home_spread_price=-110.0,
        away_spread_price=-110.0,
        total_points=145.5,
        h2h_open=None,
        h2h_close=None,
        spread_open=None,
        spread_close=None,
        total_open=None,
        total_close=None,
        current_h2h_quotes=(
            OddsSnapshotRecord(
                game_id=21,
                bookmaker_key="draftkings",
                market_key="h2h",
                captured_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-105.0,
                team2_price=-115.0,
                team1_point=None,
                team2_point=None,
                total_points=None,
            ),
            OddsSnapshotRecord(
                game_id=21,
                bookmaker_key="fanduel",
                market_key="h2h",
                captured_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-180.0,
                team2_price=150.0,
                team1_point=None,
                team2_point=None,
                total_points=None,
            ),
        ),
        current_spread_quotes=(
            OddsSnapshotRecord(
                game_id=21,
                bookmaker_key="draftkings",
                market_key="spreads",
                captured_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-110.0,
                team2_price=-110.0,
                team1_point=-3.0,
                team2_point=3.0,
                total_points=None,
            ),
            OddsSnapshotRecord(
                game_id=21,
                bookmaker_key="fanduel",
                market_key="spreads",
                captured_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
                is_closing_line=False,
                team1_price=-110.0,
                team2_price=-110.0,
                team1_point=-6.0,
                team2_point=6.0,
                total_points=None,
            ),
        ),
    )

    examples = build_training_examples(
        game_records=[prior_record, target_record],
        market="spread",
        target_seasons={2026},
    )

    home_example = examples[0]
    draftkings_probability = normalized_implied_probability_from_prices(
        side_american_price=-105.0,
        opponent_american_price=-115.0,
    )
    fanduel_probability = normalized_implied_probability_from_prices(
        side_american_price=-180.0,
        opponent_american_price=150.0,
    )

    assert draftkings_probability is not None
    assert fanduel_probability is not None
    assert (
        draftkings_probability
        < home_example.features["h2h_weighted_implied_probability"]
        < fanduel_probability
    )
    assert abs(
        home_example.features["h2h_weighted_implied_probability"]
        - draftkings_probability
    ) < abs(
        home_example.features["h2h_weighted_implied_probability"]
        - fanduel_probability
    )
    assert home_example.features["h2h_best_quote_value_edge"] > 0.0
    assert home_example.features["h2h_best_quote_book_quality"] > 1.0
    assert home_example.features["spread_weighted_line"] > -4.5
    assert home_example.features["spread_best_quote_line_edge"] == pytest.approx(0.0)
    assert home_example.features["spread_best_quote_book_quality"] > 0.0
