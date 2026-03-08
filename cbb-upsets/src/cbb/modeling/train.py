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
    trainable_examples = training_examples_only(all_examples)
    if len(trainable_examples) < config.min_examples:
        raise ValueError(
            f"Not enough {market} training examples: "
            f"need at least {config.min_examples}, found {len(trainable_examples)}"
        )

    feature_rows = feature_matrix(trainable_examples, feature_names)
    labels = labels_for_examples(trainable_examples)
    fitted = fit_logistic_regression(
        feature_rows=feature_rows,
        labels=labels,
        config=config,
    )
    probabilities = score_feature_rows(
        feature_rows=feature_rows,
        means=fitted.means,
        scales=fitted.scales,
        weights=fitted.weights,
        bias=fitted.bias,
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
    return score_feature_rows(
        feature_rows=feature_rows,
        means=artifact.means,
        scales=artifact.scales,
        weights=artifact.weights,
        bias=artifact.bias,
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
