"""Feature engineering for betting-model training and inference."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from math import log

from cbb.ingest.utils import normalize_team_key
from cbb.modeling.artifacts import ModelMarket
from cbb.modeling.dataset import (
    GameOddsRecord,
    MarketSnapshotAggregate,
    OddsSnapshotRecord,
)
from cbb.modeling.ratings import (
    TeamSnapshot,
    TeamState,
    build_team_snapshot,
    prepare_team_state_for_game,
    update_team_states,
)
from cbb.team_home_locations import build_matchup_travel_context

COMMON_FEATURE_NAMES = (
    "home_side",
    "same_conference_game",
    "side_games_played",
    "opponent_games_played",
    "games_played_diff",
    "win_pct_diff",
    "average_margin_diff",
    "average_points_for_diff",
    "average_points_against_diff",
    "elo_diff",
    "carryover_elo_diff",
    "season_elo_shift_diff",
    "rest_days_diff",
    "min_season_games_played",
    "season_opener",
    "early_season",
    "total_points",
    "has_total_points",
    "total_open_points",
    "total_close_points",
    "total_points_move",
    "total_consensus_dispersion",
    "total_books",
)
BOOKMAKER_MONEYLINE_QUALITY_PRIOR_OBSERVATIONS = 20.0
BOOKMAKER_SPREAD_QUALITY_PRIOR_OBSERVATIONS = 60.0
BOOKMAKER_MONEYLINE_BASELINE_ERROR = 0.50
BOOKMAKER_SPREAD_BASELINE_ERROR = 8.0
BOOKMAKER_SPREAD_QUALITY_MIN_ERROR_MULTIPLIER = 0.85
BOOKMAKER_SPREAD_QUALITY_MAX_ERROR_MULTIPLIER = 1.15
MONEYLINE_FEATURE_NAMES = COMMON_FEATURE_NAMES + (
    "market_implied_probability",
    "market_implied_logit",
    "has_market_line",
    "h2h_consensus_implied_probability",
    "h2h_consensus_implied_logit",
    "h2h_open_implied_probability",
    "h2h_open_implied_logit",
    "h2h_consensus_move",
    "h2h_price_value_edge",
    "h2h_consensus_dispersion",
    "h2h_books",
    "h2h_weighted_implied_probability",
    "h2h_weighted_value_edge",
    "h2h_best_quote_value_edge",
    "h2h_best_quote_book_quality",
    "spread_line",
    "spread_abs_line",
    "spread_price_implied_probability",
    "spread_price_implied_logit",
    "has_spread_line",
    "spread_consensus_line",
    "spread_open_line",
    "spread_line_move",
    "spread_consensus_dispersion",
    "spread_price_value_edge",
    "spread_books",
    "spread_weighted_implied_probability",
    "spread_weighted_line",
    "spread_weighted_value_edge",
    "spread_weighted_line_value_edge",
    "spread_best_quote_value_edge",
    "spread_best_quote_line_edge",
    "spread_best_quote_book_quality",
)
SPREAD_FEATURE_NAMES = COMMON_FEATURE_NAMES + (
    "spread_line",
    "spread_abs_line",
    "market_implied_probability",
    "market_implied_logit",
    "has_market_line",
    "spread_consensus_line",
    "spread_open_line",
    "spread_line_move",
    "spread_consensus_dispersion",
    "spread_price_value_edge",
    "spread_books",
    "spread_weighted_implied_probability",
    "spread_weighted_line",
    "spread_weighted_value_edge",
    "spread_weighted_line_value_edge",
    "spread_best_quote_value_edge",
    "spread_best_quote_line_edge",
    "spread_best_quote_book_quality",
    "spread_total_interaction",
    "total_move_abs",
    "moneyline_implied_probability",
    "moneyline_implied_logit",
    "has_moneyline_line",
    "h2h_consensus_implied_probability",
    "h2h_consensus_implied_logit",
    "h2h_open_implied_probability",
    "h2h_open_implied_logit",
    "h2h_consensus_move",
    "h2h_price_value_edge",
    "h2h_consensus_dispersion",
    "h2h_books",
    "h2h_weighted_implied_probability",
    "h2h_weighted_value_edge",
    "h2h_best_quote_value_edge",
    "h2h_best_quote_book_quality",
)


@dataclass(frozen=True)
class ModelExample:
    """One side-based training or prediction example."""

    game_id: int
    season: int
    commence_time: str
    market: ModelMarket
    team_name: str
    opponent_name: str
    side: str
    features: dict[str, float]
    label: int | None
    settlement: str
    market_price: float | None
    market_implied_probability: float | None
    minimum_games_played: int
    line_value: float | None
    team_conference_key: str | None = None
    team_conference_name: str | None = None
    opponent_conference_key: str | None = None
    opponent_conference_name: str | None = None
    regression_target: float | None = None
    observation_time: str | None = None
    executable_quotes: tuple[ExecutableQuote, ...] = ()
    neutral_site: bool | None = None
    travel_distance_miles: float | None = None
    opponent_travel_distance_miles: float | None = None
    travel_distance_diff_miles: float | None = None
    timezone_crossings: int | None = None
    opponent_timezone_crossings: int | None = None
    timezone_crossings_diff: int | None = None


@dataclass(frozen=True)
class ExecutableQuote:
    """One currently executable side-specific bookmaker quote."""

    bookmaker_key: str
    market_price: float
    market_implied_probability: float | None
    line_value: float | None = None


@dataclass
class BookmakerMarketState:
    """One bookmaker's historical error profile for a market."""

    observations: int = 0
    total_error: float = 0.0


@dataclass(frozen=True)
class BookQuoteProfile:
    """Weighted current-quote summary for one market side."""

    weighted_probability: float | None = None
    best_probability: float | None = None
    best_quote_book_quality: float = 1.0
    weighted_line: float | None = None
    best_line: float | None = None


@dataclass
class PredictionFeatureContext:
    """Prepared rolling-state context reused across many prediction matchups."""

    team_states: dict[int, TeamState]
    bookmaker_states: dict[tuple[str, str], BookmakerMarketState]


def feature_names_for_market(market: ModelMarket) -> tuple[str, ...]:
    """Return the stable feature ordering for one market."""
    if market == "moneyline":
        return MONEYLINE_FEATURE_NAMES
    return SPREAD_FEATURE_NAMES


