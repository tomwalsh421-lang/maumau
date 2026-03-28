from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from cbb.infra_loop import (
    build_codex_exec_command,
    citations_use_allowed_sources,
    load_agent_config,
    load_codex_agent_registry,
    load_loop_policy,
    path_is_allowed,
    select_verification_commands,
    split_commit_message,
    url_uses_allowed_domain,
    validate_changed_paths,
)

CLUSTER_LIST_STDOUT = (
    "NAME SERVERS AGENTS LOADBALANCER\n"
    "cbb-upsets-cluster 1/1 0/0 true\n"
)


def _load_run_infra_loops_module():
    module_path = Path("scripts/run_infra_loops.py").resolve()
    sys.path.insert(0, str(Path("src").resolve()))
    try:
        spec = importlib.util.spec_from_file_location("run_infra_loops", module_path)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def test_load_codex_agent_registry_resolves_relative_config_paths(
    tmp_path: Path,
) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    config_path = codex_dir / "config.toml"
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "infra-researcher.toml").write_text("", encoding="utf-8")
    config_path.write_text(
        """
[agents]
max_threads = 3

[agents.infra_researcher]
description = "infra"
config_file = "../agents/infra-researcher.toml"
""".strip(),
        encoding="utf-8",
    )

    registry = load_codex_agent_registry(config_path)

    assert registry["infra_researcher"].config_file == (
        agents_dir / "infra-researcher.toml"
    )


def test_policy_allows_infra_paths_and_blocks_model_paths() -> None:
    policy = load_loop_policy(
        Path("ops/infra-loop-policy.toml")
    )

    assert path_is_allowed("Makefile", policy) is True
    assert path_is_allowed("src/cbb/infra_loop.py", policy) is True
    assert path_is_allowed("src/cbb/modeling/train.py", policy) is False
    assert validate_changed_paths(
        ["Makefile", "src/cbb/modeling/train.py"],
        policy,
    ) == ["src/cbb/modeling/train.py"]


def test_url_allowlist_accepts_repo_scoped_github_and_rejects_other_paths() -> None:
    policy = load_loop_policy(
        Path("ops/infra-loop-policy.toml")
    )

    assert (
        url_uses_allowed_domain(
            "https://github.com/tomwalsh421-lang/maumau/blob/main/README.md",
            policy,
        )
        is True
    )
    assert (
        url_uses_allowed_domain(
            "https://github.com/openai/openai-python",
            policy,
        )
        is False
    )


def test_citations_allow_repo_paths_and_reject_non_whitelisted_urls() -> None:
    policy = load_loop_policy(
        Path("ops/infra-loop-policy.toml")
    )

    assert citations_use_allowed_sources(["README.md"], policy) == []
    assert citations_use_allowed_sources(
        [
            "https://kubernetes.io/docs/concepts/overview/",
            "https://example.com/not-allowed",
        ],
        policy,
    ) == ["https://example.com/not-allowed"]


def test_select_verification_commands_expands_for_python_trigger_paths() -> None:
    policy = load_loop_policy(
        Path("ops/infra-loop-policy.toml")
    )

    commands = select_verification_commands(
        ["src/cbb/infra_loop.py"],
        policy,
    )

    assert commands == [
        (
            "helm lint chart/cbb-upsets -f chart/cbb-upsets/values.yaml "
            "-f chart/cbb-upsets/values-local.yaml"
        ),
        (
            "helm template cbb-upsets chart/cbb-upsets "
            "-f chart/cbb-upsets/values.yaml "
            "-f chart/cbb-upsets/values-local.yaml"
        ),
        (
            "./.venv/bin/ruff check src/cbb/infra_loop.py "
            "tests/test_infra_loop.py scripts/run_infra_loops.py"
        ),
        "./.venv/bin/mypy src",
        "./.venv/bin/pytest -q tests/test_infra_loop.py",
    ]


def test_split_commit_message_preserves_body_paragraphs() -> None:
    subject, body = split_commit_message(
        "Add local infra supervisor\n\n- start/stop commands\n- detached worktrees"
    )

    assert subject == "Add local infra supervisor"
    assert body == ["- start/stop commands\n- detached worktrees"]


