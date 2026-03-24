"""Generic local autonomous loop supervisor."""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cbb.infra_loop import (
    DEFAULT_CODEX_CONFIG_PATH,
    DEFAULT_POLICY_DIR,
    DEFAULT_SUPERVISOR_RUNTIME_ROOT,
    REPO_ROOT,
    LaneAgentSet,
    LaneRuntimePaths,
    LoopPolicy,
    advance_branch,
    build_codex_exec_command,
    changed_paths_for_worktree,
    citations_use_allowed_sources,
    commit_all,
    create_detached_worktree,
    ensure_command_available,
    ensure_lane_runtime_dirs,
    ensure_local_branch,
    ensure_single_supervisor,
    ensure_worktree_venv,
    hydrate_approved_source_cache,
    lane_runtime_paths,
    load_agent_config,
    load_codex_agent_registry,
    load_lane_agent_set,
    load_loop_policies,
    pid_is_running,
    policy_prompt_block,
    port_is_open,
    read_json,
    remove_worktree,
    repo_is_clean,
    run_subprocess,
    select_verification_commands,
    utc_now_iso,
    validate_changed_paths,
    write_heartbeat,
    write_json,
    write_pid,
)


@dataclass(frozen=True)
class LaneContext:
    """One enabled lane and its resolved runtime state."""

    policy: LoopPolicy
    agents: LaneAgentSet
    runtime: LaneRuntimePaths


