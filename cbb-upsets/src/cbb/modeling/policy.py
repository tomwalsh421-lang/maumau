"""Bet selection and stake sizing policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from cbb.modeling.artifacts import ModelMarket
from cbb.modeling.features import ModelExample, implied_probability_from_american

BEST_CANDIDATE_MARKET_PRIORITY: dict[ModelMarket, int] = {
    "spread": 0,
    "moneyline": 1,
}


@dataclass(frozen=True)
class BetPolicy:
    """Risk controls for converting model scores into bets."""

    min_edge: float = 0.02
    min_confidence: float = 0.0
    min_probability_edge: float = 0.025
    min_games_played: int = 8
    kelly_fraction: float = 0.10
    max_bet_fraction: float = 0.02
    max_daily_exposure_fraction: float = 0.05
    min_moneyline_price: float = -500.0
    max_moneyline_price: float = 125.0
    max_spread_abs_line: float | None = None
    max_abs_rest_days_diff: float | None = None
    min_positive_ev_books: int = 1
    min_median_expected_value: float | None = None


@dataclass(frozen=True)
class SupportingQuote:
    """One additional sportsbook quote that supports the selected side."""

    sportsbook: str
    line_value: float | None
    market_price: float
    expected_value: float


DEFAULT_DEPLOYABLE_SPREAD_POLICY = BetPolicy(
    min_edge=0.04,
    min_confidence=0.518,
    min_probability_edge=0.04,
    min_games_played=8,
    max_spread_abs_line=10.0,
    max_abs_rest_days_diff=3.0,
    min_positive_ev_books=2,
)


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
    probability_edge: float
    expected_value: float
    stake_fraction: float
    settlement: str
    sportsbook: str = ""
    eligible_books: int = 0
    positive_ev_books: int = 0
    coverage_rate: float = 0.0
    supporting_quotes: tuple[SupportingQuote, ...] = ()
    min_acceptable_line: float | None = None
    min_acceptable_price: float | None = None
    minimum_games_played: int = 0
    abs_rest_days_diff: float = 0.0


def build_candidate_bet(
    *,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
) -> CandidateBet | None:
    """Build one candidate bet before policy threshold filtering."""
    return build_candidate_bet_for_quote(
        example=example,
        probability=probability,
        policy=policy,
        sportsbook="",
        market_price=example.market_price,
        implied_probability=example.market_implied_probability,
        line_value=example.line_value,
    )


def build_candidate_bet_for_quote(
    *,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
    sportsbook: str,
    market_price: float | None,
    implied_probability: float | None,
    line_value: float | None,
) -> CandidateBet | None:
    """Build one candidate bet for a specific executable quote."""
    candidate = score_candidate_bet_for_quote(
        example=example,
        probability=probability,
        policy=policy,
        sportsbook=sportsbook,
        market_price=market_price,
        implied_probability=implied_probability,
        line_value=line_value,
    )
    if candidate is None or candidate.stake_fraction <= 0.0:
        return None
    return candidate


def score_candidate_bet_for_quote(
    *,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
    sportsbook: str,
    market_price: float | None,
    implied_probability: float | None,
    line_value: float | None,
) -> CandidateBet | None:
    """Score one quote even when its EV is not high enough to stake."""
    if market_price is None:
        return None

    effective_implied_probability = (
        implied_probability or implied_probability_from_american(market_price)
    )
    if effective_implied_probability is None:
        return None

    expected_value = expected_value_from_american(
        probability=probability,
        american_price=market_price,
    )
    raw_kelly = kelly_fraction_from_american(
        probability=probability,
        american_price=market_price,
    )
    stake_fraction = (
        min(policy.max_bet_fraction, raw_kelly * policy.kelly_fraction)
        if raw_kelly > 0.0
        else 0.0
    )

    return CandidateBet(
        game_id=example.game_id,
        commence_time=example.commence_time,
        market=example.market,
        team_name=example.team_name,
        opponent_name=example.opponent_name,
        side=example.side,
        sportsbook=sportsbook,
        market_price=market_price,
        line_value=line_value,
        model_probability=probability,
        implied_probability=effective_implied_probability,
        probability_edge=probability - effective_implied_probability,
        expected_value=expected_value,
        stake_fraction=stake_fraction,
        settlement=example.settlement,
        minimum_games_played=example.minimum_games_played,
        abs_rest_days_diff=abs(example.features.get("rest_days_diff", 0.0)),
    )


def candidate_matches_policy(
    *,
    candidate: CandidateBet,
    policy: BetPolicy,
) -> bool:
    """Return whether one raw candidate clears the selection policy."""
    if not candidate_matches_non_edge_policy(
        candidate=candidate,
        policy=policy,
    ):
        return False
    if candidate.probability_edge < policy.min_probability_edge:
        return False
    if candidate.expected_value < policy.min_edge:
        return False
    return True


def candidate_matches_non_edge_policy(
    *,
    candidate: CandidateBet,
    policy: BetPolicy,
) -> bool:
    """Return whether one candidate clears non-edge guardrails."""
    if candidate.minimum_games_played < policy.min_games_played:
        return False
    if (
        candidate.market == "moneyline"
        and (
            candidate.market_price < policy.min_moneyline_price
            or candidate.market_price > policy.max_moneyline_price
        )
    ):
        return False
    if (
        candidate.market == "spread"
        and policy.max_spread_abs_line is not None
        and (
            candidate.line_value is None
            or abs(candidate.line_value) > policy.max_spread_abs_line
        )
    ):
        return False
    if (
        candidate.market == "spread"
        and policy.max_abs_rest_days_diff is not None
        and candidate.abs_rest_days_diff > policy.max_abs_rest_days_diff
    ):
        return False
    if candidate.model_probability < policy.min_confidence:
        return False
    return True


def deployable_spread_policy(policy: BetPolicy) -> BetPolicy:
    """Resolve the fixed deployable spread policy used by default."""
    if policy == BetPolicy():
        return DEFAULT_DEPLOYABLE_SPREAD_POLICY
    return policy


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
    probability_edge: float
    expected_value: float
    stake_fraction: float
    stake_amount: float
    settlement: str
    sportsbook: str = ""
    eligible_books: int = 0
    positive_ev_books: int = 0
    coverage_rate: float = 0.0
    supporting_quotes: tuple[SupportingQuote, ...] = ()
    min_acceptable_line: float | None = None
    min_acceptable_price: float | None = None


def score_candidate_bet(
    *,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
) -> CandidateBet | None:
    """Turn one scored example into a candidate bet."""
    candidate = build_candidate_bet(
        example=example,
        probability=probability,
        policy=policy,
    )
    if candidate is None or not candidate_matches_policy(
        candidate=candidate,
        policy=policy,
    ):
        return None
    return candidate


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
                    sportsbook=candidate.sportsbook,
                    market_price=candidate.market_price,
                    line_value=candidate.line_value,
                    model_probability=candidate.model_probability,
                    implied_probability=candidate.implied_probability,
                    probability_edge=candidate.probability_edge,
                    expected_value=candidate.expected_value,
                    stake_fraction=candidate.stake_fraction,
                    stake_amount=stake_amount,
                    settlement=candidate.settlement,
                    eligible_books=candidate.eligible_books,
                    positive_ev_books=candidate.positive_ev_books,
                    coverage_rate=candidate.coverage_rate,
                    supporting_quotes=candidate.supporting_quotes,
                    min_acceptable_line=candidate.min_acceptable_line,
                    min_acceptable_price=candidate.min_acceptable_price,
                )
            )
            daily_exposure += stake_amount
    return placed_bets


def select_best_candidates(candidate_bets: list[CandidateBet]) -> list[CandidateBet]:
    """Keep at most one market per game, preferring spread-first deployment."""
    candidate_bets = select_best_quote_candidates(candidate_bets)
    best_by_game: dict[int, CandidateBet] = {}
    for candidate in candidate_bets:
        current_best = best_by_game.get(candidate.game_id)
        if current_best is None or _best_candidate_sort_key(
            candidate
        ) < _best_candidate_sort_key(current_best):
            best_by_game[candidate.game_id] = candidate
    return [
        best_by_game[game_id]
        for game_id in sorted(
            best_by_game,
            key=lambda game_id: _candidate_sort_key(best_by_game[game_id]),
        )
    ]


def select_best_quote_candidates(
    candidate_bets: list[CandidateBet],
) -> list[CandidateBet]:
    """Keep the single best executable quote for each game, market, and side."""
    best_by_scope: dict[tuple[int, ModelMarket, str], CandidateBet] = {}
    for candidate in candidate_bets:
        scope_key = (candidate.game_id, candidate.market, candidate.side)
        current_best = best_by_scope.get(scope_key)
        if current_best is None or _candidate_sort_key(
            candidate
        ) < _candidate_sort_key(current_best):
            best_by_scope[scope_key] = candidate
    return [
        best_by_scope[scope_key]
        for scope_key in sorted(
            best_by_scope,
            key=lambda scope_key: _candidate_sort_key(best_by_scope[scope_key]),
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


def _candidate_sort_key(
    candidate: CandidateBet,
) -> tuple[float, int, float, float, float, int, str, ModelMarket]:
    return (
        -candidate.coverage_rate,
        -candidate.positive_ev_books,
        -candidate.expected_value,
        -candidate.probability_edge,
        -candidate.model_probability,
        candidate.game_id,
        candidate.sportsbook,
        candidate.market,
    )


def _best_candidate_sort_key(
    candidate: CandidateBet,
) -> tuple[int, float, int, float, float, float, int, str]:
    return (
        BEST_CANDIDATE_MARKET_PRIORITY.get(candidate.market, 99),
        -candidate.coverage_rate,
        -candidate.positive_ev_books,
        -candidate.expected_value,
        -candidate.probability_edge,
        -candidate.model_probability,
        candidate.game_id,
        candidate.sportsbook,
    )
