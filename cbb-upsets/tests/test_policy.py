from cbb.modeling.policy import (
    BetPolicy,
    CandidateBet,
    apply_bankroll_limits_with_diagnostics,
)


def _candidate(game_id: int, expected_value: float) -> CandidateBet:
    return CandidateBet(
        game_id=game_id,
        commence_time="2026-03-01T19:00:00+00:00",
        market="spread",
        team_name=f"Team {game_id}",
        opponent_name=f"Opponent {game_id}",
        side="home",
        sportsbook="draftkings",
        market_price=-110.0,
        line_value=-3.5,
        model_probability=0.56,
        implied_probability=0.50,
        probability_edge=expected_value,
        expected_value=expected_value,
        stake_fraction=0.01,
        settlement="win",
        coverage_rate=0.90,
        positive_ev_books=5,
        median_expected_value=expected_value,
        market_book_count=6,
    )


def test_apply_bankroll_limits_tracks_cap_boundary_pair() -> None:
    result = apply_bankroll_limits_with_diagnostics(
        bankroll=1000.0,
        policy=BetPolicy(
            max_bets_per_day=5,
            max_daily_exposure_fraction=1.0,
            max_bet_fraction=1.0,
            kelly_fraction=1.0,
        ),
        candidate_bets=[
            _candidate(1, 0.12),
            _candidate(2, 0.11),
            _candidate(3, 0.10),
            _candidate(4, 0.09),
            _candidate(5, 0.08),
            _candidate(6, 0.07),
        ],
    )

    assert len(result.placed_bets) == 5
    assert len(result.skipped_by_bet_cap_candidates) == 1
    assert len(result.bet_cap_boundary_pairs) == 1
    assert result.bet_cap_boundary_pairs[0].placed_bet.game_id == 5
    assert result.bet_cap_boundary_pairs[0].skipped_candidate.game_id == 6
