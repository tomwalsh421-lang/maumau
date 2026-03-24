from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cbb.autonomous_loop import (
    _lane_is_eligible,
    _managed_pids_from_state,
    _parse_lanes,
    _policy_overrides,
    show_status,
)
from cbb.infra_loop import lane_runtime_paths, write_json


def test_parse_lanes_trims_and_preserves_order() -> None:
    assert _parse_lanes("infra, model ,ux") == ("infra", "model", "ux")


def test_policy_overrides_require_single_lane() -> None:
    with pytest.raises(ValueError):
        _policy_overrides(Path("ops/infra-loop-policy.toml"), ("infra", "model"))


def test_managed_pids_from_state_dedupes_port_forward_pid() -> None:
    assert _managed_pids_from_state(
        {"managed_pids": [12, 34, 12], "port_forward_pid": 34}
    ) == [12, 34]


def test_lane_is_eligible_respects_backoff_until(tmp_path: Path) -> None:
    runtime = lane_runtime_paths(tmp_path, "model")
    runtime.root.mkdir(parents=True, exist_ok=True)

    write_json(
        runtime.state_path,
        {
            "status": "failed",
            "backoff_until": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
        },
    )
    assert _lane_is_eligible(runtime) is False

    write_json(
        runtime.state_path,
        {
            "status": "failed",
            "backoff_until": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
        },
    )
    assert _lane_is_eligible(runtime) is True


def test_show_status_reports_lane_state_and_heartbeat(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    runtime = lane_runtime_paths(tmp_path, "model")
    runtime.root.mkdir(parents=True, exist_ok=True)
    write_json(runtime.state_path, {"status": "accepted", "lane": "model"})
    write_json(runtime.heartbeat_path, {"status": "running", "phase": "testing"})

    exit_code = show_status(tmp_path, ("model",))

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lanes"]["model"]["state"]["status"] == "accepted"
    assert payload["lanes"]["model"]["heartbeat"]["phase"] == "testing"