def build_training_examples(
    *,
    game_records: list[GameOddsRecord],
    market: ModelMarket,
    target_seasons: set[int],
) -> list[ModelExample]:
    """Build sequential training examples for one market."""
    team_states: dict[int, TeamState] = defaultdict(TeamState)
    bookmaker_states: dict[tuple[str, str], BookmakerMarketState] = defaultdict(
        BookmakerMarketState
    )
    examples: list[ModelExample] = []

    for record in game_records:
        home_state = team_states[record.home_team_id]
        away_state = team_states[record.away_team_id]
        prepare_team_state_for_game(state=home_state, season=record.season)
        prepare_team_state_for_game(state=away_state, season=record.season)
        home_snapshot = build_team_snapshot(home_state, record.commence_time)
        away_snapshot = build_team_snapshot(away_state, record.commence_time)

        if record.season in target_seasons:
            examples.extend(
                _build_examples_for_record(
                    record=record,
                    market=market,
                    home_snapshot=home_snapshot,
                    away_snapshot=away_snapshot,
                    bookmaker_states=bookmaker_states,
                )
            )

        if (
            record.completed
            and record.home_score is not None
            and record.away_score is not None
        ):
            update_team_states(
                home_state=home_state,
                away_state=away_state,
                home_score=record.home_score,
                away_score=record.away_score,
                commence_time=record.commence_time,
            )
            _update_bookmaker_market_states(
                bookmaker_states=bookmaker_states,
                record=record,
            )

    return examples


def build_prediction_examples(
    *,
    completed_records: list[GameOddsRecord],
    upcoming_records: list[GameOddsRecord],
    market: ModelMarket,
) -> list[ModelExample]:
    """Build current prediction examples for one market."""
    context = build_prediction_context(completed_records=completed_records)
    return build_prediction_examples_from_context(
        context=context,
        upcoming_records=upcoming_records,
        market=market,
    )


def build_prediction_context(
    *,
    completed_records: list[GameOddsRecord],
) -> PredictionFeatureContext:
    """Prepare reusable rolling-state context for prediction-only scoring."""
    team_states: dict[int, TeamState] = defaultdict(TeamState)
    bookmaker_states: dict[tuple[str, str], BookmakerMarketState] = defaultdict(
        BookmakerMarketState
    )

    for record in completed_records:
        home_state = team_states[record.home_team_id]
        away_state = team_states[record.away_team_id]
        prepare_team_state_for_game(state=home_state, season=record.season)
        prepare_team_state_for_game(state=away_state, season=record.season)
        if (
            record.completed
            and record.home_score is not None
            and record.away_score is not None
        ):
            update_team_states(
                home_state=home_state,
                away_state=away_state,
                home_score=record.home_score,
                away_score=record.away_score,
                commence_time=record.commence_time,
            )
            _update_bookmaker_market_states(
                bookmaker_states=bookmaker_states,
                record=record,
            )

    return PredictionFeatureContext(
        team_states=dict(team_states),
        bookmaker_states=dict(bookmaker_states),
    )


def build_prediction_examples_from_context(
    *,
    context: PredictionFeatureContext,
    upcoming_records: list[GameOddsRecord],
    market: ModelMarket,
) -> list[ModelExample]:
    """Build prediction examples from a precomputed rolling-state context."""
    examples: list[ModelExample] = []
    for record in upcoming_records:
        prepare_team_state_for_game(
            state=context.team_states.setdefault(record.home_team_id, TeamState()),
            season=record.season,
        )
        prepare_team_state_for_game(
            state=context.team_states.setdefault(record.away_team_id, TeamState()),
            season=record.season,
        )
        home_snapshot = build_team_snapshot(
            context.team_states[record.home_team_id], record.commence_time
        )
        away_snapshot = build_team_snapshot(
            context.team_states[record.away_team_id], record.commence_time
        )
        examples.extend(
            _build_examples_for_record(
                record=record,
                market=market,
                home_snapshot=home_snapshot,
                away_snapshot=away_snapshot,
                bookmaker_states=context.bookmaker_states,
            )
        )
    return examples


def feature_matrix(
    examples: list[ModelExample],
    feature_names: tuple[str, ...],
) -> list[list[float]]:
    """Convert examples into a matrix matching the artifact feature order."""
    return [
        [example.features[feature_name] for feature_name in feature_names]
        for example in examples
    ]


def labels_for_examples(examples: list[ModelExample]) -> list[int]:
    """Return non-null labels for examples used in training."""
    labels: list[int] = []
    for example in examples:
        if example.label is None:
            continue
        labels.append(example.label)
    return labels


def regression_targets_for_examples(examples: list[ModelExample]) -> list[float]:
    """Return non-null continuous targets for regression-style training."""
    targets: list[float] = []
    for example in examples:
        if example.regression_target is None:
            continue
        targets.append(example.regression_target)
    return targets


def training_examples_only(examples: list[ModelExample]) -> list[ModelExample]:
    """Filter examples down to trainable rows with non-null labels."""
    return [example for example in examples if example.label is not None]


def repriced_spread_example(
    *,
    example: ModelExample,
    line_value: float,
) -> ModelExample:
    """Return one spread example with line-dependent features updated."""
    if example.market != "spread":
        raise ValueError("repriced_spread_example only supports spread examples")
    updated_features = dict(example.features)
    total_close_points = updated_features.get(
        "total_close_points",
        updated_features.get("total_points", 0.0),
    )
    updated_features["spread_line"] = line_value
    updated_features["spread_abs_line"] = abs(line_value)
    updated_features["spread_total_interaction"] = line_value * (
        total_close_points / 100.0
    )
    return replace(
        example,
        features=updated_features,
        line_value=line_value,
    )


