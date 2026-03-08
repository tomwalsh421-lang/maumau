"""Bet selection and stake sizing policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from cbb.modeling.artifacts import ModelMarket
from cbb.modeling.features import ModelExample, implied_probability_from_american


@dataclass(frozen=True)
class BetPolicy:
    """Risk controls for converting model scores into bets."""

    min_edge: float = 0.01
    min_confidence: float = 0.50
    kelly_fraction: float = 0.25
    max_bet_fraction: float = 0.05
    max_daily_exposure_fraction: float = 0.20


@dataclass(frozen=True)
class CandidateBet:
    """Scored market opportunity before bankroll limits are applied."""

    game_id: int
    commence_time: str
    market: ModelMarket
    team_name: str
    opponent_name: str
    side: str
    market_price: float
    line_value: float | None
    model_probability: float
    implied_probability: float
    expected_value: float
    stake_fraction: float
    settlement: str


@dataclass(frozen=True)
class PlacedBet:
    """Bet after bankroll sizing has been applied."""

    game_id: int
    commence_time: str
    market: ModelMarket
    team_name: str
    opponent_name: str
    side: str
    market_price: float
    line_value: float | None
    model_probability: float
    implied_probability: float
    expected_value: float
    stake_fraction: float
    stake_amount: float
    settlement: str


def score_candidate_bet(
    *,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
) -> CandidateBet | None:
    """Turn one scored example into a candidate bet."""
    if example.market_price is None:
        return None
    if probability < policy.min_confidence:
        return None

    implied_probability = implied_probability_from_american(example.market_price)
    if implied_probability is None:
        return None

    expected_value = expected_value_from_american(
        probability=probability,
        american_price=example.market_price,
    )
    if expected_value < policy.min_edge:
        return None

    raw_kelly = kelly_fraction_from_american(
        probability=probability,
        american_price=example.market_price,
    )
    if raw_kelly <= 0:
        return None

    stake_fraction = min(
        policy.max_bet_fraction,
        raw_kelly * policy.kelly_fraction,
    )
    if stake_fraction <= 0:
        return None

    return CandidateBet(
        game_id=example.game_id,
        commence_time=example.commence_time,
        market=example.market,
        team_name=example.team_name,
        opponent_name=example.opponent_name,
        side=example.side,
        market_price=example.market_price,
        line_value=example.line_value,
        model_probability=probability,
        implied_probability=implied_probability,
        expected_value=expected_value,
        stake_fraction=stake_fraction,
        settlement=example.settlement,
    )


def apply_bankroll_limits(
    *,
    bankroll: float,
    policy: BetPolicy,
    candidate_bets: list[CandidateBet],
) -> list[PlacedBet]:
    """Apply per-day exposure limits to already-scored candidate bets."""
    if bankroll <= 0:
        return []

    grouped_by_day: dict[date, list[CandidateBet]] = {}
    for candidate in candidate_bets:
        game_day = date.fromisoformat(candidate.commence_time[:10])
        grouped_by_day.setdefault(game_day, []).append(candidate)

    placed_bets: list[PlacedBet] = []
    for game_day in sorted(grouped_by_day):
        daily_limit = bankroll * policy.max_daily_exposure_fraction
        daily_exposure = 0.0
        for candidate in sorted(
            grouped_by_day[game_day],
            key=lambda item: (
                -item.expected_value,
                -item.model_probability,
                item.game_id,
                item.market,
            ),
        ):
            stake_amount = min(
                bankroll * candidate.stake_fraction,
                daily_limit - daily_exposure,
            )
            if stake_amount <= 0:
                continue
            placed_bets.append(
                PlacedBet(
                    game_id=candidate.game_id,
                    commence_time=candidate.commence_time,
                    market=candidate.market,
                    team_name=candidate.team_name,
                    opponent_name=candidate.opponent_name,
                    side=candidate.side,
                    market_price=candidate.market_price,
                    line_value=candidate.line_value,
                    model_probability=candidate.model_probability,
                    implied_probability=candidate.implied_probability,
                    expected_value=candidate.expected_value,
                    stake_fraction=candidate.stake_fraction,
                    stake_amount=stake_amount,
                    settlement=candidate.settlement,
                )
            )
            daily_exposure += stake_amount
    return placed_bets


def select_best_candidates(candidate_bets: list[CandidateBet]) -> list[CandidateBet]:
    """Keep at most one market per game, preferring the strongest edge."""
    best_by_game: dict[int, CandidateBet] = {}
    for candidate in candidate_bets:
        current_best = best_by_game.get(candidate.game_id)
        if current_best is None or _candidate_sort_key(candidate) < _candidate_sort_key(
            current_best
        ):
            best_by_game[candidate.game_id] = candidate
    return [
        best_by_game[game_id]
        for game_id in sorted(
            best_by_game,
            key=lambda game_id: _candidate_sort_key(best_by_game[game_id]),
        )
    ]


def american_to_decimal_odds(american_price: float) -> float:
    """Convert American odds into decimal odds."""
    if american_price > 0:
        return (american_price / 100.0) + 1.0
    return (100.0 / -american_price) + 1.0


def expected_value_from_american(*, probability: float, american_price: float) -> float:
    """Return expected profit per staked dollar."""
    decimal_odds = american_to_decimal_odds(american_price)
    payout_multiple = decimal_odds - 1.0
    return probability * payout_multiple - (1.0 - probability)


def kelly_fraction_from_american(*, probability: float, american_price: float) -> float:
    """Return the full Kelly bet fraction for one priced side."""
    decimal_odds = american_to_decimal_odds(american_price)
    payout_multiple = decimal_odds - 1.0
    if payout_multiple <= 0:
        return 0.0
    kelly = (probability * payout_multiple - (1.0 - probability)) / payout_multiple
    return max(0.0, kelly)


def settle_bet(placed_bet: PlacedBet) -> float:
    """Return net bankroll profit for one settled bet."""
    if placed_bet.settlement == "push":
        return 0.0
    if placed_bet.settlement == "win":
        return placed_bet.stake_amount * (
            american_to_decimal_odds(placed_bet.market_price) - 1.0
        )
    return -placed_bet.stake_amount


def _candidate_sort_key(candidate: CandidateBet) -> tuple[float, float, int, str]:
    return (
        -candidate.expected_value,
        -candidate.model_probability,
        candidate.game_id,
        candidate.market,
    )
