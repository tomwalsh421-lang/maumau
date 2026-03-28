"""Prediction workflow for trained betting models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from cbb.db import AvailabilityGameSideShadow, get_availability_game_side_shadows
from cbb.modeling.artifacts import (
    DEFAULT_ARTIFACT_NAME,
    ModelArtifact,
    ModelMarket,
    StrategyMarket,
    load_artifact,
)
from cbb.modeling.backtest import (
    DEFAULT_BACKTEST_RETRAIN_DAYS,
    DEFAULT_STARTING_BANKROLL,
    derive_latest_spread_policy_from_records,
)
from cbb.modeling.dataset import (
    get_available_seasons,
    load_completed_game_records,
    load_live_board_game_records,
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
    bankroll: float = DEFAULT_STARTING_BANKROLL
    limit: int = 10
    database_url: str | None = None
    artifacts_dir: Path | None = None
    now: datetime | None = None
    auto_tune_spread_policy: bool = False
    use_timing_layer: bool = False
    policy: BetPolicy = field(default_factory=BetPolicy)


@dataclass(frozen=True)
class PredictionAvailabilitySummary:
    """Shadow-only availability coverage summary for the current slate."""

    games_with_context: int = 0
    games_with_both_reports: int = 0
    games_with_team_only: int = 0
    games_with_opponent_only: int = 0
    games_with_unmatched_rows: int = 0
    team_sides_with_unmatched_rows: int = 0
    opponent_sides_with_unmatched_rows: int = 0
    games_with_any_out: int = 0
    games_with_any_questionable: int = 0
    latest_report_update_at: str | None = None
    closest_report_minutes_before_tip: float | None = None


@dataclass(frozen=True)
class PredictionSummary:
    """Ranked predictions for upcoming games."""

    market: StrategyMarket
    available_games: int
    candidates_considered: int
    bets_placed: int
    recommendations: list[PlacedBet]
    deferred_recommendations: list[DeferredRecommendation] = field(default_factory=list)
    upcoming_games: list[UpcomingGamePrediction] = field(default_factory=list)
    live_board_games: list[LiveBoardGame] = field(default_factory=list)
    availability_summary: PredictionAvailabilitySummary = field(
        default_factory=PredictionAvailabilitySummary
    )
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
class AvailabilitySideContext:
    """Shadow-only availability summary for one team on one game row."""

    has_report: bool = False
    source_name: str | None = None
    latest_update_at: str | None = None
    latest_minutes_before_tip: float | None = None
    any_out: bool = False
    any_questionable: bool = False
    out_count: int = 0
    questionable_count: int = 0
    matched_row_count: int = 0
    unmatched_row_count: int = 0


@dataclass(frozen=True)
class AvailabilityGameContext:
    """Shadow-only availability context for one prediction or board row."""

    coverage_status: str
    team: AvailabilitySideContext
    opponent: AvailabilitySideContext


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
    availability_context: AvailabilityGameContext | None = None


@dataclass(frozen=True)
class LiveBoardGame:
    """One live-board row spanning recent finals through upcoming games."""

    game_id: int
    commence_time: str
    home_team_name: str
    away_team_name: str
    game_status: str
    board_status: str
    market: ModelMarket | None = None
    team_name: str | None = None
    opponent_name: str | None = None
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
    home_score: int | None = None
    away_score: int | None = None
    last_score_update: datetime | None = None
    availability_context: AvailabilityGameContext | None = None


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
    live_board_records = load_live_board_game_records(
        database_url=options.database_url,
        now=options.now,
    )
    upcoming_records = [
        record
        for record in live_board_records
        if _record_is_upcoming(record, generated_at)
    ]
    if not live_board_records:
        return PredictionSummary(
            market=options.market,
            available_games=0,
            candidates_considered=0,
            bets_placed=0,
            recommendations=[],
            deferred_recommendations=[],
            upcoming_games=[],
            live_board_games=[],
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
    availability_shadows_by_game_side = _availability_shadows_by_game_side(
        database_url=options.database_url,
        game_ids={
            int(game_id)
            for game_id in (
                getattr(record, "game_id", None) for record in live_board_records
            )
            if isinstance(game_id, int)
        },
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
            upcoming_records=live_board_records,
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
    actionable_game_ids = {record.game_id for record in upcoming_records}
    actionable_bets = [
        bet for bet in ranked_bets if bet.game_id in actionable_game_ids
    ][: options.limit]
    actionable_deferred_recommendations = [
        recommendation
        for recommendation in ranked_deferred_recommendations
        if recommendation.candidate.game_id in actionable_game_ids
    ][: options.limit]
    upcoming_games = _build_upcoming_game_predictions(
        upcoming_records=upcoming_records,
        strategy_market=options.market,
        applied_policy=applied_policy,
        raw_opportunities=raw_opportunities,
        placed_bets=ranked_bets,
        deferred_recommendations=ranked_deferred_recommendations,
        availability_shadows_by_game_side=availability_shadows_by_game_side,
    )
    live_board_games = _build_live_board_game_predictions(
        board_records=live_board_records,
        strategy_market=options.market,
        applied_policy=applied_policy,
        raw_opportunities=raw_opportunities,
        placed_bets=ranked_bets,
        deferred_recommendations=ranked_deferred_recommendations,
        current_time=generated_at,
        availability_shadows_by_game_side=availability_shadows_by_game_side,
    )
    availability_summary = _summarize_prediction_availability(
        upcoming_games=upcoming_games
    )
    return PredictionSummary(
        market=options.market,
        available_games=len(actionable_game_ids),
        candidates_considered=(
            len(
                [
                    candidate
                    for candidate in candidate_bets
                    if candidate.game_id in actionable_game_ids
                ]
            )
            + len(
                [
                    recommendation
                    for recommendation in ranked_deferred_recommendations
                    if recommendation.candidate.game_id in actionable_game_ids
                ]
            )
        ),
        bets_placed=len(actionable_bets),
        recommendations=actionable_bets,
        deferred_recommendations=actionable_deferred_recommendations,
        upcoming_games=upcoming_games,
        live_board_games=live_board_games,
        availability_summary=availability_summary,
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


def _summarize_prediction_availability(
    *,
    upcoming_games: Sequence[UpcomingGamePrediction],
) -> PredictionAvailabilitySummary:
    games_with_context = 0
    games_with_both_reports = 0
    games_with_team_only = 0
    games_with_opponent_only = 0
    games_with_unmatched_rows = 0
    team_sides_with_unmatched_rows = 0
    opponent_sides_with_unmatched_rows = 0
    games_with_any_out = 0
    games_with_any_questionable = 0
    latest_report_update_at: datetime | None = None
    closest_report_minutes_before_tip: float | None = None
    for prediction in upcoming_games:
        context = prediction.availability_context
        if context is None:
            continue
        games_with_context += 1
        if context.coverage_status == "both":
            games_with_both_reports += 1
        elif context.coverage_status == "team_only":
            games_with_team_only += 1
        elif context.coverage_status == "opponent_only":
            games_with_opponent_only += 1
        team_has_unmatched_rows = context.team.unmatched_row_count > 0
        opponent_has_unmatched_rows = context.opponent.unmatched_row_count > 0
        if team_has_unmatched_rows or opponent_has_unmatched_rows:
            games_with_unmatched_rows += 1
        if team_has_unmatched_rows:
            team_sides_with_unmatched_rows += 1
        if opponent_has_unmatched_rows:
            opponent_sides_with_unmatched_rows += 1
        if context.team.any_out or context.opponent.any_out:
            games_with_any_out += 1
        if context.team.any_questionable or context.opponent.any_questionable:
            games_with_any_questionable += 1
        for side_context in (context.team, context.opponent):
            if side_context.latest_update_at is not None:
                parsed_update_at = _parse_shadow_update_at(
                    side_context.latest_update_at
                )
                if (
                    latest_report_update_at is None
                    or parsed_update_at > latest_report_update_at
                ):
                    latest_report_update_at = parsed_update_at
            if side_context.latest_minutes_before_tip is not None and (
                closest_report_minutes_before_tip is None
                or side_context.latest_minutes_before_tip
                < closest_report_minutes_before_tip
            ):
                closest_report_minutes_before_tip = (
                    side_context.latest_minutes_before_tip
                )
    return PredictionAvailabilitySummary(
        games_with_context=games_with_context,
        games_with_both_reports=games_with_both_reports,
        games_with_team_only=games_with_team_only,
        games_with_opponent_only=games_with_opponent_only,
        games_with_unmatched_rows=games_with_unmatched_rows,
        team_sides_with_unmatched_rows=team_sides_with_unmatched_rows,
        opponent_sides_with_unmatched_rows=opponent_sides_with_unmatched_rows,
        games_with_any_out=games_with_any_out,
        games_with_any_questionable=games_with_any_questionable,
        latest_report_update_at=(
            latest_report_update_at.isoformat()
            if latest_report_update_at is not None
            else None
        ),
        closest_report_minutes_before_tip=closest_report_minutes_before_tip,
    )


def _parse_shadow_update_at(value: str) -> datetime:
    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value


def _build_upcoming_game_predictions(
    *,
    upcoming_records,
    strategy_market: StrategyMarket,
    applied_policy: BetPolicy,
    raw_opportunities: list[_ScoredPredictionOpportunity],
    placed_bets: list[PlacedBet],
    deferred_recommendations: list[DeferredRecommendation],
    availability_shadows_by_game_side: dict[
        tuple[int, str], AvailabilityGameSideShadow
    ],
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
                    availability_context=_availability_context_for_matchup(
                        record=record,
                        team_name=placed_bet.team_name,
                        opponent_name=placed_bet.opponent_name,
                        preferred_side=placed_bet.side,
                        availability_shadows_by_game_side=availability_shadows_by_game_side,
                    ),
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
                    availability_context=_availability_context_for_matchup(
                        record=record,
                        team_name=candidate.team_name,
                        opponent_name=candidate.opponent_name,
                        preferred_side=candidate.side,
                        availability_shadows_by_game_side=availability_shadows_by_game_side,
                    ),
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
                    availability_context=_availability_context_for_matchup(
                        record=record,
                        team_name=str(
                            getattr(record, "home_team_name", "Unknown Team")
                        ),
                        opponent_name=str(
                            getattr(record, "away_team_name", "Unknown Opponent")
                        ),
                        preferred_side="home",
                        availability_shadows_by_game_side=availability_shadows_by_game_side,
                    ),
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
                availability_context=_availability_context_for_matchup(
                    record=record,
                    team_name=opportunity.team_name,
                    opponent_name=opportunity.opponent_name,
                    preferred_side=opportunity.side,
                    availability_shadows_by_game_side=availability_shadows_by_game_side,
                ),
            )
        )
    return predictions


def _build_live_board_game_predictions(
    *,
    board_records,
    strategy_market: StrategyMarket,
    applied_policy: BetPolicy,
    raw_opportunities: list[_ScoredPredictionOpportunity],
    placed_bets: list[PlacedBet],
    deferred_recommendations: list[DeferredRecommendation],
    current_time: datetime,
    availability_shadows_by_game_side: dict[
        tuple[int, str], AvailabilityGameSideShadow
    ],
) -> list[LiveBoardGame]:
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
    predictions: list[LiveBoardGame] = []
    for record in sorted(
        board_records,
        key=lambda record: (
            str(getattr(record, "commence_time", "")),
            getattr(record, "game_id", 0),
        ),
    ):
        game_status = _live_board_game_status(record, current_time)
        placed_bet = placed_by_game.get(record.game_id)
        if placed_bet is not None:
            predictions.append(
                LiveBoardGame(
                    game_id=placed_bet.game_id,
                    commence_time=placed_bet.commence_time,
                    home_team_name=str(
                        getattr(record, "home_team_name", placed_bet.team_name)
                    ),
                    away_team_name=str(
                        getattr(record, "away_team_name", placed_bet.opponent_name)
                    ),
                    game_status=game_status,
                    board_status="bet",
                    market=placed_bet.market,
                    team_name=placed_bet.team_name,
                    opponent_name=placed_bet.opponent_name,
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
                    note="qualified",
                    home_score=getattr(record, "home_score", None),
                    away_score=getattr(record, "away_score", None),
                    last_score_update=getattr(record, "last_score_update", None),
                    availability_context=_availability_context_for_matchup(
                        record=record,
                        team_name=placed_bet.team_name,
                        opponent_name=placed_bet.opponent_name,
                        preferred_side=placed_bet.side,
                        availability_shadows_by_game_side=availability_shadows_by_game_side,
                    ),
                )
            )
            continue
        deferred_recommendation = deferred_by_game.get(record.game_id)
        if deferred_recommendation is not None:
            candidate = deferred_recommendation.candidate
            board_status = "wait" if game_status == "upcoming" else "pass"
            reason_code = "timing_wait" if game_status == "upcoming" else "watch_only"
            note = (
                "watch_only"
                if game_status != "upcoming"
                else (
                    "close_probability="
                    f"{deferred_recommendation.favorable_close_probability:.3f}"
                )
            )
            predictions.append(
                LiveBoardGame(
                    game_id=candidate.game_id,
                    commence_time=candidate.commence_time,
                    home_team_name=str(
                        getattr(record, "home_team_name", candidate.team_name)
                    ),
                    away_team_name=str(
                        getattr(record, "away_team_name", candidate.opponent_name)
                    ),
                    game_status=game_status,
                    board_status=board_status,
                    market=candidate.market,
                    team_name=candidate.team_name,
                    opponent_name=candidate.opponent_name,
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
                    reason_code=reason_code,
                    note=note,
                    home_score=getattr(record, "home_score", None),
                    away_score=getattr(record, "away_score", None),
                    last_score_update=getattr(record, "last_score_update", None),
                    availability_context=_availability_context_for_matchup(
                        record=record,
                        team_name=candidate.team_name,
                        opponent_name=candidate.opponent_name,
                        preferred_side=candidate.side,
                        availability_shadows_by_game_side=availability_shadows_by_game_side,
                    ),
                )
            )
            continue
        opportunity = pass_by_game.get(record.game_id)
        if opportunity is None:
            predictions.append(
                LiveBoardGame(
                    game_id=record.game_id,
                    commence_time=_record_commence_time(record),
                    home_team_name=str(
                        getattr(record, "home_team_name", "Unknown Team")
                    ),
                    away_team_name=str(
                        getattr(record, "away_team_name", "Unknown Opponent")
                    ),
                    game_status=game_status,
                    board_status="pass",
                    reason_code="no_priced_market",
                    note="no_priced_market",
                    home_score=getattr(record, "home_score", None),
                    away_score=getattr(record, "away_score", None),
                    last_score_update=getattr(record, "last_score_update", None),
                    availability_context=_availability_context_for_matchup(
                        record=record,
                        team_name=str(
                            getattr(record, "home_team_name", "Unknown Team")
                        ),
                        opponent_name=str(
                            getattr(record, "away_team_name", "Unknown Opponent")
                        ),
                        preferred_side="home",
                        availability_shadows_by_game_side=availability_shadows_by_game_side,
                    ),
                )
            )
            continue
        reason_code = _opportunity_blocker_reason_code(
            opportunity=opportunity,
            policy=applied_policy,
        )
        predictions.append(
            LiveBoardGame(
                game_id=opportunity.game_id,
                commence_time=opportunity.commence_time,
                home_team_name=str(
                    getattr(record, "home_team_name", opportunity.team_name)
                ),
                away_team_name=str(
                    getattr(record, "away_team_name", opportunity.opponent_name)
                ),
                game_status=game_status,
                board_status="pass",
                market=opportunity.market,
                team_name=opportunity.team_name,
                opponent_name=opportunity.opponent_name,
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
                home_score=getattr(record, "home_score", None),
                away_score=getattr(record, "away_score", None),
                last_score_update=getattr(record, "last_score_update", None),
                availability_context=_availability_context_for_matchup(
                    record=record,
                    team_name=opportunity.team_name,
                    opponent_name=opportunity.opponent_name,
                    preferred_side=opportunity.side,
                    availability_shadows_by_game_side=availability_shadows_by_game_side,
                ),
            )
        )
    return predictions


def _availability_shadows_by_game_side(
    *,
    database_url: str | None,
    game_ids: set[int],
) -> dict[tuple[int, str], AvailabilityGameSideShadow]:
    if not game_ids:
        return {}
    try:
        return {
            (shadow.game_id, shadow.side): shadow
            for shadow in get_availability_game_side_shadows(database_url)
            if shadow.game_id in game_ids
        }
    except RuntimeError:
        return {}


def _availability_context_for_matchup(
    *,
    record: object,
    team_name: str,
    opponent_name: str,
    preferred_side: str | None,
    availability_shadows_by_game_side: dict[
        tuple[int, str], AvailabilityGameSideShadow
    ],
) -> AvailabilityGameContext | None:
    game_id = getattr(record, "game_id", None)
    if not isinstance(game_id, int):
        return None
    side = _matchup_side(
        record=record,
        team_name=team_name,
        opponent_name=opponent_name,
        preferred_side=preferred_side,
    )
    if side is None:
        return None
    team_shadow = availability_shadows_by_game_side.get((game_id, side))
    opponent_shadow = availability_shadows_by_game_side.get(
        (game_id, "away" if side == "home" else "home")
    )
    if team_shadow is None and opponent_shadow is None:
        return None
    coverage_status = (
        "both"
        if team_shadow is not None and opponent_shadow is not None
        else "team_only"
        if team_shadow is not None
        else "opponent_only"
    )
    return AvailabilityGameContext(
        coverage_status=coverage_status,
        team=_availability_side_context(team_shadow),
        opponent=_availability_side_context(opponent_shadow),
    )


def _availability_side_context(
    shadow: AvailabilityGameSideShadow | None,
) -> AvailabilitySideContext:
    if shadow is None:
        return AvailabilitySideContext()
    return AvailabilitySideContext(
        has_report=shadow.has_official_report,
        source_name=shadow.source_name,
        latest_update_at=shadow.latest_update_at,
        latest_minutes_before_tip=shadow.latest_minutes_before_tip,
        any_out=shadow.team_any_out,
        any_questionable=shadow.team_any_questionable,
        out_count=shadow.team_out_count,
        questionable_count=shadow.team_questionable_count,
        matched_row_count=shadow.matched_row_count,
        unmatched_row_count=shadow.unmatched_row_count,
    )


def _matchup_side(
    *,
    record: object,
    team_name: str,
    opponent_name: str,
    preferred_side: str | None,
) -> str | None:
    if preferred_side in {"home", "away"}:
        return preferred_side
    home_team_name = str(getattr(record, "home_team_name", ""))
    away_team_name = str(getattr(record, "away_team_name", ""))
    if team_name == home_team_name and opponent_name == away_team_name:
        return "home"
    if team_name == away_team_name and opponent_name == home_team_name:
        return "away"
    return None


def _record_commence_time(record: object) -> str:
    commence_time = getattr(record, "commence_time", None)
    if isinstance(commence_time, datetime):
        return commence_time.isoformat()
    if commence_time is None:
        return ""
    return str(commence_time)


def _record_is_upcoming(record: object, current_time: datetime) -> bool:
    commence_time = getattr(record, "commence_time", None)
    return isinstance(commence_time, datetime) and commence_time > current_time


def _live_board_game_status(record: object, current_time: datetime) -> str:
    if bool(getattr(record, "completed", False)):
        return "final"
    if _record_is_upcoming(record, current_time):
        return "upcoming"
    return "in_progress"


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
    if policy.min_median_expected_value is not None and (
        opportunity.median_expected_value is None
        or opportunity.median_expected_value < policy.min_median_expected_value
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
    if policy.min_median_expected_value is not None and (
        opportunity.median_expected_value is None
        or opportunity.median_expected_value < policy.min_median_expected_value
    ):
        observed = (
            "none"
            if opportunity.median_expected_value is None
            else f"{opportunity.median_expected_value:.3f}"
        )
        return (
            f"median_expected_value={observed}/{policy.min_median_expected_value:.3f}"
        )
    return blocker_reason_code


def _opportunity_non_edge_blocker_note(
    *,
    opportunity: _ScoredPredictionOpportunity,
    policy: BetPolicy,
) -> str | None:
    if opportunity.minimum_games_played < policy.min_games_played:
        return "games_played"
    if opportunity.market == "moneyline" and (
        opportunity.market_price < policy.min_moneyline_price
        or opportunity.market_price > policy.max_moneyline_price
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