def _build_examples_for_record(
    *,
    record: GameOddsRecord,
    market: ModelMarket,
    home_snapshot: TeamSnapshot,
    away_snapshot: TeamSnapshot,
    bookmaker_states: dict[tuple[str, str], BookmakerMarketState],
) -> list[ModelExample]:
    same_conference_game = (
        record.home_conference_key is not None
        and record.home_conference_key == record.away_conference_key
    )
    home_team_key = record.home_team_key or normalize_team_key(record.home_team_name)
    away_team_key = record.away_team_key or normalize_team_key(record.away_team_name)
    home_travel_context, away_travel_context = build_matchup_travel_context(
        home_team_key=home_team_key,
        away_team_key=away_team_key,
        neutral_site=record.neutral_site,
        venue_city=record.venue_city,
        venue_state=record.venue_state,
        commence_time=record.commence_time,
    )
    home_features = _base_feature_map(
        home_side=True,
        same_conference_game=same_conference_game,
        side_snapshot=home_snapshot,
        opponent_snapshot=away_snapshot,
        total_points=record.total_points,
        total_open_points=(
            record.total_open.total_points if record.total_open is not None else None
        ),
        total_close_points=(
            record.total_close.total_points
            if record.total_close is not None
            else record.total_points
        ),
        total_consensus_dispersion=(
            record.total_close.total_points_range
            if record.total_close is not None
            else None
        ),
        total_books=_market_book_count(record.total_close),
    )
    away_features = _base_feature_map(
        home_side=False,
        same_conference_game=same_conference_game,
        side_snapshot=away_snapshot,
        opponent_snapshot=home_snapshot,
        total_points=record.total_points,
        total_open_points=(
            record.total_open.total_points if record.total_open is not None else None
        ),
        total_close_points=(
            record.total_close.total_points
            if record.total_close is not None
            else record.total_points
        ),
        total_consensus_dispersion=(
            record.total_close.total_points_range
            if record.total_close is not None
            else None
        ),
        total_books=_market_book_count(record.total_close),
    )
    minimum_games_played = min(home_snapshot.games_played, away_snapshot.games_played)
    home_moneyline_probability = normalized_implied_probability_from_prices(
        side_american_price=record.home_h2h_price,
        opponent_american_price=record.away_h2h_price,
    )
    away_moneyline_probability = normalized_implied_probability_from_prices(
        side_american_price=record.away_h2h_price,
        opponent_american_price=record.home_h2h_price,
    )
    home_spread_probability = normalized_implied_probability_from_prices(
        side_american_price=record.home_spread_price,
        opponent_american_price=record.away_spread_price,
    )
    away_spread_probability = normalized_implied_probability_from_prices(
        side_american_price=record.away_spread_price,
        opponent_american_price=record.home_spread_price,
    )
    home_h2h_consensus_probability = _market_side_probability(
        aggregate=record.h2h_close,
        home_side=True,
    )
    away_h2h_consensus_probability = _market_side_probability(
        aggregate=record.h2h_close,
        home_side=False,
    )
    home_h2h_open_probability = _market_side_probability(
        aggregate=record.h2h_open,
        home_side=True,
    )
    away_h2h_open_probability = _market_side_probability(
        aggregate=record.h2h_open,
        home_side=False,
    )
    home_h2h_consensus_dispersion = _market_side_probability_range(
        aggregate=record.h2h_close,
        home_side=True,
    )
    away_h2h_consensus_dispersion = _market_side_probability_range(
        aggregate=record.h2h_close,
        home_side=False,
    )
    home_h2h_books = _market_book_count(record.h2h_close)
    away_h2h_books = _market_book_count(record.h2h_close)
    home_spread_consensus_line = _market_side_point(
        aggregate=record.spread_close,
        home_side=True,
    )
    away_spread_consensus_line = _market_side_point(
        aggregate=record.spread_close,
        home_side=False,
    )
    home_spread_open_line = _market_side_point(
        aggregate=record.spread_open,
        home_side=True,
    )
    away_spread_open_line = _market_side_point(
        aggregate=record.spread_open,
        home_side=False,
    )
    home_spread_consensus_probability = _market_side_probability(
        aggregate=record.spread_close,
        home_side=True,
    )
    away_spread_consensus_probability = _market_side_probability(
        aggregate=record.spread_close,
        home_side=False,
    )
    home_spread_consensus_dispersion = _market_side_point_range(
        aggregate=record.spread_close,
        home_side=True,
    )
    away_spread_consensus_dispersion = _market_side_point_range(
        aggregate=record.spread_close,
        home_side=False,
    )
    home_spread_books = _market_book_count(record.spread_close)
    away_spread_books = _market_book_count(record.spread_close)
    home_moneyline_quotes = _side_executable_quotes(
        quotes=record.current_h2h_quotes,
        home_side=True,
        market="moneyline",
    )
    away_moneyline_quotes = _side_executable_quotes(
        quotes=record.current_h2h_quotes,
        home_side=False,
        market="moneyline",
    )
    home_spread_quotes = _side_executable_quotes(
        quotes=record.current_spread_quotes,
        home_side=True,
        market="spread",
    )
    away_spread_quotes = _side_executable_quotes(
        quotes=record.current_spread_quotes,
        home_side=False,
        market="spread",
    )
    home_h2h_quote_profile = _book_quote_profile(
        quotes=record.current_h2h_quotes,
        home_side=True,
        market="moneyline",
        bookmaker_states=bookmaker_states,
    )
    away_h2h_quote_profile = _book_quote_profile(
        quotes=record.current_h2h_quotes,
        home_side=False,
        market="moneyline",
        bookmaker_states=bookmaker_states,
    )
    home_spread_quote_profile = _book_quote_profile(
        quotes=record.current_spread_quotes,
        home_side=True,
        market="spread",
        bookmaker_states=bookmaker_states,
    )
    away_spread_quote_profile = _book_quote_profile(
        quotes=record.current_spread_quotes,
        home_side=False,
        market="spread",
        bookmaker_states=bookmaker_states,
    )

    if market == "moneyline":
        home_features.update(
            _moneyline_feature_map(
                market_implied_probability=home_moneyline_probability,
                h2h_consensus_implied_probability=home_h2h_consensus_probability,
                h2h_open_implied_probability=home_h2h_open_probability,
                h2h_consensus_dispersion=home_h2h_consensus_dispersion,
                h2h_books=home_h2h_books,
                h2h_weighted_implied_probability=(
                    home_h2h_quote_profile.weighted_probability
                ),
                h2h_best_quote_value_edge=_default_delta(
                    home_h2h_quote_profile.weighted_probability,
                    home_h2h_quote_profile.best_probability,
                ),
                h2h_best_quote_book_quality=(
                    home_h2h_quote_profile.best_quote_book_quality
                ),
                spread_line=record.home_spread_line,
                spread_price_implied_probability=home_spread_probability,
                spread_consensus_line=home_spread_consensus_line,
                spread_open_line=home_spread_open_line,
                spread_consensus_dispersion=home_spread_consensus_dispersion,
                spread_consensus_implied_probability=home_spread_consensus_probability,
                spread_books=home_spread_books,
                spread_weighted_implied_probability=(
                    home_spread_quote_profile.weighted_probability
                ),
                spread_weighted_line=home_spread_quote_profile.weighted_line,
                spread_best_quote_value_edge=_default_delta(
                    home_spread_quote_profile.weighted_probability,
                    home_spread_quote_profile.best_probability,
                ),
                spread_best_quote_line_edge=_default_delta(
                    home_spread_quote_profile.best_line,
                    record.home_spread_line,
                ),
                spread_best_quote_book_quality=(
                    home_spread_quote_profile.best_quote_book_quality
                ),
            )
        )
        away_features.update(
            _moneyline_feature_map(
                market_implied_probability=away_moneyline_probability,
                h2h_consensus_implied_probability=away_h2h_consensus_probability,
                h2h_open_implied_probability=away_h2h_open_probability,
                h2h_consensus_dispersion=away_h2h_consensus_dispersion,
                h2h_books=away_h2h_books,
                h2h_weighted_implied_probability=(
                    away_h2h_quote_profile.weighted_probability
                ),
                h2h_best_quote_value_edge=_default_delta(
                    away_h2h_quote_profile.weighted_probability,
                    away_h2h_quote_profile.best_probability,
                ),
                h2h_best_quote_book_quality=(
                    away_h2h_quote_profile.best_quote_book_quality
                ),
                spread_line=record.away_spread_line,
                spread_price_implied_probability=away_spread_probability,
                spread_consensus_line=away_spread_consensus_line,
                spread_open_line=away_spread_open_line,
                spread_consensus_dispersion=away_spread_consensus_dispersion,
                spread_consensus_implied_probability=away_spread_consensus_probability,
                spread_books=away_spread_books,
                spread_weighted_implied_probability=(
                    away_spread_quote_profile.weighted_probability
                ),
                spread_weighted_line=away_spread_quote_profile.weighted_line,
                spread_best_quote_value_edge=_default_delta(
                    away_spread_quote_profile.weighted_probability,
                    away_spread_quote_profile.best_probability,
                ),
                spread_best_quote_line_edge=_default_delta(
                    away_spread_quote_profile.best_line,
                    record.away_spread_line,
                ),
                spread_best_quote_book_quality=(
                    away_spread_quote_profile.best_quote_book_quality
                ),
            )
        )
        return [
            ModelExample(
                game_id=record.game_id,
                season=record.season,
                commence_time=record.commence_time.isoformat(),
                market=market,
                team_name=record.home_team_name,
                opponent_name=record.away_team_name,
                side="home",
                features=home_features,
                label=_moneyline_label(record.home_score, record.away_score),
                regression_target=None,
                settlement=_moneyline_settlement(record.home_score, record.away_score),
                market_price=record.home_h2h_price,
                market_implied_probability=home_moneyline_probability,
                minimum_games_played=minimum_games_played,
                line_value=record.home_h2h_price,
                team_conference_key=record.home_conference_key,
                team_conference_name=record.home_conference_name,
                opponent_conference_key=record.away_conference_key,
                opponent_conference_name=record.away_conference_name,
                observation_time=record.observation_time.isoformat()
                if record.observation_time is not None
                else None,
                executable_quotes=home_moneyline_quotes,
                neutral_site=record.neutral_site,
                travel_distance_miles=home_travel_context.distance_miles,
                opponent_travel_distance_miles=away_travel_context.distance_miles,
                travel_distance_diff_miles=_default_delta(
                    home_travel_context.distance_miles,
                    away_travel_context.distance_miles,
                ),
                timezone_crossings=home_travel_context.timezone_crossings,
                opponent_timezone_crossings=away_travel_context.timezone_crossings,
                timezone_crossings_diff=_optional_difference(
                    home_travel_context.timezone_crossings,
                    away_travel_context.timezone_crossings,
                ),
            ),
            ModelExample(
                game_id=record.game_id,
                season=record.season,
                commence_time=record.commence_time.isoformat(),
                market=market,
                team_name=record.away_team_name,
                opponent_name=record.home_team_name,
                side="away",
                features=away_features,
                label=_moneyline_label(record.away_score, record.home_score),
                regression_target=None,
                settlement=_moneyline_settlement(record.away_score, record.home_score),
                market_price=record.away_h2h_price,
                market_implied_probability=away_moneyline_probability,
                minimum_games_played=minimum_games_played,
                line_value=record.away_h2h_price,
                team_conference_key=record.away_conference_key,
                team_conference_name=record.away_conference_name,
                opponent_conference_key=record.home_conference_key,
                opponent_conference_name=record.home_conference_name,
                observation_time=record.observation_time.isoformat()
                if record.observation_time is not None
                else None,
                executable_quotes=away_moneyline_quotes,
                neutral_site=record.neutral_site,
                travel_distance_miles=away_travel_context.distance_miles,
                opponent_travel_distance_miles=home_travel_context.distance_miles,
                travel_distance_diff_miles=_default_delta(
                    away_travel_context.distance_miles,
                    home_travel_context.distance_miles,
                ),
                timezone_crossings=away_travel_context.timezone_crossings,
                opponent_timezone_crossings=home_travel_context.timezone_crossings,
                timezone_crossings_diff=_optional_difference(
                    away_travel_context.timezone_crossings,
                    home_travel_context.timezone_crossings,
                ),
            ),
        ]

    spread_examples: list[ModelExample] = []
    for example in [
        (
            "home",
            record.home_team_name,
            record.away_team_name,
            home_features,
            record.home_spread_line,
            record.home_spread_price,
            record.home_h2h_price,
            home_spread_probability,
            record.home_score,
            record.away_score,
        ),
        (
            "away",
            record.away_team_name,
            record.home_team_name,
            away_features,
            record.away_spread_line,
            record.away_spread_price,
            record.away_h2h_price,
            away_spread_probability,
            record.away_score,
            record.home_score,
        ),
    ]:
        (
            side,
            team_name,
            opponent_name,
            feature_map,
            spread_line,
            spread_price,
            moneyline_price,
            spread_implied_probability,
            side_score,
            opponent_score,
        ) = example
        if spread_line is None or spread_price is None:
            continue
        feature_map.update(
            _spread_feature_map(
                spread_line=spread_line,
                market_implied_probability=spread_implied_probability,
                spread_consensus_line=(
                    home_spread_consensus_line
                    if side == "home"
                    else away_spread_consensus_line
                ),
                spread_open_line=(
                    home_spread_open_line if side == "home" else away_spread_open_line
                ),
                spread_consensus_dispersion=(
                    home_spread_consensus_dispersion
                    if side == "home"
                    else away_spread_consensus_dispersion
                ),
                spread_consensus_implied_probability=(
                    home_spread_consensus_probability
                    if side == "home"
                    else away_spread_consensus_probability
                ),
                spread_books=(
                    home_spread_books if side == "home" else away_spread_books
                ),
                spread_weighted_implied_probability=(
                    home_spread_quote_profile.weighted_probability
                    if side == "home"
                    else away_spread_quote_profile.weighted_probability
                ),
                spread_weighted_line=(
                    home_spread_quote_profile.weighted_line
                    if side == "home"
                    else away_spread_quote_profile.weighted_line
                ),
                spread_best_quote_value_edge=_default_delta(
                    (
                        home_spread_quote_profile.weighted_probability
                        if side == "home"
                        else away_spread_quote_profile.weighted_probability
                    ),
                    (
                        home_spread_quote_profile.best_probability
                        if side == "home"
                        else away_spread_quote_profile.best_probability
                    ),
                ),
                spread_best_quote_line_edge=_default_delta(
                    (
                        home_spread_quote_profile.best_line
                        if side == "home"
                        else away_spread_quote_profile.best_line
                    ),
                    spread_line,
                ),
                spread_best_quote_book_quality=(
                    home_spread_quote_profile.best_quote_book_quality
                    if side == "home"
                    else away_spread_quote_profile.best_quote_book_quality
                ),
                moneyline_implied_probability=normalized_implied_probability_from_prices(
                    side_american_price=moneyline_price,
                    opponent_american_price=(
                        record.away_h2h_price
                        if side == "home"
                        else record.home_h2h_price
                    ),
                ),
                h2h_consensus_implied_probability=(
                    home_h2h_consensus_probability
                    if side == "home"
                    else away_h2h_consensus_probability
                ),
                h2h_open_implied_probability=(
                    home_h2h_open_probability
                    if side == "home"
                    else away_h2h_open_probability
                ),
                h2h_consensus_dispersion=(
                    home_h2h_consensus_dispersion
                    if side == "home"
                    else away_h2h_consensus_dispersion
                ),
                h2h_books=home_h2h_books if side == "home" else away_h2h_books,
                h2h_weighted_implied_probability=(
                    home_h2h_quote_profile.weighted_probability
                    if side == "home"
                    else away_h2h_quote_profile.weighted_probability
                ),
                h2h_best_quote_value_edge=_default_delta(
                    (
                        home_h2h_quote_profile.weighted_probability
                        if side == "home"
                        else away_h2h_quote_profile.weighted_probability
                    ),
                    (
                        home_h2h_quote_profile.best_probability
                        if side == "home"
                        else away_h2h_quote_profile.best_probability
                    ),
                ),
                h2h_best_quote_book_quality=(
                    home_h2h_quote_profile.best_quote_book_quality
                    if side == "home"
                    else away_h2h_quote_profile.best_quote_book_quality
                ),
                total_close_points=(
                    record.total_close.total_points
                    if record.total_close is not None
                    else record.total_points
                ),
                total_open_points=(
                    record.total_open.total_points
                    if record.total_open is not None
                    else None
                ),
                total_consensus_dispersion=(
                    record.total_close.total_points_range
                    if record.total_close is not None
                    else None
                ),
                total_books=_market_book_count(record.total_close),
            )
        )
        regression_target, label, settlement = _spread_target(
            side_score=side_score,
            opponent_score=opponent_score,
            spread_line=spread_line,
        )
        spread_examples.append(
            ModelExample(
                game_id=record.game_id,
                season=record.season,
                commence_time=record.commence_time.isoformat(),
                market=market,
                team_name=team_name,
                opponent_name=opponent_name,
                side=side,
                features=feature_map,
                label=label,
                regression_target=regression_target,
                settlement=settlement,
                market_price=spread_price,
                market_implied_probability=spread_implied_probability,
                minimum_games_played=minimum_games_played,
                line_value=spread_line,
                team_conference_key=(
                    record.home_conference_key
                    if side == "home"
                    else record.away_conference_key
                ),
                team_conference_name=(
                    record.home_conference_name
                    if side == "home"
                    else record.away_conference_name
                ),
                opponent_conference_key=(
                    record.away_conference_key
                    if side == "home"
                    else record.home_conference_key
                ),
                opponent_conference_name=(
                    record.away_conference_name
                    if side == "home"
                    else record.home_conference_name
                ),
                observation_time=record.observation_time.isoformat()
                if record.observation_time is not None
                else None,
                executable_quotes=(
                    home_spread_quotes if side == "home" else away_spread_quotes
                ),
                neutral_site=record.neutral_site,
                travel_distance_miles=(
                    home_travel_context.distance_miles
                    if side == "home"
                    else away_travel_context.distance_miles
                ),
                opponent_travel_distance_miles=(
                    away_travel_context.distance_miles
                    if side == "home"
                    else home_travel_context.distance_miles
                ),
                travel_distance_diff_miles=(
                    _default_delta(
                        home_travel_context.distance_miles,
                        away_travel_context.distance_miles,
                    )
                    if side == "home"
                    else _default_delta(
                        away_travel_context.distance_miles,
                        home_travel_context.distance_miles,
                    )
                ),
                timezone_crossings=(
                    home_travel_context.timezone_crossings
                    if side == "home"
                    else away_travel_context.timezone_crossings
                ),
                opponent_timezone_crossings=(
                    away_travel_context.timezone_crossings
                    if side == "home"
                    else home_travel_context.timezone_crossings
                ),
                timezone_crossings_diff=(
                    _optional_difference(
                        home_travel_context.timezone_crossings,
                        away_travel_context.timezone_crossings,
                    )
                    if side == "home"
                    else _optional_difference(
                        away_travel_context.timezone_crossings,
                        home_travel_context.timezone_crossings,
                    )
                ),
            )
        )
    return spread_examples


