from cbb.modeling.backtest import (
    CandidateBlock,
    _select_tuned_spread_policy,
    _spread_policy_replay_candidate_policy,
)
from cbb.modeling.policy import BetPolicy, CandidateBet


def _make_candidate(
    *,
    game_id: int,
    commence_time: str,
    settlement: str,
    positive_ev_books: int,
    median_expected_value: float | None,
) -> CandidateBet:
    return CandidateBet(
        game_id=game_id,
        commence_time=commence_time,
        market="spread",
        team_name=f"Team {game_id}",
        opponent_name=f"Opponent {game_id}",
        side="team1",
        sportsbook=f"book-{game_id}",
        market_price=100.0,
        line_value=5.0,
        model_probability=0.60,
        implied_probability=0.50,
        probability_edge=0.10,
        expected_value=0.10,
        stake_fraction=0.02,
        settlement=settlement,
        eligible_books=max(positive_ev_books, 5),
        positive_ev_books=positive_ev_books,
        coverage_rate=1.0,
        median_expected_value=median_expected_value,
        minimum_games_played=20,
        market_book_count=max(positive_ev_books, 5),
    )


def _make_policy(**overrides: float | int | None) -> BetPolicy:
    policy_kwargs: dict[str, float | int | None] = {
        "min_edge": 0.04,
        "min_confidence": 0.518,
        "min_probability_edge": 0.04,
        "min_games_played": 8,
        "max_spread_abs_line": 10.0,
        "min_positive_ev_books": 4,
        "min_median_expected_value": None,
        "max_daily_exposure_fraction": 1.0,
        "max_bets_per_day": None,
    }
    policy_kwargs.update(overrides)
    return BetPolicy(
        **policy_kwargs,
    )


def test_spread_policy_replay_candidate_policy_relaxes_tuned_guards() -> None:
    base_policy = _make_policy(
        min_median_expected_value=0.01,
        uncertainty_probability_buffer=0.0075,
        max_abs_rest_days_diff=3.0,
    )

    replay_policy = _spread_policy_replay_candidate_policy(base_policy)

    assert replay_policy.min_confidence == 0.0
    assert replay_policy.min_games_played == 4
    assert replay_policy.max_spread_abs_line is None
    assert replay_policy.min_positive_ev_books == 2
    assert replay_policy.min_median_expected_value is None
    assert replay_policy.uncertainty_probability_buffer == 0.0075
    assert replay_policy.max_abs_rest_days_diff == 3.0


def test_select_tuned_spread_policy_can_raise_min_positive_ev_books() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time=f"2026-02-0{day}T18:00:00+00:00",
            candidates=(
                _make_candidate(
                    game_id=(day * 10) + 1,
                    commence_time=f"2026-02-0{day}T18:00:00+00:00",
                    settlement="loss",
                    positive_ev_books=4,
                    median_expected_value=0.03,
                ),
                _make_candidate(
                    game_id=(day * 10) + 2,
                    commence_time=f"2026-02-0{day}T18:00:00+00:00",
                    settlement="win",
                    positive_ev_books=5,
                    median_expected_value=0.03,
                ),
            ),
        )
        for day in range(1, 4)
    ]

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=_make_policy(),
        starting_bankroll=1000.0,
    )

    assert evaluation.policy.min_positive_ev_books == 5
    assert evaluation.policy.min_median_expected_value is None
    assert evaluation.bets_placed == 3
    assert evaluation.profit > 0.0


def test_select_tuned_spread_policy_can_add_median_ev_floor() -> None:
    candidate_blocks = [
        CandidateBlock(
            commence_time=f"2026-03-0{day}T18:00:00+00:00",
            candidates=(
                _make_candidate(
                    game_id=(day * 10) + 1,
                    commence_time=f"2026-03-0{day}T18:00:00+00:00",
                    settlement="loss",
                    positive_ev_books=4,
                    median_expected_value=0.003,
                ),
                _make_candidate(
                    game_id=(day * 10) + 2,
                    commence_time=f"2026-03-0{day}T18:00:00+00:00",
                    settlement="win",
                    positive_ev_books=4,
                    median_expected_value=0.012,
                ),
            ),
        )
        for day in range(1, 4)
    ]

    evaluation = _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=_make_policy(),
        starting_bankroll=1000.0,
    )

    assert evaluation.policy.min_positive_ev_books == 4
    assert evaluation.policy.min_median_expected_value == 0.005
    assert evaluation.bets_placed == 3
    assert evaluation.profit > 0.0
