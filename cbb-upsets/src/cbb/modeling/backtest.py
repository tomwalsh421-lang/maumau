"""Walk-forward bankroll backtesting for trained betting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

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
    score_candidate_bet,
    select_best_candidates,
    settle_bet,
)
from cbb.modeling.train import (
    DEFAULT_MODEL_SEASONS_BACK,
    LogisticRegressionConfig,
    resolve_training_seasons,
    score_examples,
    train_artifact_from_records,
)

DEFAULT_BACKTEST_RETRAIN_DAYS = 30
DEFAULT_STARTING_BANKROLL = 1000.0
DEFAULT_UNIT_SIZE = 25.0


@dataclass(frozen=True)
class BacktestOptions:
    """Options for walk-forward bankroll simulation."""

    market: StrategyMarket = "best"
    seasons_back: int = DEFAULT_MODEL_SEASONS_BACK
    evaluation_season: int | None = None
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL
    unit_size: float = DEFAULT_UNIT_SIZE
    retrain_days: int = DEFAULT_BACKTEST_RETRAIN_DAYS
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

    bankroll = options.starting_bankroll
    peak_bankroll = bankroll
    max_drawdown = 0.0
    total_staked = 0.0
    candidates_considered = 0
    placed_bets: list[PlacedBet] = []
    prior_evaluation_records: list[GameOddsRecord] = []
    trained_any_block = False

    for block in evaluation_blocks:
        training_records = sorted(
            [*base_records, *prior_evaluation_records],
            key=lambda record: (record.commence_time, record.game_id),
        )
        trained_artifacts = _train_block_artifacts(
            training_records=training_records,
            requested_market=options.market,
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
            policy=options.policy,
        )
        if options.market == "best":
            block_candidates = select_best_candidates(block_candidates)
        candidates_considered += len(block_candidates)

        for day_candidates in _group_candidates_by_day(block_candidates):
            day_bets = apply_bankroll_limits(
                bankroll=bankroll,
                policy=options.policy,
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
    )


def _train_block_artifacts(
    *,
    training_records: list[GameOddsRecord],
    requested_market: StrategyMarket,
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
                config=config,
            )
        except ValueError:
            if requested_market != "best":
                raise
            continue
    return trained_artifacts


def _score_block_candidates(
    *,
    training_records: list[GameOddsRecord],
    evaluation_block: list[GameOddsRecord],
    trained_artifacts: dict[ModelMarket, ModelArtifact],
    policy: BetPolicy,
) -> list[CandidateBet]:
    candidates: list[CandidateBet] = []
    for market, artifact in trained_artifacts.items():
        examples = build_prediction_examples(
            completed_records=training_records,
            upcoming_records=evaluation_block,
            market=market,
        )
        probabilities = score_examples(artifact=artifact, examples=examples)
        candidates.extend(
            candidate
            for example, probability in zip(examples, probabilities, strict=True)
            if (
                candidate := score_candidate_bet(
                    example=example,
                    probability=probability,
                    policy=policy,
                )
            )
            is not None
        )
    return candidates


def _requested_markets(strategy_market: StrategyMarket) -> list[ModelMarket]:
    if strategy_market == "best":
        return ["moneyline", "spread"]
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
