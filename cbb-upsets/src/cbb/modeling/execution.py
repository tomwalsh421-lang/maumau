"""Executable quote selection for model-scored betting candidates."""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import median

from cbb.modeling.artifacts import ModelArtifact
from cbb.modeling.features import ExecutableQuote, ModelExample
from cbb.modeling.policy import (
    BetPolicy,
    CandidateBet,
    SupportingQuote,
    build_candidate_bet,
    candidate_matches_non_edge_policy,
    candidate_matches_policy,
    score_candidate_bet_for_quote,
)
from cbb.modeling.train import score_spread_probability_at_line


@dataclass(frozen=True)
class ExecutableCandidateDiagnostics:
    """Cross-book survivability measurements for one side."""

    eligible_books: int
    positive_ev_books: int
    coverage_rate: float
    median_expected_value: float | None


@dataclass(frozen=True)
class ExecutableCandidateEvaluation:
    """Quote-level candidate evaluation and side-level survivability context."""

    scored_candidates: list[CandidateBet]
    eligible_candidates: list[CandidateBet]
    diagnostics: ExecutableCandidateDiagnostics


def build_executable_candidate_bets(
    *,
    artifact: ModelArtifact,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
) -> list[CandidateBet]:
    """Build one candidate per currently executable quote for an example."""
    evaluation = evaluate_executable_quote_candidates(
        artifact=artifact,
        example=example,
        probability=probability,
        policy=policy,
    )
    if evaluation.diagnostics.positive_ev_books < policy.min_positive_ev_books:
        return []
    if policy.min_median_expected_value is not None and (
        evaluation.diagnostics.median_expected_value is None
        or (
            evaluation.diagnostics.median_expected_value
            < policy.min_median_expected_value
        )
    ):
        return []
    return [
        candidate
        for candidate in evaluation.eligible_candidates
        if candidate.stake_fraction > 0.0
    ]


def evaluate_executable_quote_candidates(
    *,
    artifact: ModelArtifact,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
) -> ExecutableCandidateEvaluation:
    """Score executable quotes and attach shared side-level survivability data."""
    scored_candidates = score_executable_quote_candidates(
        artifact=artifact,
        example=example,
        probability=probability,
        policy=policy,
    )
    eligible_candidates = [
        candidate
        for candidate in scored_candidates
        if candidate_matches_non_edge_policy(candidate=candidate, policy=policy)
    ]
    diagnostics = summarize_executable_candidates(eligible_candidates)
    qualifying_candidates = [
        candidate
        for candidate in eligible_candidates
        if candidate_matches_policy(candidate=candidate, policy=policy)
    ]
    annotated_candidates = _annotate_candidate_group(
        candidates=scored_candidates,
        diagnostics=diagnostics,
        qualifying_candidates=qualifying_candidates,
    )
    return ExecutableCandidateEvaluation(
        scored_candidates=annotated_candidates,
        eligible_candidates=[
            candidate
            for candidate in annotated_candidates
            if candidate_matches_non_edge_policy(candidate=candidate, policy=policy)
        ],
        diagnostics=diagnostics,
    )


def score_executable_quote_candidates(
    *,
    artifact: ModelArtifact,
    example: ModelExample,
    probability: float,
    policy: BetPolicy,
) -> list[CandidateBet]:
    """Score every current quote for one side before survivability filtering."""
    executable_quotes = example.executable_quotes or _fallback_quote_candidates(example)
    candidates: list[CandidateBet] = []
    if executable_quotes:
        for executable_quote in executable_quotes:
            quote_probability = probability
            if example.market == "spread":
                if executable_quote.line_value is None:
                    continue
                quote_probability = score_spread_probability_at_line(
                    artifact=artifact,
                    example=example,
                    line_value=executable_quote.line_value,
                )
            candidate = score_candidate_bet_for_quote(
                example=example,
                probability=quote_probability,
                policy=policy,
                sportsbook=executable_quote.bookmaker_key,
                market_price=executable_quote.market_price,
                implied_probability=executable_quote.market_implied_probability,
                line_value=executable_quote.line_value,
            )
            if candidate is not None:
                candidates.append(candidate)
    else:
        fallback_candidate = build_candidate_bet(
            example=example,
            probability=probability,
            policy=policy,
        )
        if fallback_candidate is not None:
            candidates.append(fallback_candidate)
    return candidates


def summarize_executable_candidates(
    candidates: list[CandidateBet],
) -> ExecutableCandidateDiagnostics:
    """Return cross-book robustness measurements for eligible quotes."""
    if not candidates:
        return ExecutableCandidateDiagnostics(
            eligible_books=0,
            positive_ev_books=0,
            coverage_rate=0.0,
            median_expected_value=None,
        )
    eligible_books = len(candidates)
    positive_ev_books = sum(
        1 for candidate in candidates if candidate.stake_fraction > 0.0
    )
    return ExecutableCandidateDiagnostics(
        eligible_books=eligible_books,
        positive_ev_books=positive_ev_books,
        coverage_rate=positive_ev_books / float(eligible_books),
        median_expected_value=median(
            candidate.expected_value for candidate in candidates
        ),
    )


def _annotate_candidate_group(
    *,
    candidates: list[CandidateBet],
    diagnostics: ExecutableCandidateDiagnostics,
    qualifying_candidates: list[CandidateBet],
) -> list[CandidateBet]:
    min_acceptable_line = _worst_acceptable_line(qualifying_candidates)
    min_acceptable_price = _worst_acceptable_price(qualifying_candidates)
    return [
        replace(
            candidate,
            eligible_books=diagnostics.eligible_books,
            positive_ev_books=diagnostics.positive_ev_books,
            coverage_rate=diagnostics.coverage_rate,
            median_expected_value=diagnostics.median_expected_value,
            supporting_quotes=_supporting_quotes_for_candidate(
                candidate=candidate,
                qualifying_candidates=qualifying_candidates,
            ),
            min_acceptable_line=min_acceptable_line,
            min_acceptable_price=min_acceptable_price,
        )
        for candidate in candidates
    ]


def _supporting_quotes_for_candidate(
    *,
    candidate: CandidateBet,
    qualifying_candidates: list[CandidateBet],
) -> tuple[SupportingQuote, ...]:
    other_candidates = [
        quote_candidate
        for quote_candidate in qualifying_candidates
        if quote_candidate.sportsbook != candidate.sportsbook
    ]
    return tuple(
        SupportingQuote(
            sportsbook=quote_candidate.sportsbook,
            line_value=quote_candidate.line_value,
            market_price=quote_candidate.market_price,
            expected_value=quote_candidate.expected_value,
        )
        for quote_candidate in sorted(
            other_candidates,
            key=lambda item: (
                -item.expected_value,
                -item.probability_edge,
                -item.model_probability,
                item.sportsbook,
            ),
        )
    )


def _worst_acceptable_line(
    qualifying_candidates: list[CandidateBet],
) -> float | None:
    line_values = [
        candidate.line_value
        for candidate in qualifying_candidates
        if candidate.line_value is not None
    ]
    if not line_values:
        return None
    return min(line_values)


def _worst_acceptable_price(
    qualifying_candidates: list[CandidateBet],
) -> float | None:
    if not qualifying_candidates:
        return None
    return min(candidate.market_price for candidate in qualifying_candidates)


def _fallback_quote_candidates(
    example: ModelExample,
) -> tuple[ExecutableQuote, ...]:
    if example.market_price is None:
        return ()
    return (
        ExecutableQuote(
            bookmaker_key="",
            market_price=example.market_price,
            market_implied_probability=example.market_implied_probability,
            line_value=example.line_value,
        ),
    )