def test_build_codex_exec_command_applies_agent_settings() -> None:
    command = build_codex_exec_command(
        prompt="test prompt",
        agent=load_agent_config(Path("agents/infra-researcher.toml")),
        workdir=Path("/tmp/worktree"),
        output_path=Path("/tmp/output.json"),
        output_schema_path=Path("/tmp/schema.json"),
    )

    assert command[:4] == ["codex", "exec", "-C", "/tmp/worktree"]
    assert "--output-schema" in command
    assert any(item == 'approval_policy="never"' for item in command)


def test_ensure_cluster_prereqs_requires_configured_cluster_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    observed_commands: list[list[str]] = []

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        observed_commands.append(command)
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="docker-desktop\n",
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)

    with pytest.raises(
        RuntimeError,
        match="does not match configured local cluster context",
    ):
        module._ensure_cluster_prereqs(policy=policy, run_id="run-1")

    assert observed_commands == [
        ["k3d", "cluster", "list"],
        ["kubectl", "config", "current-context"],
    ]


def test_ensure_cluster_prereqs_reports_k3d_command_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    observed_commands: list[list[str]] = []

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        observed_commands.append(command)
        if command == ["k3d", "cluster", "list"]:
            raise subprocess.CalledProcessError(
                1,
                command,
                output="",
                stderr="k3d failed to talk to Docker",
            )
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)

    with pytest.raises(
        RuntimeError,
        match="Unable to inspect local k3d clusters.*k3d failed to talk to Docker",
    ):
        module._ensure_cluster_prereqs(policy=policy, run_id="run-1")

    assert observed_commands == [["k3d", "cluster", "list"]]


def test_ensure_cluster_prereqs_reports_cluster_reachability_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    observed_commands: list[list[str]] = []

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        observed_commands.append(command)
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="k3d-cbb-upsets-cluster\n",
                stderr="",
            )
        if command == ["kubectl", "cluster-info"]:
            raise subprocess.CalledProcessError(
                1,
                command,
                output="",
                stderr="The connection to the server 127.0.0.1:6443 was refused",
            )
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(
        module,
        "port_is_open",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("port checks should not run")
        ),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Unable to reach configured local cluster context "
            "'k3d-cbb-upsets-cluster'.*127.0.0.1:6443 was refused"
        ),
    ):
        module._ensure_cluster_prereqs(policy=policy, run_id="run-1")

    assert observed_commands == [
        ["k3d", "cluster", "list"],
        ["kubectl", "config", "current-context"],
        ["kubectl", "cluster-info"],
    ]


def test_ensure_cluster_prereqs_reuses_existing_managed_local_postgres_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="k3d-cbb-upsets-cluster\n",
                stderr="",
            )
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == [
            "helm",
            "status",
            policy.helm_release,
            "-n",
            policy.helm_namespace,
        ]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(module, "port_is_open", lambda host, port: True)
    monkeypatch.setattr(module, "_existing_port_forward_pid", lambda: 4242)
    monkeypatch.setattr(
        module,
        "_has_expected_existing_port_forward",
        lambda policy: False,
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    assert module._ensure_cluster_prereqs(policy=policy, run_id="run-1") == 4242


def test_ensure_cluster_prereqs_reuses_matching_existing_local_postgres_forward(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    state_path = tmp_path / "state.json"
    pid_path = tmp_path / "port-forward.pid"

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="k3d-cbb-upsets-cluster\n",
                stderr="",
            )
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == [
            "helm",
            "status",
            policy.helm_release,
            "-n",
            policy.helm_namespace,
        ]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(module, "STATE_PATH", state_path)
    monkeypatch.setattr(module, "PORT_FORWARD_PID_PATH", pid_path)
    monkeypatch.setattr(module, "port_is_open", lambda host, port: True)
    monkeypatch.setattr(module, "_existing_port_forward_pid", lambda: None)
    monkeypatch.setattr(
        module,
        "_has_expected_existing_port_forward",
        lambda policy: True,
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    assert module._ensure_cluster_prereqs(policy=policy, run_id="run-1") is None
    assert not state_path.exists()
    assert not pid_path.exists()


def test_ensure_cluster_prereqs_rejects_unrelated_local_postgres_listener(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="k3d-cbb-upsets-cluster\n",
                stderr="",
            )
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == [
            "helm",
            "status",
            policy.helm_release,
            "-n",
            policy.helm_namespace,
        ]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(module, "port_is_open", lambda host, port: True)
    monkeypatch.setattr(module, "_existing_port_forward_pid", lambda: None)
    monkeypatch.setattr(
        module,
        "_has_expected_existing_port_forward",
        lambda policy: False,
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            r"Local Postgres port 127\.0\.0\.1:5432 is already in use by an "
            r"unrelated listener"
        ),
    ):
        module._ensure_cluster_prereqs(policy=policy, run_id="run-1")


def test_looks_like_expected_port_forward_requires_matching_service_and_port() -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))

    assert (
        module._looks_like_expected_port_forward(
            (
                "/usr/local/bin/kubectl port-forward "
                "svc/cbb-upsets-postgresql 5432:5432 -n default"
            ),
            policy,
        )
        is True
    )
    assert (
        module._looks_like_expected_port_forward(
            (
                "/usr/local/bin/kubectl port-forward "
                "svc/other-postgresql 5432:5432 -n default"
            ),
            policy,
        )
        is False
    )


