"""Training workflow for betting models."""

from __future__ import annotations

import base64
import pickle
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from math import exp, log, pi, sqrt
from pathlib import Path
from typing import cast

from sklearn.ensemble import HistGradientBoostingClassifier

from cbb.modeling.artifacts import (
    DEFAULT_ARTIFACT_NAME,
    ModelArtifact,
    ModelFamily,
    ModelMarket,
    MoneylineBandModel,
    MoneylineSegmentCalibration,
    SpreadBookDepthResidualScale,
    SpreadConferenceCalibration,
    SpreadLineCalibration,
    SpreadLineResidualScale,
    SpreadModelingMode,
    SpreadSeasonPhaseCalibration,
    SpreadSeasonPhaseResidualScale,
    SpreadTimingModel,
    TrainingMetrics,
    current_timestamp,
    save_artifact,
)
from cbb.modeling.dataset import (
    GameOddsRecord,
    derive_game_record_at_observation_time,
    get_available_seasons,
    load_completed_game_records,
)
from cbb.modeling.features import (
    ModelExample,
    build_training_examples,
    feature_matrix,
    feature_names_for_market,
    labels_for_examples,
    regression_targets_for_examples,
    repriced_spread_example,
    training_examples_only,
)
from cbb.modeling.policy import BetPolicy

DEFAULT_MODEL_SEASONS_BACK = 5
DEFAULT_LEARNING_RATE = 0.05
DEFAULT_EPOCHS = 100
DEFAULT_L2_PENALTY = 0.001
DEFAULT_MIN_EXAMPLES = 50
DEFAULT_PLATT_SCALE = 1.0
DEFAULT_PLATT_BIAS = 0.0
DEFAULT_MARKET_BLEND_WEIGHT = 0.25
DEFAULT_MAX_MARKET_PROBABILITY_DELTA = 0.05
DEFAULT_MODEL_FAMILY: ModelFamily = "logistic"
DEFAULT_SPREAD_MODEL_FAMILY: ModelFamily = "logistic"
DEFAULT_SPREAD_MODELING_MODE: SpreadModelingMode = "margin_regression"
CALIBRATION_HOLDOUT_FRACTION = 0.20
MIN_CALIBRATION_GAMES = 25
PLATT_LEARNING_RATE = 0.05
PLATT_EPOCHS = 250
PLATT_L2_PENALTY = 0.01
MARKET_CALIBRATION_VALIDATION_FRACTION = 0.50
SPECIALIZED_SPREAD_CALIBRATION_VALIDATION_FRACTION = 0.50
MIN_MARKET_CALIBRATION_GAMES = 10
MIN_SPREAD_BUCKET_CALIBRATION_GAMES = 75
MIN_SPREAD_CONFERENCE_CALIBRATION_GAMES = 75
MIN_SPREAD_SEASON_PHASE_CALIBRATION_GAMES = 75
MIN_SPREAD_RESIDUAL_SCALE_BUCKET_GAMES = 75
MIN_SPREAD_TIMING_EXAMPLES = 50
MONEYLINE_CORE_PRICE_MIN = BetPolicy().min_moneyline_price
MONEYLINE_HEAVY_FAVORITE_PRICE_MAX = -200.0
MONEYLINE_FAVORITE_PRICE_MIN = -199.0
MONEYLINE_FAVORITE_PRICE_MAX = -125.0
MONEYLINE_BALANCED_PRICE_MIN = -124.0
MONEYLINE_BALANCED_PRICE_MAX = BetPolicy().max_moneyline_price
MONEYLINE_SHORT_DOG_PRICE_MIN = 126.0
MONEYLINE_SHORT_DOG_PRICE_MAX = 175.0
DEFAULT_MONEYLINE_TRAIN_MIN_PRICE = MONEYLINE_CORE_PRICE_MIN
DEFAULT_MONEYLINE_TRAIN_MAX_PRICE = MONEYLINE_SHORT_DOG_PRICE_MAX
MONEYLINE_DISPATCH_BANDS = (
    (
        "heavy_favorite",
        MONEYLINE_CORE_PRICE_MIN,
        MONEYLINE_HEAVY_FAVORITE_PRICE_MAX,
    ),
    (
        "favorite",
        MONEYLINE_FAVORITE_PRICE_MIN,
        MONEYLINE_FAVORITE_PRICE_MAX,
    ),
    (
        "balanced",
        MONEYLINE_BALANCED_PRICE_MIN,
        MONEYLINE_BALANCED_PRICE_MAX,
    ),
    ("short_dog", MONEYLINE_SHORT_DOG_PRICE_MIN, MONEYLINE_SHORT_DOG_PRICE_MAX),
)
MONEYLINE_SEGMENT_MIN_GAMES = 50
MONEYLINE_SEGMENT_KEYS = (
    "heavy_favorite",
    "favorite",
    "balanced",
    "short_dog",
    "longshot",
)
LOGISTIC_STDDEV_TO_SCALE = sqrt(3.0) / pi
MIN_SPREAD_RESIDUAL_SCALE = 1.0
SPREAD_LINE_BUCKETS = (
    ("tight", 0.0, 4.5),
    ("priced_range", 5.0, 10.0),
    ("long_line", 10.5, None),
)
SPREAD_SEASON_PHASE_BUCKETS = (
    ("opener", 0, 0),
    ("early", 1, 5),
    ("established", 6, None),
)
SPREAD_BOOK_DEPTH_BUCKETS = (
    ("low_depth", 0, 4),
    ("mid_depth", 5, 7),
    ("high_depth", 8, None),
)
SPREAD_TIMING_HOURS_BEFORE_TIP = (48.0, 24.0, 12.0, 6.0)
DEFAULT_SPREAD_TIMING_MIN_HOURS_TO_TIP = 6.0
DEFAULT_SPREAD_TIMING_MIN_FAVORABLE_PROBABILITY = 0.5
LOW_PROFILE_TIMING_BOOK_THRESHOLD = 8.0
SPREAD_TIMING_PROFILE_KEYS = ("low_profile", "high_profile")
SPREAD_TIMING_FEATURE_NAMES = (
    "home_side",
    "same_conference_game",
    "games_played_diff",
    "min_season_games_played",
    "season_opener",
    "early_season",
    "elo_diff",
    "carryover_elo_diff",
    "season_elo_shift_diff",
    "rest_days_diff",
    "spread_line",
    "spread_abs_line",
    "spread_line_move",
    "spread_consensus_dispersion",
    "spread_books",
    "h2h_consensus_move",
    "h2h_consensus_dispersion",
    "h2h_books",
    "total_points_move",
    "total_consensus_dispersion",
    "total_books",
    "hours_to_tip",
)


@dataclass(frozen=True)
class LogisticRegressionConfig:
    """Trainer hyperparameters for logistic and tree-based models."""

    learning_rate: float = DEFAULT_LEARNING_RATE
    epochs: int = DEFAULT_EPOCHS
    l2_penalty: float = DEFAULT_L2_PENALTY
    min_examples: int = DEFAULT_MIN_EXAMPLES
    tree_learning_rate: float = 0.05
    tree_max_iter: int = 150
    tree_max_depth: int = 3
    tree_min_samples_leaf: int = 20
    tree_l2_regularization: float = 0.05


@dataclass(frozen=True)
class TrainingOptions:
    """Options for training one betting model artifact."""

    market: ModelMarket
    seasons_back: int = DEFAULT_MODEL_SEASONS_BACK
    max_season: int | None = None
    artifact_name: str = DEFAULT_ARTIFACT_NAME
    database_url: str | None = None
    artifacts_dir: Path | None = None
    model_family: ModelFamily = DEFAULT_MODEL_FAMILY
    moneyline_price_min: float = DEFAULT_MONEYLINE_TRAIN_MIN_PRICE
    moneyline_price_max: float = DEFAULT_MONEYLINE_TRAIN_MAX_PRICE
    config: LogisticRegressionConfig = field(default_factory=LogisticRegressionConfig)


@dataclass(frozen=True)
class TrainingSummary:
    """Reported result after training and saving one artifact."""

    market: ModelMarket
    model_family: ModelFamily
    start_season: int
    end_season: int
    examples: int
    priced_examples: int
    training_examples: int
    accuracy: float
    log_loss: float
    brier_score: float
    market_blend_weight: float
    max_market_probability_delta: float
    artifact_path: Path


@dataclass(frozen=True)
class FittedParameters:
    """Standardized logistic-regression parameters."""

    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float


@dataclass(frozen=True)
class RawProbabilityModel:
    """Trained raw model before probability calibration."""

    model_family: ModelFamily
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    serialized_model_base64: str | None = None


@dataclass(frozen=True)
class RawSpreadMarginModel:
    """Trained linear spread model before probability calibration."""

    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    spread_residual_scale: float
    spread_line_residual_scales: tuple[SpreadLineResidualScale, ...] = ()
    spread_season_phase_residual_scales: tuple[SpreadSeasonPhaseResidualScale, ...] = ()
    spread_book_depth_residual_scales: tuple[SpreadBookDepthResidualScale, ...] = ()


@dataclass(frozen=True)
class FittedProbabilityModel:
    """Fitted model plus calibration controls."""

    model_family: ModelFamily
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    platt_scale: float
    platt_bias: float
    market_blend_weight: float
    max_market_probability_delta: float
    moneyline_segment_calibrations: tuple[MoneylineSegmentCalibration, ...] = ()
    spread_modeling_mode: SpreadModelingMode = "cover_classifier"
    spread_residual_scale: float = 1.0
    spread_line_calibrations: tuple[SpreadLineCalibration, ...] = ()
    spread_conference_calibrations: tuple[SpreadConferenceCalibration, ...] = ()
    spread_season_phase_calibrations: tuple[SpreadSeasonPhaseCalibration, ...] = ()
    spread_line_residual_scales: tuple[SpreadLineResidualScale, ...] = ()
    spread_season_phase_residual_scales: tuple[SpreadSeasonPhaseResidualScale, ...] = ()
    spread_book_depth_residual_scales: tuple[SpreadBookDepthResidualScale, ...] = ()
    serialized_model_base64: str | None = None


def train_betting_model(options: TrainingOptions) -> TrainingSummary:
    """Train and persist one betting-model artifact."""
    selected_seasons = resolve_training_seasons(
        seasons_back=options.seasons_back,
        max_season=options.max_season,
        database_url=options.database_url,
    )
    completed_records = load_completed_game_records(
        max_season=selected_seasons[-1],
        database_url=options.database_url,
    )
    filtered_records = [
        record for record in completed_records if record.season in set(selected_seasons)
    ]
    artifact = train_artifact_from_records(
        market=options.market,
        game_records=filtered_records,
        seasons=selected_seasons,
        model_family=options.model_family,
        moneyline_price_min=options.moneyline_price_min,
        moneyline_price_max=options.moneyline_price_max,
        config=options.config,
    )
    artifact_path = save_artifact(
        artifact,
        artifact_name=options.artifact_name,
        artifacts_dir=options.artifacts_dir,
    )
    return TrainingSummary(
        market=artifact.market,
        model_family=artifact.model_family,
        start_season=artifact.metrics.start_season,
        end_season=artifact.metrics.end_season,
        examples=artifact.metrics.examples,
        priced_examples=artifact.metrics.priced_examples,
        training_examples=artifact.metrics.training_examples,
        accuracy=artifact.metrics.accuracy,
        log_loss=artifact.metrics.log_loss,
        brier_score=artifact.metrics.brier_score,
        market_blend_weight=artifact.market_blend_weight,
        max_market_probability_delta=artifact.max_market_probability_delta,
        artifact_path=artifact_path,
    )


