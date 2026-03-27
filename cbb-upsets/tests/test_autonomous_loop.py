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
    _normalize_repo_path,
    _normalize_repo_reference,
    _normalize_research_payload,
    _parse_lanes,
    _policy_overrides,
    _run_lane_iteration,
    _run_lane_with_recovery,
    _service_has_ready_endpoints,
    _tail_log,
    show_status,
)
from cbb.infra_loop import (
    GIT_REPO_ROOT,
    REPO_ROOT,
    ensure_lane_runtime_dirs,
    lane_runtime_paths,
    load_codex_agent_registry,
    load_lane_agent_set,
    load_loop_policy,
    worktree_project_root,
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


def test_normalize_repo_path_strips_worktree_and_repo_prefixes() -> None:
    worktree_path = Path("/tmp/ux/worktrees/run-1")

    assert (
        _normalize_repo_path(
            (
                "/tmp/ux/worktrees/run-1/"
                "cbb-upsets/src/cbb/ui/templates/picks.html"
            ),
            worktree_path,
        )
        == "src/cbb/ui/templates/picks.html"
    )
    assert (
        _normalize_repo_path(
            "/Users/tomwalsh/git/maumau/cbb-upsets/tests/test_dashboard_ui.py",
            worktree_path,
        )
        == "tests/test_dashboard_ui.py"
    )
    assert (
        _normalize_repo_path(
            "cbb-upsets/docs/ui-ux-roadmap.md",
            worktree_path,
        )
        == "docs/ui-ux-roadmap.md"
    )


def test_normalize_repo_reference_preserves_line_suffixes() -> None:
    worktree_path = Path("/tmp/ux/worktrees/run-1")

    assert (
        _normalize_repo_reference(
            (
                "/tmp/ux/worktrees/run-1/"
                "cbb-upsets/src/cbb/ui/templates/picks.html:73"
            ),
            worktree_path,
        )
        == "src/cbb/ui/templates/picks.html:73"
    )
    assert (
        _normalize_repo_reference(
            "cbb-upsets/src/cbb/dashboard/service.py#L458",
            worktree_path,
        )
        == "src/cbb/dashboard/service.py#L458"
    )


def test_normalize_research_payload_sanitizes_bad_worktree_paths() -> None:
    worktree_path = Path("/tmp/ux/worktrees/run-1")
    payload = {
        "files_to_touch": [
            (
                "/tmp/ux/worktrees/run-1/"
                "cbb-upsets/src/cbb/ui/templates/picks.html"
            ),
            "cbb-upsets/tests/test_dashboard_ui.py",
        ],
        "citations": [
            (
                "/tmp/ux/worktrees/run-1/"
                "cbb-upsets/src/cbb/dashboard/service.py:458"
            ),
            "https://example.com/allowed-to-pass-through",
        ],
    }

    assert _normalize_research_payload(payload, worktree_path) == {
        "files_to_touch": [
            "src/cbb/ui/templates/picks.html",
            "tests/test_dashboard_ui.py",
        ],
        "citations": [
            "src/cbb/dashboard/service.py:458",
            "https://example.com/allowed-to-pass-through",
        ],
    }


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


def test_run_lane_iteration_provisions_worktree_venv_before_research(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = load_loop_policy(Path("ops/ux-loop-policy.toml"))
    agents = load_lane_agent_set(
        policy,
        load_codex_agent_registry(Path(".codex/config.toml")),
    )
    runtime = lane_runtime_paths(tmp_path, "ux")
    ensure_lane_runtime_dirs(runtime)
    context = LaneContext(policy=policy, agents=agents, runtime=runtime)
    events: list[str] = []
    worktree_root = runtime.worktrees_dir / "20260324T023222+0000"
    project_worktree_path = worktree_project_root(worktree_root)

    monkeypatch.setattr(
        "cbb.autonomous_loop.utc_now_iso",
        lambda: "2026-03-24T02:32:22+00:00",
    )
    monkeypatch.setattr("cbb.autonomous_loop.repo_is_clean", lambda _: True)
    monkeypatch.setattr(
        "cbb.autonomous_loop.ensure_command_available",
        lambda _: None,
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop.hydrate_approved_source_cache",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop._ensure_lane_prereqs",
        lambda _context: None,
    )

    def fake_create_detached_worktree(
        repo_root: Path,
        branch: str,
        worktree_path: Path,
    ) -> None:
        assert repo_root == GIT_REPO_ROOT
        del branch
        assert worktree_path == worktree_root
        worktree_project_root(worktree_path).mkdir(parents=True, exist_ok=True)
        events.append("create")

    monkeypatch.setattr(
        "cbb.autonomous_loop.create_detached_worktree",
        fake_create_detached_worktree,
    )
    def fake_ensure_worktree_venv(repo_root: Path, worktree_path: Path) -> None:
        assert repo_root == REPO_ROOT
        assert worktree_path == project_worktree_path
        events.append("venv")

    monkeypatch.setattr(
        "cbb.autonomous_loop.ensure_worktree_venv",
        fake_ensure_worktree_venv,
    )

    def fake_run_researcher(
        *,
        context: LaneContext,
        run_dir: Path,
        worktree_path: Path,
    ) -> dict[str, object]:
        del context, run_dir
        assert worktree_path == project_worktree_path
        events.append("research")
        return {
            "task_id": "ux-loop-1",
            "title": "Refresh dashboard",
            "summary": "Adjust the main dashboard layout.",
            "files_to_touch": ["src/cbb/ui/app.py"],
            "commands_to_run": [],
            "acceptance_criteria": ["Dashboard renders."],
            "promotion_criteria": ["Verification passes."],
            "citations": [],
        }

    monkeypatch.setattr(
        "cbb.autonomous_loop._run_researcher",
        fake_run_researcher,
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop._run_implementer",
        lambda **_kwargs: events.append("implement"),
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop.changed_paths_for_worktree",
        lambda _worktree_path: ["src/cbb/ui/app.py"],
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop._run_verification_commands",
        lambda **_kwargs: [
            {
                "command": "./.venv/bin/ruff check src tests scripts",
                "returncode": 0,
                "stdout": "",
                "stderr": "",
                "ok": True,
            }
        ],
    )

    def fake_run_verifier(**_kwargs: object) -> dict[str, object]:
        events.append("verify")
        return {
            "approved": True,
            "summary": "Looks good.",
            "commit_message": "Refresh dashboard UX",
            "violations": [],
            "citations": [],
        }

    monkeypatch.setattr("cbb.autonomous_loop._run_verifier", fake_run_verifier)
    monkeypatch.setattr(
        "cbb.autonomous_loop.commit_all",
        lambda _worktree_path, _message: events.append("commit"),
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop._git_stdout",
        lambda _cwd, *_args: "abc123\n",
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop.advance_branch",
        lambda repo_root, _branch, _commit_sha: (
            repo_root == GIT_REPO_ROOT and events.append("advance")
        ),
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop.remove_worktree",
        lambda repo_root, worktree_path: (
            repo_root == GIT_REPO_ROOT
            and worktree_path == worktree_root
            and events.append("remove")
        ),
    )

    payload = _run_lane_iteration(context)

    assert payload["status"] == "accepted"
    assert events[:3] == ["create", "venv", "research"]
    assert events[-1] == "remove"


def test_run_lane_with_recovery_records_venv_provisioning_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = load_loop_policy(Path("ops/ux-loop-policy.toml"))
    runtime = lane_runtime_paths(tmp_path, "ux")
    ensure_lane_runtime_dirs(runtime)
    context = LaneContext(policy=policy, agents=None, runtime=runtime)  # type: ignore[arg-type]
    events: list[str] = []
    worktree_root = runtime.worktrees_dir / "20260324T023222+0000"
    project_worktree_path = worktree_project_root(worktree_root)

    monkeypatch.setattr(
        "cbb.autonomous_loop.utc_now_iso",
        lambda: "2026-03-24T02:32:22+00:00",
    )
    monkeypatch.setattr("cbb.autonomous_loop.repo_is_clean", lambda _: True)
    monkeypatch.setattr(
        "cbb.autonomous_loop.ensure_command_available",
        lambda _: None,
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop.hydrate_approved_source_cache",
        lambda *_args: [],
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop._ensure_lane_prereqs",
        lambda _context: None,
    )

    def fake_create_detached_worktree(
        repo_root: Path,
        branch: str,
        worktree_path: Path,
    ) -> None:
        assert repo_root == GIT_REPO_ROOT
        del branch
        assert worktree_path == worktree_root
        worktree_project_root(worktree_path).mkdir(parents=True, exist_ok=True)
        events.append("create")

    monkeypatch.setattr(
        "cbb.autonomous_loop.create_detached_worktree",
        fake_create_detached_worktree,
    )

    def fake_ensure_worktree_venv(repo_root: Path, worktree_path: Path) -> None:
        assert repo_root == REPO_ROOT
        assert worktree_path == project_worktree_path
        events.append("venv")
        raise RuntimeError("Primary repo virtualenv is missing required executables")

    monkeypatch.setattr(
        "cbb.autonomous_loop.ensure_worktree_venv",
        fake_ensure_worktree_venv,
    )
    monkeypatch.setattr(
        "cbb.autonomous_loop.remove_worktree",
        lambda repo_root, worktree_path: (
            repo_root == GIT_REPO_ROOT
            and worktree_path == worktree_root
            and events.append("remove")
        ),
    )

    payload = _run_lane_with_recovery(context)

    assert payload["status"] == "failed"
    assert payload["lane"] == "ux"
    assert "Primary repo virtualenv" in payload["error"]
    assert payload["consecutive_failures"] == 1
    assert events == ["create", "venv", "remove"]