def _base_feature_map(
    *,
    home_side: bool,
    same_conference_game: bool,
    side_snapshot: TeamSnapshot,
    opponent_snapshot: TeamSnapshot,
    total_points: float | None,
    total_open_points: float | None,
    total_close_points: float | None,
    total_consensus_dispersion: float | None,
    total_books: float,
) -> dict[str, float]:
    effective_total_close_points = (
        total_close_points if total_close_points is not None else total_points
    )
    min_season_games_played = min(
        side_snapshot.games_played,
        opponent_snapshot.games_played,
    )
    side_elo_shift = side_snapshot.elo - side_snapshot.season_opening_elo
    opponent_elo_shift = opponent_snapshot.elo - opponent_snapshot.season_opening_elo
    return {
        "home_side": 1.0 if home_side else 0.0,
        "same_conference_game": 1.0 if same_conference_game else 0.0,
        "side_games_played": float(side_snapshot.games_played),
        "opponent_games_played": float(opponent_snapshot.games_played),
        "games_played_diff": float(
            side_snapshot.games_played - opponent_snapshot.games_played
        ),
        "win_pct_diff": side_snapshot.win_pct - opponent_snapshot.win_pct,
        "average_margin_diff": (
            side_snapshot.average_margin - opponent_snapshot.average_margin
        ),
        "average_points_for_diff": (
            side_snapshot.average_points_for - opponent_snapshot.average_points_for
        ),
        "average_points_against_diff": (
            side_snapshot.average_points_against
            - opponent_snapshot.average_points_against
        ),
        "elo_diff": side_snapshot.elo - opponent_snapshot.elo,
        "carryover_elo_diff": (
            side_snapshot.season_opening_elo - opponent_snapshot.season_opening_elo
        ),
        "season_elo_shift_diff": side_elo_shift - opponent_elo_shift,
        "rest_days_diff": side_snapshot.rest_days - opponent_snapshot.rest_days,
        "min_season_games_played": float(min_season_games_played),
        "season_opener": 1.0 if min_season_games_played == 0 else 0.0,
        "early_season": 1.0 if min_season_games_played < 6 else 0.0,
        "total_points": total_points or 0.0,
        "has_total_points": 1.0 if total_points is not None else 0.0,
        "total_open_points": total_open_points or 0.0,
        "total_close_points": effective_total_close_points or 0.0,
        "total_points_move": _default_delta(
            effective_total_close_points,
            total_open_points,
        ),
        "total_consensus_dispersion": total_consensus_dispersion or 0.0,
        "total_books": total_books,
    }