def resolve_training_seasons(
    *,
    seasons_back: int,
    max_season: int | None = None,
    database_url: str | None = None,
) -> list[int]:
    """Resolve the rolling season window used for training."""
    available_seasons = get_available_seasons(database_url)
    eligible_seasons = [
        season
        for season in available_seasons
        if max_season is None or season <= max_season
    ]
    if not eligible_seasons:
        raise ValueError("No completed seasons are available for training")
    return eligible_seasons[-seasons_back:]


def train_artifact_from_records(
    *,
    market: ModelMarket,
    game_records: list[GameOddsRecord],
    seasons: Sequence[int],
    model_family: ModelFamily = DEFAULT_MODEL_FAMILY,
    moneyline_price_min: float = DEFAULT_MONEYLINE_TRAIN_MIN_PRICE,
    moneyline_price_max: float = DEFAULT_MONEYLINE_TRAIN_MAX_PRICE,
    config: LogisticRegressionConfig,
) -> ModelArtifact:
    """Fit one artifact from in-memory completed game records."""
    if market == "moneyline" and model_family != "logistic":
        raise ValueError("Moneyline currently only supports model_family=logistic")
    target_seasons = set(seasons)
    feature_names = feature_names_for_market(market)
    all_examples = build_training_examples(
        game_records=game_records,
        market=market,
        target_seasons=target_seasons,
    )
    effective_moneyline_price_min = (
        moneyline_price_min if market == "moneyline" else None
    )
    effective_moneyline_price_max = (
        moneyline_price_max if market == "moneyline" else None
    )
    trainable_examples = _deployable_training_examples(
        all_examples,
        moneyline_price_min=effective_moneyline_price_min,
        moneyline_price_max=effective_moneyline_price_max,
    )
    if len(trainable_examples) < config.min_examples:
        raise ValueError(
            f"Not enough {market} training examples: "
            f"need at least {config.min_examples}, found {len(trainable_examples)}"
        )

    fitted_model, probabilities, labels = _fit_probability_model(
        trainable_examples=trainable_examples,
        feature_names=feature_names,
        market=market,
        model_family=model_family,
        config=config,
    )
    spread_timing_model = (
        _train_spread_timing_model(
            game_records=game_records,
            seasons=target_seasons,
            config=config,
        )
        if market == "spread"
        else None
    )
    spread_timing_models = (
        _train_spread_timing_profile_models(
            game_records=game_records,
            seasons=target_seasons,
            config=config,
        )
        if market == "spread"
        else ()
    )
    moneyline_band_models = (
        _train_moneyline_band_models(
            all_examples=all_examples,
            feature_names=feature_names,
            price_min=effective_moneyline_price_min,
            price_max=effective_moneyline_price_max,
            config=config,
        )
        if market == "moneyline"
        else ()
    )
    if moneyline_band_models:
        probabilities = _score_moneyline_dispatcher_examples(
            artifact=ModelArtifact(
                market=market,
                model_family=fitted_model.model_family,
                feature_names=feature_names,
                means=fitted_model.means,
                scales=fitted_model.scales,
                weights=fitted_model.weights,
                bias=fitted_model.bias,
                metrics=TrainingMetrics(
                    examples=0,
                    priced_examples=0,
                    training_examples=0,
                    feature_names=feature_names,
                    log_loss=0.0,
                    brier_score=0.0,
                    accuracy=0.0,
                    start_season=min(target_seasons),
                    end_season=max(target_seasons),
                    trained_at=current_timestamp(),
                ),
                platt_scale=fitted_model.platt_scale,
                platt_bias=fitted_model.platt_bias,
                market_blend_weight=fitted_model.market_blend_weight,
                max_market_probability_delta=fitted_model.max_market_probability_delta,
                spread_modeling_mode=fitted_model.spread_modeling_mode,
                spread_residual_scale=fitted_model.spread_residual_scale,
                spread_line_residual_scales=(fitted_model.spread_line_residual_scales),
                spread_season_phase_residual_scales=(
                    fitted_model.spread_season_phase_residual_scales
                ),
                spread_book_depth_residual_scales=(
                    fitted_model.spread_book_depth_residual_scales
                ),
                moneyline_price_min=effective_moneyline_price_min,
                moneyline_price_max=effective_moneyline_price_max,
                moneyline_band_models=moneyline_band_models,
                moneyline_segment_calibrations=(
                    fitted_model.moneyline_segment_calibrations
                ),
                spread_line_calibrations=fitted_model.spread_line_calibrations,
                spread_conference_calibrations=(
                    fitted_model.spread_conference_calibrations
                ),
                spread_season_phase_calibrations=(
                    fitted_model.spread_season_phase_calibrations
                ),
                spread_timing_model=spread_timing_model,
                spread_timing_models=spread_timing_models,
                serialized_model_base64=fitted_model.serialized_model_base64,
            ),
            examples=trainable_examples,
        )
        labels = labels_for_examples(trainable_examples)
    else:
        probabilities = _score_examples_with_model(
            examples=trainable_examples,
            feature_names=feature_names,
            market=market,
            model_family=fitted_model.model_family,
            means=fitted_model.means,
            scales=fitted_model.scales,
            weights=fitted_model.weights,
            bias=fitted_model.bias,
            serialized_model_base64=fitted_model.serialized_model_base64,
            platt_scale=fitted_model.platt_scale,
            platt_bias=fitted_model.platt_bias,
            market_blend_weight=fitted_model.market_blend_weight,
            max_market_probability_delta=fitted_model.max_market_probability_delta,
            spread_modeling_mode=fitted_model.spread_modeling_mode,
            spread_residual_scale=fitted_model.spread_residual_scale,
            spread_line_residual_scales=fitted_model.spread_line_residual_scales,
            spread_season_phase_residual_scales=(
                fitted_model.spread_season_phase_residual_scales
            ),
            spread_book_depth_residual_scales=(
                fitted_model.spread_book_depth_residual_scales
            ),
            spread_line_calibrations=fitted_model.spread_line_calibrations,
            spread_conference_calibrations=(
                fitted_model.spread_conference_calibrations
            ),
            spread_season_phase_calibrations=(
                fitted_model.spread_season_phase_calibrations
            ),
            moneyline_segment_calibrations=(
                fitted_model.moneyline_segment_calibrations
            ),
        )
        labels = labels_for_examples(trainable_examples)
    metrics = _build_training_metrics(
        examples=all_examples,
        trainable_examples=trainable_examples,
        probabilities=probabilities,
        labels=labels,
        feature_names=feature_names,
        start_season=min(target_seasons),
        end_season=max(target_seasons),
    )
    return ModelArtifact(
        market=market,
        feature_names=feature_names,
        means=fitted_model.means,
        scales=fitted_model.scales,
        weights=fitted_model.weights,
        bias=fitted_model.bias,
        model_family=fitted_model.model_family,
        metrics=metrics,
        serialized_model_base64=fitted_model.serialized_model_base64,
        platt_scale=fitted_model.platt_scale,
        platt_bias=fitted_model.platt_bias,
        market_blend_weight=fitted_model.market_blend_weight,
        max_market_probability_delta=fitted_model.max_market_probability_delta,
        spread_modeling_mode=fitted_model.spread_modeling_mode,
        spread_residual_scale=fitted_model.spread_residual_scale,
        spread_line_residual_scales=fitted_model.spread_line_residual_scales,
        spread_season_phase_residual_scales=(
            fitted_model.spread_season_phase_residual_scales
        ),
        spread_book_depth_residual_scales=(
            fitted_model.spread_book_depth_residual_scales
        ),
        moneyline_price_min=effective_moneyline_price_min,
        moneyline_price_max=effective_moneyline_price_max,
        moneyline_band_models=moneyline_band_models,
        moneyline_segment_calibrations=fitted_model.moneyline_segment_calibrations,
        spread_line_calibrations=fitted_model.spread_line_calibrations,
        spread_conference_calibrations=fitted_model.spread_conference_calibrations,
        spread_season_phase_calibrations=(
            fitted_model.spread_season_phase_calibrations
        ),
        spread_timing_model=spread_timing_model,
        spread_timing_models=spread_timing_models,
    )


def fit_logistic_regression(
    *,
    feature_rows: list[list[float]],
    labels: list[int],
    config: LogisticRegressionConfig,
) -> FittedParameters:
    """Fit a standardized logistic-regression model with batch gradient descent."""
    if not feature_rows:
        raise ValueError("Cannot fit logistic regression without feature rows")
    feature_count = len(feature_rows[0])
    if feature_count == 0:
        raise ValueError("Cannot fit logistic regression without features")
    if len(labels) != len(feature_rows):
        raise ValueError("Feature row count must match label count")

    means, scales = _compute_standardization(feature_rows)
    standardized_rows = [
        _standardize_row(row, means=means, scales=scales) for row in feature_rows
    ]
    label_mean = sum(labels) / len(labels)
    weights = [0.0 for _ in range(feature_count)]
    bias = _logit(_clip_probability(label_mean))
    sample_count = float(len(standardized_rows))

    for _ in range(config.epochs):
        weight_gradients = [config.l2_penalty * weight for weight in weights]
        bias_gradient = 0.0
        for row, label in zip(standardized_rows, labels, strict=True):
            probability = _sigmoid(_linear_score(row, weights, bias))
            error = probability - float(label)
            for feature_index, value in enumerate(row):
                weight_gradients[feature_index] += error * value / sample_count
            bias_gradient += error / sample_count
        for feature_index in range(feature_count):
            weights[feature_index] -= (
                config.learning_rate * weight_gradients[feature_index]
            )
        bias -= config.learning_rate * bias_gradient

    return FittedParameters(
        means=means,
        scales=scales,
        weights=tuple(weights),
        bias=bias,
    )


def fit_linear_regression(
    *,
    feature_rows: list[list[float]],
    targets: list[float],
    config: LogisticRegressionConfig,
) -> FittedParameters:
    """Fit a standardized linear model for spread residual prediction."""
    if not feature_rows:
        raise ValueError("Cannot fit linear regression without feature rows")
    feature_count = len(feature_rows[0])
    if feature_count == 0:
        raise ValueError("Cannot fit linear regression without features")
    if len(targets) != len(feature_rows):
        raise ValueError("Feature row count must match target count")

    means, scales = _compute_standardization(feature_rows)
    standardized_rows = [
        _standardize_row(row, means=means, scales=scales) for row in feature_rows
    ]
    weights = [0.0 for _ in range(feature_count)]
    bias = sum(targets) / len(targets)
    sample_count = float(len(standardized_rows))

    for _ in range(config.epochs):
        weight_gradients = [config.l2_penalty * weight for weight in weights]
        bias_gradient = 0.0
        for row, target in zip(standardized_rows, targets, strict=True):
            prediction = _linear_score(row, weights, bias)
            error = prediction - target
            for feature_index, value in enumerate(row):
                weight_gradients[feature_index] += 2.0 * error * value / sample_count
            bias_gradient += 2.0 * error / sample_count
        for feature_index in range(feature_count):
            weights[feature_index] -= (
                config.learning_rate * weight_gradients[feature_index]
            )
        bias -= config.learning_rate * bias_gradient

    return FittedParameters(
        means=means,
        scales=scales,
        weights=tuple(weights),
        bias=bias,
    )


def _train_spread_timing_model(
    *,
    game_records: list[GameOddsRecord],
    seasons: set[int],
    config: LogisticRegressionConfig,
) -> SpreadTimingModel | None:
    feature_rows, labels = _collect_spread_timing_examples(
        game_records=game_records,
        seasons=seasons,
        scoped_profile_key=None,
    )
    return _fit_spread_timing_model_from_rows(
        feature_rows=feature_rows,
        labels=labels,
        config=config,
        profile_key="global",
    )


