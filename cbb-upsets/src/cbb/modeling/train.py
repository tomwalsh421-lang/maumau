"""Training workflow for baseline betting models."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from math import exp, log
from pathlib import Path

from cbb.modeling.artifacts import (
    DEFAULT_ARTIFACT_NAME,
    ModelArtifact,
    ModelMarket,
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
    training_examples_only,
)

DEFAULT_MODEL_SEASONS_BACK = 3
DEFAULT_LEARNING_RATE = 0.05
DEFAULT_EPOCHS = 100
DEFAULT_L2_PENALTY = 0.001
DEFAULT_MIN_EXAMPLES = 50
DEFAULT_PLATT_SCALE = 1.0
DEFAULT_PLATT_BIAS = 0.0
DEFAULT_MARKET_BLEND_WEIGHT = 0.25
DEFAULT_MAX_MARKET_PROBABILITY_DELTA = 0.05
CALIBRATION_HOLDOUT_FRACTION = 0.20
MIN_CALIBRATION_GAMES = 25
PLATT_LEARNING_RATE = 0.05
PLATT_EPOCHS = 250
PLATT_L2_PENALTY = 0.01
MARKET_CALIBRATION_VALIDATION_FRACTION = 0.50
MIN_MARKET_CALIBRATION_GAMES = 10


@dataclass(frozen=True)
class LogisticRegressionConfig:
    """Hyperparameters for the baseline logistic-regression trainer."""

    learning_rate: float = DEFAULT_LEARNING_RATE
    epochs: int = DEFAULT_EPOCHS
    l2_penalty: float = DEFAULT_L2_PENALTY
    min_examples: int = DEFAULT_MIN_EXAMPLES


@dataclass(frozen=True)
class TrainingOptions:
    """Options for training one betting model artifact."""

    market: ModelMarket
    seasons_back: int = DEFAULT_MODEL_SEASONS_BACK
    max_season: int | None = None
    artifact_name: str = DEFAULT_ARTIFACT_NAME
    database_url: str | None = None
    artifacts_dir: Path | None = None
    config: LogisticRegressionConfig = field(
        default_factory=LogisticRegressionConfig
    )


@dataclass(frozen=True)
class TrainingSummary:
    """Reported result after training and saving one artifact."""

    market: ModelMarket
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
        config=options.config,
    )
    artifact_path = save_artifact(
        artifact,
        artifact_name=options.artifact_name,
        artifacts_dir=options.artifacts_dir,
    )
    return TrainingSummary(
        market=artifact.market,
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
    config: LogisticRegressionConfig,
) -> ModelArtifact:
    """Fit one artifact from in-memory completed game records."""
    target_seasons = set(seasons)
    feature_names = feature_names_for_market(market)
    all_examples = build_training_examples(
        game_records=game_records,
        market=market,
        target_seasons=target_seasons,
    )
    trainable_examples = _deployable_training_examples(all_examples)
    if len(trainable_examples) < config.min_examples:
        raise ValueError(
            f"Not enough {market} training examples: "
            f"need at least {config.min_examples}, found {len(trainable_examples)}"
        )

    provisional_training_examples, calibration_examples = (
        _split_examples_for_calibration(trainable_examples)
    )
    provisional_feature_rows = feature_matrix(
        provisional_training_examples,
        feature_names,
    )
    provisional_labels = labels_for_examples(provisional_training_examples)
    provisional_fitted = fit_logistic_regression(
        feature_rows=provisional_feature_rows,
        labels=provisional_labels,
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
    market_blend_weight, max_market_probability_delta = (
        _select_market_calibration(
            fitted=provisional_fitted,
            feature_names=feature_names,
            calibration_examples=market_calibration_examples,
            platt_scale=platt_scale,
            platt_bias=platt_bias,
        )
    )

    feature_rows = feature_matrix(trainable_examples, feature_names)
    labels = labels_for_examples(trainable_examples)
    fitted = fit_logistic_regression(
        feature_rows=feature_rows,
        labels=labels,
        config=config,
    )
    probabilities = calibrate_probabilities(
        raw_probabilities=score_feature_rows(
            feature_rows=feature_rows,
            means=fitted.means,
            scales=fitted.scales,
            weights=fitted.weights,
            bias=fitted.bias,
        ),
        examples=trainable_examples,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
    )
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
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
        metrics=metrics,
        platt_scale=platt_scale,
        platt_bias=platt_bias,
        market_blend_weight=market_blend_weight,
        max_market_probability_delta=max_market_probability_delta,
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
            weights[feature_index] -= config.learning_rate * weight_gradients[
                feature_index
            ]
        bias -= config.learning_rate * bias_gradient

    return FittedParameters(
        means=means,
        scales=scales,
        weights=tuple(weights),
        bias=bias,
    )


def score_examples(
    *,
    artifact: ModelArtifact,
    examples: list[ModelExample],
) -> list[float]:
    """Score examples with a stored artifact and return win probabilities."""
    feature_rows = feature_matrix(examples, artifact.feature_names)
    raw_probabilities = score_feature_rows(
        feature_rows=feature_rows,
        means=artifact.means,
        scales=artifact.scales,
        weights=artifact.weights,
        bias=artifact.bias,
    )
    return calibrate_probabilities(
        raw_probabilities=raw_probabilities,
        examples=examples,
        platt_scale=artifact.platt_scale,
        platt_bias=artifact.platt_bias,
        market_blend_weight=artifact.market_blend_weight,
        max_market_probability_delta=artifact.max_market_probability_delta,
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


def calibrate_probabilities(
    *,
    raw_probabilities: Sequence[float],
    examples: Sequence[ModelExample],
    platt_scale: float,
    platt_bias: float,
    market_blend_weight: float,
    max_market_probability_delta: float,
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

        blended_probability = (
            market_blend_weight * probability
            + (1.0 - market_blend_weight) * market_probability
        )
        lower_bound = market_probability - max_market_probability_delta
        upper_bound = market_probability + max_market_probability_delta
        stabilized_probabilities.append(
            _clip_probability(
                min(max(blended_probability, lower_bound), upper_bound)
            )
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
) -> list[ModelExample]:
    return [
        example
        for example in training_examples_only(examples)
        if (
            example.market_price is not None
            and example.market_implied_probability is not None
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
    fitted: FittedParameters,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
) -> tuple[float, float]:
    if not calibration_examples:
        return DEFAULT_PLATT_SCALE, DEFAULT_PLATT_BIAS

    labels = labels_for_examples(calibration_examples)
    if len(set(labels)) < 2:
        return DEFAULT_PLATT_SCALE, DEFAULT_PLATT_BIAS

    feature_rows = feature_matrix(calibration_examples, feature_names)
    raw_probabilities = score_feature_rows(
        feature_rows=feature_rows,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
    )
    return fit_platt_scaling(
        raw_probabilities=raw_probabilities,
        labels=labels,
    )


def _select_market_calibration(
    *,
    fitted: FittedParameters,
    feature_names: tuple[str, ...],
    calibration_examples: list[ModelExample],
    platt_scale: float,
    platt_bias: float,
) -> tuple[float, float]:
    if not calibration_examples:
        return DEFAULT_MARKET_BLEND_WEIGHT, DEFAULT_MAX_MARKET_PROBABILITY_DELTA

    feature_rows = feature_matrix(calibration_examples, feature_names)
    labels = labels_for_examples(calibration_examples)
    raw_probabilities = score_feature_rows(
        feature_rows=feature_rows,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
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
            if (
                log_loss < best_log_loss - 1e-9
                or (
                    abs(log_loss - best_log_loss) <= 1e-9
                    and brier_score < best_brier - 1e-9
                )
            ):
                best_config = (
                    market_blend_weight,
                    max_market_probability_delta,
                )
                best_log_loss = log_loss
                best_brier = brier_score
    return best_config


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
        float(value) * float(weight)
        for value, weight in zip(row, weights, strict=True)
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