def test_ensure_cluster_prereqs_reconciles_missing_helm_release_before_port_forward(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    observed_commands: list[list[str]] = []
    port_checks: list[tuple[str, int]] = []

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        observed_commands.append(command)
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="k3d-cbb-upsets-cluster\n",
                stderr="",
            )
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == [
            "helm",
            "status",
            policy.helm_release,
            "-n",
            policy.helm_namespace,
        ]:
            raise subprocess.CalledProcessError(
                1,
                command,
                output="",
                stderr="Error: release: not found",
            )
        if command == [
            "helm",
            "upgrade",
            "--install",
            policy.helm_release,
            "chart/cbb-upsets",
            "-n",
            policy.helm_namespace,
            "-f",
            "chart/cbb-upsets/values.yaml",
            "-f",
            "chart/cbb-upsets/values-local.yaml",
        ]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)

    def fake_port_is_open(host: str, port: int) -> bool:
        port_checks.append((host, port))
        return True

    monkeypatch.setattr(module, "port_is_open", fake_port_is_open)
    monkeypatch.setattr(module, "_existing_port_forward_pid", lambda: 4242)
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    assert module._ensure_cluster_prereqs(policy=policy, run_id="run-1") == 4242
    assert observed_commands == [
        ["k3d", "cluster", "list"],
        ["kubectl", "config", "current-context"],
        ["kubectl", "cluster-info"],
        ["helm", "status", policy.helm_release, "-n", policy.helm_namespace],
        [
            "helm",
            "upgrade",
            "--install",
            policy.helm_release,
            "chart/cbb-upsets",
            "-n",
            policy.helm_namespace,
            "-f",
            "chart/cbb-upsets/values.yaml",
            "-f",
            "chart/cbb-upsets/values-local.yaml",
        ],
    ]
    assert port_checks == [("127.0.0.1", policy.postgres_local_port)]


def test_ensure_cluster_prereqs_stops_when_helm_reconcile_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    observed_commands: list[list[str]] = []

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        observed_commands.append(command)
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="k3d-cbb-upsets-cluster\n",
                stderr="",
            )
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == [
            "helm",
            "status",
            policy.helm_release,
            "-n",
            policy.helm_namespace,
        ]:
            raise subprocess.CalledProcessError(
                1,
                command,
                output="",
                stderr="Error: release: not found",
            )
        if command == [
            "helm",
            "upgrade",
            "--install",
            policy.helm_release,
            "chart/cbb-upsets",
            "-n",
            policy.helm_namespace,
            "-f",
            "chart/cbb-upsets/values.yaml",
            "-f",
            "chart/cbb-upsets/values-local.yaml",
        ]:
            raise subprocess.CalledProcessError(
                1,
                command,
                output="",
                stderr="Error: chart install failed",
            )
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(
        module,
        "port_is_open",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("port checks should not run")
        ),
    )
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not run")),
    )

    with pytest.raises(
        RuntimeError,
        match=(
            "Unable to reconcile local Helm release "
            "'cbb-upsets'.*chart install failed"
        ),
    ):
        module._ensure_cluster_prereqs(policy=policy, run_id="run-1")

    assert observed_commands == [
        ["k3d", "cluster", "list"],
        ["kubectl", "config", "current-context"],
        ["kubectl", "cluster-info"],
        ["helm", "status", policy.helm_release, "-n", policy.helm_namespace],
        [
            "helm",
            "upgrade",
            "--install",
            policy.helm_release,
            "chart/cbb-upsets",
            "-n",
            policy.helm_namespace,
            "-f",
            "chart/cbb-upsets/values.yaml",
            "-f",
            "chart/cbb-upsets/values-local.yaml",
        ],
    ]