def main(argv: Sequence[str] | None = None) -> int:
    """Run the generic autonomous loop CLI."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--policy-dir", type=Path, default=DEFAULT_POLICY_DIR)
    parser.add_argument("--policy", type=Path)
    parser.add_argument(
        "--codex-config",
        type=Path,
        default=DEFAULT_CODEX_CONFIG_PATH,
    )
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=DEFAULT_SUPERVISOR_RUNTIME_ROOT,
    )
    parser.add_argument("--lanes", default="infra,model,ux")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--stop", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    lanes = _parse_lanes(args.lanes)
    policy_overrides = _policy_overrides(args.policy, lanes)

    if args.status:
        return show_status(args.runtime_root, lanes)
    if args.stop:
        return stop_supervisor(args.runtime_root, lanes)

    return run_supervisor(
        policy_dir=args.policy_dir,
        policy_overrides=policy_overrides,
        codex_config=args.codex_config,
        runtime_root=args.runtime_root,
        lanes=lanes,
        once=args.once,
    )


def run_supervisor(
    *,
    policy_dir: Path,
    policy_overrides: dict[str, Path],
    codex_config: Path,
    runtime_root: Path,
    lanes: tuple[str, ...],
    once: bool,
) -> int:
    """Run the long-lived autonomous supervisor."""

    policies = load_loop_policies(
        policy_dir,
        lanes,
        policy_overrides=policy_overrides,
    )
    registry = load_codex_agent_registry(codex_config)
    orchestrator = load_agent_config(registry["loop_orchestrator"].config_file)
    contexts = {
        lane: LaneContext(
            policy=policy,
            agents=load_lane_agent_set(policy, registry),
            runtime=lane_runtime_paths(runtime_root, policy.runtime_subdir),
        )
        for lane, policy in policies.items()
    }

    runtime_root.mkdir(parents=True, exist_ok=True)
    _orchestrator_runs_dir(runtime_root).mkdir(parents=True, exist_ok=True)
    for context in contexts.values():
        ensure_lane_runtime_dirs(context.runtime)

    supervisor_pid_path = runtime_root / "supervisor.pid"
    supervisor_heartbeat_path = runtime_root / "heartbeat.json"
    ensure_single_supervisor(supervisor_pid_path, "Local autonomous loop supervisor")
    write_pid(supervisor_pid_path)
    try:
        for context in contexts.values():
            ensure_local_branch(REPO_ROOT, context.policy.branch)

        while True:
            selection = _select_lane(
                orchestrator=orchestrator,
                contexts=contexts,
                runtime_root=runtime_root,
            )
            if selection is None:
                heartbeat = {
                    "status": "idle",
                    "reason": "No enabled lane is currently eligible to run.",
                }
                write_heartbeat(
                    supervisor_heartbeat_path,
                    phase="idle",
                    status="idle",
                    extra=heartbeat,
                )
                if once:
                    return 0
                time.sleep(_idle_sleep_seconds(contexts))
                continue

            lane = selection["lane"]
            context = contexts[lane]
            write_heartbeat(
                supervisor_heartbeat_path,
                phase="running",
                status="running",
                extra=selection,
            )
            result = _run_lane_with_recovery(context)
            supervisor_payload = dict(selection)
            supervisor_payload["lane_result"] = result
            write_heartbeat(
                supervisor_heartbeat_path,
                phase="sleeping",
                status=result["status"],
                extra=supervisor_payload,
            )
            if once:
                return 0
            time.sleep(context.policy.sleep_seconds)
    finally:
        if supervisor_pid_path.exists():
            supervisor_pid_path.unlink()


def show_status(runtime_root: Path, lanes: Sequence[str]) -> int:
    """Print supervisor and lane status as JSON."""

    pid_path = runtime_root / "supervisor.pid"
    heartbeat_path = runtime_root / "heartbeat.json"
    payload: dict[str, Any] = {
        "supervisor_running": False,
        "supervisor_pid": None,
        "heartbeat": None,
        "lanes": {},
    }
    if pid_path.exists():
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        payload["supervisor_pid"] = pid
        payload["supervisor_running"] = pid_is_running(pid)
    if heartbeat_path.exists():
        payload["heartbeat"] = read_json(heartbeat_path)
    for lane in lanes:
        runtime = lane_runtime_paths(runtime_root, lane)
        lane_payload: dict[str, Any] = {
            "heartbeat": None,
            "state": None,
        }
        if runtime.heartbeat_path.exists():
            lane_payload["heartbeat"] = read_json(runtime.heartbeat_path)
        if runtime.state_path.exists():
            lane_payload["state"] = read_json(runtime.state_path)
        payload["lanes"][lane] = lane_payload
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def stop_supervisor(runtime_root: Path, lanes: Sequence[str]) -> int:
    """Stop the supervisor and any tracked managed helper processes."""

    pid_path = runtime_root / "supervisor.pid"
    if pid_path.exists():
        pid = int(pid_path.read_text(encoding="utf-8").strip())
        if pid_is_running(pid):
            os.kill(pid, signal.SIGTERM)

    for lane in lanes:
        runtime = lane_runtime_paths(runtime_root, lane)
        if not runtime.state_path.exists():
            continue
        state = read_json(runtime.state_path)
        for pid in _managed_pids_from_state(state):
            if pid_is_running(pid):
                os.kill(pid, signal.SIGTERM)

    print("Stopped local autonomous loop supervisor.")
    return 0


def _run_lane_with_recovery(context: LaneContext) -> dict[str, Any]:
    """Run one lane iteration and record failures locally."""

    try:
        return _run_lane_iteration(context)
    except Exception as exc:
        previous_state = _read_lane_state(context.runtime)
        failure_count = int(previous_state.get("consecutive_failures", 0)) + 1
        state_payload = {
            "status": "failed",
            "lane": context.policy.lane,
            "branch": context.policy.branch,
            "error": str(exc),
            "failed_at": utc_now_iso(),
            "consecutive_failures": failure_count,
            "backoff_until": _backoff_until(context.policy),
            "managed_pids": previous_state.get("managed_pids", []),
        }
        write_json(context.runtime.state_path, state_payload)
        write_heartbeat(
            context.runtime.heartbeat_path,
            phase="backoff",
            status="failed",
            extra=state_payload,
        )
        return state_payload


def _run_lane_iteration(context: LaneContext) -> dict[str, Any]:
    """Run one accepted or rejected lane iteration."""

    policy = context.policy
    runtime = context.runtime

    if not repo_is_clean(REPO_ROOT):
        raise RuntimeError(
            "Primary worktree is dirty. Autonomous loops require a clean repo."
        )

    for command in ("codex", "git"):
        ensure_command_available(command)
    if policy.lane == "infra":
        for command in ("helm", "kubectl", "k3d"):
            ensure_command_available(command)

    run_id = utc_now_iso().replace(":", "").replace("+00:00", "Z")
    run_id = run_id.replace("-", "")
    run_dir = runtime.runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    worktree_path = runtime.worktrees_dir / run_id

    write_heartbeat(
        runtime.heartbeat_path,
        phase="preflight",
        status="running",
        extra={"lane": policy.lane, "run_id": run_id},
    )

    hydrate_approved_source_cache(policy, runtime.source_cache_dir)
    managed_pids: list[int] = []
    port_forward_pid = _ensure_lane_prereqs(context)
    if port_forward_pid is not None:
        managed_pids.append(port_forward_pid)

    create_detached_worktree(REPO_ROOT, policy.branch, worktree_path)
    try:
        ensure_worktree_venv(REPO_ROOT, worktree_path)
        research_payload = _run_researcher(
            context=context,
            run_dir=run_dir,
            worktree_path=worktree_path,
        )
        write_json(runtime.current_task_path, research_payload)
        write_heartbeat(
            runtime.heartbeat_path,
            phase="implementing",
            status="running",
            extra={
                "lane": policy.lane,
                "run_id": run_id,
                "task_id": research_payload["task_id"],
            },
        )
        _run_implementer(
            context=context,
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
        verification_commands = select_verification_commands(
            changed_paths,
            policy,
            research_payload.get("commands_to_run", []),
        )
        verification_results = _run_verification_commands(
            worktree_path=worktree_path,
            commands=verification_commands,
        )
        verifier_payload = _run_verifier(
            context=context,
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
            previous_state = _read_lane_state(runtime)
            rejection_payload = {
                "status": "rejected",
                "lane": policy.lane,
                "branch": policy.branch,
                "run_id": run_id,
                "task_id": research_payload["task_id"],
                "task_title": research_payload["title"],
                "changed_paths": changed_paths,
                "violations": verifier_payload.get("violations", []),
                "summary": verifier_payload["summary"],
                "completed_at": utc_now_iso(),
                "consecutive_failures": (
                    int(previous_state.get("consecutive_failures", 0)) + 1
                ),
                "backoff_until": _backoff_until(policy),
                "managed_pids": managed_pids,
            }
            write_json(runtime.state_path, rejection_payload)
            write_heartbeat(
                runtime.heartbeat_path,
                phase="rejected",
                status="rejected",
                extra=rejection_payload,
            )
            return rejection_payload
        if policy.auto_commit:
            commit_all(worktree_path, verifier_payload["commit_message"])
        accepted_commit = _git_stdout(worktree_path, "rev-parse", "HEAD").strip()
        advance_branch(REPO_ROOT, policy.branch, accepted_commit)
        state_payload = {
            "status": "accepted",
            "lane": policy.lane,
            "branch": policy.branch,
            "run_id": run_id,
            "task_id": research_payload["task_id"],
            "task_title": research_payload["title"],
            "last_commit": accepted_commit,
            "changed_paths": changed_paths,
            "completed_at": utc_now_iso(),
            "consecutive_failures": 0,
            "managed_pids": managed_pids,
        }
        if port_forward_pid is not None:
            state_payload["port_forward_pid"] = port_forward_pid
        write_json(runtime.state_path, state_payload)
        write_heartbeat(
            runtime.heartbeat_path,
            phase="accepted",
            status="accepted",
            extra=state_payload,
        )
        return state_payload
    finally:
        remove_worktree(REPO_ROOT, worktree_path)


def _run_researcher(
    *,
    context: LaneContext,
    run_dir: Path,
    worktree_path: Path,
) -> dict[str, Any]:
    schema_path = run_dir / "research-output-schema.json"
    output_path = run_dir / "research-output.json"
    _write_schema(schema_path, _research_schema())
    prompt = (
        f"{context.agents.research.developer_instructions}\n\n"
        "Repository policy:\n"
        f"{policy_prompt_block(context.policy)}\n\n"
        f"Use roadmap file `{context.policy.roadmap_path}`.\n"
        f"{_research_goal(context.policy)}\n"
        "Use repo-relative paths in `files_to_touch` and local citations.\n"
        f"Do not emit absolute paths or prefix paths with `{REPO_ROOT.name}/`.\n"
        "Choose exactly one approved item.\n"
        "Output only JSON matching the supplied schema.\n"
    )
    if context.policy.source_seed_urls:
        prompt += (
            "Cached approved-source docs are available under "
            f"`{context.runtime.source_cache_dir.relative_to(REPO_ROOT)}`.\n"
        )
    if context.policy.lane == "infra":
        prompt += "You may use local cluster state for bounded infra decisions.\n"

    command = build_codex_exec_command(
        prompt=prompt,
        agent=context.agents.research,
        workdir=worktree_path,
        output_path=output_path,
        output_schema_path=schema_path,
    )
    run_subprocess(command, cwd=worktree_path)
    research_payload = json.loads(output_path.read_text(encoding="utf-8"))
    normalized_payload = _normalize_research_payload(research_payload, worktree_path)
    write_json(output_path, normalized_payload)
    return normalized_payload


def _run_implementer(
    *,
    context: LaneContext,
    run_dir: Path,
    worktree_path: Path,
    research_payload: dict[str, Any],
) -> None:
    output_path = run_dir / "implementer-output.txt"
    prompt = (
        f"{context.agents.implement.developer_instructions}\n\n"
        "Repository policy:\n"
        f"{policy_prompt_block(context.policy)}\n\n"
        "Implement exactly this bounded task:\n"
        f"{json.dumps(research_payload, indent=2, sort_keys=True)}\n\n"
        "All local file paths above are repo-relative to this detached worktree. "
        "Do not create or edit a nested copy of the repo such as "
        f"`{REPO_ROOT.name}/...`.\n"
        "Work only in this detached worktree. Keep the change set minimal, "
        "complete, and inside policy. At the end, summarize what changed.\n"
    )
    command = build_codex_exec_command(
        prompt=prompt,
        agent=context.agents.implement,
        workdir=worktree_path,
        output_path=output_path,
    )
    run_subprocess(command, cwd=worktree_path)


def _run_verifier(
    *,
    context: LaneContext,
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
        f"{context.agents.verify.developer_instructions}\n\n"
        "Repository policy:\n"
        f"{policy_prompt_block(context.policy)}\n\n"
        "Current approved task:\n"
        f"{json.dumps(research_payload, indent=2, sort_keys=True)}\n\n"
        "Changed paths:\n"
        f"{json.dumps(changed_paths, indent=2)}\n\n"
        "Local verification results:\n"
        f"{json.dumps(verification_results, indent=2, sort_keys=True)}\n\n"
        "Reject if scope, source, verification, or promotion criteria were "
        "violated. Output only JSON matching the supplied schema.\n"
    )
    command = build_codex_exec_command(
        prompt=prompt,
        agent=context.agents.verify,
        workdir=worktree_path,
        output_path=output_path,
        output_schema_path=schema_path,
    )
    run_subprocess(command, cwd=worktree_path)
    return json.loads(output_path.read_text(encoding="utf-8"))


def _select_lane(
    *,
    orchestrator,
    contexts: dict[str, LaneContext],
    runtime_root: Path,
) -> dict[str, Any] | None:
    eligible = {
        lane: context
        for lane, context in contexts.items()
        if _lane_is_eligible(context.runtime)
    }
    if not eligible:
        return None
    if len(eligible) == 1:
        lane = next(iter(eligible))
        return {
            "lane": lane,
            "reason": "Only one enabled lane is currently eligible.",
            "priority_note": "single-lane fallback",
        }

    schema_path = runtime_root / "orchestrator-selection-schema.json"
    _write_schema(schema_path, _orchestrator_schema(tuple(eligible)))
    summaries = {
        lane: _lane_summary(context)
        for lane, context in contexts.items()
    }
    prompt = (
        f"{orchestrator.developer_instructions}\n\n"
        "Enabled lane summaries:\n"
        f"{json.dumps(summaries, indent=2, sort_keys=True)}\n\n"
        "Choose exactly one eligible lane to run next.\n"
        "Prefer a lane that has approved backlog, is not in backoff, and has "
        "been idle the longest.\n"
        "Output only JSON matching the supplied schema.\n"
    )
    command = build_codex_exec_command(
        prompt=prompt,
        agent=orchestrator,
        workdir=REPO_ROOT,
        output_path=_orchestrator_output_path(runtime_root),
        output_schema_path=schema_path,
    )
    run_subprocess(command, cwd=REPO_ROOT)
    selection = json.loads(
        _orchestrator_output_path(runtime_root).read_text(encoding="utf-8")
    )
    lane = selection["lane"]
    if lane not in eligible:
        raise RuntimeError(f"Orchestrator selected ineligible lane: {lane}")
    return selection


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


def _ensure_lane_prereqs(context: LaneContext) -> int | None:
    if context.policy.lane != "infra":
        return None

    policy = context.policy
    if policy.helm_release is None or policy.helm_namespace is None:
        raise RuntimeError("Infra policy is missing Helm release configuration.")
    if policy.postgres_service is None or policy.postgres_local_port is None:
        raise RuntimeError("Infra policy is missing Postgres port-forward settings.")

    run_subprocess(["k3d", "cluster", "list"], cwd=REPO_ROOT)
    run_subprocess(["kubectl", "cluster-info"], cwd=REPO_ROOT)
    release_status = _helm_release_status(policy.helm_release, policy.helm_namespace)
    if release_status != "deployed":
        raise RuntimeError(
            "Helm release "
            f"{policy.helm_release} in namespace {policy.helm_namespace} "
            f"is not healthy: status={release_status}"
        )
    postgres_service_name = _kubectl_resource_name(policy.postgres_service)
    if not _service_has_ready_endpoints(
        postgres_service_name,
        policy.helm_namespace,
    ):
        raise RuntimeError(
            "Postgres service "
            f"{policy.postgres_service} in namespace {policy.helm_namespace} "
            "has no ready endpoints."
        )
    if port_is_open("127.0.0.1", policy.postgres_local_port):
        return _existing_port_forward_pid(context.runtime)
    port_forward_log = context.runtime.port_forward_log_path.open("a", encoding="utf-8")
    try:
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
    finally:
        port_forward_log.close()
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if port_is_open("127.0.0.1", policy.postgres_local_port):
            return process.pid
        if process.poll() is not None:
            break
        time.sleep(0.25)
    if process.poll() is None:
        process.terminate()
    error_tail = _tail_log(context.runtime.port_forward_log_path)
    message = (
        "Unable to establish local Postgres port-forward on "
        f"127.0.0.1:{policy.postgres_local_port}"
    )
    if error_tail:
        message += f": {error_tail}"
    raise RuntimeError(message)


def _existing_port_forward_pid(runtime: LaneRuntimePaths) -> int | None:
    if not runtime.state_path.exists():
        return None
    payload = read_json(runtime.state_path)
    pid = payload.get("port_forward_pid")
    if isinstance(pid, int) and pid_is_running(pid):
        return pid
    return None


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
            "promotion_criteria",
            "citations",
        ],
        "properties": {
            "task_id": {"type": "string"},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "files_to_touch": {"type": "array", "items": {"type": "string"}},
            "commands_to_run": {"type": "array", "items": {"type": "string"}},
            "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
            "promotion_criteria": {"type": "array", "items": {"type": "string"}},
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


def _orchestrator_schema(eligible_lanes: tuple[str, ...]) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["lane", "reason", "priority_note"],
        "properties": {
            "lane": {"type": "string", "enum": list(eligible_lanes)},
            "reason": {"type": "string"},
            "priority_note": {"type": "string"},
        },
    }


def _lane_summary(context: LaneContext) -> dict[str, Any]:
    state = _read_lane_state(context.runtime)
    heartbeat = _read_lane_heartbeat(context.runtime)
    return {
        "lane": context.policy.lane,
        "branch": context.policy.branch,
        "roadmap_path": context.policy.roadmap_path,
        "runtime_subdir": context.policy.runtime_subdir,
        "current_status": state.get("status"),
        "consecutive_failures": state.get("consecutive_failures", 0),
        "backoff_until": state.get("backoff_until"),
        "last_completed_at": state.get("completed_at") or state.get("failed_at"),
        "heartbeat": heartbeat,
        "eligible_now": _lane_is_eligible(context.runtime),
    }


def _read_lane_state(runtime: LaneRuntimePaths) -> dict[str, Any]:
    if not runtime.state_path.exists():
        return {}
    return read_json(runtime.state_path)


def _read_lane_heartbeat(runtime: LaneRuntimePaths) -> dict[str, Any] | None:
    if not runtime.heartbeat_path.exists():
        return None
    return read_json(runtime.heartbeat_path)


def _lane_is_eligible(runtime: LaneRuntimePaths) -> bool:
    state = _read_lane_state(runtime)
    backoff_until = state.get("backoff_until")
    if not isinstance(backoff_until, str):
        return True
    return datetime.now(UTC) >= datetime.fromisoformat(backoff_until)


def _helm_release_status(release: str, namespace: str) -> str:
    completed = run_subprocess(
        ["helm", "status", release, "-n", namespace, "-o", "json"],
        cwd=REPO_ROOT,
    )
    payload = json.loads(completed.stdout)
    info = payload.get("info", {})
    status = info.get("status")
    if not isinstance(status, str) or not status:
        raise RuntimeError(
            f"Helm release {release} returned an unreadable status payload."
        )
    return status.lower()


def _kubectl_resource_name(resource: str) -> str:
    for prefix in ("service/", "svc/"):
        if resource.startswith(prefix):
            return resource.removeprefix(prefix)
    return resource


def _service_has_ready_endpoints(service_name: str, namespace: str) -> bool:
    completed = run_subprocess(
        ["kubectl", "get", "endpoints", service_name, "-n", namespace, "-o", "json"],
        cwd=REPO_ROOT,
    )
    payload = json.loads(completed.stdout)
    subsets = payload.get("subsets")
    if not isinstance(subsets, list):
        return False
    for subset in subsets:
        if not isinstance(subset, dict):
            continue
        addresses = subset.get("addresses")
        if isinstance(addresses, list) and addresses:
            return True
    return False


def _tail_log(path: Path, *, max_lines: int = 8) -> str | None:
    if not path.exists():
        return None
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        return None
    return " | ".join(lines[-max_lines:])


def _normalize_research_payload(
    payload: dict[str, Any],
    worktree_path: Path,
) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["files_to_touch"] = [
        _normalize_repo_reference(value, worktree_path)
        for value in _string_list(payload.get("files_to_touch"))
    ]
    normalized["citations"] = [
        _normalize_repo_reference(value, worktree_path)
        for value in _string_list(payload.get("citations"))
    ]
    return normalized


def _normalize_repo_reference(reference: str, worktree_path: Path) -> str:
    value = reference.strip()
    if not value or "://" in value:
        return value

    suffix = ""
    if "#L" in value:
        value, line_suffix = value.split("#L", 1)
        suffix = f"#L{line_suffix}"
    else:
        match = re.match(r"^(.*?)(:\d+(?::\d+)?)$", value)
        if match is not None:
            value = match.group(1)
            suffix = match.group(2)

    normalized_path = _normalize_repo_path(value, worktree_path)
    return f"{normalized_path}{suffix}"


def _normalize_repo_path(path: str, worktree_path: Path) -> str:
    normalized = path.replace("\\", "/").strip()
    if not normalized:
        return normalized

    worktree_prefix = f"{worktree_path.as_posix().rstrip('/')}/"
    repo_prefix = f"{REPO_ROOT.as_posix().rstrip('/')}/"
    if normalized.startswith(worktree_prefix):
        normalized = normalized[len(worktree_prefix):]
    elif normalized.startswith(repo_prefix):
        normalized = normalized[len(repo_prefix):]

    normalized = normalized.lstrip("./")
    nested_repo_prefix = f"{REPO_ROOT.name}/"
    if normalized.startswith(nested_repo_prefix):
        normalized = normalized[len(nested_repo_prefix):]
    return normalized


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _managed_pids_from_state(state: dict[str, Any]) -> list[int]:
    managed_pids: list[int] = []
    payload = state.get("managed_pids")
    if isinstance(payload, list):
        managed_pids.extend(pid for pid in payload if isinstance(pid, int))
    port_forward_pid = state.get("port_forward_pid")
    if isinstance(port_forward_pid, int):
        managed_pids.append(port_forward_pid)
    return sorted(set(managed_pids))


def _policy_overrides(
    policy_path: Path | None,
    lanes: tuple[str, ...],
) -> dict[str, Path]:
    if policy_path is None:
        return {}
    if len(lanes) != 1:
        raise ValueError("--policy can only be used when exactly one lane is enabled.")
    return {lanes[0]: policy_path}


def _parse_lanes(raw_lanes: str) -> tuple[str, ...]:
    lanes = tuple(
        lane.strip()
        for lane in raw_lanes.split(",")
        if lane.strip()
    )
    if not lanes:
        raise ValueError("At least one lane must be enabled.")
    return lanes


def _research_goal(policy: LoopPolicy) -> str:
    if policy.lane == "infra":
        return "Select the next single approved infra task for the local cluster lane."
    if policy.lane == "model":
        return "Select the next single approved model-improvement task."
    if policy.lane == "ux":
        return "Select the next single approved UI/UX task."
    return f"Select the next single approved task for the `{policy.lane}` lane."


def _backoff_until(policy: LoopPolicy) -> str:
    deadline = time.time() + policy.failure_backoff_seconds
    return datetime.fromtimestamp(deadline, UTC).isoformat()


def _idle_sleep_seconds(contexts: dict[str, LaneContext]) -> int:
    return min(context.policy.failure_backoff_seconds for context in contexts.values())


def _orchestrator_output_path(runtime_root: Path) -> Path:
    return runtime_root / "current-selection.json"


def _orchestrator_runs_dir(runtime_root: Path) -> Path:
    return runtime_root / "orchestrator-runs"


def _write_schema(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _git_stdout(repo_root: Path, *args: str) -> str:
    return run_subprocess(["git", *args], cwd=repo_root).stdout


if __name__ == "__main__":
    sys.exit(main())
