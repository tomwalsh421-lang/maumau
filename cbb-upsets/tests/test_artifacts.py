from __future__ import annotations

from pathlib import Path

import orjson

from cbb.modeling.artifacts import artifact_path, load_artifact


def test_load_artifact_defaults_backward_compatible_fields(tmp_path: Path) -> None:
    legacy_artifact_path = artifact_path(
        market="spread",
        artifact_name="legacy",
        artifacts_dir=tmp_path,
    )
    legacy_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_artifact_path.write_bytes(
        orjson.dumps(
            {
                "market": "spread",
                "feature_names": ["feature_a", "feature_b"],
                "means": [0.0, 1.0],
                "scales": [1.0, 2.0],
                "weights": [0.1, -0.2],
                "bias": 0.3,
                "metrics": {
                    "examples": 20,
                    "priced_examples": 18,
                    "training_examples": 18,
                    "feature_names": ["feature_a", "feature_b"],
                    "log_loss": 0.6,
                    "brier_score": 0.2,
                    "accuracy": 0.55,
                    "start_season": 2024,
                    "end_season": 2025,
                    "trained_at": "2026-03-08T12:00:00+00:00",
                },
            }
        )
    )

    artifact = load_artifact(
        market="spread",
        artifact_name="legacy",
        artifacts_dir=tmp_path,
    )

    assert artifact.market == "spread"
    assert artifact.model_family == "logistic"
    assert artifact.platt_scale == 1.0
    assert artifact.platt_bias == 0.0
    assert artifact.market_blend_weight == 1.0
    assert artifact.max_market_probability_delta == 1.0
    assert artifact.spread_modeling_mode == "cover_classifier"
    assert artifact.spread_residual_scale == 1.0
    assert artifact.moneyline_band_models == ()
    assert artifact.moneyline_segment_calibrations == ()
    assert artifact.spread_line_calibrations == ()
    assert artifact.serialized_model_base64 is None


def test_load_artifact_infers_margin_regression_from_residual_scale(
    tmp_path: Path,
) -> None:
    legacy_artifact_path = artifact_path(
        market="spread",
        artifact_name="legacy_margin",
        artifacts_dir=tmp_path,
    )
    legacy_artifact_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_artifact_path.write_bytes(
        orjson.dumps(
            {
                "market": "spread",
                "model_family": "logistic",
                "feature_names": ["feature_a"],
                "means": [0.0],
                "scales": [1.0],
                "weights": [0.1],
                "bias": 0.3,
                "spread_residual_scale": 2.5,
                "metrics": {
                    "examples": 20,
                    "priced_examples": 18,
                    "training_examples": 18,
                    "feature_names": ["feature_a"],
                    "log_loss": 0.6,
                    "brier_score": 0.2,
                    "accuracy": 0.55,
                    "start_season": 2024,
                    "end_season": 2025,
                    "trained_at": "2026-03-08T12:00:00+00:00",
                },
            }
        )
    )

    artifact = load_artifact(
        market="spread",
        artifact_name="legacy_margin",
        artifacts_dir=tmp_path,
    )

    assert artifact.market == "spread"
    assert artifact.spread_modeling_mode == "margin_regression"
    assert artifact.spread_residual_scale == 2.5
    assert artifact.spread_line_calibrations == ()
