"""Walk-forward bankroll backtesting for trained betting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from statistics import pstdev
from typing import TypeVar

from cbb.modeling.artifacts import ModelArtifact, ModelMarket, StrategyMarket
from cbb.modeling.dataset import (
    GameOddsRecord,
    get_available_seasons,
    load_completed_game_records,
)
from cbb.modeling.features import build_prediction_examples
from cbb.modeling.policy import (
    BetPolicy,
    CandidateBet,
    PlacedBet,
    apply_bankroll_limits,
    build_candidate_bet,
    candidate_matches_policy,
    select_best_candidates,
    settle_bet,
)
from cbb.modeling.train import (
    DEFAULT_MONEYLINE_TRAIN_MAX_PRICE,
    DEFAULT_MODEL_SEASONS_BACK,
    LogisticRegressionConfig,
    resolve_training_seasons,
    score_examples,
    train_artifact_from_records,
)

DEFAULT_BACKTEST_RETRAIN_DAYS = 30
DEFAULT_STARTING_BANKROLL = 1000.0
DEFAULT_UNIT_SIZE = 25.0
DEFAULT_TUNED_SPREAD_MIN_EDGE_VALUES = (0.015, 0.02, 0.03)
DEFAULT_TUNED_SPREAD_MIN_PROBABILITY_EDGE_VALUES = (0.015, 0.02, 0.025, 0.03)
DEFAULT_TUNED_SPREAD_MIN_GAMES_PLAYED_VALUES = (4, 8, 12)
DEFAULT_TUNED_SPREAD_MAX_ABS_LINE_VALUES = (None, 25.0, 20.0, 15.0, 10.0)

ValueT = TypeVar("ValueT")


@dataclass(frozen=True)
class BacktestOptions:
    """Options for walk-forward bankroll simulation."""

    market: StrategyMarket = "best"
    seasons_back: int = DEFAULT_MODEL_SEASONS_BACK
    evaluation_season: int | None = None
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL
    unit_size: float = DEFAULT_UNIT_SIZE
    retrain_days: int = DEFAULT_BACKTEST_RETRAIN_DAYS
    auto_tune_spread_policy: bool = False
    database_url: str | None = None
    policy: BetPolicy = field(default_factory=BetPolicy)
    config: LogisticRegressionConfig = field(
        default_factory=LogisticRegressionConfig
    )


@dataclass(frozen=True)
class BacktestSummary:
    """Reported bankroll outcomes for one backtest run."""

    market: StrategyMarket
    start_season: int
    end_season: int
    evaluation_season: int
    blocks: int
    candidates_considered: int
    bets_placed: int
    wins: int
    losses: int
    pushes: int
    total_staked: float
    profit: float
    roi: float
    units_won: float
    starting_bankroll: float
    ending_bankroll: float
    max_drawdown: float
    sample_bets: list[PlacedBet]
    policy_tuned_blocks: int = 0
    final_policy: BetPolicy | None = None


@dataclass(frozen=True)
class CandidateBlock:
    """One walk-forward block of raw candidate opportunities."""

    commence_time: str
    candidates: tuple[CandidateBet, ...]


@dataclass(frozen=True)
class PolicyEvaluation:
    """Outcome from replaying raw candidate blocks under one policy."""

    policy: BetPolicy
    blocks_evaluated: int
    blocks_with_bets: int
    profitable_blocks: int
    bets_placed: int
    total_staked: float
    profit: float
    roi: float
    profitable_block_rate: float
    worst_block_roi: float
    block_roi_stddev: float
    stability_score: float
    max_drawdown: float


def backtest_betting_model(options: BacktestOptions) -> BacktestSummary:
    """Run a walk-forward bankroll simulation for one strategy market."""
    available_seasons = get_available_seasons(options.database_url)
    if not available_seasons:
        raise ValueError("No completed seasons are available for backtesting")

    evaluation_season = options.evaluation_season or available_seasons[-1]
    selected_seasons = resolve_training_seasons(
        seasons_back=options.seasons_back,
        max_season=evaluation_season,
        database_url=options.database_url,
    )
    all_records = load_completed_game_records(
        max_season=evaluation_season,
        database_url=options.database_url,
    )
    selected_records = [
        record for record in all_records if record.season in set(selected_seasons)
    ]
    evaluation_records = [
        record for record in selected_records if record.season == evaluation_season
    ]
    if not evaluation_records:
        raise ValueError(
            f"No completed games found for evaluation season {evaluation_season}"
        )

    base_records = [
        record for record in selected_records if record.season < evaluation_season
    ]
    evaluation_blocks = _build_evaluation_blocks(
        records=evaluation_records,
        retrain_days=options.retrain_days,
    )
    spread_tuning_blocks = (
        _build_walk_forward_candidate_blocks(
            records=selected_records,
            requested_market="spread",
            retrain_days=options.retrain_days,
            candidate_policy=options.policy,
            config=options.config,
        )
        if options.auto_tune_spread_policy and options.market in {"spread", "best"}
        else []
    )

    bankroll = options.starting_bankroll
    peak_bankroll = bankroll
    max_drawdown = 0.0
    total_staked = 0.0
    candidates_considered = 0
    placed_bets: list[PlacedBet] = []
    prior_evaluation_records: list[GameOddsRecord] = []
    trained_any_block = False
    policy_tuned_blocks = 0
    final_policy: BetPolicy | None = None

    for block in evaluation_blocks:
        active_policy = options.policy
        if spread_tuning_blocks:
            prior_tuning_blocks = [
                candidate_block
                for candidate_block in spread_tuning_blocks
                if candidate_block.commence_time < block[0].commence_time.isoformat()
            ]
            active_policy = _select_tuned_spread_policy(
                candidate_blocks=prior_tuning_blocks,
                base_policy=options.policy,
                starting_bankroll=options.starting_bankroll,
            ).policy
            if prior_tuning_blocks:
                policy_tuned_blocks += 1
                final_policy = active_policy

        training_records = sorted(
            [*base_records, *prior_evaluation_records],
            key=lambda record: (record.commence_time, record.game_id),
        )
        trained_artifacts = _train_block_artifacts(
            training_records=training_records,
            requested_market=options.market,
            policy=options.policy,
            config=options.config,
        )
        if trained_artifacts:
            trained_any_block = True
        else:
            prior_evaluation_records.extend(block)
            continue

        block_candidates = _score_block_candidates(
            training_records=training_records,
            evaluation_block=block,
            trained_artifacts=trained_artifacts,
            candidate_policy=options.policy,
            selection_policy=active_policy,
        )
        if options.market == "best":
            block_candidates = select_best_candidates(block_candidates)
        candidates_considered += len(block_candidates)

        for day_candidates in _group_candidates_by_day(block_candidates):
            day_bets = apply_bankroll_limits(
                bankroll=bankroll,
                policy=active_policy,
                candidate_bets=day_candidates,
            )
            if not day_bets:
                continue
            total_staked += sum(bet.stake_amount for bet in day_bets)
            bankroll += sum(settle_bet(bet) for bet in day_bets)
            peak_bankroll = max(peak_bankroll, bankroll)
            if peak_bankroll > 0:
                max_drawdown = max(
                    max_drawdown,
                    (peak_bankroll - bankroll) / peak_bankroll,
                )
            placed_bets.extend(day_bets)

        prior_evaluation_records.extend(block)

    if not trained_any_block:
        raise ValueError(
            "Backtest could not train any model blocks with the available data"
        )

    wins = sum(1 for bet in placed_bets if bet.settlement == "win")
    losses = sum(1 for bet in placed_bets if bet.settlement == "loss")
    pushes = sum(1 for bet in placed_bets if bet.settlement == "push")
    profit = bankroll - options.starting_bankroll
    roi = profit / total_staked if total_staked > 0 else 0.0
    sample_bets = sorted(
        placed_bets,
        key=lambda bet: (
            -bet.expected_value,
            -bet.model_probability,
            bet.commence_time,
            bet.game_id,
        ),
    )[:5]
    return BacktestSummary(
        market=options.market,
        start_season=selected_seasons[0],
        end_season=selected_seasons[-1],
        evaluation_season=evaluation_season,
        blocks=len(evaluation_blocks),
        candidates_considered=candidates_considered,
        bets_placed=len(placed_bets),
        wins=wins,
        losses=losses,
        pushes=pushes,
        total_staked=total_staked,
        profit=profit,
        roi=roi,
        units_won=profit / options.unit_size if options.unit_size > 0 else 0.0,
        starting_bankroll=options.starting_bankroll,
        ending_bankroll=bankroll,
        max_drawdown=max_drawdown,
        sample_bets=sample_bets,
        policy_tuned_blocks=policy_tuned_blocks,
        final_policy=final_policy,
    )


def _train_block_artifacts(
    *,
    training_records: list[GameOddsRecord],
    requested_market: StrategyMarket,
    policy: BetPolicy,
    config: LogisticRegressionConfig,
) -> dict[ModelMarket, ModelArtifact]:
    training_seasons = sorted({record.season for record in training_records})
    if not training_seasons:
        return {}

    trained_artifacts: dict[ModelMarket, ModelArtifact] = {}
    for market in _requested_markets(requested_market):
        try:
            trained_artifacts[market] = train_artifact_from_records(
                market=market,
                game_records=training_records,
                seasons=training_seasons,
                moneyline_price_min=policy.min_moneyline_price,
                moneyline_price_max=max(
                    policy.max_moneyline_price,
                    DEFAULT_MONEYLINE_TRAIN_MAX_PRICE,
                ),
                config=config,
            )
        except ValueError:
            continue
    return trained_artifacts


def _score_block_candidates(
    *,
    training_records: list[GameOddsRecord],
    evaluation_block: list[GameOddsRecord],
    trained_artifacts: dict[ModelMarket, ModelArtifact],
    candidate_policy: BetPolicy,
    selection_policy: BetPolicy | None,
) -> list[CandidateBet]:
    candidates: list[CandidateBet] = []
    for market, artifact in trained_artifacts.items():
        examples = build_prediction_examples(
            completed_records=training_records,
            upcoming_records=evaluation_block,
            market=market,
        )
        probabilities = score_examples(artifact=artifact, examples=examples)
        for example, probability in zip(examples, probabilities, strict=True):
            candidate = build_candidate_bet(
                example=example,
                probability=probability,
                policy=candidate_policy,
            )
            if candidate is None:
                continue
            if selection_policy is not None and not candidate_matches_policy(
                candidate=candidate,
                policy=selection_policy,
            ):
                continue
            candidates.append(candidate)
    return candidates


def _requested_markets(strategy_market: StrategyMarket) -> list[ModelMarket]:
    if strategy_market == "best":
        return ["spread", "moneyline"]
    return [strategy_market]


def _build_evaluation_blocks(
    *,
    records: list[GameOddsRecord],
    retrain_days: int,
) -> list[list[GameOddsRecord]]:
    sorted_records = sorted(
        records,
        key=lambda record: (record.commence_time, record.game_id),
    )
    if not sorted_records:
        return []

    blocks: list[list[GameOddsRecord]] = []
    current_block: list[GameOddsRecord] = []
    current_anchor = sorted_records[0].commence_time
    window_size = timedelta(days=retrain_days)

    for record in sorted_records:
        if current_block and record.commence_time >= current_anchor + window_size:
            blocks.append(current_block)
            current_block = []
            current_anchor = record.commence_time
        current_block.append(record)

    if current_block:
        blocks.append(current_block)
    return blocks


def _group_candidates_by_day(
    candidates: list[CandidateBet],
) -> list[list[CandidateBet]]:
    grouped: dict[str, list[CandidateBet]] = {}
    for candidate in candidates:
        grouped.setdefault(candidate.commence_time[:10], []).append(candidate)
    return [grouped[day_key] for day_key in sorted(grouped)]


def _build_walk_forward_candidate_blocks(
    *,
    records: list[GameOddsRecord],
    requested_market: StrategyMarket,
    retrain_days: int,
    candidate_policy: BetPolicy,
    config: LogisticRegressionConfig,
) -> list[CandidateBlock]:
    evaluation_blocks = _build_evaluation_blocks(
        records=records,
        retrain_days=retrain_days,
    )
    candidate_blocks: list[CandidateBlock] = []
    prior_records: list[GameOddsRecord] = []

    for block in evaluation_blocks:
        trained_artifacts = _train_block_artifacts(
            training_records=prior_records,
            requested_market=requested_market,
            policy=candidate_policy,
            config=config,
        )
        if trained_artifacts:
            block_candidates = _score_block_candidates(
                training_records=prior_records,
                evaluation_block=block,
                trained_artifacts=trained_artifacts,
                candidate_policy=candidate_policy,
                selection_policy=None,
            )
            candidate_blocks.append(
                CandidateBlock(
                    commence_time=block[0].commence_time.isoformat(),
                    candidates=tuple(block_candidates),
                )
            )
        prior_records.extend(block)

    return candidate_blocks


def tune_spread_policy_from_records(
    *,
    completed_records: list[GameOddsRecord],
    base_policy: BetPolicy,
    retrain_days: int = DEFAULT_BACKTEST_RETRAIN_DAYS,
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL,
    config: LogisticRegressionConfig | None = None,
) -> PolicyEvaluation:
    """Tune a deployable spread policy from completed records only."""
    candidate_blocks = _build_walk_forward_candidate_blocks(
        records=completed_records,
        requested_market="spread",
        retrain_days=retrain_days,
        candidate_policy=base_policy,
        config=config or LogisticRegressionConfig(),
    )
    return _select_tuned_spread_policy(
        candidate_blocks=candidate_blocks,
        base_policy=base_policy,
        starting_bankroll=starting_bankroll,
    )


def derive_latest_spread_policy_from_records(
    *,
    completed_records: list[GameOddsRecord],
    base_policy: BetPolicy,
    retrain_days: int = DEFAULT_BACKTEST_RETRAIN_DAYS,
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL,
    config: LogisticRegressionConfig | None = None,
) -> PolicyEvaluation:
    """Return the final tuned spread policy from the latest walk-forward season."""
    if not completed_records:
        return _select_tuned_spread_policy(
            candidate_blocks=[],
            base_policy=base_policy,
            starting_bankroll=starting_bankroll,
        )

    evaluation_season = max(record.season for record in completed_records)
    evaluation_records = [
        record for record in completed_records if record.season == evaluation_season
    ]
    if not evaluation_records:
        return _select_tuned_spread_policy(
            candidate_blocks=[],
            base_policy=base_policy,
            starting_bankroll=starting_bankroll,
        )

    spread_tuning_blocks = _build_walk_forward_candidate_blocks(
        records=completed_records,
        requested_market="spread",
        retrain_days=retrain_days,
        candidate_policy=base_policy,
        config=config or LogisticRegressionConfig(),
    )
    final_evaluation = _select_tuned_spread_policy(
        candidate_blocks=[],
        base_policy=base_policy,
        starting_bankroll=starting_bankroll,
    )
    for block in _build_evaluation_blocks(
        records=evaluation_records,
        retrain_days=retrain_days,
    ):
        prior_tuning_blocks = [
            candidate_block
            for candidate_block in spread_tuning_blocks
            if candidate_block.commence_time < block[0].commence_time.isoformat()
        ]
        if not prior_tuning_blocks:
            continue
        final_evaluation = _select_tuned_spread_policy(
            candidate_blocks=prior_tuning_blocks,
            base_policy=base_policy,
            starting_bankroll=starting_bankroll,
        )
    return final_evaluation


def _select_tuned_spread_policy(
    *,
    candidate_blocks: list[CandidateBlock],
    base_policy: BetPolicy,
    starting_bankroll: float,
) -> PolicyEvaluation:
    if not candidate_blocks:
        return PolicyEvaluation(
            policy=base_policy,
            blocks_evaluated=0,
            blocks_with_bets=0,
            profitable_blocks=0,
            bets_placed=0,
            total_staked=0.0,
            profit=0.0,
            roi=0.0,
            profitable_block_rate=0.0,
            worst_block_roi=0.0,
            block_roi_stddev=0.0,
            stability_score=0.0,
            max_drawdown=0.0,
        )

    best_evaluation: PolicyEvaluation | None = None
    for policy in _spread_policy_grid(base_policy):
        evaluation = _evaluate_policy_on_candidate_blocks(
            candidate_blocks=candidate_blocks,
            policy=policy,
            starting_bankroll=starting_bankroll,
        )
        if best_evaluation is None or _policy_evaluation_sort_key(
            evaluation=evaluation,
            base_policy=base_policy,
        ) > _policy_evaluation_sort_key(
            evaluation=best_evaluation,
            base_policy=base_policy,
        ):
            best_evaluation = evaluation

    assert best_evaluation is not None
    return best_evaluation


def _spread_policy_grid(base_policy: BetPolicy) -> list[BetPolicy]:
    min_edge_values = _ordered_unique_values(
        (base_policy.min_edge, *DEFAULT_TUNED_SPREAD_MIN_EDGE_VALUES)
    )
    min_probability_edge_values = _ordered_unique_values(
        (
            base_policy.min_probability_edge,
            *DEFAULT_TUNED_SPREAD_MIN_PROBABILITY_EDGE_VALUES,
        )
    )
    min_games_played_values = _ordered_unique_values(
        (
            base_policy.min_games_played,
            *DEFAULT_TUNED_SPREAD_MIN_GAMES_PLAYED_VALUES,
        )
    )
    max_spread_abs_line_values = _ordered_unique_values(
        (
            base_policy.max_spread_abs_line,
            *DEFAULT_TUNED_SPREAD_MAX_ABS_LINE_VALUES,
        )
    )

    return [
        BetPolicy(
            min_edge=min_edge,
            min_confidence=base_policy.min_confidence,
            min_probability_edge=min_probability_edge,
            min_games_played=min_games_played,
            kelly_fraction=base_policy.kelly_fraction,
            max_bet_fraction=base_policy.max_bet_fraction,
            max_daily_exposure_fraction=base_policy.max_daily_exposure_fraction,
            min_moneyline_price=base_policy.min_moneyline_price,
            max_moneyline_price=base_policy.max_moneyline_price,
            max_spread_abs_line=max_spread_abs_line,
        )
        for min_edge in min_edge_values
        for min_probability_edge in min_probability_edge_values
        for min_games_played in min_games_played_values
        for max_spread_abs_line in max_spread_abs_line_values
    ]


def _evaluate_policy_on_candidate_blocks(
    *,
    candidate_blocks: list[CandidateBlock],
    policy: BetPolicy,
    starting_bankroll: float,
) -> PolicyEvaluation:
    bankroll = starting_bankroll
    peak_bankroll = bankroll
    max_drawdown = 0.0
    total_staked = 0.0
    blocks_with_bets = 0
    profitable_blocks = 0
    active_block_rois: list[float] = []
    bets_placed = 0

    for candidate_block in candidate_blocks:
        block_bankroll_start = bankroll
        block_total_staked = 0.0
        filtered_candidates = [
            candidate
            for candidate in candidate_block.candidates
            if candidate_matches_policy(candidate=candidate, policy=policy)
        ]
        for day_candidates in _group_candidates_by_day(filtered_candidates):
            day_bets = apply_bankroll_limits(
                bankroll=bankroll,
                policy=policy,
                candidate_bets=day_candidates,
            )
            if not day_bets:
                continue
            day_total_staked = sum(bet.stake_amount for bet in day_bets)
            total_staked += day_total_staked
            block_total_staked += day_total_staked
            bets_placed += len(day_bets)
            bankroll += sum(settle_bet(bet) for bet in day_bets)
            peak_bankroll = max(peak_bankroll, bankroll)
            if peak_bankroll > 0:
                max_drawdown = max(
                    max_drawdown,
                    (peak_bankroll - bankroll) / peak_bankroll,
                )

        if block_total_staked > 0:
            blocks_with_bets += 1
            block_profit = bankroll - block_bankroll_start
            block_roi = block_profit / block_total_staked
            active_block_rois.append(block_roi)
            if block_profit > 0:
                profitable_blocks += 1

    profit = bankroll - starting_bankroll
    roi = profit / total_staked if total_staked > 0 else 0.0
    profitable_block_rate = (
        profitable_blocks / len(candidate_blocks) if candidate_blocks else 0.0
    )
    worst_block_roi = min(active_block_rois) if active_block_rois else 0.0
    block_roi_stddev = pstdev(active_block_rois) if len(active_block_rois) > 1 else 0.0
    stability_score = (
        (roi * profitable_block_rate)
        - (0.50 * max_drawdown)
        - (0.25 * block_roi_stddev)
    )
    return PolicyEvaluation(
        policy=policy,
        blocks_evaluated=len(candidate_blocks),
        blocks_with_bets=blocks_with_bets,
        profitable_blocks=profitable_blocks,
        bets_placed=bets_placed,
        total_staked=total_staked,
        profit=profit,
        roi=roi,
        profitable_block_rate=profitable_block_rate,
        worst_block_roi=worst_block_roi,
        block_roi_stddev=block_roi_stddev,
        stability_score=stability_score,
        max_drawdown=max_drawdown,
    )


def _policy_evaluation_sort_key(
    *,
    evaluation: PolicyEvaluation,
    base_policy: BetPolicy,
) -> tuple[float, float, float, float, float, float, float, int, int]:
    return (
        round(evaluation.stability_score, 10),
        round(evaluation.roi, 10),
        round(evaluation.profitable_block_rate, 10),
        round(evaluation.worst_block_roi, 10),
        -round(evaluation.max_drawdown, 10),
        -round(evaluation.block_roi_stddev, 10),
        round(evaluation.profit, 10),
        -evaluation.bets_placed,
        1 if evaluation.policy == base_policy else 0,
    )


def _ordered_unique_values(values: tuple[ValueT, ...]) -> list[ValueT]:
    unique_values: list[ValueT] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values
