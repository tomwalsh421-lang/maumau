from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cbb.autonomous_loop import (
    LaneContext,
    _ensure_lane_prereqs,
    _kubectl_resource_name,
    _lane_is_eligible,
    _managed_pids_from_state,
    _parse_lanes,
    _policy_overrides,
    _service_has_ready_endpoints,
    _tail_log,
    show_status,
)
from cbb.infra_loop import (
    ensure_lane_runtime_dirs,
    lane_runtime_paths,
    load_loop_policy,
    write_json,
)


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


def test_kubectl_resource_name_strips_service_prefix() -> None:
    assert _kubectl_resource_name("svc/cbb-upsets-postgresql") == (
        "cbb-upsets-postgresql"
    )
    assert _kubectl_resource_name("service/cbb-upsets-postgresql") == (
        "cbb-upsets-postgresql"
    )
    assert _kubectl_resource_name("cbb-upsets-postgresql") == (
        "cbb-upsets-postgresql"
    )


def test_service_has_ready_endpoints_uses_address_presence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_subprocess(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, capture_output
        assert command == [
            "kubectl",
            "get",
            "endpoints",
            "cbb-upsets-postgresql",
            "-n",
            "default",
            "-o",
            "json",
        ]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"subsets": [{"addresses": [{"ip": "10.0.0.9"}]}]}),
            stderr="",
        )

    monkeypatch.setattr("cbb.autonomous_loop.run_subprocess", fake_run_subprocess)

    assert _service_has_ready_endpoints("cbb-upsets-postgresql", "default") is True


def test_ensure_lane_prereqs_rejects_failed_helm_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    runtime = lane_runtime_paths(tmp_path, "infra")
    ensure_lane_runtime_dirs(runtime)
    context = LaneContext(policy=policy, agents=None, runtime=runtime)  # type: ignore[arg-type]

    def fake_run_subprocess(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, capture_output
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["helm", "status", policy.helm_release]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"info": {"status": "failed"}}),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr("cbb.autonomous_loop.run_subprocess", fake_run_subprocess)

    with pytest.raises(
        RuntimeError,
        match="is not healthy: status=failed",
    ):
        _ensure_lane_prereqs(context)


def test_ensure_lane_prereqs_rejects_service_without_ready_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    runtime = lane_runtime_paths(tmp_path, "infra")
    ensure_lane_runtime_dirs(runtime)
    context = LaneContext(policy=policy, agents=None, runtime=runtime)  # type: ignore[arg-type]

    def fake_run_subprocess(
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env, capture_output
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command[:3] == ["helm", "status", policy.helm_release]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"info": {"status": "deployed"}}),
                stderr="",
            )
        if command[:3] == ["kubectl", "get", "endpoints"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"subsets": []}),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr("cbb.autonomous_loop.run_subprocess", fake_run_subprocess)

    with pytest.raises(RuntimeError, match="has no ready endpoints"):
        _ensure_lane_prereqs(context)


def test_tail_log_returns_recent_non_empty_lines(tmp_path: Path) -> None:
    log_path = tmp_path / "port-forward.log"
    log_path.write_text("\nfirst\n\nsecond\nthird\n", encoding="utf-8")

    assert _tail_log(log_path, max_lines=2) == "second | third"


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