def _moneyline_feature_map(
    *,
    market_implied_probability: float | None,
    h2h_consensus_implied_probability: float | None,
    h2h_open_implied_probability: float | None,
    h2h_consensus_dispersion: float | None,
    h2h_books: float,
    h2h_weighted_implied_probability: float | None,
    h2h_best_quote_value_edge: float,
    h2h_best_quote_book_quality: float,
    spread_line: float | None,
    spread_price_implied_probability: float | None,
    spread_consensus_line: float | None,
    spread_open_line: float | None,
    spread_consensus_dispersion: float | None,
    spread_consensus_implied_probability: float | None,
    spread_books: float,
    spread_weighted_implied_probability: float | None,
    spread_weighted_line: float | None,
    spread_best_quote_value_edge: float,
    spread_best_quote_line_edge: float,
    spread_best_quote_book_quality: float,
) -> dict[str, float]:
    return {
        "market_implied_probability": _default_probability(market_implied_probability),
        "market_implied_logit": _default_probability_logit(market_implied_probability),
        "has_market_line": 1.0 if market_implied_probability is not None else 0.0,
        "h2h_consensus_implied_probability": _default_probability(
            h2h_consensus_implied_probability
        ),
        "h2h_consensus_implied_logit": _default_probability_logit(
            h2h_consensus_implied_probability
        ),
        "h2h_open_implied_probability": _default_probability(
            h2h_open_implied_probability
        ),
        "h2h_open_implied_logit": _default_probability_logit(
            h2h_open_implied_probability
        ),
        "h2h_consensus_move": _default_delta(
            h2h_consensus_implied_probability,
            h2h_open_implied_probability,
        ),
        "h2h_price_value_edge": _default_delta(
            h2h_consensus_implied_probability,
            market_implied_probability,
        ),
        "h2h_consensus_dispersion": h2h_consensus_dispersion or 0.0,
        "h2h_books": h2h_books,
        "h2h_weighted_implied_probability": _default_probability(
            h2h_weighted_implied_probability
        ),
        "h2h_weighted_value_edge": _default_delta(
            h2h_weighted_implied_probability,
            market_implied_probability,
        ),
        "h2h_best_quote_value_edge": h2h_best_quote_value_edge,
        "h2h_best_quote_book_quality": h2h_best_quote_book_quality,
        "spread_line": spread_line or 0.0,
        "spread_abs_line": abs(spread_line or 0.0),
        "spread_price_implied_probability": _default_probability(
            spread_price_implied_probability
        ),
        "spread_price_implied_logit": _default_probability_logit(
            spread_price_implied_probability
        ),
        "has_spread_line": 1.0 if spread_line is not None else 0.0,
        "spread_consensus_line": spread_consensus_line or 0.0,
        "spread_open_line": spread_open_line or 0.0,
        "spread_line_move": _default_delta(
            spread_consensus_line,
            spread_open_line,
        ),
        "spread_consensus_dispersion": spread_consensus_dispersion or 0.0,
        "spread_price_value_edge": _default_delta(
            spread_consensus_implied_probability,
            spread_price_implied_probability,
        ),
        "spread_books": spread_books,
        "spread_weighted_implied_probability": _default_probability(
            spread_weighted_implied_probability
        ),
        "spread_weighted_line": spread_weighted_line or 0.0,
        "spread_weighted_value_edge": _default_delta(
            spread_weighted_implied_probability,
            spread_price_implied_probability,
        ),
        "spread_weighted_line_value_edge": _default_delta(
            spread_line,
            spread_weighted_line,
        ),
        "spread_best_quote_value_edge": spread_best_quote_value_edge,
        "spread_best_quote_line_edge": spread_best_quote_line_edge,
        "spread_best_quote_book_quality": spread_best_quote_book_quality,
    }


