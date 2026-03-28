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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY_PATH)
    parser.add_argument("--codex-config", type=Path, default=DEFAULT_CODEX_CONFIG_PATH)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args()

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
        if SUPERVISOR_PID_PATH.exists():
            SUPERVISOR_PID_PATH.unlink()


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
    cluster_list = run_subprocess(["k3d", "cluster", "list"], cwd=REPO_ROOT)
    if not _cluster_exists(cluster_list.stdout, policy.cluster_name):
        raise RuntimeError(
            "Configured k3d cluster "
            f"'{policy.cluster_name}' is not available. Start it with `make k8s-up`."
        )
    current_context = run_subprocess(
        ["kubectl", "config", "current-context"],
        cwd=REPO_ROOT,
    ).stdout.strip()
    expected_context = _expected_k3d_context(policy.cluster_name)
    if current_context != expected_context:
        display_context = current_context or "<empty>"
        raise RuntimeError(
            "kubectl current context "
            f"'{display_context}' does not match configured local cluster context "
            f"'{expected_context}'."
        )
    run_subprocess(["kubectl", "cluster-info"], cwd=REPO_ROOT)
    run_subprocess(
        [
            "helm",
            "status",
            policy.helm_release,
            "-n",
            policy.helm_namespace,
        ],
        cwd=REPO_ROOT,
    )
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


def _existing_port_forward_pid() -> int | None:
    if not STATE_PATH.exists():
        return None
    payload = read_json(STATE_PATH)
    pid = payload.get("port_forward_pid")
    if isinstance(pid, int) and _pid_is_running(pid):
        return pid
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
    if not STATE_PATH.exists():
        return
    payload = read_json(STATE_PATH)
    if payload.get("port_forward_pid") != port_forward_pid:
        return
    payload.pop("port_forward_pid", None)
    payload["updated_at"] = _utc_now_iso()
    write_json(STATE_PATH, payload)


def _write_failure_state(*, error: str) -> dict[str, Any]:
    failure_payload = {
        "status": "failed",
        "error": error,
        "failed_at": _utc_now_iso(),
    }
    port_forward_pid = _existing_port_forward_pid()
    if port_forward_pid is not None:
        failure_payload["port_forward_pid"] = port_forward_pid
    write_json(STATE_PATH, failure_payload)
    return failure_payload


def _show_status(runtime_root: Path) -> int:
    state_path = runtime_root / "state.json"
    heartbeat_path = runtime_root / "heartbeat.json"
    pid_path = runtime_root / "supervisor.pid"
    payload = {
        "supervisor_running": False,
        "supervisor_pid": None,
        "heartbeat": None,
        "state": None,
    }
    if pid_path.exists():
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        payload["supervisor_pid"] = pid
        payload["supervisor_running"] = _pid_is_running(pid)
    if heartbeat_path.exists():
        payload["heartbeat"] = read_json(heartbeat_path)
    if state_path.exists():
        payload["state"] = read_json(state_path)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _stop_supervisor(runtime_root: Path) -> int:
    pid_path = runtime_root / "supervisor.pid"
    state_path = runtime_root / "state.json"
    if pid_path.exists():
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        if _pid_is_running(pid):
            os.kill(pid, signal.SIGTERM)
    if state_path.exists():
        payload = read_json(state_path)
        port_forward_pid = payload.get("port_forward_pid")
        if isinstance(port_forward_pid, int) and _pid_is_running(port_forward_pid):
            os.kill(port_forward_pid, signal.SIGTERM)
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


def _write_pid(path: Path) -> None:
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")


def _write_heartbeat(*, phase: str, status: str, extra: dict[str, Any]) -> None:
    payload: dict[str, Any] = {
        "phase": phase,
        "status": status,
        "updated_at": _utc_now_iso(),
    }
    payload.update(extra)
    write_json(HEARTBEAT_PATH, payload)


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