def test_ensure_cluster_prereqs_records_managed_port_forward_pid_immediately(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    state_path = tmp_path / "state.json"
    log_path = tmp_path / "port-forward.log"
    pid_path = tmp_path / "port-forward.pid"

    def fake_run_subprocess(command: list[str], *, cwd: Path, **_: object):
        if command == ["k3d", "cluster", "list"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=CLUSTER_LIST_STDOUT,
                stderr="",
            )
        if command == ["kubectl", "config", "current-context"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="k3d-cbb-upsets-cluster\n",
                stderr="",
            )
        if command == ["kubectl", "cluster-info"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == [
            "helm",
            "status",
            policy.helm_release,
            "-n",
            policy.helm_namespace,
        ]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {command}")

    class FakeProcess:
        pid = 5151

        def terminate(self) -> None:
            raise AssertionError("terminate should not be called")

    call_count = 0

    def fake_port_is_open(host: str, port: int) -> bool:
        nonlocal call_count
        assert host == "127.0.0.1"
        assert port == policy.postgres_local_port
        call_count += 1
        if call_count == 1:
            return False
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        assert payload["status"] == "running"
        assert payload["branch"] == policy.branch
        assert payload["run_id"] == "run-1"
        assert payload["port_forward_pid"] == 5151
        return True

    monkeypatch.setattr(module, "run_subprocess", fake_run_subprocess)
    monkeypatch.setattr(module, "STATE_PATH", state_path)
    monkeypatch.setattr(module, "PORT_FORWARD_LOG_PATH", log_path)
    monkeypatch.setattr(module, "PORT_FORWARD_PID_PATH", pid_path)
    monkeypatch.setattr(module, "port_is_open", fake_port_is_open)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        module.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(),
    )

    assert module._ensure_cluster_prereqs(policy=policy, run_id="run-1") == 5151

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["port_forward_pid"] == 5151
    assert pid_path.read_text(encoding="utf-8").strip() == "5151"


def test_existing_port_forward_pid_prefers_state_when_marker_is_stale(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_run_infra_loops_module()
    state_path = tmp_path / "state.json"
    pid_path = tmp_path / "port-forward.pid"
    pid_path.write_text("4242\n", encoding="utf-8")
    state_path.write_text(
        json.dumps({"port_forward_pid": 5151}),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "STATE_PATH", state_path)
    monkeypatch.setattr(module, "PORT_FORWARD_PID_PATH", pid_path)
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 5151)

    assert module._existing_port_forward_pid() == 5151
    assert pid_path.read_text(encoding="utf-8").strip() == "5151"


def test_write_failure_state_preserves_running_managed_port_forward(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_run_infra_loops_module()
    state_path = tmp_path / "state.json"
    pid_path = tmp_path / "port-forward.pid"
    state_path.write_text(
        json.dumps({"last_commit": "abc123", "port_forward_pid": 4242}),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "STATE_PATH", state_path)
    monkeypatch.setattr(module, "PORT_FORWARD_PID_PATH", pid_path)
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 4242)

    payload = module._write_failure_state(error="boom")

    assert payload["last_commit"] == "abc123"
    assert payload["port_forward_pid"] == 4242
    written = json.loads(state_path.read_text(encoding="utf-8"))
    assert written["status"] == "failed"
    assert written["last_commit"] == "abc123"
    assert written["port_forward_pid"] == 4242
    assert pid_path.read_text(encoding="utf-8").strip() == "4242"


def test_record_active_worktree_state_tracks_run_and_relative_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_run_infra_loops_module()
    policy = load_loop_policy(Path("ops/infra-loop-policy.toml"))
    runtime_root = tmp_path / "infra-loop"
    runtime_root.mkdir()
    state_path = runtime_root / "state.json"
    worktrees_dir = tmp_path / "repo" / ".codex" / "local" / "infra-loop" / "worktrees"
    worktree_path = worktrees_dir / "run-3"

    monkeypatch.setattr(module, "STATE_PATH", state_path)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path / "repo")

    module._record_active_worktree_state(
        policy=policy,
        run_id="run-3",
        worktree_path=worktree_path,
        port_forward_pid=5151,
    )

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["status"] == "running"
    assert payload["branch"] == policy.branch
    assert payload["run_id"] == "run-3"
    assert payload["active_run_id"] == "run-3"
    assert (
        payload["active_worktree_path"]
        == ".codex/local/infra-loop/worktrees/run-3"
    )
    assert payload["port_forward_pid"] == 5151
    assert "updated_at" in payload