def _spread_feature_map(
    *,
    spread_line: float,
    market_implied_probability: float | None,
    spread_consensus_line: float | None,
    spread_open_line: float | None,
    spread_consensus_dispersion: float | None,
    spread_consensus_implied_probability: float | None,
    spread_books: float,
    spread_weighted_implied_probability: float | None,
    spread_weighted_line: float | None,
    spread_best_quote_value_edge: float,
    spread_best_quote_line_edge: float,
    spread_best_quote_book_quality: float,
    moneyline_implied_probability: float | None,
    h2h_consensus_implied_probability: float | None,
    h2h_open_implied_probability: float | None,
    h2h_consensus_dispersion: float | None,
    h2h_books: float,
    h2h_weighted_implied_probability: float | None,
    h2h_best_quote_value_edge: float,
    h2h_best_quote_book_quality: float,
    total_close_points: float | None,
    total_open_points: float | None,
    total_consensus_dispersion: float | None,
    total_books: float,
) -> dict[str, float]:
    total_points_move = _default_delta(total_close_points, total_open_points)
    return {
        "spread_line": spread_line,
        "spread_abs_line": abs(spread_line),
        "market_implied_probability": _default_probability(market_implied_probability),
        "market_implied_logit": _default_probability_logit(market_implied_probability),
        "has_market_line": 1.0 if market_implied_probability is not None else 0.0,
        "spread_consensus_line": spread_consensus_line or 0.0,
        "spread_open_line": spread_open_line or 0.0,
        "spread_line_move": _default_delta(
            spread_consensus_line,
            spread_open_line,
        ),
        "spread_consensus_dispersion": spread_consensus_dispersion or 0.0,
        "spread_price_value_edge": _default_delta(
            spread_consensus_implied_probability,
            market_implied_probability,
        ),
        "spread_books": spread_books,
        "spread_weighted_implied_probability": _default_probability(
            spread_weighted_implied_probability
        ),
        "spread_weighted_line": spread_weighted_line or 0.0,
        "spread_weighted_value_edge": _default_delta(
            spread_weighted_implied_probability,
            market_implied_probability,
        ),
        "spread_weighted_line_value_edge": _default_delta(
            spread_line,
            spread_weighted_line,
        ),
        "spread_best_quote_value_edge": spread_best_quote_value_edge,
        "spread_best_quote_line_edge": spread_best_quote_line_edge,
        "spread_best_quote_book_quality": spread_best_quote_book_quality,
        "moneyline_implied_probability": _default_probability(
            moneyline_implied_probability
        ),
        "moneyline_implied_logit": _default_probability_logit(
            moneyline_implied_probability
        ),
        "has_moneyline_line": 1.0 if moneyline_implied_probability is not None else 0.0,
        "h2h_consensus_implied_probability": _default_probability(
            h2h_consensus_implied_probability
        ),
        "h2h_consensus_implied_logit": _default_probability_logit(
            h2h_consensus_implied_probability
        ),
        "h2h_open_implied_probability": _default_probability(
            h2h_open_implied_probability
        ),
        "h2h_open_implied_logit": _default_probability_logit(
            h2h_open_implied_probability
        ),
        "h2h_consensus_move": _default_delta(
            h2h_consensus_implied_probability,
            h2h_open_implied_probability,
        ),
        "h2h_price_value_edge": _default_delta(
            h2h_consensus_implied_probability,
            moneyline_implied_probability,
        ),
        "h2h_consensus_dispersion": h2h_consensus_dispersion or 0.0,
        "h2h_books": h2h_books,
        "h2h_weighted_implied_probability": _default_probability(
            h2h_weighted_implied_probability
        ),
        "h2h_weighted_value_edge": _default_delta(
            h2h_weighted_implied_probability,
            moneyline_implied_probability,
        ),
        "h2h_best_quote_value_edge": h2h_best_quote_value_edge,
        "h2h_best_quote_book_quality": h2h_best_quote_book_quality,
        "spread_total_interaction": spread_line * ((total_close_points or 0.0) / 100.0),
        "total_move_abs": abs(total_points_move),
    }


