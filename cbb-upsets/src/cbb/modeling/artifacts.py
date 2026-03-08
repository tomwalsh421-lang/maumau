"""Artifact storage for trained betting models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import orjson

from cbb.db import REPO_ROOT

ModelMarket = Literal["moneyline", "spread"]
StrategyMarket = Literal["moneyline", "spread", "best"]
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
class ModelArtifact:
    """Serialized logistic-regression artifact."""

    market: ModelMarket
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    bias: float
    metrics: TrainingMetrics


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
        feature_names=tuple(payload["feature_names"]),
        means=tuple(float(value) for value in payload["means"]),
        scales=tuple(float(value) for value in payload["scales"]),
        weights=tuple(float(value) for value in payload["weights"]),
        bias=float(payload["bias"]),
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


def current_timestamp() -> str:
    """Return the current UTC timestamp used for artifact metadata."""
    return datetime.now(UTC).isoformat()
