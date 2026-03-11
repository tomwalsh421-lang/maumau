"""Prediction workflow for trained betting models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
from cbb.modeling.execution import (
    build_executable_candidate_bets,
    evaluate_executable_quote_candidates,
)
from cbb.modeling.features import (
    ModelExample,
    build_prediction_examples,
    repriced_spread_example,
)
from cbb.modeling.policy import (
    BEST_CANDIDATE_MARKET_PRIORITY,
    BetPolicy,
    CandidateBet,
    PlacedBet,
    SupportingQuote,
    apply_bankroll_limits,
    candidate_matches_policy,
    deployable_spread_policy,
    select_best_candidates,
    select_best_quote_candidates,
)
from cbb.modeling.train import (
    score_examples,
    score_spread_timing_probability,
    select_spread_timing_model,
)


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
    auto_tune_spread_policy: bool = False
    use_timing_layer: bool = False
    policy: BetPolicy = field(default_factory=BetPolicy)


@dataclass(frozen=True)
class PredictionSummary:
    """Ranked predictions for upcoming games."""

    market: StrategyMarket
    available_games: int
    candidates_considered: int
    bets_placed: int
    recommendations: list[PlacedBet]
    deferred_recommendations: list[DeferredRecommendation] = field(
        default_factory=list
    )
    upcoming_games: list[UpcomingGamePrediction] = field(default_factory=list)
    artifact_name: str = DEFAULT_ARTIFACT_NAME
    generated_at: datetime | None = None
    expires_at: datetime | None = None
    applied_policy: BetPolicy | None = None
    policy_was_auto_tuned: bool = False
    policy_tuned_blocks: int = 0


@dataclass(frozen=True)
class DeferredRecommendation:
    """Candidate bet deferred because the timing layer prefers waiting."""

    candidate: CandidateBet
    favorable_close_probability: float


@dataclass(frozen=True)
class UpcomingGamePrediction:
    """Best currently known angle for one upcoming game."""

    game_id: int
    commence_time: str
    team_name: str
    opponent_name: str
    status: str
    market: ModelMarket | None = None
    side: str | None = None
    sportsbook: str | None = None
    market_price: float | None = None
    line_value: float | None = None
    eligible_books: int = 0
    positive_ev_books: int = 0
    coverage_rate: float = 0.0
    model_probability: float | None = None
    implied_probability: float | None = None
    probability_edge: float | None = None
    expected_value: float | None = None
    stake_fraction: float | None = None
    stake_amount: float | None = None
    supporting_quotes: tuple[SupportingQuote, ...] = ()
    min_acceptable_line: float | None = None
    min_acceptable_price: float | None = None
    favorable_close_probability: float | None = None
    reason_code: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class _ScoredPredictionOpportunity:
    game_id: int
    commence_time: str
    market: ModelMarket
    team_name: str
    opponent_name: str
    side: str
    sportsbook: str
    market_price: float
    line_value: float | None
    eligible_books: int
    model_probability: float
    implied_probability: float
    probability_edge: float
    expected_value: float
    stake_fraction: float
    minimum_games_played: int
    abs_rest_days_diff: float
    positive_ev_books: int
    coverage_rate: float
    supporting_quotes: tuple[SupportingQuote, ...]
    min_acceptable_line: float | None
    min_acceptable_price: float | None
    median_expected_value: float | None


def predict_best_bets(options: PredictionOptions) -> PredictionSummary:
    """Load trained artifacts and return current ranked bet suggestions."""
    generated_at = options.now or datetime.now(UTC)
    applied_policy = (
        deployable_spread_policy(options.policy)
        if options.market in {"spread", "best"}
        else options.policy
    )
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
            deferred_recommendations=[],
            upcoming_games=[],
            artifact_name=options.artifact_name,
            generated_at=generated_at,
            expires_at=None,
            applied_policy=applied_policy,
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

    policy_was_auto_tuned = False
    policy_tuned_blocks = 0
    deferred_recommendations: list[DeferredRecommendation] = []
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
            base_policy=applied_policy,
            spread_model_family=spread_artifact.model_family,
            retrain_days=DEFAULT_BACKTEST_RETRAIN_DAYS,
            starting_bankroll=options.bankroll,
        )
        if tuning_evaluation.meets_tuning_constraints:
            applied_policy = tuning_evaluation.policy
            policy_was_auto_tuned = True
            policy_tuned_blocks = tuning_evaluation.blocks_evaluated

    raw_candidate_bets: list[CandidateBet] = []
    raw_deferred_recommendations: list[DeferredRecommendation] = []
    raw_opportunities: list[_ScoredPredictionOpportunity] = []
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
        for example, probability in zip(examples, probabilities, strict=True):
            raw_opportunities.extend(
                _score_executable_prediction_opportunities(
                    artifact=artifact,
                    example=example,
                    probability=probability,
                    policy=market_policy,
                )
            )
            executable_candidates = build_executable_candidate_bets(
                artifact=artifact,
                example=example,
                probability=probability,
                policy=market_policy,
            )
            if not executable_candidates:
                continue
            for candidate in executable_candidates:
                if not candidate_matches_policy(
                    candidate=candidate,
                    policy=market_policy,
                ):
                    continue
                if (
                    options.use_timing_layer
                    and market_name == "spread"
                    and (
                        deferred_recommendation := _defer_spread_candidate_for_timing(
                            artifact=artifact,
                            example=_timing_example_for_candidate(
                                example=example,
                                candidate=candidate,
                            ),
                            candidate=candidate,
                        )
                    )
                    is not None
                ):
                    raw_deferred_recommendations.append(deferred_recommendation)
                    continue
                raw_candidate_bets.append(candidate)

    candidate_bets = select_best_quote_candidates(raw_candidate_bets)
    if options.market == "best":
        candidate_bets = select_best_candidates(candidate_bets)
    deferred_recommendations = _best_deferred_recommendations(
        deferred_recommendations=raw_deferred_recommendations,
        strategy_market=options.market,
        placed_candidate_keys={
            (candidate.game_id, candidate.market, candidate.side)
            for candidate in candidate_bets
        },
    )

    placed_bets = apply_bankroll_limits(
        bankroll=options.bankroll,
        policy=applied_policy,
        candidate_bets=candidate_bets,
    )
    ranked_bets = sorted(
        placed_bets,
        key=lambda bet: (
            -bet.coverage_rate,
            -bet.positive_ev_books,
            -bet.expected_value,
            -bet.probability_edge,
            -bet.model_probability,
            bet.commence_time,
            bet.game_id,
            bet.sportsbook,
        ),
    )
    ranked_deferred_recommendations = sorted(
        deferred_recommendations,
        key=lambda recommendation: (
            recommendation.candidate.commence_time,
            -recommendation.candidate.expected_value,
            recommendation.candidate.game_id,
            recommendation.candidate.sportsbook,
        ),
    )
    upcoming_games = _build_upcoming_game_predictions(
        upcoming_records=upcoming_records,
        strategy_market=options.market,
        applied_policy=applied_policy,
        raw_opportunities=raw_opportunities,
        placed_bets=ranked_bets,
        deferred_recommendations=ranked_deferred_recommendations,
    )
    return PredictionSummary(
        market=options.market,
        available_games=len({record.game_id for record in upcoming_records}),
        candidates_considered=(
            len(candidate_bets) + len(ranked_deferred_recommendations)
        ),
        bets_placed=len(ranked_bets[: options.limit]),
        recommendations=ranked_bets[: options.limit],
        deferred_recommendations=ranked_deferred_recommendations[: options.limit],
        upcoming_games=upcoming_games,
        artifact_name=options.artifact_name,
        generated_at=generated_at,
        expires_at=_prediction_expires_at(
            generated_at=generated_at,
            upcoming_records=upcoming_records,
        ),
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
        return [("spread", spread_artifact)]

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


def _defer_spread_candidate_for_timing(
    *,
    artifact: ModelArtifact,
    example: ModelExample,
    candidate: CandidateBet,
) -> DeferredRecommendation | None:
    timing_model = select_spread_timing_model(
        artifact=artifact,
        example=example,
    )
    if timing_model is None:
        return None
    favorable_close_probability = score_spread_timing_probability(
        timing_model=timing_model,
        example=example,
    )
    if favorable_close_probability is None:
        return None
    if favorable_close_probability >= timing_model.min_favorable_probability:
        return None
    return DeferredRecommendation(
        candidate=candidate,
        favorable_close_probability=favorable_close_probability,
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


def _best_deferred_recommendations(
    *,
    deferred_recommendations: list[DeferredRecommendation],
    strategy_market: StrategyMarket,
    placed_candidate_keys: set[tuple[int, ModelMarket, str]],
) -> list[DeferredRecommendation]:
    best_by_scope: dict[tuple[int, ModelMarket, str], DeferredRecommendation] = {}
    for recommendation in deferred_recommendations:
        scope_key = (
            recommendation.candidate.game_id,
            recommendation.candidate.market,
            recommendation.candidate.side,
        )
        if scope_key in placed_candidate_keys:
            continue
        current_best = best_by_scope.get(scope_key)
        if current_best is None or _candidate_sort_key(
            recommendation.candidate,
            strategy_market=strategy_market,
        ) < _candidate_sort_key(
            current_best.candidate,
            strategy_market=strategy_market,
        ):
            best_by_scope[scope_key] = recommendation
    scoped_recommendations = list(best_by_scope.values())
    if strategy_market != "best":
        return scoped_recommendations

    best_by_game: dict[int, DeferredRecommendation] = {}
    for recommendation in scoped_recommendations:
        current_best = best_by_game.get(recommendation.candidate.game_id)
        if current_best is None or _candidate_sort_key(
            recommendation.candidate,
            strategy_market=strategy_market,
        ) < _candidate_sort_key(
            current_best.candidate,
            strategy_market=strategy_market,
        ):
            best_by_game[recommendation.candidate.game_id] = recommendation
    return list(best_by_game.values())


def _score_executable_prediction_opportunities(
    *,
    artifact: ModelArtifact,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
) -> list[_ScoredPredictionOpportunity]:
    evaluation = evaluate_executable_quote_candidates(
        artifact=artifact,
        example=example,
        probability=probability,
        policy=policy,
    )
    opportunities: list[_ScoredPredictionOpportunity] = []
    for candidate in evaluation.scored_candidates:
        opportunities.append(
            _ScoredPredictionOpportunity(
                game_id=candidate.game_id,
                commence_time=candidate.commence_time,
                market=candidate.market,
                team_name=candidate.team_name,
                opponent_name=candidate.opponent_name,
                side=candidate.side,
                sportsbook=candidate.sportsbook,
                market_price=candidate.market_price,
                line_value=candidate.line_value,
                eligible_books=candidate.eligible_books,
                model_probability=candidate.model_probability,
                implied_probability=candidate.implied_probability,
                probability_edge=candidate.probability_edge,
                expected_value=candidate.expected_value,
                stake_fraction=candidate.stake_fraction,
                minimum_games_played=candidate.minimum_games_played,
                abs_rest_days_diff=candidate.abs_rest_days_diff,
                positive_ev_books=candidate.positive_ev_books,
                coverage_rate=candidate.coverage_rate,
                supporting_quotes=candidate.supporting_quotes,
                min_acceptable_line=candidate.min_acceptable_line,
                min_acceptable_price=candidate.min_acceptable_price,
                median_expected_value=evaluation.diagnostics.median_expected_value,
            )
        )
    return opportunities


def _prediction_expires_at(
    *,
    generated_at: datetime,
    upcoming_records: Sequence[object],
) -> datetime | None:
    commence_times = [
        commence_time
        for record in upcoming_records
        if isinstance(
            (commence_time := getattr(record, "commence_time", None)),
            datetime,
        )
    ]
    if not commence_times:
        return None
    earliest_commence = min(commence_times)
    return min(generated_at + timedelta(minutes=15), earliest_commence)


def _build_upcoming_game_predictions(
    *,
    upcoming_records,
    strategy_market: StrategyMarket,
    applied_policy: BetPolicy,
    raw_opportunities: list[_ScoredPredictionOpportunity],
    placed_bets: list[PlacedBet],
    deferred_recommendations: list[DeferredRecommendation],
) -> list[UpcomingGamePrediction]:
    placed_by_game = _best_placed_bets_by_game(
        placed_bets=placed_bets,
        strategy_market=strategy_market,
    )
    deferred_by_game = _best_deferred_by_game(
        deferred_recommendations=deferred_recommendations,
        strategy_market=strategy_market,
    )
    pass_by_game = _best_pass_opportunities_by_game(
        raw_opportunities=raw_opportunities,
        strategy_market=strategy_market,
        excluded_game_ids=set(placed_by_game) | set(deferred_by_game),
    )
    predictions: list[UpcomingGamePrediction] = []
    for record in sorted(
        upcoming_records,
        key=lambda record: (
            str(getattr(record, "commence_time", "")),
            getattr(record, "game_id", 0),
        ),
    ):
        placed_bet = placed_by_game.get(record.game_id)
        if placed_bet is not None:
            predictions.append(
                UpcomingGamePrediction(
                    game_id=placed_bet.game_id,
                    commence_time=placed_bet.commence_time,
                    team_name=placed_bet.team_name,
                    opponent_name=placed_bet.opponent_name,
                    status="bet",
                    market=placed_bet.market,
                    side=placed_bet.side,
                    sportsbook=placed_bet.sportsbook,
                    market_price=placed_bet.market_price,
                    line_value=placed_bet.line_value,
                    eligible_books=placed_bet.eligible_books,
                    positive_ev_books=placed_bet.positive_ev_books,
                    coverage_rate=placed_bet.coverage_rate,
                    model_probability=placed_bet.model_probability,
                    implied_probability=placed_bet.implied_probability,
                    probability_edge=placed_bet.probability_edge,
                    expected_value=placed_bet.expected_value,
                    stake_fraction=placed_bet.stake_fraction,
                    stake_amount=placed_bet.stake_amount,
                    supporting_quotes=placed_bet.supporting_quotes,
                    min_acceptable_line=placed_bet.min_acceptable_line,
                    min_acceptable_price=placed_bet.min_acceptable_price,
                    reason_code="qualified",
                )
            )
            continue
        deferred_recommendation = deferred_by_game.get(record.game_id)
        if deferred_recommendation is not None:
            candidate = deferred_recommendation.candidate
            predictions.append(
                UpcomingGamePrediction(
                    game_id=candidate.game_id,
                    commence_time=candidate.commence_time,
                    team_name=candidate.team_name,
                    opponent_name=candidate.opponent_name,
                    status="wait",
                    market=candidate.market,
                    side=candidate.side,
                    sportsbook=candidate.sportsbook,
                    market_price=candidate.market_price,
                    line_value=candidate.line_value,
                    eligible_books=candidate.eligible_books,
                    positive_ev_books=candidate.positive_ev_books,
                    coverage_rate=candidate.coverage_rate,
                    model_probability=candidate.model_probability,
                    implied_probability=candidate.implied_probability,
                    probability_edge=candidate.probability_edge,
                    expected_value=candidate.expected_value,
                    stake_fraction=candidate.stake_fraction,
                    supporting_quotes=candidate.supporting_quotes,
                    min_acceptable_line=candidate.min_acceptable_line,
                    min_acceptable_price=candidate.min_acceptable_price,
                    favorable_close_probability=(
                        deferred_recommendation.favorable_close_probability
                    ),
                    reason_code="timing_wait",
                )
            )
            continue
        opportunity = pass_by_game.get(record.game_id)
        if opportunity is None:
            predictions.append(
                UpcomingGamePrediction(
                    game_id=record.game_id,
                    commence_time=_record_commence_time(record),
                    team_name=str(getattr(record, "home_team_name", "Unknown Team")),
                    opponent_name=str(
                        getattr(record, "away_team_name", "Unknown Opponent")
                    ),
                    status="pass",
                    reason_code="no_priced_market",
                    note="no_priced_market",
                )
            )
            continue
        reason_code = _opportunity_blocker_reason_code(
            opportunity=opportunity,
            policy=applied_policy,
        )
        predictions.append(
            UpcomingGamePrediction(
                game_id=opportunity.game_id,
                commence_time=opportunity.commence_time,
                team_name=opportunity.team_name,
                opponent_name=opportunity.opponent_name,
                status="pass",
                market=opportunity.market,
                side=opportunity.side,
                sportsbook=opportunity.sportsbook,
                market_price=opportunity.market_price,
                line_value=opportunity.line_value,
                eligible_books=opportunity.eligible_books,
                positive_ev_books=opportunity.positive_ev_books,
                coverage_rate=opportunity.coverage_rate,
                model_probability=opportunity.model_probability,
                implied_probability=opportunity.implied_probability,
                probability_edge=opportunity.probability_edge,
                expected_value=opportunity.expected_value,
                stake_fraction=opportunity.stake_fraction,
                supporting_quotes=opportunity.supporting_quotes,
                min_acceptable_line=opportunity.min_acceptable_line,
                min_acceptable_price=opportunity.min_acceptable_price,
                reason_code=reason_code,
                note=_opportunity_blocker_note(
                    opportunity=opportunity,
                    policy=applied_policy,
                    reason_code=reason_code,
                ),
            )
        )
    return predictions


def _record_commence_time(record: object) -> str:
    commence_time = getattr(record, "commence_time", None)
    if isinstance(commence_time, datetime):
        return commence_time.isoformat()
    if commence_time is None:
        return ""
    return str(commence_time)


def _best_placed_bets_by_game(
    *,
    placed_bets: list[PlacedBet],
    strategy_market: StrategyMarket,
) -> dict[int, PlacedBet]:
    best_by_game: dict[int, PlacedBet] = {}
    for placed_bet in placed_bets:
        current_best = best_by_game.get(placed_bet.game_id)
        if current_best is None or _placed_bet_sort_key(
            placed_bet,
            strategy_market=strategy_market,
        ) < _placed_bet_sort_key(current_best, strategy_market=strategy_market):
            best_by_game[placed_bet.game_id] = placed_bet
    return best_by_game


def _best_deferred_by_game(
    *,
    deferred_recommendations: list[DeferredRecommendation],
    strategy_market: StrategyMarket,
) -> dict[int, DeferredRecommendation]:
    best_by_game: dict[int, DeferredRecommendation] = {}
    for deferred_recommendation in deferred_recommendations:
        current_best = best_by_game.get(deferred_recommendation.candidate.game_id)
        if current_best is None or _candidate_sort_key(
            deferred_recommendation.candidate,
            strategy_market=strategy_market,
        ) < _candidate_sort_key(
            current_best.candidate,
            strategy_market=strategy_market,
        ):
            best_by_game[deferred_recommendation.candidate.game_id] = (
                deferred_recommendation
            )
    return best_by_game


def _best_pass_opportunities_by_game(
    *,
    raw_opportunities: list[_ScoredPredictionOpportunity],
    strategy_market: StrategyMarket,
    excluded_game_ids: set[int],
) -> dict[int, _ScoredPredictionOpportunity]:
    best_by_game: dict[int, _ScoredPredictionOpportunity] = {}
    for opportunity in raw_opportunities:
        if opportunity.game_id in excluded_game_ids:
            continue
        current_best = best_by_game.get(opportunity.game_id)
        if current_best is None or _opportunity_sort_key(
            opportunity,
            strategy_market=strategy_market,
        ) < _opportunity_sort_key(current_best, strategy_market=strategy_market):
            best_by_game[opportunity.game_id] = opportunity
    return best_by_game


def _placed_bet_sort_key(
    placed_bet: PlacedBet,
    *,
    strategy_market: StrategyMarket,
) -> tuple[int, float, int, float, float, float, int, str]:
    market_priority = (
        BEST_CANDIDATE_MARKET_PRIORITY.get(placed_bet.market, 99)
        if strategy_market == "best"
        else 0
    )
    return (
        market_priority,
        -placed_bet.coverage_rate,
        -placed_bet.positive_ev_books,
        -placed_bet.expected_value,
        -placed_bet.probability_edge,
        -placed_bet.model_probability,
        placed_bet.game_id,
        placed_bet.sportsbook,
    )


def _candidate_sort_key(
    candidate: CandidateBet,
    *,
    strategy_market: StrategyMarket,
) -> tuple[int, float, int, float, float, float, int, str]:
    market_priority = (
        BEST_CANDIDATE_MARKET_PRIORITY.get(candidate.market, 99)
        if strategy_market == "best"
        else 0
    )
    return (
        market_priority,
        -candidate.coverage_rate,
        -candidate.positive_ev_books,
        -candidate.expected_value,
        -candidate.probability_edge,
        -candidate.model_probability,
        candidate.game_id,
        candidate.sportsbook,
    )


def _opportunity_sort_key(
    opportunity: _ScoredPredictionOpportunity,
    *,
    strategy_market: StrategyMarket,
) -> tuple[int, float, int, float, float, float, int, str]:
    market_priority = (
        BEST_CANDIDATE_MARKET_PRIORITY.get(opportunity.market, 99)
        if strategy_market == "best"
        else 0
    )
    return (
        market_priority,
        -opportunity.coverage_rate,
        -opportunity.positive_ev_books,
        -opportunity.expected_value,
        -opportunity.probability_edge,
        -opportunity.model_probability,
        opportunity.game_id,
        opportunity.sportsbook,
    )


def _opportunity_blocker_reason_code(
    *,
    opportunity: _ScoredPredictionOpportunity,
    policy: BetPolicy,
) -> str:
    if opportunity.expected_value <= 0.0 or opportunity.stake_fraction <= 0.0:
        return "no_positive_ev"
    non_edge_blocker = _opportunity_non_edge_blocker_note(
        opportunity=opportunity,
        policy=policy,
    )
    if non_edge_blocker is not None:
        return non_edge_blocker
    if opportunity.probability_edge < policy.min_probability_edge:
        return "probability_edge"
    if opportunity.expected_value < policy.min_edge:
        return "edge"
    if opportunity.positive_ev_books < policy.min_positive_ev_books:
        return "positive_ev_books"
    if (
        policy.min_median_expected_value is not None
        and (
            opportunity.median_expected_value is None
            or opportunity.median_expected_value < policy.min_median_expected_value
        )
    ):
        return "not_selected"
    return "not_selected"


def _opportunity_blocker_note(
    *,
    opportunity: _ScoredPredictionOpportunity,
    policy: BetPolicy,
    reason_code: str | None = None,
) -> str:
    blocker_reason_code = reason_code or _opportunity_blocker_reason_code(
        opportunity=opportunity,
        policy=policy,
    )
    if blocker_reason_code == "positive_ev_books":
        return (
            "positive_ev_books="
            f"{opportunity.positive_ev_books}/{policy.min_positive_ev_books}"
        )
    if (
        policy.min_median_expected_value is not None
        and (
            opportunity.median_expected_value is None
            or opportunity.median_expected_value < policy.min_median_expected_value
        )
    ):
        observed = (
            "none"
            if opportunity.median_expected_value is None
            else f"{opportunity.median_expected_value:.3f}"
        )
        return (
            "median_expected_value="
            f"{observed}/{policy.min_median_expected_value:.3f}"
        )
    return blocker_reason_code


def _opportunity_non_edge_blocker_note(
    *,
    opportunity: _ScoredPredictionOpportunity,
    policy: BetPolicy,
) -> str | None:
    if opportunity.minimum_games_played < policy.min_games_played:
        return "games_played"
    if (
        opportunity.market == "moneyline"
        and (
            opportunity.market_price < policy.min_moneyline_price
            or opportunity.market_price > policy.max_moneyline_price
        )
    ):
        return "moneyline_price"
    if (
        opportunity.market == "spread"
        and policy.max_spread_abs_line is not None
        and (
            opportunity.line_value is None
            or abs(opportunity.line_value) > policy.max_spread_abs_line
        )
    ):
        return "spread_abs_line"
    if (
        opportunity.market == "spread"
        and policy.max_abs_rest_days_diff is not None
        and opportunity.abs_rest_days_diff > policy.max_abs_rest_days_diff
    ):
        return "rest_days_diff"
    if opportunity.model_probability < policy.min_confidence:
        return "confidence"
    return None


def _candidate_to_opportunity(candidate: CandidateBet) -> _ScoredPredictionOpportunity:
    """Project one quote-scored candidate onto the pass-diagnostics shape."""
    return _ScoredPredictionOpportunity(
        game_id=candidate.game_id,
        commence_time=candidate.commence_time,
        market=candidate.market,
        team_name=candidate.team_name,
        opponent_name=candidate.opponent_name,
        side=candidate.side,
        sportsbook=candidate.sportsbook,
        market_price=candidate.market_price,
        line_value=candidate.line_value,
        eligible_books=candidate.eligible_books,
        model_probability=candidate.model_probability,
        implied_probability=candidate.implied_probability,
        probability_edge=candidate.probability_edge,
        expected_value=candidate.expected_value,
        stake_fraction=candidate.stake_fraction,
        minimum_games_played=candidate.minimum_games_played,
        abs_rest_days_diff=candidate.abs_rest_days_diff,
        positive_ev_books=candidate.positive_ev_books,
        coverage_rate=candidate.coverage_rate,
        supporting_quotes=candidate.supporting_quotes,
        min_acceptable_line=candidate.min_acceptable_line,
        min_acceptable_price=candidate.min_acceptable_price,
        median_expected_value=None,
    )