def _moneyline_label(side_score: int | None, opponent_score: int | None) -> int | None:
    if side_score is None or opponent_score is None:
        return None
    return 1 if side_score > opponent_score else 0


def _moneyline_settlement(
    side_score: int | None,
    opponent_score: int | None,
) -> str:
    label = _moneyline_label(side_score, opponent_score)
    if label is None:
        return "pending"
    return "win" if label == 1 else "loss"


def _spread_target(
    *,
    side_score: int | None,
    opponent_score: int | None,
    spread_line: float,
) -> tuple[float | None, int | None, str]:
    if side_score is None or opponent_score is None:
        return None, None, "pending"
    margin_with_line = float(side_score - opponent_score) + spread_line
    if margin_with_line > 0:
        return margin_with_line, 1, "win"
    if margin_with_line < 0:
        return margin_with_line, 0, "loss"
    return None, None, "push"


def _default_probability(probability: float | None) -> float:
    if probability is None:
        return 0.5
    return probability


def _default_probability_logit(probability: float | None) -> float:
    if probability is None:
        return 0.0
    clipped_probability = min(max(probability, 1e-6), 1.0 - 1e-6)
    return log(clipped_probability / (1.0 - clipped_probability))


def _default_delta(current: float | None, previous: float | None) -> float:
    if current is None or previous is None:
        return 0.0
    return current - previous


def _optional_difference(current: int | None, previous: int | None) -> int | None:
    if current is None or previous is None:
        return None
    return current - previous


def _market_side_probability(
    *,
    aggregate: MarketSnapshotAggregate | None,
    home_side: bool,
) -> float | None:
    if aggregate is None:
        return None
    if home_side:
        return aggregate.team1_implied_probability
    return aggregate.team2_implied_probability


def _market_side_probability_range(
    *,
    aggregate: MarketSnapshotAggregate | None,
    home_side: bool,
) -> float | None:
    if aggregate is None:
        return None
    if home_side:
        return aggregate.team1_probability_range
    return aggregate.team2_probability_range


def _market_side_point(
    *,
    aggregate: MarketSnapshotAggregate | None,
    home_side: bool,
) -> float | None:
    if aggregate is None:
        return None
    if home_side:
        return aggregate.team1_point
    return aggregate.team2_point


def _market_side_point_range(
    *,
    aggregate: MarketSnapshotAggregate | None,
    home_side: bool,
) -> float | None:
    if aggregate is None:
        return None
    if home_side:
        return aggregate.team1_point_range
    return aggregate.team2_point_range