def _train_spread_timing_profile_models(
    *,
    game_records: list[GameOddsRecord],
    seasons: set[int],
    config: LogisticRegressionConfig,
) -> tuple[SpreadTimingModel, ...]:
    models: list[SpreadTimingModel] = []
    for profile_key in SPREAD_TIMING_PROFILE_KEYS:
        feature_rows, labels = _collect_spread_timing_examples(
            game_records=game_records,
            seasons=seasons,
            scoped_profile_key=profile_key,
        )
        model = _fit_spread_timing_model_from_rows(
            feature_rows=feature_rows,
            labels=labels,
            config=config,
            profile_key=profile_key,
        )
        if model is not None:
            models.append(model)
    return tuple(models)


def _collect_spread_timing_examples(
    *,
    game_records: list[GameOddsRecord],
    seasons: set[int],
    scoped_profile_key: str | None,
) -> tuple[list[list[float]], list[int]]:
    feature_rows: list[list[float]] = []
    labels: list[int] = []
    final_lines_by_game_side = {
        (record.game_id, "home"): record.home_spread_line
        for record in game_records
        if record.season in seasons
    }
    final_lines_by_game_side.update(
        {
            (record.game_id, "away"): record.away_spread_line
            for record in game_records
            if record.season in seasons
        }
    )

    for hours_to_tip in SPREAD_TIMING_HOURS_BEFORE_TIP:
        observation_records = [
            derive_game_record_at_observation_time(
                record,
                observation_time=record.commence_time - timedelta(hours=hours_to_tip),
            )
            for record in game_records
        ]
        timing_examples = build_training_examples(
            game_records=observation_records,
            market="spread",
            target_seasons=seasons,
        )
        for example in timing_examples:
            if example.line_value is None:
                continue
            final_line = final_lines_by_game_side.get((example.game_id, example.side))
            if final_line is None:
                continue
            if (
                scoped_profile_key is not None
                and _spread_timing_profile_key(example) != scoped_profile_key
            ):
                continue
            feature_rows.append(
                _spread_timing_feature_row(
                    example=example,
                    hours_to_tip=hours_to_tip,
                )
            )
            labels.append(1 if example.line_value > final_line else 0)
    return feature_rows, labels


def _fit_spread_timing_model_from_rows(
    *,
    feature_rows: list[list[float]],
    labels: list[int],
    config: LogisticRegressionConfig,
    profile_key: str,
) -> SpreadTimingModel | None:
    if len(feature_rows) < max(config.min_examples, MIN_SPREAD_TIMING_EXAMPLES):
        return None
    if len(set(labels)) < 2:
        return None

    fitted = fit_logistic_regression(
        feature_rows=feature_rows,
        labels=labels,
        config=config,
    )
    return SpreadTimingModel(
        feature_names=SPREAD_TIMING_FEATURE_NAMES,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        min_favorable_probability=DEFAULT_SPREAD_TIMING_MIN_FAVORABLE_PROBABILITY,
        min_hours_to_tip=DEFAULT_SPREAD_TIMING_MIN_HOURS_TO_TIP,
        profile_key=profile_key,
    )


def _spread_timing_feature_row(
    *,
    example: ModelExample,
    hours_to_tip: float,
) -> list[float]:
    feature_values = dict(example.features)
    feature_values["hours_to_tip"] = hours_to_tip
    return [
        feature_values.get(feature_name, 0.0)
        for feature_name in SPREAD_TIMING_FEATURE_NAMES
    ]


def _fit_probability_model(
    *,
    trainable_examples: list[ModelExample],
    feature_names: tuple[str, ...],
    market: ModelMarket,
    model_family: ModelFamily,
    config: LogisticRegressionConfig,
) -> tuple[FittedProbabilityModel, list[float], list[int]]:
    if market == "spread" and model_family == "logistic":
        return _fit_spread_margin_probability_model(
            trainable_examples=trainable_examples,
            feature_names=feature_names,
            config=config,
        )

    provisional_training_examples, calibration_examples = (
        _split_examples_for_calibration(trainable_examples)
    )
    provisional_fitted = _fit_raw_probability_model(
        trainable_examples=provisional_training_examples,
        feature_names=feature_names,
        model_family=model_family,
        config=config,
    )
    probability_calibration_examples, market_calibration_examples = (
        _split_market_calibration_examples(calibration_examples)
    )
    platt_scale, platt_bias = _fit_probability_calibration(
        fitted=provisional_fitted,
        feature_names=feature_names,
        calibration_examples=probability_calibration_examples,
    )
    market_blend_weight, max_market_probability_delta = _select_market_calibration(
        fitted=provisional_fitted,
        feature_names=feature_names,
        calibration_examples=market_calibration_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
    )
    moneyline_segment_calibrations = (
        _select_moneyline_segment_calibrations(
            fitted=provisional_fitted,
            feature_names=feature_names,
            calibration_examples=market_calibration_examples,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            default_market_blend_weight=market_blend_weight,
            default_max_market_probability_delta=max_market_probability_delta,
        )
        if market == "moneyline"
        else ()
    )

    labels = labels_for_examples(trainable_examples)
    fitted = _fit_raw_probability_model(
        trainable_examples=trainable_examples,
        feature_names=feature_names,
        model_family=model_family,
        config=config,
    )
    probabilities = _score_examples_with_model(
        examples=trainable_examples,
        feature_names=feature_names,
        market=market,
        model_family=fitted.model_family,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        serialized_model_base64=fitted.serialized_model_base64,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
        moneyline_segment_calibrations=moneyline_segment_calibrations,
    )
    return (
        FittedProbabilityModel(
            model_family=fitted.model_family,
            means=fitted.means,
            scales=fitted.scales,
            weights=fitted.weights,
            bias=fitted.bias,
            serialized_model_base64=fitted.serialized_model_base64,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            market_blend_weight=market_blend_weight,
            max_market_probability_delta=max_market_probability_delta,
            moneyline_segment_calibrations=moneyline_segment_calibrations,
        ),
        probabilities,
        labels,
    )


def _fit_spread_margin_probability_model(
    *,
    trainable_examples: list[ModelExample],
    feature_names: tuple[str, ...],
    config: LogisticRegressionConfig,
) -> tuple[FittedProbabilityModel, list[float], list[int]]:
    provisional_training_examples, calibration_examples = (
        _split_examples_for_calibration(trainable_examples)
    )
    provisional_fitted = _fit_raw_spread_margin_model(
        trainable_examples=provisional_training_examples,
        feature_names=feature_names,
        config=config,
    )
    probability_calibration_examples, market_calibration_examples = (
        _split_market_calibration_examples(calibration_examples)
    )
    provisional_raw_probabilities = _score_raw_spread_margin_probabilities(
        examples=probability_calibration_examples,
        feature_names=feature_names,
        means=provisional_fitted.means,
        scales=provisional_fitted.scales,
        weights=provisional_fitted.weights,
        bias=provisional_fitted.bias,
        spread_residual_scale=provisional_fitted.spread_residual_scale,
        spread_line_residual_scales=(provisional_fitted.spread_line_residual_scales),
        spread_season_phase_residual_scales=(
            provisional_fitted.spread_season_phase_residual_scales
        ),
        spread_book_depth_residual_scales=(
            provisional_fitted.spread_book_depth_residual_scales
        ),
    )
    platt_scale, platt_bias = fit_platt_scaling(
        raw_probabilities=provisional_raw_probabilities,
        labels=labels_for_examples(probability_calibration_examples),
    )
    market_blend_weight, max_market_probability_delta = (
        _select_spread_market_calibration(
            means=provisional_fitted.means,
            scales=provisional_fitted.scales,
            weights=provisional_fitted.weights,
            bias=provisional_fitted.bias,
            feature_names=feature_names,
            calibration_examples=market_calibration_examples,
            spread_residual_scale=provisional_fitted.spread_residual_scale,
            spread_line_residual_scales=(
                provisional_fitted.spread_line_residual_scales
            ),
            spread_season_phase_residual_scales=(
                provisional_fitted.spread_season_phase_residual_scales
            ),
            spread_book_depth_residual_scales=(
                provisional_fitted.spread_book_depth_residual_scales
            ),
            platt_scale=platt_scale,
            platt_bias=platt_bias,
        )
    )
    spread_line_calibrations = _select_spread_line_calibrations(
        means=provisional_fitted.means,
        scales=provisional_fitted.scales,
        weights=provisional_fitted.weights,
        bias=provisional_fitted.bias,
        feature_names=feature_names,
        calibration_examples=market_calibration_examples,
        spread_residual_scale=provisional_fitted.spread_residual_scale,
        spread_line_residual_scales=(provisional_fitted.spread_line_residual_scales),
        spread_season_phase_residual_scales=(
            provisional_fitted.spread_season_phase_residual_scales
        ),
        spread_book_depth_residual_scales=(
            provisional_fitted.spread_book_depth_residual_scales
        ),
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        default_market_blend_weight=market_blend_weight,
        default_max_market_probability_delta=max_market_probability_delta,
    )
    spread_conference_calibrations = _select_spread_conference_calibrations(
        means=provisional_fitted.means,
        scales=provisional_fitted.scales,
        weights=provisional_fitted.weights,
        bias=provisional_fitted.bias,
        feature_names=feature_names,
        calibration_examples=market_calibration_examples,
        spread_residual_scale=provisional_fitted.spread_residual_scale,
        spread_line_residual_scales=(provisional_fitted.spread_line_residual_scales),
        spread_season_phase_residual_scales=(
            provisional_fitted.spread_season_phase_residual_scales
        ),
        spread_book_depth_residual_scales=(
            provisional_fitted.spread_book_depth_residual_scales
        ),
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        default_market_blend_weight=market_blend_weight,
        default_max_market_probability_delta=max_market_probability_delta,
    )
    spread_season_phase_calibrations = _select_spread_season_phase_calibrations(
        means=provisional_fitted.means,
        scales=provisional_fitted.scales,
        weights=provisional_fitted.weights,
        bias=provisional_fitted.bias,
        feature_names=feature_names,
        calibration_examples=market_calibration_examples,
        spread_residual_scale=provisional_fitted.spread_residual_scale,
        spread_line_residual_scales=(provisional_fitted.spread_line_residual_scales),
        spread_season_phase_residual_scales=(
            provisional_fitted.spread_season_phase_residual_scales
        ),
        spread_book_depth_residual_scales=(
            provisional_fitted.spread_book_depth_residual_scales
        ),
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        default_market_blend_weight=market_blend_weight,
        default_max_market_probability_delta=max_market_probability_delta,
    )

    fitted = _fit_raw_spread_margin_model(
        trainable_examples=trainable_examples,
        feature_names=feature_names,
        config=config,
    )
    probabilities = _score_examples_with_margin_model(
        examples=trainable_examples,
        feature_names=feature_names,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        spread_residual_scale=fitted.spread_residual_scale,
        spread_line_residual_scales=fitted.spread_line_residual_scales,
        spread_season_phase_residual_scales=(
            fitted.spread_season_phase_residual_scales
        ),
        spread_book_depth_residual_scales=(fitted.spread_book_depth_residual_scales),
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
        spread_line_calibrations=spread_line_calibrations,
        spread_conference_calibrations=spread_conference_calibrations,
        spread_season_phase_calibrations=spread_season_phase_calibrations,
    )
    labels = labels_for_examples(trainable_examples)
    return (
        FittedProbabilityModel(
            model_family="logistic",
            means=fitted.means,
            scales=fitted.scales,
            weights=fitted.weights,
            bias=fitted.bias,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            market_blend_weight=market_blend_weight,
            max_market_probability_delta=max_market_probability_delta,
            spread_modeling_mode=DEFAULT_SPREAD_MODELING_MODE,
            spread_residual_scale=fitted.spread_residual_scale,
            spread_line_calibrations=spread_line_calibrations,
            spread_conference_calibrations=spread_conference_calibrations,
            spread_season_phase_calibrations=spread_season_phase_calibrations,
            spread_line_residual_scales=fitted.spread_line_residual_scales,
            spread_season_phase_residual_scales=(
                fitted.spread_season_phase_residual_scales
            ),
            spread_book_depth_residual_scales=(
                fitted.spread_book_depth_residual_scales
            ),
        ),
        probabilities,
        labels,
    )


