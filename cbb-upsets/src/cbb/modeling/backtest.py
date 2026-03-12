"""Walk-forward bankroll backtesting for trained betting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from math import ceil
from statistics import pstdev
from typing import TypeVar

from cbb.modeling.artifacts import (
    ModelArtifact,
    ModelFamily,
    ModelMarket,
    StrategyMarket,
)
from cbb.modeling.dataset import (
    GameOddsRecord,
    derive_game_record_at_observation_time,
    get_available_seasons,
    load_completed_game_records,
)
from cbb.modeling.execution import build_executable_candidate_bets
from cbb.modeling.features import (
    ModelExample,
    build_prediction_examples,
    implied_probability_from_american,
    normalized_implied_probability_from_prices,
    repriced_spread_example,
)
from cbb.modeling.policy import (
    SPREAD_SEGMENT_DIMENSIONS,
    BetPolicy,
    CandidateBet,
    PlacedBet,
    apply_bankroll_limits,
    candidate_matches_policy,
    deployable_spread_policy,
    expected_value_from_american,
    select_best_candidates,
    select_best_quote_candidates,
    settle_bet,
    spread_candidate_segment_values,
)
from cbb.modeling.train import (
    DEFAULT_MODEL_SEASONS_BACK,
    DEFAULT_MONEYLINE_TRAIN_MAX_PRICE,
    DEFAULT_SPREAD_MODEL_FAMILY,
    DEFAULT_SPREAD_TIMING_MIN_HOURS_TO_TIP,
    LogisticRegressionConfig,
    resolve_training_seasons,
    score_examples,
    score_spread_probability_at_line,
    score_spread_timing_probability,
    train_artifact_from_records,
)

DEFAULT_BACKTEST_RETRAIN_DAYS = 30
DEFAULT_STARTING_BANKROLL = 1000.0
DEFAULT_UNIT_SIZE = 25.0
DEFAULT_TUNED_SPREAD_MIN_EDGE_VALUES = (0.015, 0.02, 0.03)
DEFAULT_TUNED_SPREAD_MIN_PROBABILITY_EDGE_VALUES = (0.015, 0.02, 0.025, 0.03)
DEFAULT_TUNED_SPREAD_MIN_GAMES_PLAYED_VALUES = (4, 8, 12)
DEFAULT_TUNED_SPREAD_MIN_CONFIDENCE_VALUES = (0.0, 0.515, 0.52, 0.525)
DEFAULT_TUNED_SPREAD_MAX_ABS_LINE_VALUES = (None, 15.0, 12.5, 10.0, 7.5)
MIN_TUNED_SPREAD_ACTIVE_BLOCK_RATE = 0.25
MIN_TUNED_SPREAD_BETS = 3
MIN_TUNED_SPREAD_STAKED_FRACTION = 0.01
MIN_TUNED_SPREAD_AVERAGE_CLOSING_EV = 0.0
MIN_TUNED_SPREAD_AVERAGE_NO_VIG_CLOSE_DELTA = 0.0

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
    use_timing_layer: bool = False
    spread_model_family: ModelFamily = DEFAULT_SPREAD_MODEL_FAMILY
    database_url: str | None = None
    policy: BetPolicy = field(default_factory=BetPolicy)
    config: LogisticRegressionConfig = field(default_factory=LogisticRegressionConfig)


@dataclass(frozen=True)
class CandidateBlock:
    """One walk-forward block of raw candidate opportunities."""

    commence_time: str
    candidates: tuple[CandidateBet, ...]
    completed_records: tuple[GameOddsRecord, ...] = ()
    spread_closing_metrics: tuple[
        tuple[tuple[int, str], SpreadClosingMarketMetrics],
        ...,
    ] = ()


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
    active_block_rate: float
    profitable_block_rate: float
    worst_block_roi: float
    block_roi_stddev: float
    stability_score: float
    max_drawdown: float
    meets_activity_constraints: bool = False
    meets_close_quality_constraints: bool = True
    activity_score: float = 0.0
    clv: ClosingLineValueSummary = field(
        default_factory=lambda: ClosingLineValueSummary()
    )

    @property
    def meets_tuning_constraints(self) -> bool:
        """Return whether a policy clears both deployment gates."""
        return (
            self.meets_activity_constraints
            and self.meets_close_quality_constraints
        )


@dataclass(frozen=True)
class SpreadTuningActivityConstraints:
    """Minimum activity required for a spread policy to count as deployable."""

    min_active_blocks: int
    min_bets: int
    min_total_staked: float


@dataclass(frozen=True)
class SpreadClosingMarketMetrics:
    """Stored closing-market measurements for one spread side."""

    closing_line: float | None = None
    closing_price_probability: float | None = None
    closing_no_vig_probability: float | None = None
    closing_expected_value: float | None = None


@dataclass(frozen=True)
class ClosingLineValueObservation:
    """One bet-level closing-line-value measurement."""

    market: ModelMarket
    reference_delta: float
    spread_line_delta: float | None = None
    spread_price_probability_delta: float | None = None
    spread_no_vig_probability_delta: float | None = None
    spread_closing_expected_value: float | None = None
    moneyline_probability_delta: float | None = None
    game_id: int | None = None
    side: str | None = None


@dataclass(frozen=True)
class ClosingLineValueSummary:
    """How often placed bets beat the stored closing market."""

    bets_evaluated: int = 0
    positive_bets: int = 0
    negative_bets: int = 0
    neutral_bets: int = 0
    spread_bets_evaluated: int = 0
    total_spread_line_delta: float = 0.0
    spread_price_bets_evaluated: int = 0
    total_spread_price_probability_delta: float = 0.0
    spread_no_vig_bets_evaluated: int = 0
    total_spread_no_vig_probability_delta: float = 0.0
    spread_closing_ev_bets_evaluated: int = 0
    total_spread_closing_expected_value: float = 0.0
    moneyline_bets_evaluated: int = 0
    total_moneyline_probability_delta: float = 0.0

    @property
    def positive_rate(self) -> float:
        if self.bets_evaluated == 0:
            return 0.0
        return self.positive_bets / self.bets_evaluated

    @property
    def average_spread_line_delta(self) -> float | None:
        if self.spread_bets_evaluated == 0:
            return None
        return self.total_spread_line_delta / self.spread_bets_evaluated

    @property
    def average_spread_price_probability_delta(self) -> float | None:
        if self.spread_price_bets_evaluated == 0:
            return None
        return (
            self.total_spread_price_probability_delta
            / self.spread_price_bets_evaluated
        )

    @property
    def average_spread_no_vig_probability_delta(self) -> float | None:
        if self.spread_no_vig_bets_evaluated == 0:
            return None
        return (
            self.total_spread_no_vig_probability_delta
            / self.spread_no_vig_bets_evaluated
        )

    @property
    def average_spread_closing_expected_value(self) -> float | None:
        if self.spread_closing_ev_bets_evaluated == 0:
            return None
        return (
            self.total_spread_closing_expected_value
            / self.spread_closing_ev_bets_evaluated
        )

    @property
    def average_moneyline_probability_delta(self) -> float | None:
        if self.moneyline_bets_evaluated == 0:
            return None
        return (
            self.total_moneyline_probability_delta / self.moneyline_bets_evaluated
        )


@dataclass(frozen=True)
class SpreadSegmentSummary:
    """Season-level ROI and close-EV attribution for one spread segment."""

    value: str
    bets: int
    total_staked: float
    profit: float
    roi: float
    share_of_bets: float
    clv: ClosingLineValueSummary = field(
        default_factory=lambda: ClosingLineValueSummary()
    )


@dataclass(frozen=True)
class SpreadSegmentAttribution:
    """One spread segment dimension and its aggregated outcomes."""

    dimension: str
    segments: tuple[SpreadSegmentSummary, ...]


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
    placed_bets: list[PlacedBet] = field(default_factory=list)
    clv: ClosingLineValueSummary = field(default_factory=ClosingLineValueSummary)
    spread_segment_attribution: tuple[SpreadSegmentAttribution, ...] = ()
    policy_tuned_blocks: int = 0
    final_policy: BetPolicy | None = None


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
    spread_base_policy = (
        deployable_spread_policy(options.policy)
        if options.market in {"spread", "best"}
        else options.policy
    )
    evaluation_blocks = _build_evaluation_blocks(
        records=evaluation_records,
        retrain_days=options.retrain_days,
    )
    spread_tuning_blocks = (
        _build_walk_forward_candidate_blocks(
            records=selected_records,
            requested_market="spread",
            spread_model_family=options.spread_model_family,
            retrain_days=options.retrain_days,
            candidate_policy=spread_base_policy,
            use_timing_layer=options.use_timing_layer,
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
    clv_observations: list[ClosingLineValueObservation] = []
    prior_evaluation_records: list[GameOddsRecord] = []
    trained_any_block = False
    policy_tuned_blocks = 0
    final_policy: BetPolicy | None = (
        spread_base_policy if options.market in {"spread", "best"} else None
    )

    for block in evaluation_blocks:
        active_policy = spread_base_policy
        if spread_tuning_blocks:
            prior_tuning_blocks = [
                candidate_block
                for candidate_block in spread_tuning_blocks
                if candidate_block.commence_time < block[0].commence_time.isoformat()
            ]
            if prior_tuning_blocks:
                tuning_evaluation = _select_tuned_spread_policy(
                    candidate_blocks=prior_tuning_blocks,
                    base_policy=spread_base_policy,
                    starting_bankroll=options.starting_bankroll,
                )
                if tuning_evaluation.meets_tuning_constraints:
                    active_policy = tuning_evaluation.policy
                    policy_tuned_blocks += 1
                    final_policy = active_policy

        training_records = sorted(
            [*base_records, *prior_evaluation_records],
            key=lambda record: (record.commence_time, record.game_id),
        )
        trained_artifacts = _train_block_artifacts(
            training_records=training_records,
            requested_market=options.market,
            spread_model_family=options.spread_model_family,
            policy=options.policy,
            config=options.config,
        )
        if trained_artifacts:
            trained_any_block = True
        else:
            prior_evaluation_records.extend(block)
            continue

        scoring_block = _build_scoring_block(
            evaluation_block=block,
            trained_artifacts=trained_artifacts,
            use_timing_layer=options.use_timing_layer,
        )
        block_candidates = _score_block_candidates(
            training_records=training_records,
            evaluation_block=scoring_block,
            trained_artifacts=trained_artifacts,
            candidate_policy=spread_base_policy,
            selection_policy=active_policy,
            use_timing_layer=options.use_timing_layer,
        )
        spread_closing_metrics = _build_spread_closing_market_metrics(
            training_records=training_records,
            completed_records=block,
            artifact=trained_artifacts.get("spread"),
        )
        block_candidates = select_best_quote_candidates(block_candidates)
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
            clv_observations.extend(
                _closing_line_value_observations(
                    placed_bets=day_bets,
                    completed_records=block,
                    spread_closing_metrics=spread_closing_metrics,
                )
            )

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
    clv_summary = _summarize_closing_line_value(clv_observations)
    spread_segment_attribution = _summarize_spread_segment_attribution(
        placed_bets=placed_bets,
        clv_observations=clv_observations,
    )
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
        placed_bets=placed_bets,
        clv=clv_summary,
        spread_segment_attribution=spread_segment_attribution,
        policy_tuned_blocks=policy_tuned_blocks,
        final_policy=final_policy,
    )


def _train_block_artifacts(
    *,
    training_records: list[GameOddsRecord],
    requested_market: StrategyMarket,
    spread_model_family: ModelFamily,
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
                model_family=(
                    spread_model_family if market == "spread" else "logistic"
                ),
                moneyline_price_min=policy.min_moneyline_price,
                moneyline_price_max=max(
                    policy.max_moneyline_price,
                    DEFAULT_MONEYLINE_TRAIN_MAX_PRICE,
                ),
                config=config,
            )
        except ValueError:
            continue
        if requested_market == "best" and market == "spread":
            return {"spread": trained_artifacts["spread"]}
    return trained_artifacts


def _score_block_candidates(
    *,
    training_records: list[GameOddsRecord],
    evaluation_block: list[GameOddsRecord],
    trained_artifacts: dict[ModelMarket, ModelArtifact],
    candidate_policy: BetPolicy,
    selection_policy: BetPolicy | None,
    use_timing_layer: bool,
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
            executable_candidates = build_executable_candidate_bets(
                artifact=artifact,
                example=example,
                probability=probability,
                policy=candidate_policy,
            )
            if not executable_candidates:
                continue
            for candidate in executable_candidates:
                if (
                    use_timing_layer
                    and market == "spread"
                    and artifact.spread_timing_model is not None
                ):
                    favorable_close_probability = score_spread_timing_probability(
                        timing_model=artifact.spread_timing_model,
                        example=_timing_example_for_candidate(
                            example=example,
                            candidate=candidate,
                        ),
                    )
                    if (
                        favorable_close_probability is not None
                        and favorable_close_probability
                        < artifact.spread_timing_model.min_favorable_probability
                    ):
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


def _derive_timing_decision_records(
    records: list[GameOddsRecord],
    *,
    hours_before_tip: float,
) -> list[GameOddsRecord]:
    return [
        derive_game_record_at_observation_time(
            record,
            observation_time=record.commence_time - timedelta(hours=hours_before_tip),
        )
        for record in records
    ]


def _build_scoring_block(
    *,
    evaluation_block: list[GameOddsRecord],
    trained_artifacts: dict[ModelMarket, ModelArtifact],
    use_timing_layer: bool,
) -> list[GameOddsRecord]:
    if not use_timing_layer or "spread" not in trained_artifacts:
        return evaluation_block
    return _derive_timing_decision_records(
        evaluation_block,
        hours_before_tip=DEFAULT_SPREAD_TIMING_MIN_HOURS_TO_TIP,
    )


def _closing_line_value_observations(
    *,
    placed_bets: list[PlacedBet],
    completed_records: list[GameOddsRecord],
    spread_closing_metrics: dict[tuple[int, str], SpreadClosingMarketMetrics],
) -> list[ClosingLineValueObservation]:
    records_by_game = {
        record.game_id: record
        for record in completed_records
    }
    observations: list[ClosingLineValueObservation] = []
    for bet in placed_bets:
        record = records_by_game.get(bet.game_id)
        if record is None:
            continue
        if bet.market == "spread":
            line_delta = _spread_line_clv_delta(
                record=record,
                side=bet.side,
                line_value=bet.line_value,
            )
            spread_metrics = spread_closing_metrics.get((bet.game_id, bet.side))
            entry_price_probability = implied_probability_from_american(
                bet.market_price
            )
            price_delta = None
            if (
                spread_metrics is not None
                and spread_metrics.closing_price_probability is not None
                and entry_price_probability is not None
            ):
                price_delta = (
                    spread_metrics.closing_price_probability
                    - entry_price_probability
                )
            no_vig_delta = (
                spread_metrics.closing_no_vig_probability - bet.implied_probability
                if spread_metrics is not None
                and spread_metrics.closing_no_vig_probability is not None
                else None
            )
            reference_delta = line_delta if line_delta is not None else no_vig_delta
            if reference_delta is None:
                continue
            observations.append(
                ClosingLineValueObservation(
                    market="spread",
                    reference_delta=reference_delta,
                    spread_line_delta=line_delta,
                    spread_price_probability_delta=price_delta,
                    spread_no_vig_probability_delta=no_vig_delta,
                    spread_closing_expected_value=(
                        spread_metrics.closing_expected_value
                        if spread_metrics is not None
                        else None
                    ),
                    game_id=bet.game_id,
                    side=bet.side,
                )
            )
            continue
        closing_probability = _closing_moneyline_probability(
            record=record,
            side=bet.side,
        )
        if closing_probability is None:
            continue
        moneyline_delta = closing_probability - bet.implied_probability
        observations.append(
            ClosingLineValueObservation(
                market="moneyline",
                reference_delta=moneyline_delta,
                moneyline_probability_delta=moneyline_delta,
                game_id=bet.game_id,
                side=bet.side,
            )
        )
    return observations


def _summarize_closing_line_value(
    observations: list[ClosingLineValueObservation],
) -> ClosingLineValueSummary:
    positive_bets = 0
    negative_bets = 0
    neutral_bets = 0
    spread_bets_evaluated = 0
    total_spread_line_delta = 0.0
    spread_price_bets_evaluated = 0
    total_spread_price_probability_delta = 0.0
    spread_no_vig_bets_evaluated = 0
    total_spread_no_vig_probability_delta = 0.0
    spread_closing_ev_bets_evaluated = 0
    total_spread_closing_expected_value = 0.0
    moneyline_bets_evaluated = 0
    total_moneyline_probability_delta = 0.0

    for observation in observations:
        if observation.reference_delta > 1e-9:
            positive_bets += 1
        elif observation.reference_delta < -1e-9:
            negative_bets += 1
        else:
            neutral_bets += 1
        if observation.market == "spread":
            if observation.spread_line_delta is not None:
                spread_bets_evaluated += 1
                total_spread_line_delta += observation.spread_line_delta
            if observation.spread_price_probability_delta is not None:
                spread_price_bets_evaluated += 1
                total_spread_price_probability_delta += (
                    observation.spread_price_probability_delta
                )
            if observation.spread_no_vig_probability_delta is not None:
                spread_no_vig_bets_evaluated += 1
                total_spread_no_vig_probability_delta += (
                    observation.spread_no_vig_probability_delta
                )
            if observation.spread_closing_expected_value is not None:
                spread_closing_ev_bets_evaluated += 1
                total_spread_closing_expected_value += (
                    observation.spread_closing_expected_value
                )
        else:
            moneyline_bets_evaluated += 1
            total_moneyline_probability_delta += (
                observation.moneyline_probability_delta or 0.0
            )

    return ClosingLineValueSummary(
        bets_evaluated=len(observations),
        positive_bets=positive_bets,
        negative_bets=negative_bets,
        neutral_bets=neutral_bets,
        spread_bets_evaluated=spread_bets_evaluated,
        total_spread_line_delta=total_spread_line_delta,
        spread_price_bets_evaluated=spread_price_bets_evaluated,
        total_spread_price_probability_delta=total_spread_price_probability_delta,
        spread_no_vig_bets_evaluated=spread_no_vig_bets_evaluated,
        total_spread_no_vig_probability_delta=total_spread_no_vig_probability_delta,
        spread_closing_ev_bets_evaluated=spread_closing_ev_bets_evaluated,
        total_spread_closing_expected_value=total_spread_closing_expected_value,
        moneyline_bets_evaluated=moneyline_bets_evaluated,
        total_moneyline_probability_delta=total_moneyline_probability_delta,
    )


def _summarize_spread_segment_attribution(
    *,
    placed_bets: list[PlacedBet],
    clv_observations: list[ClosingLineValueObservation],
) -> tuple[SpreadSegmentAttribution, ...]:
    spread_bets = [bet for bet in placed_bets if bet.market == "spread"]
    if not spread_bets:
        return ()

    observations_by_scope = {
        (observation.game_id, observation.side): observation
        for observation in clv_observations
        if observation.market == "spread"
        and observation.game_id is not None
        and observation.side is not None
    }
    grouped_bets: dict[str, dict[str, list[PlacedBet]]] = {}
    grouped_observations: dict[str, dict[str, list[ClosingLineValueObservation]]] = {}
    total_spread_bets = len(spread_bets)

    for bet in spread_bets:
        observation = observations_by_scope.get((bet.game_id, bet.side))
        for dimension, value in spread_candidate_segment_values(bet).items():
            grouped_bets.setdefault(dimension, {}).setdefault(value, []).append(bet)
            if observation is not None:
                grouped_observations.setdefault(dimension, {}).setdefault(
                    value, []
                ).append(observation)

    attribution: list[SpreadSegmentAttribution] = []
    for dimension in SPREAD_SEGMENT_DIMENSIONS:
        dimension_bets = grouped_bets.get(dimension)
        if not dimension_bets:
            continue
        segments: list[SpreadSegmentSummary] = []
        for value, segment_bets in dimension_bets.items():
            total_staked = sum(bet.stake_amount for bet in segment_bets)
            profit = sum(settle_bet(bet) for bet in segment_bets)
            segments.append(
                SpreadSegmentSummary(
                    value=value,
                    bets=len(segment_bets),
                    total_staked=total_staked,
                    profit=profit,
                    roi=profit / total_staked if total_staked > 0 else 0.0,
                    share_of_bets=len(segment_bets) / float(total_spread_bets),
                    clv=_summarize_closing_line_value(
                        grouped_observations.get(dimension, {}).get(value, [])
                    ),
                )
            )
        attribution.append(
            SpreadSegmentAttribution(
                dimension=dimension,
                segments=tuple(sorted(segments, key=_spread_segment_sort_key)),
            )
        )
    return tuple(attribution)


def _spread_segment_sort_key(
    summary: SpreadSegmentSummary,
) -> tuple[float, float, int, str]:
    average_closing_ev = summary.clv.average_spread_closing_expected_value
    return (
        average_closing_ev if average_closing_ev is not None else float("inf"),
        summary.roi,
        -summary.bets,
        summary.value,
    )


def _build_spread_closing_market_metrics(
    *,
    training_records: list[GameOddsRecord],
    completed_records: list[GameOddsRecord],
    artifact: ModelArtifact | None,
) -> dict[tuple[int, str], SpreadClosingMarketMetrics]:
    if (
        artifact is None
        or getattr(artifact, "market", None) != "spread"
        or not completed_records
    ):
        return {}

    records_by_game = {record.game_id: record for record in completed_records}
    close_examples = build_prediction_examples(
        completed_records=training_records,
        upcoming_records=completed_records,
        market="spread",
    )
    closing_metrics: dict[tuple[int, str], SpreadClosingMarketMetrics] = {}
    for example in close_examples:
        record = records_by_game.get(example.game_id)
        if record is None:
            continue
        closing_line = _closing_spread_line(record=record, side=example.side)
        closing_price = _closing_spread_price(record=record, side=example.side)
        closing_expected_value = None
        if closing_line is not None and closing_price is not None:
            closing_probability = score_spread_probability_at_line(
                artifact=artifact,
                example=example,
                line_value=closing_line,
            )
            closing_expected_value = expected_value_from_american(
                probability=closing_probability,
                american_price=closing_price,
            )
        closing_metrics[(example.game_id, example.side)] = SpreadClosingMarketMetrics(
            closing_line=closing_line,
            closing_price_probability=_closing_spread_price_probability(
                record=record,
                side=example.side,
            ),
            closing_no_vig_probability=_closing_spread_probability(
                record=record,
                side=example.side,
            ),
            closing_expected_value=closing_expected_value,
        )
    return closing_metrics


def _closing_moneyline_probability(
    *,
    record: GameOddsRecord,
    side: str,
) -> float | None:
    if record.h2h_close is not None:
        if side == "home":
            return record.h2h_close.team1_implied_probability
        return record.h2h_close.team2_implied_probability
    return normalized_implied_probability_from_prices(
        side_american_price=(
            record.home_h2h_price if side == "home" else record.away_h2h_price
        ),
        opponent_american_price=(
            record.away_h2h_price if side == "home" else record.home_h2h_price
        ),
    )


def _closing_spread_probability(
    *,
    record: GameOddsRecord,
    side: str,
) -> float | None:
    if record.spread_close is not None:
        if side == "home":
            return record.spread_close.team1_implied_probability
        return record.spread_close.team2_implied_probability
    return normalized_implied_probability_from_prices(
        side_american_price=(
            record.home_spread_price if side == "home" else record.away_spread_price
        ),
        opponent_american_price=(
            record.away_spread_price if side == "home" else record.home_spread_price
        ),
    )


def _closing_spread_price(
    *,
    record: GameOddsRecord,
    side: str,
) -> float | None:
    if record.spread_close is not None:
        if side == "home":
            return record.spread_close.team1_price
        return record.spread_close.team2_price
    return record.home_spread_price if side == "home" else record.away_spread_price


def _closing_spread_price_probability(
    *,
    record: GameOddsRecord,
    side: str,
) -> float | None:
    valid_probabilities = [
        probability
        for probability in (
            implied_probability_from_american(
                quote.team1_price if side == "home" else quote.team2_price
            )
            for quote in record.current_spread_quotes
        )
        if probability is not None
    ]
    if valid_probabilities:
        return sum(valid_probabilities) / len(valid_probabilities)
    return implied_probability_from_american(
        _closing_spread_price(record=record, side=side)
    )


def _closing_spread_line(
    *,
    record: GameOddsRecord,
    side: str,
) -> float | None:
    if record.spread_close is not None:
        if side == "home":
            return record.spread_close.team1_point
        return record.spread_close.team2_point
    return record.home_spread_line if side == "home" else record.away_spread_line


def _spread_line_clv_delta(
    *,
    record: GameOddsRecord,
    side: str,
    line_value: float | None,
) -> float | None:
    closing_line = _closing_spread_line(record=record, side=side)
    if closing_line is None or line_value is None:
        return None
    return line_value - closing_line


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
    spread_model_family: ModelFamily,
    retrain_days: int,
    candidate_policy: BetPolicy,
    use_timing_layer: bool,
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
            spread_model_family=spread_model_family,
            policy=candidate_policy,
            config=config,
        )
        if trained_artifacts:
            spread_closing_metrics = _build_spread_closing_market_metrics(
                training_records=prior_records,
                completed_records=block,
                artifact=trained_artifacts.get("spread"),
            )
            scoring_block = _build_scoring_block(
                evaluation_block=block,
                trained_artifacts=trained_artifacts,
                use_timing_layer=use_timing_layer,
            )
            block_candidates = _score_block_candidates(
                training_records=prior_records,
                evaluation_block=scoring_block,
                trained_artifacts=trained_artifacts,
                candidate_policy=candidate_policy,
                selection_policy=None,
                use_timing_layer=use_timing_layer,
            )
            candidate_blocks.append(
                CandidateBlock(
                    commence_time=block[0].commence_time.isoformat(),
                    candidates=tuple(block_candidates),
                    completed_records=tuple(block),
                    spread_closing_metrics=tuple(spread_closing_metrics.items()),
                )
            )
        prior_records.extend(block)

    return candidate_blocks


def tune_spread_policy_from_records(
    *,
    completed_records: list[GameOddsRecord],
    base_policy: BetPolicy,
    spread_model_family: ModelFamily = DEFAULT_SPREAD_MODEL_FAMILY,
    retrain_days: int = DEFAULT_BACKTEST_RETRAIN_DAYS,
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL,
    config: LogisticRegressionConfig | None = None,
) -> PolicyEvaluation:
    """Tune a deployable spread policy from completed records only."""
    candidate_blocks = _build_walk_forward_candidate_blocks(
        records=completed_records,
        requested_market="spread",
        spread_model_family=spread_model_family,
        retrain_days=retrain_days,
        candidate_policy=base_policy,
        use_timing_layer=False,
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
    spread_model_family: ModelFamily = DEFAULT_SPREAD_MODEL_FAMILY,
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
        spread_model_family=spread_model_family,
        retrain_days=retrain_days,
        candidate_policy=base_policy,
        use_timing_layer=False,
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
            active_block_rate=0.0,
            profitable_block_rate=0.0,
            worst_block_roi=0.0,
            block_roi_stddev=0.0,
            stability_score=0.0,
            max_drawdown=0.0,
        )

    activity_constraints = _build_spread_tuning_activity_constraints(
        candidate_blocks=candidate_blocks,
        starting_bankroll=starting_bankroll,
    )
    best_evaluation: PolicyEvaluation | None = None
    for policy in _spread_policy_grid(base_policy):
        evaluation = _evaluate_policy_on_candidate_blocks(
            candidate_blocks=candidate_blocks,
            policy=policy,
            starting_bankroll=starting_bankroll,
            activity_constraints=activity_constraints,
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
    min_confidence_values = _ordered_unique_values(
        (base_policy.min_confidence, *DEFAULT_TUNED_SPREAD_MIN_CONFIDENCE_VALUES)
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
            min_confidence=min_confidence,
            min_probability_edge=min_probability_edge,
            uncertainty_probability_buffer=(
                base_policy.uncertainty_probability_buffer
            ),
            min_games_played=min_games_played,
            kelly_fraction=base_policy.kelly_fraction,
            max_bet_fraction=base_policy.max_bet_fraction,
            max_daily_exposure_fraction=base_policy.max_daily_exposure_fraction,
            min_moneyline_price=base_policy.min_moneyline_price,
            max_moneyline_price=base_policy.max_moneyline_price,
            max_spread_abs_line=max_spread_abs_line,
            max_abs_rest_days_diff=base_policy.max_abs_rest_days_diff,
            min_positive_ev_books=base_policy.min_positive_ev_books,
            min_median_expected_value=base_policy.min_median_expected_value,
        )
        for min_edge in min_edge_values
        for min_confidence in min_confidence_values
        for min_probability_edge in min_probability_edge_values
        for min_games_played in min_games_played_values
        for max_spread_abs_line in max_spread_abs_line_values
    ]


def _evaluate_policy_on_candidate_blocks(
    *,
    candidate_blocks: list[CandidateBlock],
    policy: BetPolicy,
    starting_bankroll: float,
    activity_constraints: SpreadTuningActivityConstraints,
) -> PolicyEvaluation:
    bankroll = starting_bankroll
    peak_bankroll = bankroll
    max_drawdown = 0.0
    total_staked = 0.0
    blocks_with_bets = 0
    profitable_blocks = 0
    active_block_rois: list[float] = []
    bets_placed = 0
    clv_observations: list[ClosingLineValueObservation] = []

    for candidate_block in candidate_blocks:
        block_bankroll_start = bankroll
        block_total_staked = 0.0
        block_placed_bets: list[PlacedBet] = []
        spread_closing_metrics = dict(candidate_block.spread_closing_metrics)
        filtered_candidates = [
            candidate
            for candidate in candidate_block.candidates
            if candidate_matches_policy(candidate=candidate, policy=policy)
        ]
        filtered_candidates = select_best_quote_candidates(filtered_candidates)
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
            block_placed_bets.extend(day_bets)
            bankroll += sum(settle_bet(bet) for bet in day_bets)
            peak_bankroll = max(peak_bankroll, bankroll)
            if peak_bankroll > 0:
                max_drawdown = max(
                    max_drawdown,
                    (peak_bankroll - bankroll) / peak_bankroll,
                )
        if block_placed_bets:
            clv_observations.extend(
                _closing_line_value_observations(
                    placed_bets=block_placed_bets,
                    completed_records=list(candidate_block.completed_records),
                    spread_closing_metrics=spread_closing_metrics,
                )
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
    active_block_rate = (
        blocks_with_bets / len(candidate_blocks) if candidate_blocks else 0.0
    )
    profitable_block_rate = (
        profitable_blocks / blocks_with_bets if blocks_with_bets > 0 else 0.0
    )
    worst_block_roi = min(active_block_rois) if active_block_rois else 0.0
    block_roi_stddev = pstdev(active_block_rois) if len(active_block_rois) > 1 else 0.0
    clv_summary = _summarize_closing_line_value(clv_observations)
    meets_activity_constraints = (
        blocks_with_bets >= activity_constraints.min_active_blocks
        and bets_placed >= activity_constraints.min_bets
        and total_staked >= activity_constraints.min_total_staked
    )
    meets_close_quality_constraints = _meets_spread_tuning_close_quality_constraints(
        clv_summary
    )
    activity_score = (
        min(
            1.0,
            blocks_with_bets / activity_constraints.min_active_blocks,
        )
        + min(1.0, bets_placed / activity_constraints.min_bets)
        + min(1.0, total_staked / activity_constraints.min_total_staked)
    ) / 3.0
    stability_score = (
        roi
        + (0.10 * profitable_block_rate)
        + (0.05 * active_block_rate)
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
        active_block_rate=active_block_rate,
        profitable_block_rate=profitable_block_rate,
        worst_block_roi=worst_block_roi,
        block_roi_stddev=block_roi_stddev,
        stability_score=stability_score,
        max_drawdown=max_drawdown,
        meets_activity_constraints=meets_activity_constraints,
        meets_close_quality_constraints=meets_close_quality_constraints,
        activity_score=activity_score,
        clv=clv_summary,
    )


def _timing_example_for_candidate(
    *,
    example: ModelExample,
    candidate: CandidateBet,
) -> ModelExample:
    if candidate.market != "spread" or candidate.line_value is None:
        return example
    if (
        example.line_value is not None
        and abs(candidate.line_value - example.line_value) < 1e-9
    ):
        return example
    return repriced_spread_example(
        example=example,
        line_value=candidate.line_value,
    )


def _policy_evaluation_sort_key(
    *,
    evaluation: PolicyEvaluation,
    base_policy: BetPolicy,
) -> tuple[float | int, ...]:
    close_quality_sort_key = _spread_tuning_close_quality_sort_key(evaluation.clv)
    return (
        1.0 if evaluation.meets_tuning_constraints else 0.0,
        1.0 if evaluation.meets_close_quality_constraints else 0.0,
        1.0 if evaluation.meets_activity_constraints else 0.0,
        round(evaluation.profit, 10),
        *close_quality_sort_key,
        round(evaluation.roi, 10),
        round(evaluation.activity_score, 10),
        round(evaluation.active_block_rate, 10),
        round(evaluation.profitable_block_rate, 10),
        round(evaluation.worst_block_roi, 10),
        -round(evaluation.max_drawdown, 10),
        -round(evaluation.block_roi_stddev, 10),
        evaluation.bets_placed,
        1 if evaluation.policy == base_policy else 0,
    )


def _meets_spread_tuning_close_quality_constraints(
    summary: ClosingLineValueSummary,
) -> bool:
    average_closing_ev = summary.average_spread_closing_expected_value
    if average_closing_ev is not None:
        return average_closing_ev >= MIN_TUNED_SPREAD_AVERAGE_CLOSING_EV
    average_no_vig_delta = summary.average_spread_no_vig_probability_delta
    if average_no_vig_delta is not None:
        return (
            average_no_vig_delta
            >= MIN_TUNED_SPREAD_AVERAGE_NO_VIG_CLOSE_DELTA
        )
    return True


def _spread_tuning_close_quality_sort_key(
    summary: ClosingLineValueSummary,
) -> tuple[float, float, float]:
    average_closing_ev = summary.average_spread_closing_expected_value
    average_no_vig_delta = summary.average_spread_no_vig_probability_delta
    return (
        1.0 if average_closing_ev is not None else 0.0,
        round(average_closing_ev or 0.0, 10),
        round(average_no_vig_delta or 0.0, 10),
    )


def _build_spread_tuning_activity_constraints(
    *,
    candidate_blocks: list[CandidateBlock],
    starting_bankroll: float,
) -> SpreadTuningActivityConstraints:
    block_count = len(candidate_blocks)
    min_active_blocks = max(1, ceil(block_count * MIN_TUNED_SPREAD_ACTIVE_BLOCK_RATE))
    return SpreadTuningActivityConstraints(
        min_active_blocks=min_active_blocks,
        min_bets=max(MIN_TUNED_SPREAD_BETS, min_active_blocks * 2),
        min_total_staked=starting_bankroll * MIN_TUNED_SPREAD_STAKED_FRACTION * float(
            min_active_blocks
        ),
    )


def _ordered_unique_values(values: tuple[ValueT, ...]) -> list[ValueT]:
    unique_values: list[ValueT] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values