def _market_book_count(aggregate: MarketSnapshotAggregate | None) -> float:
    if aggregate is None:
        return 0.0
    return float(aggregate.bookmaker_count)


def _side_executable_quotes(
    *,
    quotes: tuple[OddsSnapshotRecord, ...],
    home_side: bool,
    market: ModelMarket,
) -> tuple[ExecutableQuote, ...]:
    executable_quotes: list[ExecutableQuote] = []
    for quote in quotes:
        market_price = quote.team1_price if home_side else quote.team2_price
        opponent_price = quote.team2_price if home_side else quote.team1_price
        if market_price is None:
            continue
        line_value: float | None
        if market == "spread":
            line_value = quote.team1_point if home_side else quote.team2_point
            if line_value is None:
                continue
        else:
            line_value = market_price
        executable_quotes.append(
            ExecutableQuote(
                bookmaker_key=quote.bookmaker_key,
                market_price=market_price,
                market_implied_probability=normalized_implied_probability_from_prices(
                    side_american_price=market_price,
                    opponent_american_price=opponent_price,
                ),
                line_value=line_value,
            )
        )
    return tuple(executable_quotes)


def _update_bookmaker_market_states(
    *,
    bookmaker_states: dict[tuple[str, str], BookmakerMarketState],
    record: GameOddsRecord,
) -> None:
    if not record.completed or record.home_score is None or record.away_score is None:
        return

    home_result = 1.0 if record.home_score > record.away_score else 0.0
    for quote in record.current_h2h_quotes:
        home_probability = normalized_implied_probability_from_prices(
            side_american_price=quote.team1_price,
            opponent_american_price=quote.team2_price,
        )
        if home_probability is None:
            continue
        state = bookmaker_states[("moneyline", quote.bookmaker_key)]
        state.observations += 1
        state.total_error += abs(home_probability - home_result)

    home_margin = float(record.home_score - record.away_score)
    for quote in record.current_spread_quotes:
        if quote.team1_point is None:
            continue
        state = bookmaker_states[("spread", quote.bookmaker_key)]
        state.observations += 1
        state.total_error += abs(home_margin + quote.team1_point)


def _book_quote_profile(
    *,
    quotes: tuple[OddsSnapshotRecord, ...],
    home_side: bool,
    market: ModelMarket,
    bookmaker_states: dict[tuple[str, str], BookmakerMarketState],
) -> BookQuoteProfile:
    probability_components: list[tuple[float, float]] = []
    line_components: list[tuple[float, float]] = []
    best_probability: float | None = None
    best_line: float | None = None
    best_quote_quality = 1.0

    for quote in quotes:
        side_price = quote.team1_price if home_side else quote.team2_price
        opponent_price = quote.team2_price if home_side else quote.team1_price
        side_probability = normalized_implied_probability_from_prices(
            side_american_price=side_price,
            opponent_american_price=opponent_price,
        )
        if side_probability is None:
            continue
        weight = _bookmaker_quality_weight(
            state=bookmaker_states.get((market, quote.bookmaker_key)),
            market=market,
        )
        probability_components.append((weight, side_probability))
        if market == "moneyline":
            if best_probability is None or side_probability < best_probability:
                best_probability = side_probability
                best_quote_quality = weight
            continue

        line_value = quote.team1_point if home_side else quote.team2_point
        if line_value is None:
            continue
        line_components.append((weight, line_value))
        if (
            best_line is None
            or line_value > best_line
            or (
                line_value == best_line
                and best_probability is not None
                and side_probability < best_probability
            )
        ):
            best_line = line_value
            best_probability = side_probability
            best_quote_quality = weight

    return BookQuoteProfile(
        weighted_probability=_weighted_average(probability_components),
        best_probability=best_probability,
        best_quote_book_quality=best_quote_quality,
        weighted_line=_weighted_average(line_components),
        best_line=best_line,
    )


def _bookmaker_quality_weight(
    *,
    state: BookmakerMarketState | None,
    market: ModelMarket,
) -> float:
    prior_observations = (
        BOOKMAKER_MONEYLINE_QUALITY_PRIOR_OBSERVATIONS
        if market == "moneyline"
        else BOOKMAKER_SPREAD_QUALITY_PRIOR_OBSERVATIONS
    )
    baseline_error = (
        BOOKMAKER_MONEYLINE_BASELINE_ERROR
        if market == "moneyline"
        else BOOKMAKER_SPREAD_BASELINE_ERROR
    )
    observations = 0 if state is None else state.observations
    total_error = 0.0 if state is None else state.total_error
    average_error = (
        total_error + prior_observations * baseline_error
    ) / (float(observations) + prior_observations)
    if market == "spread":
        # Repaired spread history can move sparse book states sharply, so keep
        # quote quality near the market baseline unless the evidence is broad.
        minimum_error = (
            baseline_error * BOOKMAKER_SPREAD_QUALITY_MIN_ERROR_MULTIPLIER
        )
        maximum_error = (
            baseline_error * BOOKMAKER_SPREAD_QUALITY_MAX_ERROR_MULTIPLIER
        )
        average_error = min(max(average_error, minimum_error), maximum_error)
    if average_error <= 0:
        return 1.0
    return 1.0 / average_error


def _weighted_average(components: list[tuple[float, float]]) -> float | None:
    if not components:
        return None
    total_weight = sum(weight for weight, _ in components)
    if total_weight <= 0:
        return None
    return sum(weight * value for weight, value in components) / total_weight


def implied_probability_from_american(american_price: float | None) -> float | None:
    """Convert American odds into implied win probability."""
    if american_price is None:
        return None
    if american_price > 0:
        return 100.0 / (american_price + 100.0)
    if american_price < 0:
        return -american_price / (-american_price + 100.0)
    return None


def normalized_implied_probability_from_prices(
    *,
    side_american_price: float | None,
    opponent_american_price: float | None,
) -> float | None:
    """Convert a two-sided market into a no-vig side probability when possible."""
    side_probability = implied_probability_from_american(side_american_price)
    opponent_probability = implied_probability_from_american(opponent_american_price)
    if side_probability is None:
        return None
    if opponent_probability is None:
        return side_probability

    total_probability = side_probability + opponent_probability
    if total_probability <= 0:
        return None
    return side_probability / total_probability