def test_wait_for_startup_signal_requires_ready_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_run_infra_loops_module()
    runtime_root = tmp_path / "infra-loop"
    runtime_root.mkdir()
    heartbeat_path = runtime_root / "heartbeat.json"
    monotonic_values = iter([0.0, 0.1, 0.2, 0.3])
    sleep_count = 0

    def fake_sleep(_: float) -> None:
        nonlocal sleep_count
        sleep_count += 1
        if sleep_count == 1:
            heartbeat_path.write_text(
                json.dumps({"phase": "preflight", "status": "running"}),
                encoding="utf-8",
            )
        elif sleep_count == 2:
            heartbeat_path.write_text(
                json.dumps({"phase": "ready", "status": "running"}),
                encoding="utf-8",
            )

    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 222)

    assert (
        module._wait_for_startup_signal(
            runtime_root,
            launcher_pid=222,
            timeout_seconds=1.0,
        )
        == 0
    )


def test_wait_for_startup_signal_fails_on_immediate_backoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_run_infra_loops_module()
    runtime_root = tmp_path / "infra-loop"
    runtime_root.mkdir()
    heartbeat_path = runtime_root / "heartbeat.json"
    monotonic_values = iter([0.0, 0.1, 0.2])

    def fake_sleep(_: float) -> None:
        heartbeat_path.write_text(
            json.dumps({"phase": "backoff", "status": "failed"}),
            encoding="utf-8",
        )

    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(module.time, "sleep", fake_sleep)
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid == 222)

    assert (
        module._wait_for_startup_signal(
            runtime_root,
            launcher_pid=222,
            timeout_seconds=1.0,
        )
        == 1
    )

    err = capsys.readouterr().err
    assert "failed startup state" in err
    assert str(runtime_root / "supervisor.log") in err


