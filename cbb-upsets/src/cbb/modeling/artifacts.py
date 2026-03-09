"""Artifact storage for trained betting models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import orjson

from cbb.db import REPO_ROOT

ModelMarket = Literal["moneyline", "spread"]
StrategyMarket = Literal["moneyline", "spread", "best"]
ModelFamily = Literal["logistic", "hist_gradient_boosting"]
SpreadModelingMode = Literal["cover_classifier", "margin_regression"]
DEFAULT_ARTIFACT_NAME = "latest"
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "models"


@dataclass(frozen=True)
class TrainingMetrics:
    """Summary metrics for one trained model artifact."""

    examples: int
    priced_examples: int
    training_examples: int
    feature_names: tuple[str, ...]
    log_loss: float
    brier_score: float
    accuracy: float
    start_season: int
    end_season: int
    trained_at: str


@dataclass(frozen=True)
class MoneylineSegmentCalibration:
    """Calibration controls for one moneyline price segment."""

    segment_key: str
    market_blend_weight: float
    max_market_probability_delta: float


@dataclass(frozen=True)
class SpreadLineCalibration:
    """Calibration controls for one spread absolute-line bucket."""

    bucket_key: str
    abs_line_min: float
    abs_line_max: float | None
    market_blend_weight: float
    max_market_probability_delta: float


@dataclass(frozen=True)
class MoneylineBandModel:
    """One specialized moneyline model used by the dispatcher."""

    band_key: str
    price_min: float | None
    price_max: float | None
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    platt_scale: float = 1.0
    platt_bias: float = 0.0
    market_blend_weight: float = 1.0
    max_market_probability_delta: float = 1.0


@dataclass(frozen=True)
class ModelArtifact:
    """Serialized betting-model artifact."""

    market: ModelMarket
    model_family: ModelFamily
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    metrics: TrainingMetrics
    platt_scale: float = 1.0
    platt_bias: float = 0.0
    market_blend_weight: float = 1.0
    max_market_probability_delta: float = 1.0
    spread_modeling_mode: SpreadModelingMode = "cover_classifier"
    spread_residual_scale: float = 1.0
    moneyline_price_min: float | None = None
    moneyline_price_max: float | None = None
    moneyline_band_models: tuple[MoneylineBandModel, ...] = ()
    moneyline_segment_calibrations: tuple[MoneylineSegmentCalibration, ...] = ()
    spread_line_calibrations: tuple[SpreadLineCalibration, ...] = ()
    serialized_model_base64: str | None = None


def artifact_path(
    *,
    market: ModelMarket,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    artifacts_dir: Path | None = None,
) -> Path:
    """Return the path used for a model artifact.

    Args:
        market: Model market identifier.
        artifact_name: User-facing artifact name.
        artifacts_dir: Optional artifact directory override.

    Returns:
        The fully resolved JSON artifact path.
    """
    resolved_dir = (artifacts_dir or ARTIFACTS_DIR).resolve()
    return resolved_dir / f"{market}_{artifact_name}.json"


def save_artifact(
    artifact: ModelArtifact,
    *,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    artifacts_dir: Path | None = None,
) -> Path:
    """Persist one model artifact to disk.

    Args:
        artifact: Trained artifact to serialize.
        artifact_name: User-facing artifact name.
        artifacts_dir: Optional artifact directory override.

    Returns:
        The path that was written.
    """
    output_path = artifact_path(
        market=artifact.market,
        artifact_name=artifact_name,
        artifacts_dir=artifacts_dir,
    )
    payload = orjson.dumps(asdict(artifact), option=orjson.OPT_INDENT_2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    if artifact_name != DEFAULT_ARTIFACT_NAME:
        latest_path = artifact_path(
            market=artifact.market,
            artifact_name=DEFAULT_ARTIFACT_NAME,
            artifacts_dir=artifacts_dir,
        )
        latest_path.write_bytes(payload)
    return output_path


def load_artifact(
    *,
    market: ModelMarket,
    artifact_name: str = DEFAULT_ARTIFACT_NAME,
    artifacts_dir: Path | None = None,
) -> ModelArtifact:
    """Load one stored model artifact from disk.

    Args:
        market: Model market identifier.
        artifact_name: User-facing artifact name.
        artifacts_dir: Optional artifact directory override.

    Returns:
        The deserialized model artifact.

    Raises:
        FileNotFoundError: If the artifact does not exist.
    """
    input_path = artifact_path(
        market=market,
        artifact_name=artifact_name,
        artifacts_dir=artifacts_dir,
    )
    payload = orjson.loads(input_path.read_bytes())
    metrics_payload = payload["metrics"]
    return ModelArtifact(
        market=payload["market"],
        model_family=payload.get("model_family", "logistic"),
        feature_names=tuple(payload["feature_names"]),
        means=tuple(float(value) for value in payload["means"]),
        scales=tuple(float(value) for value in payload["scales"]),
        weights=tuple(float(value) for value in payload["weights"]),
        bias=float(payload["bias"]),
        platt_scale=float(payload.get("platt_scale", 1.0)),
        platt_bias=float(payload.get("platt_bias", 0.0)),
        market_blend_weight=float(payload.get("market_blend_weight", 1.0)),
        max_market_probability_delta=float(
            payload.get("max_market_probability_delta", 1.0)
        ),
        spread_modeling_mode=_load_spread_modeling_mode(payload),
        spread_residual_scale=float(payload.get("spread_residual_scale", 1.0)),
        moneyline_price_min=(
            float(payload["moneyline_price_min"])
            if payload.get("moneyline_price_min") is not None
            else None
        ),
        moneyline_price_max=(
            float(payload["moneyline_price_max"])
            if payload.get("moneyline_price_max") is not None
            else None
        ),
        moneyline_band_models=tuple(
            MoneylineBandModel(
                band_key=str(band_payload["band_key"]),
                price_min=(
                    float(band_payload["price_min"])
                    if band_payload.get("price_min") is not None
                    else None
                ),
                price_max=(
                    float(band_payload["price_max"])
                    if band_payload.get("price_max") is not None
                    else None
                ),
                means=tuple(float(value) for value in band_payload["means"]),
                scales=tuple(float(value) for value in band_payload["scales"]),
                weights=tuple(float(value) for value in band_payload["weights"]),
                bias=float(band_payload["bias"]),
                platt_scale=float(band_payload.get("platt_scale", 1.0)),
                platt_bias=float(band_payload.get("platt_bias", 0.0)),
                market_blend_weight=float(
                    band_payload.get("market_blend_weight", 1.0)
                ),
                max_market_probability_delta=float(
                    band_payload.get("max_market_probability_delta", 1.0)
                ),
            )
            for band_payload in payload.get("moneyline_band_models", [])
        ),
        moneyline_segment_calibrations=tuple(
            MoneylineSegmentCalibration(
                segment_key=str(segment_payload["segment_key"]),
                market_blend_weight=float(segment_payload["market_blend_weight"]),
                max_market_probability_delta=float(
                    segment_payload["max_market_probability_delta"]
                ),
            )
            for segment_payload in payload.get("moneyline_segment_calibrations", [])
        ),
        spread_line_calibrations=tuple(
            SpreadLineCalibration(
                bucket_key=str(bucket_payload["bucket_key"]),
                abs_line_min=float(bucket_payload["abs_line_min"]),
                abs_line_max=(
                    float(bucket_payload["abs_line_max"])
                    if bucket_payload.get("abs_line_max") is not None
                    else None
                ),
                market_blend_weight=float(bucket_payload["market_blend_weight"]),
                max_market_probability_delta=float(
                    bucket_payload["max_market_probability_delta"]
                ),
            )
            for bucket_payload in payload.get("spread_line_calibrations", [])
        ),
        serialized_model_base64=(
            str(payload["serialized_model_base64"])
            if payload.get("serialized_model_base64") is not None
            else None
        ),
        metrics=TrainingMetrics(
            examples=int(metrics_payload["examples"]),
            priced_examples=int(metrics_payload["priced_examples"]),
            training_examples=int(metrics_payload["training_examples"]),
            feature_names=tuple(metrics_payload["feature_names"]),
            log_loss=float(metrics_payload["log_loss"]),
            brier_score=float(metrics_payload["brier_score"]),
            accuracy=float(metrics_payload["accuracy"]),
            start_season=int(metrics_payload["start_season"]),
            end_season=int(metrics_payload["end_season"]),
            trained_at=str(metrics_payload["trained_at"]),
        ),
    )


def _load_spread_modeling_mode(payload: dict[str, object]) -> SpreadModelingMode:
    explicit_mode = payload.get("spread_modeling_mode")
    if explicit_mode in {"cover_classifier", "margin_regression"}:
        return cast(SpreadModelingMode, explicit_mode)

    if (
        payload.get("market") == "spread"
        and payload.get("model_family", "logistic") != "hist_gradient_boosting"
        and "spread_residual_scale" in payload
    ):
        return "margin_regression"
    return "cover_classifier"


def current_timestamp() -> str:
    """Return the current UTC timestamp used for artifact metadata."""
    return datetime.now(UTC).isoformat()
