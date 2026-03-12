"""Bet selection and stake sizing policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from cbb.modeling.artifacts import ModelMarket
from cbb.modeling.features import ModelExample, implied_probability_from_american

BEST_CANDIDATE_MARKET_PRIORITY: dict[ModelMarket, int] = {
    "spread": 0,
    "moneyline": 1,
}
POWER_CONFERENCE_KEYS = frozenset(
    {
        "atlantic-coast-conference",
        "big-12-conference",
        "big-east-conference",
        "big-ten-conference",
        "pac-12-conference",
        "southeastern-conference",
    }
)
MID_MAJOR_CONFERENCE_KEYS = frozenset(
    {
        "american-athletic-conference",
        "atlantic-10-conference",
        "conference-usa",
        "missouri-valley-conference",
        "mountain-west-conference",
        "west-coast-conference",
    }
)
SPREAD_SEGMENT_DIMENSIONS = (
    "expected_value_bucket",
    "probability_edge_bucket",
    "season_phase",
    "line_bucket",
    "book_depth",
    "same_conference",
    "conference_group",
    "tip_window",
)


@dataclass(frozen=True)
class BetPolicy:
    """Risk controls for converting model scores into bets."""

    min_edge: float = 0.02
    min_confidence: float = 0.0
    min_probability_edge: float = 0.025
    uncertainty_probability_buffer: float = 0.0
    min_games_played: int = 8
    kelly_fraction: float = 0.10
    max_bet_fraction: float = 0.02
    max_daily_exposure_fraction: float = 0.05
    max_bets_per_day: int | None = None
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
    uncertainty_probability_buffer=0.0075,
    min_games_played=8,
    max_spread_abs_line=10.0,
    max_abs_rest_days_diff=3.0,
    min_positive_ev_books=2,
    max_bets_per_day=6,
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
    market_book_count: int = 0
    team_conference_key: str | None = None
    team_conference_name: str | None = None
    opponent_conference_key: str | None = None
    opponent_conference_name: str | None = None
    same_conference_game: bool | None = None
    observation_time: str | None = None


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

    effective_probability = _conservative_quote_probability(
        example=example,
        probability=probability,
        line_value=line_value,
        policy=policy,
    )
    expected_value = expected_value_from_american(
        probability=effective_probability,
        american_price=market_price,
    )
    raw_kelly = kelly_fraction_from_american(
        probability=effective_probability,
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
        probability_edge=effective_probability - effective_implied_probability,
        expected_value=expected_value,
        stake_fraction=stake_fraction,
        settlement=example.settlement,
        minimum_games_played=example.minimum_games_played,
        abs_rest_days_diff=abs(example.features.get("rest_days_diff", 0.0)),
        market_book_count=max(
            int(round(float(example.features.get("spread_books", 0.0)))),
            len(example.executable_quotes),
        ),
        team_conference_key=example.team_conference_key,
        team_conference_name=example.team_conference_name,
        opponent_conference_key=example.opponent_conference_key,
        opponent_conference_name=example.opponent_conference_name,
        same_conference_game=(
            bool(example.features.get("same_conference_game", 0.0))
            if example.team_conference_key is not None
            and example.opponent_conference_key is not None
            else None
        ),
        observation_time=example.observation_time,
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


def spread_candidate_segment_values(
    candidate: CandidateBet | PlacedBet,
) -> dict[str, str]:
    """Return stable spread-segment keys for attribution and abstention."""
    if candidate.market != "spread":
        return {}
    segment_values = {
        "expected_value_bucket": _expected_value_bucket_key(candidate.expected_value),
        "probability_edge_bucket": _probability_edge_bucket_key(
            candidate.probability_edge
        ),
        "season_phase": _season_phase_key(candidate.minimum_games_played),
        "line_bucket": _spread_line_bucket_key(candidate.line_value),
        "book_depth": _spread_book_depth_bucket_key(candidate.market_book_count),
        "same_conference": _same_conference_key(candidate.same_conference_game),
        "conference_group": _conference_group_key(candidate.team_conference_key),
    }
    tip_window_key = _tip_window_key(candidate)
    if tip_window_key is not None:
        segment_values["tip_window"] = tip_window_key
    return {
        dimension: value
        for dimension, value in segment_values.items()
        if value is not None
    }


def _conservative_quote_probability(
    *,
    example: ModelExample,
    probability: float,
    line_value: float | None,
    policy: BetPolicy,
) -> float:
    probability_buffer = _spread_probability_uncertainty_buffer(
        example=example,
        line_value=line_value,
        policy=policy,
    )
    return _clip_probability(probability - probability_buffer)


def _spread_probability_uncertainty_buffer(
    *,
    example: ModelExample,
    line_value: float | None,
    policy: BetPolicy,
) -> float:
    if (
        policy.uncertainty_probability_buffer <= 0.0
        or example.market != "spread"
    ):
        return 0.0
    return (
        policy.uncertainty_probability_buffer
        * _spread_uncertainty_index(example=example, line_value=line_value)
    )


def _expected_value_bucket_key(value: float) -> str:
    return _edge_bucket_key(value=value, prefix="ev")


def _probability_edge_bucket_key(value: float) -> str:
    return _edge_bucket_key(value=value, prefix="edge")


def _edge_bucket_key(*, value: float, prefix: str) -> str:
    if value < 0.04:
        return f"{prefix}_below_4"
    if value < 0.06:
        return f"{prefix}_4_to_6"
    if value < 0.08:
        return f"{prefix}_6_to_8"
    if value < 0.10:
        return f"{prefix}_8_to_10"
    return f"{prefix}_10_plus"


def _spread_uncertainty_index(
    *,
    example: ModelExample,
    line_value: float | None,
) -> float:
    min_games_played = max(
        float(example.minimum_games_played),
        float(example.features.get("min_season_games_played", 0.0)),
    )
    spread_books = max(
        float(example.features.get("spread_books", 0.0)),
        float(len(example.executable_quotes)),
    )
    spread_abs_line = abs(
        line_value
        if line_value is not None
        else float(example.features.get("spread_abs_line", 0.0))
    )
    spread_dispersion = max(
        0.0,
        float(example.features.get("spread_consensus_dispersion", 0.0)),
    )
    rest_gap = abs(float(example.features.get("rest_days_diff", 0.0)))
    return _clip_unit_interval(
        (0.35 * _scaled_shortfall(min_games_played, target=12.0, scale=8.0))
        + (0.20 * _scaled_shortfall(spread_books, target=8.0, scale=4.0))
        + (0.20 * _scaled_excess(spread_dispersion, floor=0.75, scale=1.5))
        + (0.15 * _scaled_excess(spread_abs_line, floor=6.0, scale=4.0))
        + (0.10 * _scaled_excess(rest_gap, floor=1.0, scale=2.0))
    )


def _scaled_shortfall(value: float, *, target: float, scale: float) -> float:
    if scale <= 0.0 or value >= target:
        return 0.0
    return _clip_unit_interval((target - value) / scale)


def _scaled_excess(value: float, *, floor: float, scale: float) -> float:
    if scale <= 0.0 or value <= floor:
        return 0.0
    return _clip_unit_interval((value - floor) / scale)


def _clip_probability(probability: float) -> float:
    return min(max(probability, 1e-6), 1.0 - 1e-6)


def _clip_unit_interval(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _season_phase_key(minimum_games_played: int) -> str:
    if minimum_games_played <= 0:
        return "opener"
    if minimum_games_played <= 5:
        return "early"
    return "established"


def _spread_line_bucket_key(line_value: float | None) -> str | None:
    if line_value is None:
        return None
    spread_abs_line = abs(line_value)
    if spread_abs_line <= 4.5:
        return "tight"
    if spread_abs_line <= 10.0:
        return "priced_range"
    return "long_line"


def _spread_book_depth_bucket_key(book_count: int) -> str:
    if book_count <= 4:
        return "low_depth"
    if book_count <= 7:
        return "mid_depth"
    return "high_depth"


def _same_conference_key(same_conference_game: bool | None) -> str | None:
    if same_conference_game is None:
        return None
    return "same_conference" if same_conference_game else "nonconference"


def _conference_group_key(conference_key: str | None) -> str:
    if conference_key is None:
        return "unknown"
    if conference_key in POWER_CONFERENCE_KEYS:
        return "power"
    if conference_key in MID_MAJOR_CONFERENCE_KEYS:
        return "mid_major"
    return "other"


def _tip_window_key(candidate: CandidateBet | PlacedBet) -> str | None:
    if candidate.observation_time is None:
        return None
    commence_time = _parse_iso_datetime(candidate.commence_time)
    observation_time = _parse_iso_datetime(candidate.observation_time)
    hours_to_tip = max(
        0.0,
        (commence_time - observation_time).total_seconds() / 3600.0,
    )
    if hours_to_tip <= 6.0:
        return "0_to_6h"
    if hours_to_tip <= 12.0:
        return "6_to_12h"
    if hours_to_tip <= 24.0:
        return "12_to_24h"
    if hours_to_tip <= 48.0:
        return "24_to_48h"
    return "48h_plus"


def _parse_iso_datetime(value: str) -> datetime:
    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value


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
    minimum_games_played: int = 0
    sportsbook: str = ""
    eligible_books: int = 0
    positive_ev_books: int = 0
    coverage_rate: float = 0.0
    supporting_quotes: tuple[SupportingQuote, ...] = ()
    min_acceptable_line: float | None = None
    min_acceptable_price: float | None = None
    market_book_count: int = 0
    team_conference_key: str | None = None
    team_conference_name: str | None = None
    opponent_conference_key: str | None = None
    opponent_conference_name: str | None = None
    same_conference_game: bool | None = None
    observation_time: str | None = None


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
        placed_bets_today = 0
        for candidate in sorted(
            grouped_by_day[game_day],
            key=lambda item: (
                -item.expected_value,
                -item.model_probability,
                item.game_id,
                item.market,
            ),
        ):
            if (
                policy.max_bets_per_day is not None
                and placed_bets_today >= policy.max_bets_per_day
            ):
                break
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
                    minimum_games_played=candidate.minimum_games_played,
                    eligible_books=candidate.eligible_books,
                    positive_ev_books=candidate.positive_ev_books,
                    coverage_rate=candidate.coverage_rate,
                    supporting_quotes=candidate.supporting_quotes,
                    min_acceptable_line=candidate.min_acceptable_line,
                    min_acceptable_price=candidate.min_acceptable_price,
                    market_book_count=candidate.market_book_count,
                    team_conference_key=candidate.team_conference_key,
                    team_conference_name=candidate.team_conference_name,
                    opponent_conference_key=candidate.opponent_conference_key,
                    opponent_conference_name=candidate.opponent_conference_name,
                    same_conference_game=candidate.same_conference_game,
                    observation_time=candidate.observation_time,
                )
            )
            daily_exposure += stake_amount
            placed_bets_today += 1
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