def _fit_raw_spread_margin_model(
    *,
    trainable_examples: list[ModelExample],
    feature_names: tuple[str, ...],
    config: LogisticRegressionConfig,
) -> RawSpreadMarginModel:
    feature_rows = feature_matrix(trainable_examples, feature_names)
    targets = regression_targets_for_examples(trainable_examples)
    if len(targets) != len(trainable_examples):
        raise ValueError("Spread margin training examples require regression_target")
    fitted = fit_linear_regression(
        feature_rows=feature_rows,
        targets=targets,
        config=config,
    )
    predicted_residuals = score_linear_feature_rows(
        feature_rows=feature_rows,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
    )
    spread_residual_scale = _estimate_spread_residual_scale(
        predicted_residuals=predicted_residuals,
        targets=targets,
    )
    spread_line_residual_scales = _select_spread_line_residual_scales(
        examples=trainable_examples,
        predicted_residuals=predicted_residuals,
        targets=targets,
    )
    spread_season_phase_residual_scales = _select_spread_season_phase_residual_scales(
        examples=trainable_examples,
        predicted_residuals=predicted_residuals,
        targets=targets,
    )
    spread_book_depth_residual_scales = _select_spread_book_depth_residual_scales(
        examples=trainable_examples,
        predicted_residuals=predicted_residuals,
        targets=targets,
    )
    return RawSpreadMarginModel(
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        spread_residual_scale=spread_residual_scale,
        spread_line_residual_scales=spread_line_residual_scales,
        spread_season_phase_residual_scales=spread_season_phase_residual_scales,
        spread_book_depth_residual_scales=spread_book_depth_residual_scales,
    )


def _score_raw_spread_margin_probabilities(
    *,
    examples: Sequence[ModelExample],
    feature_names: tuple[str, ...],
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    spread_residual_scale: float,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
) -> list[float]:
    feature_rows = feature_matrix(list(examples), feature_names)
    predicted_residuals = score_linear_feature_rows(
        feature_rows=feature_rows,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
    )
    return [
        _spread_margin_to_probability(
            predicted_margin_residual=predicted_residual,
            spread_residual_scale=_effective_spread_residual_scale(
                example=example,
                base_residual_scale=spread_residual_scale,
                spread_line_residual_scales=spread_line_residual_scales,
                spread_season_phase_residual_scales=(
                    spread_season_phase_residual_scales
                ),
                spread_book_depth_residual_scales=(spread_book_depth_residual_scales),
            ),
        )
        for example, predicted_residual in zip(
            examples,
            predicted_residuals,
            strict=True,
        )
    ]


def _fit_raw_probability_model(
    *,
    trainable_examples: list[ModelExample],
    feature_names: tuple[str, ...],
    model_family: ModelFamily,
    config: LogisticRegressionConfig,
) -> RawProbabilityModel:
    feature_rows = feature_matrix(trainable_examples, feature_names)
    labels = labels_for_examples(trainable_examples)
    if model_family == "hist_gradient_boosting":
        fitted_model = fit_hist_gradient_boosting(
            feature_rows=feature_rows,
            labels=labels,
            config=config,
        )
        return RawProbabilityModel(
            model_family=model_family,
            means=(),
            scales=(),
            weights=(),
            bias=0.0,
            serialized_model_base64=_serialize_model_object(fitted_model),
        )

    fitted = fit_logistic_regression(
        feature_rows=feature_rows,
        labels=labels,
        config=config,
    )
    return RawProbabilityModel(
        model_family=model_family,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
    )


def fit_hist_gradient_boosting(
    *,
    feature_rows: list[list[float]],
    labels: list[int],
    config: LogisticRegressionConfig,
) -> HistGradientBoostingClassifier:
    """Fit a histogram gradient-boosted tree classifier for spread modeling."""
    if not feature_rows:
        raise ValueError("Cannot fit histogram gradient boosting without feature rows")
    if len(labels) != len(feature_rows):
        raise ValueError("Feature row count must match label count")
    model = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=config.tree_learning_rate,
        max_iter=config.tree_max_iter,
        max_depth=config.tree_max_depth,
        min_samples_leaf=config.tree_min_samples_leaf,
        l2_regularization=config.tree_l2_regularization,
        random_state=0,
    )
    model.fit(feature_rows, labels)
    return model


def _train_moneyline_band_models(
    *,
    all_examples: list[ModelExample],
    feature_names: tuple[str, ...],
    price_min: float | None,
    price_max: float | None,
    config: LogisticRegressionConfig,
) -> tuple[MoneylineBandModel, ...]:
    band_models: list[MoneylineBandModel] = []
    for band_key, band_min, band_max in MONEYLINE_DISPATCH_BANDS:
        scoped_price_min = (
            max(band_min, price_min) if price_min is not None else band_min
        )
        scoped_price_max = (
            min(band_max, price_max) if price_max is not None else band_max
        )
        if scoped_price_min > scoped_price_max:
            continue
        band_examples = _deployable_training_examples(
            all_examples,
            moneyline_price_min=scoped_price_min,
            moneyline_price_max=scoped_price_max,
        )
        if len(band_examples) < config.min_examples:
            continue
        fitted_model, _, _ = _fit_probability_model(
            trainable_examples=band_examples,
            feature_names=feature_names,
            market="moneyline",
            model_family="logistic",
            config=config,
        )
        band_models.append(
            MoneylineBandModel(
                band_key=band_key,
                price_min=scoped_price_min,
                price_max=scoped_price_max,
                means=fitted_model.means,
                scales=fitted_model.scales,
                weights=fitted_model.weights,
                bias=fitted_model.bias,
                platt_scale=fitted_model.platt_scale,
                platt_bias=fitted_model.platt_bias,
                market_blend_weight=fitted_model.market_blend_weight,
                max_market_probability_delta=fitted_model.max_market_probability_delta,
            )
        )
    return tuple(band_models)


def score_examples(
    *,
    artifact: ModelArtifact,
    examples: list[ModelExample],
) -> list[float]:
    """Score examples with a stored artifact and return win probabilities."""
    if artifact.market == "moneyline" and artifact.moneyline_band_models:
        return _score_moneyline_dispatcher_examples(
            artifact=artifact,
            examples=examples,
        )
    if (
        artifact.market == "spread"
        and artifact.spread_modeling_mode == "margin_regression"
    ):
        return _score_examples_with_margin_model(
            examples=examples,
            feature_names=artifact.feature_names,
            means=artifact.means,
            scales=artifact.scales,
            weights=artifact.weights,
            bias=artifact.bias,
            spread_residual_scale=artifact.spread_residual_scale,
            spread_line_residual_scales=artifact.spread_line_residual_scales,
            spread_season_phase_residual_scales=(
                artifact.spread_season_phase_residual_scales
            ),
            spread_book_depth_residual_scales=(
                artifact.spread_book_depth_residual_scales
            ),
            platt_scale=artifact.platt_scale,
            platt_bias=artifact.platt_bias,
            market_blend_weight=artifact.market_blend_weight,
            max_market_probability_delta=artifact.max_market_probability_delta,
            spread_line_calibrations=artifact.spread_line_calibrations,
            spread_conference_calibrations=(artifact.spread_conference_calibrations),
            spread_season_phase_calibrations=(
                artifact.spread_season_phase_calibrations
            ),
        )
    return _score_examples_with_model(
        examples=examples,
        feature_names=artifact.feature_names,
        market=artifact.market,
        model_family=artifact.model_family,
        means=artifact.means,
        scales=artifact.scales,
        weights=artifact.weights,
        bias=artifact.bias,
        serialized_model_base64=artifact.serialized_model_base64,
        platt_scale=artifact.platt_scale,
        platt_bias=artifact.platt_bias,
        market_blend_weight=artifact.market_blend_weight,
        max_market_probability_delta=artifact.max_market_probability_delta,
        spread_modeling_mode=artifact.spread_modeling_mode,
        spread_residual_scale=artifact.spread_residual_scale,
        spread_line_residual_scales=artifact.spread_line_residual_scales,
        spread_season_phase_residual_scales=(
            artifact.spread_season_phase_residual_scales
        ),
        spread_book_depth_residual_scales=(artifact.spread_book_depth_residual_scales),
        moneyline_segment_calibrations=artifact.moneyline_segment_calibrations,
        spread_line_calibrations=artifact.spread_line_calibrations,
        spread_conference_calibrations=artifact.spread_conference_calibrations,
        spread_season_phase_calibrations=(artifact.spread_season_phase_calibrations),
    )


def score_feature_rows(
    *,
    feature_rows: list[list[float]],
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
) -> list[float]:
    """Score raw feature rows against standardized logistic parameters."""
    probabilities: list[float] = []
    for row in feature_rows:
        standardized_row = _standardize_row(row, means=means, scales=scales)
        probabilities.append(_sigmoid(_linear_score(standardized_row, weights, bias)))
    return probabilities


def score_linear_feature_rows(
    *,
    feature_rows: list[list[float]],
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
) -> list[float]:
    """Score feature rows with a standardized linear model."""
    scores: list[float] = []
    for row in feature_rows:
        standardized_row = _standardize_row(row, means=means, scales=scales)
        scores.append(_linear_score(standardized_row, weights, bias))
    return scores


def score_spread_timing_probability(
    *,
    timing_model: SpreadTimingModel,
    example: ModelExample,
) -> float | None:
    """Score the probability that the current spread line is better than close."""
    hours_to_tip = _hours_to_tip_for_example(example)
    if hours_to_tip is None or hours_to_tip < timing_model.min_hours_to_tip:
        return None
    return score_feature_rows(
        feature_rows=[
            _spread_timing_feature_row(
                example=example,
                hours_to_tip=hours_to_tip,
            )
        ],
        means=timing_model.means,
        scales=timing_model.scales,
        weights=timing_model.weights,
        bias=timing_model.bias,
    )[0]


def select_spread_timing_model(
    *,
    artifact: ModelArtifact,
    example: ModelExample,
) -> SpreadTimingModel | None:
    """Select the most specific stored timing model for one spread example."""
    profile_key = _spread_timing_profile_key(example)
    for timing_model in artifact.spread_timing_models:
        if timing_model.profile_key == profile_key:
            return timing_model
    return artifact.spread_timing_model


def score_spread_probability_at_line(
    *,
    artifact: ModelArtifact,
    example: ModelExample,
    line_value: float,
) -> float:
    """Score one spread example at an alternate executable line."""
    if artifact.market != "spread":
        raise ValueError("score_spread_probability_at_line requires a spread artifact")
    repriced_example = repriced_spread_example(
        example=example,
        line_value=line_value,
    )
    return score_examples(
        artifact=artifact,
        examples=[repriced_example],
    )[0]


def _score_feature_rows_with_model(
    *,
    feature_rows: list[list[float]],
    model_family: ModelFamily,
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    serialized_model_base64: str | None,
) -> list[float]:
    if model_family == "hist_gradient_boosting":
        if serialized_model_base64 is None:
            raise ValueError(
                "hist_gradient_boosting artifacts require serialized_model_base64"
            )
        model = cast(
            HistGradientBoostingClassifier,
            _deserialize_model_object(serialized_model_base64),
        )
        return [
            float(probability)
            for probability in model.predict_proba(feature_rows)[:, 1].tolist()
        ]
    return score_feature_rows(
        feature_rows=feature_rows,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
    )


