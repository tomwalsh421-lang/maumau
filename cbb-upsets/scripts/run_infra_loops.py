#!/usr/bin/env python3
"""Run the local autonomous infra loop supervisor."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cbb.infra_loop import (
    REPO_ROOT,
    advance_branch,
    build_codex_exec_command,
    changed_paths_for_worktree,
    citations_use_allowed_sources,
    commit_all,
    create_detached_worktree,
    ensure_command_available,
    ensure_local_branch,
    hydrate_approved_source_cache,
    load_agent_config,
    load_codex_agent_registry,
    load_loop_policy,
    policy_prompt_block,
    port_is_open,
    read_json,
    remove_worktree,
    repo_is_clean,
    run_subprocess,
    select_verification_commands,
    validate_changed_paths,
    write_json,
)

DEFAULT_POLICY_PATH = REPO_ROOT / "ops" / "infra-loop-policy.toml"
DEFAULT_CODEX_CONFIG_PATH = REPO_ROOT / ".codex" / "config.toml"
DEFAULT_RUNTIME_ROOT = REPO_ROOT / ".codex" / "local" / "infra-loop"
SUPERVISOR_PID_PATH = DEFAULT_RUNTIME_ROOT / "supervisor.pid"
STATE_PATH = DEFAULT_RUNTIME_ROOT / "state.json"
HEARTBEAT_PATH = DEFAULT_RUNTIME_ROOT / "heartbeat.json"
CURRENT_TASK_PATH = DEFAULT_RUNTIME_ROOT / "current_task.json"
RUNS_DIR = DEFAULT_RUNTIME_ROOT / "runs"
WORKTREES_DIR = DEFAULT_RUNTIME_ROOT / "worktrees"
SOURCE_CACHE_DIR = DEFAULT_RUNTIME_ROOT / "approved-source-cache"
PORT_FORWARD_LOG_PATH = DEFAULT_RUNTIME_ROOT / "port-forward.log"
PORT_FORWARD_PID_PATH = DEFAULT_RUNTIME_ROOT / "port-forward.pid"
SUPERVISOR_LOG_PATH = DEFAULT_RUNTIME_ROOT / "supervisor.log"
STARTUP_READY_PHASES = frozenset({"ready", "implementing", "sleeping"})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--codex-config", type=Path, default=DEFAULT_CODEX_CONFIG_PATH)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--wait-for-startup", action="store_true")
    parser.add_argument("--launcher-pid", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    args = parser.parse_args()

    if args.wait_for_startup:
        if args.launcher_pid is None:
            parser.error("--launcher-pid is required with --wait-for-startup")
        return _wait_for_startup_signal(
            DEFAULT_RUNTIME_ROOT,
            launcher_pid=args.launcher_pid,
            timeout_seconds=args.timeout_seconds,
        )
    if args.status:
        return _show_status(DEFAULT_RUNTIME_ROOT)
    if args.stop:
        return _stop_supervisor(DEFAULT_RUNTIME_ROOT)

    policy = load_loop_policy(args.policy)
    agent_registry = load_codex_agent_registry(args.codex_config)
    agents = {
        name: load_agent_config(agent_registry[name].config_file)
        for name in ("infra_researcher", "infra_implementer", "infra_verifier")
    }

    DEFAULT_RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    _ensure_single_supervisor(DEFAULT_RUNTIME_ROOT)
    _write_pid(SUPERVISOR_PID_PATH)
    try:
        ensure_local_branch(REPO_ROOT, policy.branch)
        while True:
            try:
                result = _run_iteration(
                    policy=policy,
                    agents=agents,
                )
                _write_heartbeat(
                    phase="sleeping",
                    status=result["status"],
                    extra=result,
                )
                if args.once:
                    return 0
                time.sleep(policy.sleep_seconds)
            except Exception as exc:  # pragma: no cover - exercised via CLI
                failure_payload = _write_failure_state(error=str(exc))
                _write_heartbeat(
                    phase="backoff",
                    status="failed",
                    extra=failure_payload,
                )
                if args.once:
                    raise
                time.sleep(policy.failure_backoff_seconds)
    finally:
        _safe_unlink(SUPERVISOR_PID_PATH)


def _run_iteration(
    *,
    policy,
    agents: dict[str, Any],
) -> dict[str, Any]:
    if not repo_is_clean(REPO_ROOT):
        raise RuntimeError(
            "Primary worktree is dirty. Autonomous infra loops require a clean repo."
        )

    for command in ("codex", "git", "helm", "kubectl", "k3d"):
        ensure_command_available(command)

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    worktree_path = WORKTREES_DIR / run_id
    _write_heartbeat(phase="preflight", status="running", extra={"run_id": run_id})
    hydrate_approved_source_cache(policy, SOURCE_CACHE_DIR)
    port_forward_pid = _ensure_cluster_prereqs(policy=policy, run_id=run_id)
    create_detached_worktree(REPO_ROOT, policy.branch, worktree_path)
    _write_heartbeat(phase="ready", status="running", extra={"run_id": run_id})
    try:
        research_payload = _run_researcher(
            agent=agents["infra_researcher"],
            policy=policy,
            run_dir=run_dir,
            worktree_path=worktree_path,
        )
        write_json(CURRENT_TASK_PATH, research_payload)
        _write_heartbeat(
            phase="implementing",
            status="running",
            extra={"run_id": run_id, "task_id": research_payload["task_id"]},
        )
        _run_implementer(
            agent=agents["infra_implementer"],
            policy=policy,
            run_dir=run_dir,
            worktree_path=worktree_path,
            research_payload=research_payload,
        )
        changed_paths = changed_paths_for_worktree(worktree_path)
        if not changed_paths:
            raise RuntimeError("Implementer produced no changes.")
        if len(changed_paths) > policy.max_files_changed_per_loop:
            raise RuntimeError(
                "Implementer changed too many files for one bounded loop: "
                f"{len(changed_paths)} > {policy.max_files_changed_per_loop}"
            )
        path_violations = validate_changed_paths(changed_paths, policy)
        if path_violations:
            raise RuntimeError(
                "Implementer touched disallowed paths: "
                + ", ".join(path_violations)
            )
        verification_commands = select_verification_commands(changed_paths, policy)
        verification_results = _run_verification_commands(
            worktree_path=worktree_path,
            commands=verification_commands,
        )
        verifier_payload = _run_verifier(
            agent=agents["infra_verifier"],
            policy=policy,
            run_dir=run_dir,
            worktree_path=worktree_path,
            research_payload=research_payload,
            changed_paths=changed_paths,
            verification_results=verification_results,
        )
        citation_violations = citations_use_allowed_sources(
            verifier_payload.get("citations", []),
            policy,
        )
        if citation_violations:
            raise RuntimeError(
                "Verifier cited non-whitelisted sources: "
                + ", ".join(citation_violations)
            )
        if not verifier_payload["approved"]:
            raise RuntimeError(
                "Verifier rejected iteration: "
                + "; ".join(verifier_payload.get("violations", []))
            )
        if policy.auto_commit:
            commit_all(worktree_path, verifier_payload["commit_message"])
        accepted_commit = _git_stdout(worktree_path, "rev-parse", "HEAD").strip()
        advance_branch(REPO_ROOT, policy.branch, accepted_commit)
        state_payload = {
            "status": "accepted",
            "branch": policy.branch,
            "run_id": run_id,
            "task_id": research_payload["task_id"],
            "task_title": research_payload["title"],
            "last_commit": accepted_commit,
            "changed_paths": changed_paths,
            "port_forward_pid": port_forward_pid,
            "completed_at": _utc_now_iso(),
        }
        write_json(STATE_PATH, state_payload)
        return state_payload
    finally:
        remove_worktree(REPO_ROOT, worktree_path)


def _run_researcher(
    *,
    agent,
    policy,
    run_dir: Path,
    worktree_path: Path,
) -> dict[str, Any]:
    schema_path = run_dir / "research-output-schema.json"
    output_path = run_dir / "research-output.json"
    _write_schema(schema_path, _research_schema())
    prompt = (
        f"{agent.developer_instructions}\n\n"
        "Repository policy:\n"
        f"{policy_prompt_block(policy)}\n\n"
        f"Use roadmap file `{policy.roadmap_path}`.\n"
        "Select the next single approved infra task for the local cluster lane.\n"
        "Use repo files, local cluster state, and cached approved-source docs under "
        f"`{SOURCE_CACHE_DIR.relative_to(REPO_ROOT)}`.\n"
        "Output only JSON matching the supplied schema.\n"
    )
    command = build_codex_exec_command(
        prompt=prompt,
        agent=agent,
        workdir=worktree_path,
        output_path=output_path,
        output_schema_path=schema_path,
    )
    run_subprocess(command, cwd=worktree_path)
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_implementer(
    *,
    agent,
    policy,
    run_dir: Path,
    worktree_path: Path,
    research_payload: dict[str, Any],
) -> None:
    output_path = run_dir / "implementer-output.txt"
    prompt = (
        f"{agent.developer_instructions}\n\n"
        "Repository policy:\n"
        f"{policy_prompt_block(policy)}\n\n"
        "Implement exactly this bounded task:\n"
        f"{json.dumps(research_payload, indent=2, sort_keys=True)}\n\n"
        "Work only in this detached worktree. Keep the change set minimal, "
        "complete, and inside policy. At the end, summarize what changed.\n"
    )
    command = build_codex_exec_command(
        prompt=prompt,
        agent=agent,
        workdir=worktree_path,
        output_path=output_path,
    )
    run_subprocess(command, cwd=worktree_path)


def _run_verifier(
    *,
    agent,
    policy,
    run_dir: Path,
    worktree_path: Path,
    research_payload: dict[str, Any],
    changed_paths: list[str],
    verification_results: list[dict[str, Any]],
) -> dict[str, Any]:
    schema_path = run_dir / "verifier-output-schema.json"
    output_path = run_dir / "verifier-output.json"
    _write_schema(schema_path, _verifier_schema())
    prompt = (
        f"{agent.developer_instructions}\n\n"
        "Repository policy:\n"
        f"{policy_prompt_block(policy)}\n\n"
        "Current approved task:\n"
        f"{json.dumps(research_payload, indent=2, sort_keys=True)}\n\n"
        "Changed paths:\n"
        f"{json.dumps(changed_paths, indent=2)}\n\n"
        "Local verification results:\n"
        f"{json.dumps(verification_results, indent=2, sort_keys=True)}\n\n"
        "Reject if scope, source, or verification policy was violated.\n"
        "Output only JSON matching the supplied schema.\n"
    )
    command = build_codex_exec_command(
        prompt=prompt,
        agent=agent,
        workdir=worktree_path,
        output_path=output_path,
        output_schema_path=schema_path,
    )
    run_subprocess(command, cwd=worktree_path)
    return json.loads(output_path.read_text(encoding="utf-8"))


def _run_verification_commands(
    *,
    worktree_path: Path,
    commands: list[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(
            ["/bin/bash", "-lc", command],
            cwd=worktree_path,
            text=True,
            capture_output=True,
        )
        result = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
            "ok": completed.returncode == 0,
        }
        results.append(result)
        if completed.returncode != 0:
            raise RuntimeError(
                "Verification command failed: "
                f"{command}\n{completed.stderr.strip()}"
            )
    return results


def _ensure_cluster_prereqs(*, policy, run_id: str) -> int | None:
    cluster_list = _run_cluster_prereq_command(
        ["k3d", "cluster", "list"],
        error_message=(
            "Unable to inspect local k3d clusters. Verify `k3d` is installed "
            "and the configured local cluster is available"
        ),
    )
    if not _cluster_exists(cluster_list.stdout, policy.cluster_name):
        raise RuntimeError(
            "Configured k3d cluster "
            f"'{policy.cluster_name}' is not available. Start it with `make k8s-up`."
        )
    current_context = _run_cluster_prereq_command(
        ["kubectl", "config", "current-context"],
        error_message=(
            "Unable to read the active kubectl context. Verify kubeconfig is "
            "configured for the local cluster"
        ),
    ).stdout.strip()
    expected_context = _expected_k3d_context(policy.cluster_name)
    if current_context != expected_context:
        display_context = current_context or "<empty>"
        raise RuntimeError(
            "kubectl current context "
            f"'{display_context}' does not match configured local cluster context "
            f"'{expected_context}'."
        )
    _run_cluster_prereq_command(
        ["kubectl", "cluster-info"],
        error_message=(
            "Unable to reach configured local cluster context "
            f"'{expected_context}'. Verify the cluster is running and kubectl "
            "can connect"
        ),
    )
    _ensure_helm_release(policy)
    if port_is_open("127.0.0.1", policy.postgres_local_port):
        return _existing_port_forward_pid()
    PORT_FORWARD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    port_forward_log = PORT_FORWARD_LOG_PATH.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [
            "kubectl",
            "port-forward",
            policy.postgres_service,
            f"{policy.postgres_local_port}:{policy.postgres_local_port}",
            "-n",
            policy.helm_namespace,
        ],
        cwd=REPO_ROOT,
        stdout=port_forward_log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _record_managed_port_forward_state(
        policy=policy,
        run_id=run_id,
        port_forward_pid=process.pid,
    )
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if port_is_open("127.0.0.1", policy.postgres_local_port):
            return process.pid
        time.sleep(0.25)
    process.terminate()
    _clear_managed_port_forward_state(process.pid)
    raise RuntimeError(
        "Unable to establish local Postgres port-forward on "
        f"127.0.0.1:{policy.postgres_local_port}"
    )


def _ensure_helm_release(policy) -> None:
    status_command = [
        "helm",
        "status",
        policy.helm_release,
        "-n",
        policy.helm_namespace,
    ]
    try:
        run_subprocess(status_command, cwd=REPO_ROOT)
        return
    except subprocess.CalledProcessError as exc:
        if not _helm_release_missing(exc):
            raise RuntimeError(
                "Unable to verify local Helm release "
                f"'{policy.helm_release}' in namespace '{policy.helm_namespace}': "
                f"{_called_process_detail(exc)}"
            ) from exc

    install_command = [
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
    ]
    try:
        run_subprocess(install_command, cwd=REPO_ROOT)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Unable to reconcile local Helm release "
            f"'{policy.helm_release}' in namespace '{policy.helm_namespace}': "
            f"{_called_process_detail(exc)}"
        ) from exc


def _run_cluster_prereq_command(
    command: list[str],
    *,
    error_message: str,
) -> subprocess.CompletedProcess[str]:
    try:
        return run_subprocess(command, cwd=REPO_ROOT)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"{error_message}: {_called_process_detail(exc)}"
        ) from exc


def _helm_release_missing(error: subprocess.CalledProcessError) -> bool:
    detail = _called_process_detail(error).lower()
    return "release" in detail and "not found" in detail


def _called_process_detail(error: subprocess.CalledProcessError) -> str:
    detail = (error.stderr or error.stdout or "").strip()
    if detail:
        return detail
    return str(error)


def _existing_port_forward_pid(
    *,
    state_path: Path | None = None,
    pid_path: Path | None = None,
) -> int | None:
    state_path = STATE_PATH if state_path is None else state_path
    pid_path = PORT_FORWARD_PID_PATH if pid_path is None else pid_path
    pid = _read_pid(pid_path)
    if pid is not None:
        if _pid_is_running(pid):
            return pid
        _safe_unlink(pid_path)
    if not state_path.exists():
        return None
    payload = read_json(state_path)
    candidate = payload.get("port_forward_pid")
    if isinstance(candidate, int) and _pid_is_running(candidate):
        _write_pid(pid_path, candidate)
        return candidate
    return None


def _cluster_exists(cluster_list_output: str, cluster_name: str) -> bool:
    for line in cluster_list_output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("name"):
            continue
        if stripped.split()[0] == cluster_name:
            return True
    return False


def _expected_k3d_context(cluster_name: str) -> str:
    return f"k3d-{cluster_name}"


def _record_managed_port_forward_state(
    *,
    policy,
    run_id: str,
    port_forward_pid: int,
) -> None:
    _write_pid(PORT_FORWARD_PID_PATH, port_forward_pid)
    payload = read_json(STATE_PATH) if STATE_PATH.exists() else {}
    payload.update(
        {
            "status": "running",
            "branch": policy.branch,
            "run_id": run_id,
            "port_forward_pid": port_forward_pid,
            "updated_at": _utc_now_iso(),
        }
    )
    write_json(STATE_PATH, payload)


def _clear_managed_port_forward_state(port_forward_pid: int) -> None:
    if _read_pid(PORT_FORWARD_PID_PATH) == port_forward_pid:
        _safe_unlink(PORT_FORWARD_PID_PATH)
    if not STATE_PATH.exists():
        return
    payload = read_json(STATE_PATH)
    if payload.get("port_forward_pid") != port_forward_pid:
        return
    payload.pop("port_forward_pid", None)
    payload["updated_at"] = _utc_now_iso()
    write_json(STATE_PATH, payload)


def _write_failure_state(*, error: str) -> dict[str, Any]:
    failure_payload = read_json(STATE_PATH) if STATE_PATH.exists() else {}
    failure_payload.update(
        {
            "status": "failed",
            "error": error,
            "failed_at": _utc_now_iso(),
        }
    )
    port_forward_pid = _existing_port_forward_pid()
    if port_forward_pid is not None:
        failure_payload["port_forward_pid"] = port_forward_pid
    write_json(STATE_PATH, failure_payload)
    return failure_payload


def _show_status(runtime_root: Path) -> int:
    print(_format_status_summary(_runtime_status(runtime_root)))
    return 0


def _stop_supervisor(runtime_root: Path) -> int:
    status = _runtime_status(runtime_root)
    _terminate_process(status["supervisor_pid"])
    _terminate_process(status["port_forward_pid"])
    _cleanup_runtime_markers(runtime_root)
    print("Stopped local infra loop supervisor.")
    return 0


def _ensure_single_supervisor(runtime_root: Path) -> None:
    pid_path = runtime_root / "supervisor.pid"
    if not pid_path.exists():
        return
    existing_pid = int(pid_path.read_text(encoding="utf-8").strip())
    if _pid_is_running(existing_pid):
        raise RuntimeError(
            f"Local infra loop supervisor is already running with PID {existing_pid}."
        )
    pid_path.unlink()


def _pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_pid(path: Path, pid: int | None = None) -> None:
    value = os.getpid() if pid is None else pid
    path.write_text(f"{value}\n", encoding="utf-8")


def _write_heartbeat(*, phase: str, status: str, extra: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "phase": phase,
        "status": status,
        "updated_at": _utc_now_iso(),
    }
    payload.update(extra)
    write_json(HEARTBEAT_PATH, payload)


def _wait_for_startup_signal(
    runtime_root: Path,
    *,
    launcher_pid: int,
    timeout_seconds: float,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        startup_status = _startup_signal_status(runtime_root)
        if startup_status == "ready":
            return 0
        if startup_status == "failed":
            print(
                "Infra loop supervisor entered a failed startup state. "
                f"See {runtime_root / SUPERVISOR_LOG_PATH.name}.",
                file=sys.stderr,
            )
            return 1
        if not _pid_is_running(launcher_pid):
            print(
                "Infra loop supervisor exited before publishing a ready startup "
                f"signal. See {runtime_root / SUPERVISOR_LOG_PATH.name}.",
                file=sys.stderr,
            )
            return 1
        time.sleep(0.25)
    print(
        "Infra loop supervisor did not publish a ready startup signal within "
        f"{timeout_seconds:g} seconds. See {runtime_root / SUPERVISOR_LOG_PATH.name}.",
        file=sys.stderr,
    )
    return 1


def _startup_signal_status(runtime_root: Path) -> str:
    heartbeat_path = runtime_root / HEARTBEAT_PATH.name
    if not heartbeat_path.exists():
        return "waiting"
    heartbeat = read_json(heartbeat_path)
    if not isinstance(heartbeat, dict):
        return "waiting"
    phase = heartbeat.get("phase")
    status = heartbeat.get("status")
    if phase == "backoff" or status == "failed":
        return "failed"
    if isinstance(phase, str) and phase in STARTUP_READY_PHASES:
        return "ready"
    return "waiting"


def _runtime_status(runtime_root: Path) -> dict[str, Any]:
    pid_path = runtime_root / "supervisor.pid"
    heartbeat_path = runtime_root / "heartbeat.json"
    state_path = runtime_root / "state.json"
    current_task_path = runtime_root / "current_task.json"
    supervisor_pid = _read_pid(pid_path)
    supervisor_running = False
    if supervisor_pid is not None:
        supervisor_running = _pid_is_running(supervisor_pid)
        if not supervisor_running:
            _safe_unlink(pid_path)
            supervisor_pid = None
    state = read_json(state_path) if state_path.exists() else None
    heartbeat = read_json(heartbeat_path) if heartbeat_path.exists() else None
    current_task = read_json(current_task_path) if current_task_path.exists() else None
    port_forward_pid = _existing_port_forward_pid(
        state_path=state_path,
        pid_path=runtime_root / "port-forward.pid",
    )
    port_forward_running = port_forward_pid is not None
    if port_forward_pid is None and isinstance(state, dict):
        candidate = state.get("port_forward_pid")
        if isinstance(candidate, int):
            port_forward_pid = candidate
            port_forward_running = _pid_is_running(candidate)
    return {
        "supervisor_pid": supervisor_pid,
        "supervisor_running": supervisor_running,
        "heartbeat": heartbeat,
        "heartbeat_stale": bool(heartbeat) and not supervisor_running,
        "state": state,
        "current_task": current_task,
        "port_forward_pid": port_forward_pid,
        "port_forward_running": port_forward_running,
    }


def _format_status_summary(status: dict[str, Any]) -> str:
    heartbeat = status["heartbeat"] if isinstance(status["heartbeat"], dict) else {}
    state = status["state"] if isinstance(status["state"], dict) else {}
    current_task = (
        status["current_task"] if isinstance(status["current_task"], dict) else {}
    )

    supervisor_line = "running"
    if not status["supervisor_running"]:
        supervisor_line = "stopped"
    elif status["supervisor_pid"] is not None:
        supervisor_line = f"running (pid {status['supervisor_pid']})"

    heartbeat_line = "none"
    if heartbeat:
        heartbeat_state = heartbeat.get("status", "unknown")
        heartbeat_phase = heartbeat.get("phase", "unknown")
        heartbeat_updated_at = heartbeat.get("updated_at", "unknown")
        heartbeat_prefix = "stale " if status["heartbeat_stale"] else ""
        heartbeat_line = (
            f"{heartbeat_prefix}{heartbeat_state} "
            f"({heartbeat_phase}) at {heartbeat_updated_at}"
        )

    last_run = _first_string(heartbeat.get("run_id"), state.get("run_id")) or "n/a"
    task_line = _format_task_summary(current_task, heartbeat, state)
    last_commit = _first_string(state.get("last_commit")) or "n/a"

    lines = [
        f"Supervisor: {supervisor_line}",
        f"Heartbeat: {heartbeat_line}",
        f"Last run: {last_run}",
        f"Task: {task_line}",
        f"Last accepted commit: {last_commit}",
    ]
    if state:
        lines.append(f"Recorded state: {state.get('status', 'unknown')}")
    if status["port_forward_pid"] is not None:
        port_forward_state = "running" if status["port_forward_running"] else "stale"
        lines.append(
            "Managed Postgres port-forward: "
            f"pid {status['port_forward_pid']} ({port_forward_state})"
        )
    else:
        lines.append("Managed Postgres port-forward: none")
    return "\n".join(lines)


def _format_task_summary(
    current_task: dict[str, Any],
    heartbeat: dict[str, Any],
    state: dict[str, Any],
) -> str:
    task_id = _first_string(
        current_task.get("task_id"),
        heartbeat.get("task_id"),
        state.get("task_id"),
    )
    task_title = _first_string(current_task.get("title"), state.get("task_title"))
    if task_id and task_title:
        return f"{task_id} {task_title}"
    if task_id:
        return task_id
    if task_title:
        return task_title
    return "n/a"


def _first_string(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _cleanup_runtime_markers(runtime_root: Path) -> None:
    for marker_path in (
        runtime_root / "supervisor.pid",
        runtime_root / "heartbeat.json",
        runtime_root / "current_task.json",
        runtime_root / "launcher.pid",
        runtime_root / "port-forward.pid",
    ):
        _safe_unlink(marker_path)
    state_path = runtime_root / "state.json"
    if not state_path.exists():
        return
    payload = read_json(state_path)
    payload["status"] = "stopped"
    payload.pop("port_forward_pid", None)
    payload["stopped_at"] = _utc_now_iso()
    payload["updated_at"] = _utc_now_iso()
    write_json(state_path, payload)


def _terminate_process(pid: int | None, timeout_seconds: float = 5.0) -> None:
    if pid is None or not _pid_is_running(pid):
        return
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _pid_is_running(pid):
            return
        time.sleep(0.1)
    if _pid_is_running(pid):
        os.kill(pid, signal.SIGKILL)


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _safe_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _research_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "task_id",
            "title",
            "summary",
            "files_to_touch",
            "commands_to_run",
            "acceptance_criteria",
            "citations",
        ],
        "properties": {
            "task_id": {"type": "string"},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "files_to_touch": {"type": "array", "items": {"type": "string"}},
            "commands_to_run": {"type": "array", "items": {"type": "string"}},
            "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
            "citations": {"type": "array", "items": {"type": "string"}},
        },
    }


def _verifier_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "approved",
            "summary",
            "commit_message",
            "violations",
            "citations",
        ],
        "properties": {
            "approved": {"type": "boolean"},
            "summary": {"type": "string"},
            "commit_message": {"type": "string"},
            "violations": {"type": "array", "items": {"type": "string"}},
            "citations": {"type": "array", "items": {"type": "string"}},
        },
    }


def _write_schema(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _git_stdout(repo_root: Path, *args: str) -> str:
    return run_subprocess(["git", *args], cwd=repo_root).stdout


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    sys.exit(main())