def test_wait_for_startup_signal_fails_when_launcher_exits_early(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_run_infra_loops_module()
    runtime_root = tmp_path / "infra-loop"
    runtime_root.mkdir()
    monotonic_values = iter([0.0, 0.1])

    monkeypatch.setattr(module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(module, "_pid_is_running", lambda pid: False)

    assert (
        module._wait_for_startup_signal(
            runtime_root,
            launcher_pid=222,
            timeout_seconds=1.0,
        )
        == 1
    )

    err = capsys.readouterr().err
    assert "exited before publishing a ready startup signal" in err
    assert str(runtime_root / "supervisor.log") in err


def test_show_status_prints_operator_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_run_infra_loops_module()
    runtime_root = tmp_path / "infra-loop"
    runtime_root.mkdir()
    (runtime_root / "supervisor.pid").write_text("111\n", encoding="utf-8")
    (runtime_root / "heartbeat.json").write_text(
        json.dumps(
            {
                "phase": "implementing",
                "status": "running",
                "updated_at": "2026-03-27T12:00:00Z",
                "run_id": "run-2",
                "task_id": "INFRA-LOOP-3",
            }
        ),
        encoding="utf-8",
    )
    (runtime_root / "current_task.json").write_text(
        json.dumps(
            {
                "task_id": "INFRA-LOOP-3",
                "title": "Heartbeat, status, and stop controls",
            }
        ),
        encoding="utf-8",
    )
    (runtime_root / "state.json").write_text(
        json.dumps(
            {
                "status": "accepted",
                "run_id": "run-1",
                "last_commit": "deadbeef",
                "port_forward_pid": 5151,
                "active_run_id": "run-2",
                "active_worktree_path": ".codex/local/infra-loop/worktrees/run-2",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid in {111, 5151})

    assert module._show_status(runtime_root) == 0

    output = capsys.readouterr().out
    assert "Supervisor: running (pid 111)" in output
    assert "Heartbeat: running (implementing) at 2026-03-27T12:00:00Z" in output
    assert "Last run: run-2" in output
    assert "Task: INFRA-LOOP-3 Heartbeat, status, and stop controls" in output
    assert "Last accepted commit: deadbeef" in output
    assert "Managed Postgres port-forward: pid 5151 (running)" in output
    assert (
        "Active detached worktree: "
        f"{module.REPO_ROOT / '.codex/local/infra-loop/worktrees/run-2'}"
    ) in output


def test_show_status_marks_stale_heartbeat_when_supervisor_is_stopped(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_run_infra_loops_module()
    runtime_root = tmp_path / "infra-loop"
    runtime_root.mkdir()
    (runtime_root / "supervisor.pid").write_text("111\n", encoding="utf-8")
    (runtime_root / "heartbeat.json").write_text(
        json.dumps(
            {
                "phase": "sleeping",
                "status": "accepted",
                "updated_at": "2026-03-27T12:00:00Z",
                "run_id": "run-2",
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(module, "_pid_is_running", lambda pid: False)

    assert module._show_status(runtime_root) == 0

    output = capsys.readouterr().out
    assert "Supervisor: stopped" in output
    assert "Heartbeat: stale accepted (sleeping) at 2026-03-27T12:00:00Z" in output


def test_stop_supervisor_terminates_managed_port_forward_and_cleans_markers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_run_infra_loops_module()
    runtime_root = tmp_path / "infra-loop"
    runtime_root.mkdir()
    (runtime_root / "supervisor.pid").write_text("111\n", encoding="utf-8")
    (runtime_root / "heartbeat.json").write_text("{}", encoding="utf-8")
    (runtime_root / "current_task.json").write_text("{}", encoding="utf-8")
    (runtime_root / "launcher.pid").write_text("222\n", encoding="utf-8")
    (runtime_root / "port-forward.pid").write_text("5151\n", encoding="utf-8")
    state_path = runtime_root / "state.json"
    worktree_path = (
        tmp_path / "repo" / ".codex" / "local" / "infra-loop" / "worktrees" / "run-2"
    )
    state_path.write_text(
        json.dumps(
            {
                "last_commit": "deadbeef",
                "port_forward_pid": 5151,
                "active_run_id": "run-2",
                "active_worktree_path": ".codex/local/infra-loop/worktrees/run-2",
            }
        ),
        encoding="utf-8",
    )

    running_pids = {111, 5151}
    signals: list[tuple[int, int]] = []
    removed_worktrees: list[Path] = []

    def fake_kill(pid: int, sig: int) -> None:
        signals.append((pid, sig))
        if sig in {module.signal.SIGTERM, module.signal.SIGKILL}:
            running_pids.discard(pid)

    monkeypatch.setattr(module, "_pid_is_running", lambda pid: pid in running_pids)
    monkeypatch.setattr(module.os, "kill", fake_kill)
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path / "repo")
    monkeypatch.setattr(
        module,
        "remove_worktree",
        lambda repo_root, candidate: removed_worktrees.append(candidate),
    )

    assert module._stop_supervisor(runtime_root) == 0

    assert signals == [
        (111, module.signal.SIGTERM),
        (5151, module.signal.SIGTERM),
    ]
    assert removed_worktrees == [worktree_path]
    assert not (runtime_root / "supervisor.pid").exists()
    assert not (runtime_root / "heartbeat.json").exists()
    assert not (runtime_root / "current_task.json").exists()
    assert not (runtime_root / "launcher.pid").exists()
    assert not (runtime_root / "port-forward.pid").exists()

    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert state_payload["status"] == "stopped"
    assert state_payload["last_commit"] == "deadbeef"
    assert "port_forward_pid" not in state_payload
    assert "active_run_id" not in state_payload
    assert "active_worktree_path" not in state_payload
    assert "stopped_at" in state_payload
    assert "updated_at" in state_payload
    assert "Stopped local infra loop supervisor." in capsys.readouterr().out