def _score_examples_with_model(
    *,
    examples: Sequence[ModelExample],
    feature_names: tuple[str, ...],
    market: ModelMarket,
    model_family: ModelFamily,
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    serialized_model_base64: str | None,
    platt_scale: float,
    platt_bias: float,
    market_blend_weight: float,
    max_market_probability_delta: float,
    spread_modeling_mode: SpreadModelingMode = "cover_classifier",
    spread_residual_scale: float = 1.0,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
    moneyline_segment_calibrations: Sequence[MoneylineSegmentCalibration] = (),
    spread_line_calibrations: Sequence[SpreadLineCalibration] = (),
    spread_conference_calibrations: Sequence[SpreadConferenceCalibration] = (),
    spread_season_phase_calibrations: Sequence[SpreadSeasonPhaseCalibration] = (),
) -> list[float]:
    if market == "spread" and spread_modeling_mode == "margin_regression":
        return _score_examples_with_margin_model(
            examples=examples,
            feature_names=feature_names,
            means=means,
            scales=scales,
            weights=weights,
            bias=bias,
            spread_residual_scale=spread_residual_scale,
            spread_line_residual_scales=spread_line_residual_scales,
            spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
            spread_book_depth_residual_scales=(spread_book_depth_residual_scales),
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            market_blend_weight=market_blend_weight,
            max_market_probability_delta=max_market_probability_delta,
            spread_line_calibrations=spread_line_calibrations,
            spread_conference_calibrations=spread_conference_calibrations,
            spread_season_phase_calibrations=(spread_season_phase_calibrations),
        )
    feature_rows = feature_matrix(list(examples), feature_names)
    raw_probabilities = _score_feature_rows_with_model(
        feature_rows=feature_rows,
        model_family=model_family,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
        serialized_model_base64=serialized_model_base64,
    )
    return calibrate_probabilities(
        raw_probabilities=raw_probabilities,
        examples=examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
        moneyline_segment_calibrations=moneyline_segment_calibrations,
        spread_line_calibrations=spread_line_calibrations,
        spread_conference_calibrations=spread_conference_calibrations,
        spread_season_phase_calibrations=spread_season_phase_calibrations,
    )


def _score_examples_with_margin_model(
    *,
    examples: Sequence[ModelExample],
    feature_names: tuple[str, ...],
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    spread_residual_scale: float,
    platt_scale: float,
    platt_bias: float,
    market_blend_weight: float,
    max_market_probability_delta: float,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
    spread_line_calibrations: Sequence[SpreadLineCalibration] = (),
    spread_conference_calibrations: Sequence[SpreadConferenceCalibration] = (),
    spread_season_phase_calibrations: Sequence[SpreadSeasonPhaseCalibration] = (),
) -> list[float]:
    raw_probabilities = _score_raw_spread_margin_probabilities(
        examples=examples,
        feature_names=feature_names,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
        spread_residual_scale=spread_residual_scale,
        spread_line_residual_scales=spread_line_residual_scales,
        spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
        spread_book_depth_residual_scales=spread_book_depth_residual_scales,
    )
    return calibrate_probabilities(
        raw_probabilities=raw_probabilities,
        examples=examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
        spread_line_calibrations=spread_line_calibrations,
        spread_conference_calibrations=spread_conference_calibrations,
        spread_season_phase_calibrations=spread_season_phase_calibrations,
    )


def _serialize_model_object(model: object) -> str:
    return base64.b64encode(pickle.dumps(model)).decode("ascii")


@lru_cache(maxsize=32)
def _deserialize_model_object(serialized_model_base64: str) -> object:
    return pickle.loads(base64.b64decode(serialized_model_base64))


def _score_moneyline_dispatcher_examples(
    *,
    artifact: ModelArtifact,
    examples: Sequence[ModelExample],
) -> list[float]:
    probabilities = [0.0 for _ in examples]
    scoped_examples: dict[str, list[tuple[int, ModelExample]]] = {}
    band_models_by_key = {
        band_model.band_key: band_model for band_model in artifact.moneyline_band_models
    }
    for index, example in enumerate(examples):
        band_model = _moneyline_band_model_for_example(
            band_models=artifact.moneyline_band_models,
            example=example,
        )
        scope_key = band_model.band_key if band_model is not None else "fallback"
        scoped_examples.setdefault(scope_key, []).append((index, example))

    for scope_key, indexed_examples in scoped_examples.items():
        example_indices = [item[0] for item in indexed_examples]
        scoped_records = [item[1] for item in indexed_examples]
        if scope_key == "fallback":
            scoped_probabilities = _score_examples_with_model(
                examples=scoped_records,
                feature_names=artifact.feature_names,
                market="moneyline",
                model_family="logistic",
                means=artifact.means,
                scales=artifact.scales,
                weights=artifact.weights,
                bias=artifact.bias,
                serialized_model_base64=artifact.serialized_model_base64,
                platt_scale=artifact.platt_scale,
                platt_bias=artifact.platt_bias,
                market_blend_weight=artifact.market_blend_weight,
                max_market_probability_delta=artifact.max_market_probability_delta,
                moneyline_segment_calibrations=artifact.moneyline_segment_calibrations,
            )
        else:
            band_model = band_models_by_key[scope_key]
            scoped_probabilities = _score_examples_with_model(
                examples=scoped_records,
                feature_names=artifact.feature_names,
                market="moneyline",
                model_family="logistic",
                means=band_model.means,
                scales=band_model.scales,
                weights=band_model.weights,
                bias=band_model.bias,
                serialized_model_base64=None,
                platt_scale=band_model.platt_scale,
                platt_bias=band_model.platt_bias,
                market_blend_weight=band_model.market_blend_weight,
                max_market_probability_delta=band_model.max_market_probability_delta,
            )
        for index, probability in zip(
            example_indices,
            scoped_probabilities,
            strict=True,
        ):
            probabilities[index] = probability
    return probabilities


def calibrate_probabilities(
    *,
    raw_probabilities: Sequence[float],
    examples: Sequence[ModelExample],
    platt_scale: float,
    platt_bias: float,
    market_blend_weight: float,
    max_market_probability_delta: float,
    moneyline_segment_calibrations: Sequence[MoneylineSegmentCalibration] = (),
    spread_line_calibrations: Sequence[SpreadLineCalibration] = (),
    spread_conference_calibrations: Sequence[SpreadConferenceCalibration] = (),
    spread_season_phase_calibrations: Sequence[SpreadSeasonPhaseCalibration] = (),
) -> list[float]:
    """Calibrate raw model scores, then constrain them near the market."""
    calibrated_probabilities = apply_platt_scaling(
        raw_probabilities=raw_probabilities,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
    )
    stabilized_probabilities: list[float] = []
    for probability, example in zip(calibrated_probabilities, examples, strict=True):
        market_probability = example.market_implied_probability
        if market_probability is None:
            stabilized_probabilities.append(_clip_probability(probability))
            continue

        effective_blend_weight = market_blend_weight
        effective_max_delta = max_market_probability_delta
        if example.market == "moneyline":
            segment_calibration = _moneyline_segment_calibration_for_example(
                example=example,
                segment_calibrations=moneyline_segment_calibrations,
            )
            if segment_calibration is not None:
                effective_blend_weight = segment_calibration.market_blend_weight
                effective_max_delta = segment_calibration.max_market_probability_delta
            # Force the model to stay much closer to the market on extreme
            # moneyline prices, where small probability errors create huge EV.
            market_tail_stability = (
                4.0 * market_probability * (1.0 - market_probability)
            )
            effective_blend_weight *= market_tail_stability
            effective_max_delta *= market_tail_stability
        elif example.market == "spread":
            spread_line_calibration = _spread_line_calibration_for_example(
                example=example,
                line_calibrations=spread_line_calibrations,
            )
            if spread_line_calibration is not None:
                effective_blend_weight = spread_line_calibration.market_blend_weight
                effective_max_delta = (
                    spread_line_calibration.max_market_probability_delta
                )
            spread_season_phase_calibration = (
                _spread_season_phase_calibration_for_example(
                    example=example,
                    phase_calibrations=spread_season_phase_calibrations,
                )
            )
            if spread_season_phase_calibration is not None:
                effective_blend_weight = (
                    effective_blend_weight
                    + spread_season_phase_calibration.market_blend_weight
                ) / 2.0
                effective_max_delta = min(
                    effective_max_delta,
                    spread_season_phase_calibration.max_market_probability_delta,
                )
            spread_conference_calibration = _spread_conference_calibration_for_example(
                example=example,
                conference_calibrations=spread_conference_calibrations,
            )
            if spread_conference_calibration is not None:
                effective_blend_weight = (
                    effective_blend_weight
                    + spread_conference_calibration.market_blend_weight
                ) / 2.0
                effective_max_delta = min(
                    effective_max_delta,
                    spread_conference_calibration.max_market_probability_delta,
                )

        blended_probability = (
            effective_blend_weight * probability
            + (1.0 - effective_blend_weight) * market_probability
        )
        lower_bound = market_probability - effective_max_delta
        upper_bound = market_probability + effective_max_delta
        stabilized_probabilities.append(
            _clip_probability(min(max(blended_probability, lower_bound), upper_bound))
        )
    return stabilized_probabilities


def _build_training_metrics(
    *,
    examples: list[ModelExample],
    trainable_examples: list[ModelExample],
    probabilities: list[float],
    labels: list[int],
    feature_names: tuple[str, ...],
    start_season: int,
    end_season: int,
) -> TrainingMetrics:
    priced_examples = sum(
        1 for example in trainable_examples if example.market_price is not None
    )
    return TrainingMetrics(
        examples=len(examples),
        priced_examples=priced_examples,
        training_examples=len(trainable_examples),
        feature_names=feature_names,
        log_loss=_log_loss(probabilities, labels),
        brier_score=_brier_score(probabilities, labels),
        accuracy=_accuracy(probabilities, labels),
        start_season=start_season,
        end_season=end_season,
        trained_at=current_timestamp(),
    )


def _deployable_training_examples(
    examples: list[ModelExample],
    *,
    moneyline_price_min: float | None = None,
    moneyline_price_max: float | None = None,
) -> list[ModelExample]:
    return [
        example
        for example in training_examples_only(examples)
        if (
            example.market_price is not None
            and example.market_implied_probability is not None
            and (
                example.market != "moneyline"
                or (
                    (
                        moneyline_price_min is None
                        or example.market_price >= moneyline_price_min
                    )
                    and (
                        moneyline_price_max is None
                        or example.market_price <= moneyline_price_max
                    )
                )
            )
        )
    ]


def _split_examples_for_calibration(
    trainable_examples: list[ModelExample],
) -> tuple[list[ModelExample], list[ModelExample]]:
    priced_game_ids = [
        game_id
        for game_id in _ordered_priced_game_ids(trainable_examples)
        if game_id is not None
    ]
    if len(priced_game_ids) < MIN_CALIBRATION_GAMES:
        return trainable_examples, []

    holdout_games = max(
        MIN_CALIBRATION_GAMES,
        int(len(priced_game_ids) * CALIBRATION_HOLDOUT_FRACTION),
    )
    validation_game_ids = set(priced_game_ids[-holdout_games:])
    provisional_training_examples = [
        example
        for example in trainable_examples
        if example.game_id not in validation_game_ids
    ]
    calibration_examples = [
        example
        for example in trainable_examples
        if (
            example.game_id in validation_game_ids
            and example.market_implied_probability is not None
        )
    ]
    if not provisional_training_examples or not calibration_examples:
        return trainable_examples, []
    return provisional_training_examples, calibration_examples


