"""Prediction workflow for trained betting models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import cast

from cbb.modeling.artifacts import (
    DEFAULT_ARTIFACT_NAME,
    ModelArtifact,
    ModelMarket,
    StrategyMarket,
    load_artifact,
)
from cbb.modeling.backtest import (
    DEFAULT_BACKTEST_RETRAIN_DAYS,
    derive_latest_spread_policy_from_records,
)
from cbb.modeling.dataset import (
    get_available_seasons,
    load_completed_game_records,
    load_upcoming_game_records,
)
from cbb.modeling.features import build_prediction_examples
from cbb.modeling.policy import (
    BetPolicy,
    CandidateBet,
    PlacedBet,
    apply_bankroll_limits,
    score_candidate_bet,
    select_best_candidates,
)
from cbb.modeling.train import score_examples


@dataclass(frozen=True)
class PredictionOptions:
    """Options for generating ranked betting recommendations."""

    market: StrategyMarket = "best"
    artifact_name: str = DEFAULT_ARTIFACT_NAME
    bankroll: float = 1000.0
    limit: int = 10
    database_url: str | None = None
    artifacts_dir: Path | None = None
    now: datetime | None = None
    auto_tune_spread_policy: bool = True
    policy: BetPolicy = field(default_factory=BetPolicy)


@dataclass(frozen=True)
class PredictionSummary:
    """Ranked predictions for upcoming games."""

    market: StrategyMarket
    available_games: int
    candidates_considered: int
    bets_placed: int
    recommendations: list[PlacedBet]
    applied_policy: BetPolicy | None = None
    policy_was_auto_tuned: bool = False
    policy_tuned_blocks: int = 0


def predict_best_bets(options: PredictionOptions) -> PredictionSummary:
    """Load trained artifacts and return current ranked bet suggestions."""
    upcoming_records = load_upcoming_game_records(
        database_url=options.database_url,
        now=options.now,
    )
    if not upcoming_records:
        return PredictionSummary(
            market=options.market,
            available_games=0,
            candidates_considered=0,
            bets_placed=0,
            recommendations=[],
            applied_policy=options.policy,
        )

    available_seasons = get_available_seasons(options.database_url)
    if not available_seasons:
        raise ValueError("No completed seasons are available for prediction")
    completed_records = load_completed_game_records(
        max_season=available_seasons[-1],
        database_url=options.database_url,
    )

    artifacts = _load_prediction_artifacts(
        market=options.market,
        artifact_name=options.artifact_name,
        artifacts_dir=options.artifacts_dir,
    )
    if not artifacts:
        raise FileNotFoundError(
            f"No trained artifacts are available for market={options.market!r}"
        )

    applied_policy = options.policy
    policy_was_auto_tuned = False
    policy_tuned_blocks = 0
    spread_artifact = next(
        (artifact for market_name, artifact in artifacts if market_name == "spread"),
        None,
    )
    if (
        options.auto_tune_spread_policy
        and options.market in {"spread", "best"}
        and spread_artifact is not None
    ):
        tuning_evaluation = derive_latest_spread_policy_from_records(
            completed_records=[
                record
                for record in completed_records
                if record.season >= spread_artifact.metrics.start_season
            ],
            base_policy=options.policy,
            spread_model_family=spread_artifact.model_family,
            retrain_days=DEFAULT_BACKTEST_RETRAIN_DAYS,
            starting_bankroll=options.bankroll,
        )
        if tuning_evaluation.blocks_evaluated > 0:
            applied_policy = tuning_evaluation.policy
            policy_was_auto_tuned = True
            policy_tuned_blocks = tuning_evaluation.blocks_evaluated

    candidate_bets: list[CandidateBet] = []
    for market_name, artifact in artifacts:
        market_completed_records = [
            record
            for record in completed_records
            if record.season >= artifact.metrics.start_season
        ]
        market_policy = applied_policy if market_name == "spread" else options.policy
        examples = build_prediction_examples(
            completed_records=market_completed_records,
            upcoming_records=upcoming_records,
            market=market_name,
        )
        probabilities = score_examples(artifact=artifact, examples=examples)
        candidate_bets.extend(
            candidate
            for example, probability in zip(examples, probabilities, strict=True)
            if (
                candidate := score_candidate_bet(
                    example=example,
                    probability=probability,
                    policy=market_policy,
                )
            )
            is not None
        )

    if options.market == "best":
        candidate_bets = select_best_candidates(candidate_bets)

    placed_bets = apply_bankroll_limits(
        bankroll=options.bankroll,
        policy=applied_policy,
        candidate_bets=candidate_bets,
    )
    ranked_bets = sorted(
        placed_bets,
        key=lambda bet: (
            -bet.expected_value,
            -bet.model_probability,
            bet.commence_time,
            bet.game_id,
        ),
    )
    return PredictionSummary(
        market=options.market,
        available_games=len({record.game_id for record in upcoming_records}),
        candidates_considered=len(candidate_bets),
        bets_placed=len(ranked_bets[: options.limit]),
        recommendations=ranked_bets[: options.limit],
        applied_policy=applied_policy,
        policy_was_auto_tuned=policy_was_auto_tuned,
        policy_tuned_blocks=policy_tuned_blocks,
    )


def _load_prediction_artifacts(
    *,
    market: StrategyMarket,
    artifact_name: str,
    artifacts_dir: Path | None,
) -> list[tuple[ModelMarket, ModelArtifact]]:
    artifacts: list[tuple[ModelMarket, ModelArtifact]] = []
    if market in {"moneyline", "spread"}:
        artifact = load_artifact(
            market=cast(ModelMarket, market),
            artifact_name=artifact_name,
            artifacts_dir=artifacts_dir,
        )
        return [(cast(ModelMarket, market), artifact)]

    try:
        spread_artifact = load_artifact(
            market="spread",
            artifact_name=artifact_name,
            artifacts_dir=artifacts_dir,
        )
    except FileNotFoundError:
        spread_artifact = None
    if spread_artifact is not None:
        artifacts.append(("spread", spread_artifact))

    try:
        moneyline_artifact = load_artifact(
            market="moneyline",
            artifact_name=artifact_name,
            artifacts_dir=artifacts_dir,
        )
    except FileNotFoundError:
        moneyline_artifact = None
    if moneyline_artifact is not None:
        artifacts.append(("moneyline", moneyline_artifact))
    return artifacts
