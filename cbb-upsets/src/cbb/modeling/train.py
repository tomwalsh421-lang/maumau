"""Training workflow for betting models."""

from __future__ import annotations

import base64
import pickle
from collections.abc import Sequence
from dataclasses import dataclass, field
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
    SpreadModelingMode,
    TrainingMetrics,
    current_timestamp,
    save_artifact,
)
from cbb.modeling.dataset import (
    GameOddsRecord,
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
    training_examples_only,
)
from cbb.modeling.policy import BetPolicy

DEFAULT_MODEL_SEASONS_BACK = 3
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
MIN_MARKET_CALIBRATION_GAMES = 10
MONEYLINE_CORE_PRICE_MIN = BetPolicy().min_moneyline_price
MONEYLINE_CORE_PRICE_MAX = 125.0
MONEYLINE_SHORT_DOG_PRICE_MIN = 126.0
MONEYLINE_SHORT_DOG_PRICE_MAX = 175.0
DEFAULT_MONEYLINE_TRAIN_MIN_PRICE = MONEYLINE_CORE_PRICE_MIN
DEFAULT_MONEYLINE_TRAIN_MAX_PRICE = MONEYLINE_SHORT_DOG_PRICE_MAX
MONEYLINE_DISPATCH_BANDS = (
    ("core", MONEYLINE_CORE_PRICE_MIN, MONEYLINE_CORE_PRICE_MAX),
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
    spread_modeling_mode: SpreadModelingMode = "cover_classifier"
    spread_residual_scale: float = 1.0
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
    moneyline_segment_calibrations: tuple[MoneylineSegmentCalibration, ...] = ()
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
                moneyline_price_min=effective_moneyline_price_min,
                moneyline_price_max=effective_moneyline_price_max,
                moneyline_band_models=moneyline_band_models,
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
            moneyline_segment_calibrations=moneyline_segment_calibrations,
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
        moneyline_price_min=effective_moneyline_price_min,
        moneyline_price_max=effective_moneyline_price_max,
        moneyline_band_models=moneyline_band_models,
        moneyline_segment_calibrations=moneyline_segment_calibrations,
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
                weight_gradients[feature_index] += (
                    2.0 * error * value / sample_count
                )
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
            platt_scale=platt_scale,
            platt_bias=platt_bias,
        )
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
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
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
    return RawSpreadMarginModel(
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        spread_residual_scale=_estimate_spread_residual_scale(
            predicted_residuals=predicted_residuals,
            targets=targets,
        ),
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
            spread_residual_scale=spread_residual_scale,
        )
        for predicted_residual in predicted_residuals
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
            platt_scale=artifact.platt_scale,
            platt_bias=artifact.platt_bias,
            market_blend_weight=artifact.market_blend_weight,
            max_market_probability_delta=artifact.max_market_probability_delta,
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
        moneyline_segment_calibrations=artifact.moneyline_segment_calibrations,
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
    moneyline_segment_calibrations: Sequence[MoneylineSegmentCalibration] = (),
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
            platt_scale=platt_scale,
            platt_bias=platt_bias,
            market_blend_weight=market_blend_weight,
            max_market_probability_delta=max_market_probability_delta,
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
) -> list[float]:
    feature_rows = feature_matrix(list(examples), feature_names)
    predicted_residuals = score_linear_feature_rows(
        feature_rows=feature_rows,
        means=means,
        scales=scales,
        weights=weights,
        bias=bias,
    )
    raw_probabilities = [
        _spread_margin_to_probability(
            predicted_margin_residual=predicted_residual,
            spread_residual_scale=spread_residual_scale,
        )
        for predicted_residual in predicted_residuals
    ]
    return calibrate_probabilities(
        raw_probabilities=raw_probabilities,
        examples=examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
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
    )
    best_config = (
        DEFAULT_MARKET_BLEND_WEIGHT,
        DEFAULT_MAX_MARKET_PROBABILITY_DELTA,
    )
    best_log_loss = float("inf")
    best_brier = float("inf")

    for market_blend_weight in (0.0, 0.1, 0.2, 0.35, 0.5, 0.75, 1.0):
        for max_market_probability_delta in (0.02, 0.04, 0.06, 0.08, 0.12, 0.20):
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
    labels = labels_for_examples(calibration_examples)
    raw_probabilities = _score_feature_rows_with_model(
        feature_rows=feature_rows,
        model_family=fitted.model_family,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        serialized_model_base64=fitted.serialized_model_base64,
    )
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


def _moneyline_band_model_for_example(
    *,
    band_models: Sequence[MoneylineBandModel],
    example: ModelExample,
) -> MoneylineBandModel | None:
    market_price = example.market_price
    if example.market != "moneyline" or market_price is None:
        return None
    for band_model in band_models:
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