def _split_market_calibration_examples(
    calibration_examples: list[ModelExample],
) -> tuple[list[ModelExample], list[ModelExample]]:
    priced_game_ids = _ordered_priced_game_ids(calibration_examples)
    if len(priced_game_ids) < MIN_MARKET_CALIBRATION_GAMES * 2:
        return calibration_examples, calibration_examples

    validation_games = max(
        MIN_MARKET_CALIBRATION_GAMES,
        int(len(priced_game_ids) * MARKET_CALIBRATION_VALIDATION_FRACTION),
    )
    if validation_games >= len(priced_game_ids):
        return calibration_examples, calibration_examples

    validation_game_ids = set(priced_game_ids[-validation_games:])
    probability_calibration_examples = [
        example
        for example in calibration_examples
        if example.game_id not in validation_game_ids
    ]
    market_calibration_examples = [
        example
        for example in calibration_examples
        if example.game_id in validation_game_ids
    ]
    if not probability_calibration_examples or not market_calibration_examples:
        return calibration_examples, calibration_examples
    return probability_calibration_examples, market_calibration_examples


def _ordered_priced_game_ids(trainable_examples: list[ModelExample]) -> list[int]:
    seen_game_ids: set[int] = set()
    ordered_game_ids: list[int] = []
    for example in trainable_examples:
        if (
            example.market_implied_probability is None
            or example.game_id in seen_game_ids
        ):
            continue
        seen_game_ids.add(example.game_id)
        ordered_game_ids.append(example.game_id)
    return ordered_game_ids


def _hours_to_tip_for_example(example: ModelExample) -> float | None:
    if example.observation_time is None:
        return None
    commence_time = _parse_iso_datetime(example.commence_time)
    observation_time = _parse_iso_datetime(example.observation_time)
    return max(
        0.0,
        (commence_time - observation_time).total_seconds() / 3600.0,
    )


def _parse_iso_datetime(value: str) -> datetime:
    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value


def _spread_timing_profile_key(example: ModelExample) -> str:
    market_books = max(
        float(example.features.get("spread_books", 0.0)),
        float(example.features.get("h2h_books", 0.0)),
        float(example.features.get("total_books", 0.0)),
    )
    if market_books < LOW_PROFILE_TIMING_BOOK_THRESHOLD:
        return "low_profile"
    return "high_profile"


def _fit_probability_calibration(
    *,
    fitted: RawProbabilityModel,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
) -> tuple[float, float]:
    if not calibration_examples:
        return DEFAULT_PLATT_SCALE, DEFAULT_PLATT_BIAS

    labels = labels_for_examples(calibration_examples)
    if len(set(labels)) < 2:
        return DEFAULT_PLATT_SCALE, DEFAULT_PLATT_BIAS

    feature_rows = feature_matrix(calibration_examples, feature_names)
    raw_probabilities = _score_feature_rows_with_model(
        feature_rows=feature_rows,
        model_family=fitted.model_family,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        serialized_model_base64=fitted.serialized_model_base64,
    )
    return fit_platt_scaling(
        raw_probabilities=raw_probabilities,
        labels=labels,
    )


def _select_market_calibration(
    *,
    fitted: RawProbabilityModel,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    platt_scale: float,
    platt_bias: float,
) -> tuple[float, float]:
    return _select_market_calibration_config(
        fitted=fitted,
        feature_names=feature_names,
        calibration_examples=calibration_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        default_market_blend_weight=DEFAULT_MARKET_BLEND_WEIGHT,
        default_max_market_probability_delta=DEFAULT_MAX_MARKET_PROBABILITY_DELTA,
        blend_grid=(0.0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0),
        max_delta_grid=(0.02, 0.04, 0.06, 0.08, 0.12, 0.20),
    )


def _select_spread_market_calibration(
    *,
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    spread_residual_scale: float,
    platt_scale: float,
    platt_bias: float,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
) -> tuple[float, float]:
    if not calibration_examples:
        return DEFAULT_MARKET_BLEND_WEIGHT, DEFAULT_MAX_MARKET_PROBABILITY_DELTA

    labels = labels_for_examples(calibration_examples)
    if not labels:
        return DEFAULT_MARKET_BLEND_WEIGHT, DEFAULT_MAX_MARKET_PROBABILITY_DELTA

    raw_probabilities = _score_raw_spread_margin_probabilities(
        examples=calibration_examples,
        feature_names=feature_names,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
        spread_residual_scale=spread_residual_scale,
        spread_line_residual_scales=spread_line_residual_scales,
        spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
        spread_book_depth_residual_scales=spread_book_depth_residual_scales,
    )
    return _select_calibration_config_from_raw_probabilities(
        raw_probabilities=raw_probabilities,
        calibration_examples=calibration_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        default_market_blend_weight=DEFAULT_MARKET_BLEND_WEIGHT,
        default_max_market_probability_delta=DEFAULT_MAX_MARKET_PROBABILITY_DELTA,
        blend_grid=(0.0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0),
        max_delta_grid=(0.02, 0.04, 0.06, 0.08, 0.12, 0.20),
    )


def _split_specialized_spread_calibration_examples(
    bucket_examples: list[ModelExample],
) -> tuple[list[ModelExample], list[ModelExample]]:
    game_ids = _ordered_priced_game_ids(bucket_examples)
    if len(game_ids) < MIN_MARKET_CALIBRATION_GAMES * 2:
        return [], []

    validation_games = max(
        MIN_MARKET_CALIBRATION_GAMES,
        int(
            len(game_ids)
            * SPECIALIZED_SPREAD_CALIBRATION_VALIDATION_FRACTION
        ),
    )
    if validation_games >= len(game_ids):
        return [], []

    validation_game_ids = set(game_ids[-validation_games:])
    selection_examples = [
        example
        for example in bucket_examples
        if example.game_id not in validation_game_ids
    ]
    validation_examples = [
        example
        for example in bucket_examples
        if example.game_id in validation_game_ids
    ]
    if not selection_examples or not validation_examples:
        return [], []
    return selection_examples, validation_examples


def _spread_calibration_config_improves_validation(
    *,
    raw_probabilities: Sequence[float],
    validation_examples: list[ModelExample],
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
    candidate_market_blend_weight: float,
    candidate_max_market_probability_delta: float,
) -> bool:
    labels = labels_for_examples(validation_examples)
    if not labels:
        return False

    default_probabilities = calibrate_probabilities(
        raw_probabilities=raw_probabilities,
        examples=validation_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=default_market_blend_weight,
        max_market_probability_delta=default_max_market_probability_delta,
    )
    candidate_probabilities = calibrate_probabilities(
        raw_probabilities=raw_probabilities,
        examples=validation_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=candidate_market_blend_weight,
        max_market_probability_delta=candidate_max_market_probability_delta,
    )
    default_log_loss = _log_loss(default_probabilities, labels)
    candidate_log_loss = _log_loss(candidate_probabilities, labels)
    if candidate_log_loss < default_log_loss - 1e-9:
        return True
    if abs(candidate_log_loss - default_log_loss) > 1e-9:
        return False

    default_brier = _brier_score(default_probabilities, labels)
    candidate_brier = _brier_score(candidate_probabilities, labels)
    return candidate_brier < default_brier - 1e-9


def _select_validated_spread_specialized_calibration(
    *,
    bucket_examples: list[ModelExample],
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    feature_names: tuple[str, ...],
    spread_residual_scale: float,
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
    blend_grid: Sequence[float],
    max_delta_grid: Sequence[float],
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
) -> tuple[float, float] | None:
    selection_examples, validation_examples = (
        _split_specialized_spread_calibration_examples(bucket_examples)
    )
    if not selection_examples or not validation_examples:
        return None

    selection_raw_probabilities = _score_raw_spread_margin_probabilities(
        examples=selection_examples,
        feature_names=feature_names,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
        spread_residual_scale=spread_residual_scale,
        spread_line_residual_scales=spread_line_residual_scales,
        spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
        spread_book_depth_residual_scales=(spread_book_depth_residual_scales),
    )
    candidate_market_blend_weight, candidate_max_market_probability_delta = (
        _select_calibration_config_from_raw_probabilities(
            raw_probabilities=selection_raw_probabilities,
            calibration_examples=selection_examples,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            default_market_blend_weight=default_market_blend_weight,
            default_max_market_probability_delta=default_max_market_probability_delta,
            blend_grid=blend_grid,
            max_delta_grid=max_delta_grid,
        )
    )
    if (
        candidate_market_blend_weight == default_market_blend_weight
        and candidate_max_market_probability_delta
        == default_max_market_probability_delta
    ):
        return None

    validation_raw_probabilities = _score_raw_spread_margin_probabilities(
        examples=validation_examples,
        feature_names=feature_names,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
        spread_residual_scale=spread_residual_scale,
        spread_line_residual_scales=spread_line_residual_scales,
        spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
        spread_book_depth_residual_scales=(spread_book_depth_residual_scales),
    )
    if not _spread_calibration_config_improves_validation(
        raw_probabilities=validation_raw_probabilities,
        validation_examples=validation_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        default_market_blend_weight=default_market_blend_weight,
        default_max_market_probability_delta=default_max_market_probability_delta,
        candidate_market_blend_weight=candidate_market_blend_weight,
        candidate_max_market_probability_delta=candidate_max_market_probability_delta,
    ):
        return None

    return (
        candidate_market_blend_weight,
        candidate_max_market_probability_delta,
    )


def _select_spread_line_calibrations(
    *,
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    spread_residual_scale: float,
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
) -> tuple[SpreadLineCalibration, ...]:
    if not calibration_examples:
        return ()

    line_calibrations: list[SpreadLineCalibration] = []
    for bucket_key, abs_line_min, abs_line_max in SPREAD_LINE_BUCKETS:
        bucket_examples = [
            example
            for example in calibration_examples
            if _spread_abs_line_in_bucket(
                line_value=example.line_value,
                abs_line_min=abs_line_min,
                abs_line_max=abs_line_max,
            )
        ]
        if len(bucket_examples) < MIN_SPREAD_BUCKET_CALIBRATION_GAMES:
            continue
        candidate_config = _select_validated_spread_specialized_calibration(
            bucket_examples=bucket_examples,
            feature_names=feature_names,
            means=means,
            scales=scales,
            weights=weights,
            bias=bias,
            spread_residual_scale=spread_residual_scale,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            default_market_blend_weight=default_market_blend_weight,
            default_max_market_probability_delta=default_max_market_probability_delta,
            blend_grid=(0.1, 0.2, 0.35, 0.5, 0.75, 1.0),
            max_delta_grid=(0.02, 0.04, 0.06, 0.08, 0.12),
            spread_line_residual_scales=spread_line_residual_scales,
            spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
            spread_book_depth_residual_scales=(spread_book_depth_residual_scales),
        )
        if candidate_config is None:
            continue
        market_blend_weight, max_market_probability_delta = candidate_config
        line_calibrations.append(
            SpreadLineCalibration(
                bucket_key=bucket_key,
                abs_line_min=abs_line_min,
                abs_line_max=abs_line_max,
                market_blend_weight=market_blend_weight,
                max_market_probability_delta=max_market_probability_delta,
            )
        )
    return tuple(line_calibrations)


def _select_spread_conference_calibrations(
    *,
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    spread_residual_scale: float,
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
) -> tuple[SpreadConferenceCalibration, ...]:
    if not calibration_examples:
        return ()

    conference_examples_by_key: dict[str, list[ModelExample]] = {}
    for example in calibration_examples:
        conference_key = example.team_conference_key
        if conference_key is None:
            continue
        conference_examples_by_key.setdefault(conference_key, []).append(example)

    conference_calibrations: list[SpreadConferenceCalibration] = []
    for conference_key in sorted(conference_examples_by_key):
        conference_examples = conference_examples_by_key[conference_key]
        if len(conference_examples) < MIN_SPREAD_CONFERENCE_CALIBRATION_GAMES:
            continue
        candidate_config = _select_validated_spread_specialized_calibration(
            bucket_examples=conference_examples,
            feature_names=feature_names,
            means=means,
            scales=scales,
            weights=weights,
            bias=bias,
            spread_residual_scale=spread_residual_scale,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            default_market_blend_weight=default_market_blend_weight,
            default_max_market_probability_delta=default_max_market_probability_delta,
            blend_grid=(0.1, 0.2, 0.35, 0.5, 0.75, 1.0),
            max_delta_grid=(0.02, 0.04, 0.06, 0.08, 0.12),
            spread_line_residual_scales=spread_line_residual_scales,
            spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
            spread_book_depth_residual_scales=(spread_book_depth_residual_scales),
        )
        if candidate_config is None:
            continue
        market_blend_weight, max_market_probability_delta = candidate_config
        conference_calibrations.append(
            SpreadConferenceCalibration(
                conference_key=conference_key,
                market_blend_weight=market_blend_weight,
                max_market_probability_delta=max_market_probability_delta,
            )
        )
    return tuple(conference_calibrations)


def _select_spread_season_phase_calibrations(
    *,
    means: Sequence[float],
    scales: Sequence[float],
    weights: Sequence[float],
    bias: float,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    spread_residual_scale: float,
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
) -> tuple[SpreadSeasonPhaseCalibration, ...]:
    if not calibration_examples:
        return ()

    phase_calibrations: list[SpreadSeasonPhaseCalibration] = []
    for (
        phase_key,
        min_games_played_min,
        min_games_played_max,
    ) in SPREAD_SEASON_PHASE_BUCKETS:
        phase_examples = [
            example
            for example in calibration_examples
            if _spread_min_games_played_in_bucket(
                example=example,
                min_games_played_min=min_games_played_min,
                min_games_played_max=min_games_played_max,
            )
        ]
        if len(phase_examples) < MIN_SPREAD_SEASON_PHASE_CALIBRATION_GAMES:
            continue
        candidate_config = _select_validated_spread_specialized_calibration(
            bucket_examples=phase_examples,
            feature_names=feature_names,
            means=means,
            scales=scales,
            weights=weights,
            bias=bias,
            spread_residual_scale=spread_residual_scale,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            default_market_blend_weight=default_market_blend_weight,
            default_max_market_probability_delta=default_max_market_probability_delta,
            blend_grid=(0.1, 0.2, 0.35, 0.5, 0.75, 1.0),
            max_delta_grid=(0.02, 0.04, 0.06, 0.08, 0.12),
            spread_line_residual_scales=spread_line_residual_scales,
            spread_season_phase_residual_scales=(spread_season_phase_residual_scales),
            spread_book_depth_residual_scales=(spread_book_depth_residual_scales),
        )
        if candidate_config is None:
            continue
        market_blend_weight, max_market_probability_delta = candidate_config
        phase_calibrations.append(
            SpreadSeasonPhaseCalibration(
                phase_key=phase_key,
                min_games_played_min=min_games_played_min,
                min_games_played_max=min_games_played_max,
                market_blend_weight=market_blend_weight,
                max_market_probability_delta=max_market_probability_delta,
            )
        )
    return tuple(phase_calibrations)


def _select_spread_line_residual_scales(
    *,
    examples: Sequence[ModelExample],
    predicted_residuals: Sequence[float],
    targets: Sequence[float],
) -> tuple[SpreadLineResidualScale, ...]:
    residual_scales: list[SpreadLineResidualScale] = []
    for bucket_key, abs_line_min, abs_line_max in SPREAD_LINE_BUCKETS:
        bucket_predictions: list[float] = []
        bucket_targets: list[float] = []
        for example, predicted_residual, target in zip(
            examples,
            predicted_residuals,
            targets,
            strict=True,
        ):
            if not _spread_abs_line_in_bucket(
                line_value=example.line_value,
                abs_line_min=abs_line_min,
                abs_line_max=abs_line_max,
            ):
                continue
            bucket_predictions.append(predicted_residual)
            bucket_targets.append(target)
        if len(bucket_predictions) < MIN_SPREAD_RESIDUAL_SCALE_BUCKET_GAMES:
            continue
        residual_scales.append(
            SpreadLineResidualScale(
                bucket_key=bucket_key,
                abs_line_min=abs_line_min,
                abs_line_max=abs_line_max,
                residual_scale=_estimate_spread_residual_scale(
                    predicted_residuals=bucket_predictions,
                    targets=bucket_targets,
                ),
            )
        )
    return tuple(residual_scales)


def _select_spread_season_phase_residual_scales(
    *,
    examples: Sequence[ModelExample],
    predicted_residuals: Sequence[float],
    targets: Sequence[float],
) -> tuple[SpreadSeasonPhaseResidualScale, ...]:
    residual_scales: list[SpreadSeasonPhaseResidualScale] = []
    for (
        phase_key,
        min_games_played_min,
        min_games_played_max,
    ) in SPREAD_SEASON_PHASE_BUCKETS:
        bucket_predictions: list[float] = []
        bucket_targets: list[float] = []
        for example, predicted_residual, target in zip(
            examples,
            predicted_residuals,
            targets,
            strict=True,
        ):
            if not _spread_min_games_played_in_bucket(
                example=example,
                min_games_played_min=min_games_played_min,
                min_games_played_max=min_games_played_max,
            ):
                continue
            bucket_predictions.append(predicted_residual)
            bucket_targets.append(target)
        if len(bucket_predictions) < MIN_SPREAD_RESIDUAL_SCALE_BUCKET_GAMES:
            continue
        residual_scales.append(
            SpreadSeasonPhaseResidualScale(
                phase_key=phase_key,
                min_games_played_min=min_games_played_min,
                min_games_played_max=min_games_played_max,
                residual_scale=_estimate_spread_residual_scale(
                    predicted_residuals=bucket_predictions,
                    targets=bucket_targets,
                ),
            )
        )
    return tuple(residual_scales)


def _select_spread_book_depth_residual_scales(
    *,
    examples: Sequence[ModelExample],
    predicted_residuals: Sequence[float],
    targets: Sequence[float],
) -> tuple[SpreadBookDepthResidualScale, ...]:
    residual_scales: list[SpreadBookDepthResidualScale] = []
    for bucket_key, min_books, max_books in SPREAD_BOOK_DEPTH_BUCKETS:
        bucket_predictions: list[float] = []
        bucket_targets: list[float] = []
        for example, predicted_residual, target in zip(
            examples,
            predicted_residuals,
            targets,
            strict=True,
        ):
            if not _spread_book_count_in_bucket(
                book_count=example.features.get("spread_books"),
                min_books=min_books,
                max_books=max_books,
            ):
                continue
            bucket_predictions.append(predicted_residual)
            bucket_targets.append(target)
        if len(bucket_predictions) < MIN_SPREAD_RESIDUAL_SCALE_BUCKET_GAMES:
            continue
        residual_scales.append(
            SpreadBookDepthResidualScale(
                bucket_key=bucket_key,
                min_books=min_books,
                max_books=max_books,
                residual_scale=_estimate_spread_residual_scale(
                    predicted_residuals=bucket_predictions,
                    targets=bucket_targets,
                ),
            )
        )
    return tuple(residual_scales)


def _select_market_calibration_config(
    *,
    fitted: RawProbabilityModel,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
    blend_grid: Sequence[float],
    max_delta_grid: Sequence[float],
) -> tuple[float, float]:
    if not calibration_examples:
        return default_market_blend_weight, default_max_market_probability_delta

    feature_rows = feature_matrix(calibration_examples, feature_names)
    raw_probabilities = _score_feature_rows_with_model(
        feature_rows=feature_rows,
        model_family=fitted.model_family,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        serialized_model_base64=fitted.serialized_model_base64,
    )
    return _select_calibration_config_from_raw_probabilities(
        raw_probabilities=raw_probabilities,
        calibration_examples=calibration_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        default_market_blend_weight=default_market_blend_weight,
        default_max_market_probability_delta=default_max_market_probability_delta,
        blend_grid=blend_grid,
        max_delta_grid=max_delta_grid,
    )


def _select_calibration_config_from_raw_probabilities(
    *,
    raw_probabilities: Sequence[float],
    calibration_examples: list[ModelExample],
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
    blend_grid: Sequence[float],
    max_delta_grid: Sequence[float],
) -> tuple[float, float]:
    labels = labels_for_examples(calibration_examples)
    if not labels:
        return default_market_blend_weight, default_max_market_probability_delta
    best_config = (
        default_market_blend_weight,
        default_max_market_probability_delta,
    )
    best_log_loss = float("inf")
    best_brier = float("inf")

    for market_blend_weight in blend_grid:
        for max_market_probability_delta in max_delta_grid:
            probabilities = calibrate_probabilities(
                raw_probabilities=raw_probabilities,
                examples=calibration_examples,
                platt_scale=platt_scale,
                platt_bias=platt_bias,
                market_blend_weight=market_blend_weight,
                max_market_probability_delta=max_market_probability_delta,
            )
            log_loss = _log_loss(probabilities, labels)
            brier_score = _brier_score(probabilities, labels)
            if log_loss < best_log_loss - 1e-9 or (
                abs(log_loss - best_log_loss) <= 1e-9
                and brier_score < best_brier - 1e-9
            ):
                best_config = (
                    market_blend_weight,
                    max_market_probability_delta,
                )
                best_log_loss = log_loss
                best_brier = brier_score
    return best_config


def _select_moneyline_segment_calibrations(
    *,
    fitted: RawProbabilityModel,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    platt_scale: float,
    platt_bias: float,
    default_market_blend_weight: float,
    default_max_market_probability_delta: float,
) -> tuple[MoneylineSegmentCalibration, ...]:
    if not calibration_examples:
        return ()

    segment_calibrations: list[MoneylineSegmentCalibration] = []
    for segment_key in MONEYLINE_SEGMENT_KEYS:
        segment_examples = [
            example
            for example in calibration_examples
            if _moneyline_segment_key(example.market_price) == segment_key
        ]
        if len(segment_examples) < MONEYLINE_SEGMENT_MIN_GAMES:
            market_blend_weight = default_market_blend_weight
            max_market_probability_delta = default_max_market_probability_delta
        else:
            market_blend_weight, max_market_probability_delta = (
                _select_market_calibration_config(
                    fitted=fitted,
                    feature_names=feature_names,
                    calibration_examples=segment_examples,
                    platt_scale=platt_scale,
                    platt_bias=platt_bias,
                    default_market_blend_weight=default_market_blend_weight,
                    default_max_market_probability_delta=default_max_market_probability_delta,
                    blend_grid=(0.0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0),
                    max_delta_grid=(0.0, 0.01, 0.02, 0.04, 0.06, 0.08, 0.12),
                )
            )
        segment_calibrations.append(
            MoneylineSegmentCalibration(
                segment_key=segment_key,
                market_blend_weight=market_blend_weight,
                max_market_probability_delta=max_market_probability_delta,
            )
        )
    return tuple(segment_calibrations)


def _moneyline_segment_calibration_for_example(
    *,
    example: ModelExample,
    segment_calibrations: Sequence[MoneylineSegmentCalibration],
) -> MoneylineSegmentCalibration | None:
    segment_key = _moneyline_segment_key(example.market_price)
    if segment_key is None:
        return None
    for segment_calibration in segment_calibrations:
        if segment_calibration.segment_key == segment_key:
            return segment_calibration
    return None


def _spread_line_calibration_for_example(
    *,
    example: ModelExample,
    line_calibrations: Sequence[SpreadLineCalibration],
) -> SpreadLineCalibration | None:
    for line_calibration in line_calibrations:
        if _spread_abs_line_in_bucket(
            line_value=example.line_value,
            abs_line_min=line_calibration.abs_line_min,
            abs_line_max=line_calibration.abs_line_max,
        ):
            return line_calibration
    return None


def _spread_conference_calibration_for_example(
    *,
    example: ModelExample,
    conference_calibrations: Sequence[SpreadConferenceCalibration],
) -> SpreadConferenceCalibration | None:
    conference_key = example.team_conference_key
    if conference_key is None:
        return None
    for conference_calibration in conference_calibrations:
        if conference_calibration.conference_key == conference_key:
            return conference_calibration
    return None


def _spread_season_phase_calibration_for_example(
    *,
    example: ModelExample,
    phase_calibrations: Sequence[SpreadSeasonPhaseCalibration],
) -> SpreadSeasonPhaseCalibration | None:
    for phase_calibration in phase_calibrations:
        if _spread_min_games_played_in_bucket(
            example=example,
            min_games_played_min=phase_calibration.min_games_played_min,
            min_games_played_max=phase_calibration.min_games_played_max,
        ):
            return phase_calibration
    return None


def _effective_spread_residual_scale(
    *,
    example: ModelExample,
    base_residual_scale: float,
    spread_line_residual_scales: Sequence[SpreadLineResidualScale] = (),
    spread_season_phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale] = (),
    spread_book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale] = (),
) -> float:
    matching_scales = [base_residual_scale]
    line_residual_scale = _spread_line_residual_scale_for_example(
        example=example,
        line_residual_scales=spread_line_residual_scales,
    )
    if line_residual_scale is not None:
        matching_scales.append(line_residual_scale.residual_scale)
    season_phase_residual_scale = _spread_season_phase_residual_scale_for_example(
        example=example,
        phase_residual_scales=spread_season_phase_residual_scales,
    )
    if season_phase_residual_scale is not None:
        matching_scales.append(season_phase_residual_scale.residual_scale)
    book_depth_residual_scale = _spread_book_depth_residual_scale_for_example(
        example=example,
        book_depth_residual_scales=spread_book_depth_residual_scales,
    )
    if book_depth_residual_scale is not None:
        matching_scales.append(book_depth_residual_scale.residual_scale)
    return max(
        MIN_SPREAD_RESIDUAL_SCALE,
        sum(matching_scales) / float(len(matching_scales)),
    )


def _spread_line_residual_scale_for_example(
    *,
    example: ModelExample,
    line_residual_scales: Sequence[SpreadLineResidualScale],
) -> SpreadLineResidualScale | None:
    for line_residual_scale in line_residual_scales:
        if _spread_abs_line_in_bucket(
            line_value=example.line_value,
            abs_line_min=line_residual_scale.abs_line_min,
            abs_line_max=line_residual_scale.abs_line_max,
        ):
            return line_residual_scale
    return None


def _spread_season_phase_residual_scale_for_example(
    *,
    example: ModelExample,
    phase_residual_scales: Sequence[SpreadSeasonPhaseResidualScale],
) -> SpreadSeasonPhaseResidualScale | None:
    for phase_residual_scale in phase_residual_scales:
        if _spread_min_games_played_in_bucket(
            example=example,
            min_games_played_min=phase_residual_scale.min_games_played_min,
            min_games_played_max=phase_residual_scale.min_games_played_max,
        ):
            return phase_residual_scale
    return None


def _spread_book_depth_residual_scale_for_example(
    *,
    example: ModelExample,
    book_depth_residual_scales: Sequence[SpreadBookDepthResidualScale],
) -> SpreadBookDepthResidualScale | None:
    for book_depth_residual_scale in book_depth_residual_scales:
        if _spread_book_count_in_bucket(
            book_count=example.features.get("spread_books"),
            min_books=book_depth_residual_scale.min_books,
            max_books=book_depth_residual_scale.max_books,
        ):
            return book_depth_residual_scale
    return None


def _spread_abs_line_in_bucket(
    *,
    line_value: float | None,
    abs_line_min: float,
    abs_line_max: float | None,
) -> bool:
    if line_value is None:
        return False
    abs_line_value = abs(line_value)
    if abs_line_value < abs_line_min:
        return False
    return abs_line_max is None or abs_line_value <= abs_line_max


def _spread_book_count_in_bucket(
    *,
    book_count: float | None,
    min_books: int,
    max_books: int | None,
) -> bool:
    if book_count is None:
        return False
    if book_count < float(min_books):
        return False
    return max_books is None or book_count <= float(max_books)


def _spread_min_games_played_in_bucket(
    *,
    example: ModelExample,
    min_games_played_min: int,
    min_games_played_max: int | None,
) -> bool:
    observed_min_games_played = round(
        example.features.get("min_season_games_played", 0.0)
    )
    if observed_min_games_played < min_games_played_min:
        return False
    return (
        min_games_played_max is None
        or observed_min_games_played <= min_games_played_max
    )


def _moneyline_band_model_for_example(
    *,
    band_models: Sequence[MoneylineBandModel],
    example: ModelExample,
) -> MoneylineBandModel | None:
    market_price = example.market_price
    if example.market != "moneyline" or market_price is None:
        return None
    segment_key = _moneyline_segment_key(market_price)
    for band_model in band_models:
        if band_model.band_key in MONEYLINE_SEGMENT_KEYS:
            if band_model.band_key == segment_key:
                return band_model
            continue
        if band_model.price_min is not None and market_price < band_model.price_min:
            continue
        if band_model.price_max is not None and market_price > band_model.price_max:
            continue
        return band_model
    return None


def _moneyline_segment_key(market_price: float | None) -> str | None:
    if market_price is None:
        return None
    if market_price <= -200.0:
        return "heavy_favorite"
    if market_price <= -125.0:
        return "favorite"
    if market_price <= 125.0:
        return "balanced"
    if market_price <= 250.0:
        return "short_dog"
    return "longshot"


def fit_platt_scaling(
    *,
    raw_probabilities: Sequence[float],
    labels: Sequence[int],
) -> tuple[float, float]:
    """Fit a one-feature logistic calibration layer over raw model probabilities."""
    if len(raw_probabilities) != len(labels):
        raise ValueError("Raw probability count must match label count")
    if not raw_probabilities or len(set(labels)) < 2:
        return DEFAULT_PLATT_SCALE, DEFAULT_PLATT_BIAS

    logits = [_logit(probability) for probability in raw_probabilities]
    sample_count = float(len(logits))
    scale = DEFAULT_PLATT_SCALE
    bias = DEFAULT_PLATT_BIAS

    for _ in range(PLATT_EPOCHS):
        scale_gradient = PLATT_L2_PENALTY * (scale - DEFAULT_PLATT_SCALE)
        bias_gradient = PLATT_L2_PENALTY * (bias - DEFAULT_PLATT_BIAS)
        for logit_value, label in zip(logits, labels, strict=True):
            probability = _sigmoid((scale * logit_value) + bias)
            error = probability - float(label)
            scale_gradient += error * logit_value / sample_count
            bias_gradient += error / sample_count
        scale -= PLATT_LEARNING_RATE * scale_gradient
        bias -= PLATT_LEARNING_RATE * bias_gradient

    return scale, bias


def apply_platt_scaling(
    *,
    raw_probabilities: Sequence[float],
    platt_scale: float,
    platt_bias: float,
) -> list[float]:
    """Apply stored Platt scaling parameters to raw model probabilities."""
    if (
        abs(platt_scale - DEFAULT_PLATT_SCALE) <= 1e-9
        and abs(platt_bias - DEFAULT_PLATT_BIAS) <= 1e-9
    ):
        return [_clip_probability(probability) for probability in raw_probabilities]
    return [
        _clip_probability(_sigmoid((platt_scale * _logit(probability)) + platt_bias))
        for probability in raw_probabilities
    ]


def _compute_standardization(
    feature_rows: list[list[float]],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    feature_count = len(feature_rows[0])
    means: list[float] = []
    scales: list[float] = []
    sample_count = float(len(feature_rows))

    for feature_index in range(feature_count):
        values = [row[feature_index] for row in feature_rows]
        mean_value = sum(values) / sample_count
        variance = sum((value - mean_value) ** 2 for value in values) / sample_count
        scale_value = variance**0.5
        means.append(mean_value)
        scales.append(scale_value if scale_value > 0 else 1.0)

    return tuple(means), tuple(scales)


def _standardize_row(
    row: Sequence[float],
    *,
    means: Sequence[float],
    scales: Sequence[float],
) -> list[float]:
    return [
        (float(value) - float(mean_value)) / float(scale_value)
        for value, mean_value, scale_value in zip(row, means, scales, strict=True)
    ]


def _linear_score(
    row: Sequence[float],
    weights: Sequence[float],
    bias: float,
) -> float:
    return bias + sum(
        float(value) * float(weight) for value, weight in zip(row, weights, strict=True)
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        negative_exponent = exp(-value)
        return 1.0 / (1.0 + negative_exponent)
    positive_exponent = exp(value)
    return positive_exponent / (1.0 + positive_exponent)


def _logit(probability: float) -> float:
    clipped_probability = _clip_probability(probability)
    return log(clipped_probability / (1.0 - clipped_probability))


def _clip_probability(probability: float) -> float:
    return min(max(probability, 1e-6), 1.0 - 1e-6)


def _estimate_spread_residual_scale(
    *,
    predicted_residuals: Sequence[float],
    targets: Sequence[float],
) -> float:
    if len(predicted_residuals) != len(targets):
        raise ValueError("Predicted residual count must match target count")
    if not predicted_residuals:
        return MIN_SPREAD_RESIDUAL_SCALE
    mean_squared_error = sum(
        (target - prediction) ** 2
        for prediction, target in zip(predicted_residuals, targets, strict=True)
    ) / len(predicted_residuals)
    error_stddev = sqrt(mean_squared_error)
    return max(MIN_SPREAD_RESIDUAL_SCALE, error_stddev * LOGISTIC_STDDEV_TO_SCALE)


def _spread_margin_to_probability(
    *,
    predicted_margin_residual: float,
    spread_residual_scale: float,
) -> float:
    effective_scale = max(spread_residual_scale, MIN_SPREAD_RESIDUAL_SCALE)
    return _clip_probability(_sigmoid(predicted_margin_residual / effective_scale))


def _log_loss(probabilities: Sequence[float], labels: Sequence[int]) -> float:
    if not probabilities:
        return 0.0
    losses = [
        -(
            float(label) * log(_clip_probability(probability))
            + (1.0 - float(label)) * log(_clip_probability(1.0 - probability))
        )
        for probability, label in zip(probabilities, labels, strict=True)
    ]
    return sum(losses) / len(losses)


def _brier_score(probabilities: Sequence[float], labels: Sequence[int]) -> float:
    if not probabilities:
        return 0.0
    squared_errors = [
        (probability - float(label)) ** 2
        for probability, label in zip(probabilities, labels, strict=True)
    ]
    return sum(squared_errors) / len(squared_errors)


def _accuracy(probabilities: Sequence[float], labels: Sequence[int]) -> float:
    if not probabilities:
        return 0.0
    correct = sum(
        1
        for probability, label in zip(probabilities, labels, strict=True)
        if (probability >= 0.5) == bool(label)
    )
    return correct / len(labels)
