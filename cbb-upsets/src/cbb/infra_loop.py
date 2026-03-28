"""Helpers for local autonomous loop supervisors."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import subprocess
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
GIT_REPO_ROOT = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
)
WORKTREE_PROJECT_SUBDIR = (
    Path(".")
    if REPO_ROOT == GIT_REPO_ROOT
    else REPO_ROOT.relative_to(GIT_REPO_ROOT)
)
DEFAULT_POLICY_DIR = REPO_ROOT / "ops"
DEFAULT_CODEX_CONFIG_PATH = REPO_ROOT / ".codex" / "config.toml"
DEFAULT_SUPERVISOR_RUNTIME_ROOT = REPO_ROOT / ".codex" / "local" / "auto-loop"
REQUIRED_WORKTREE_VENV_TOOLS = ("python", "ruff", "mypy", "pytest")
WORKTREE_MIRRORED_PATHS = (Path("chart/cbb-upsets/charts"),)


@dataclass(frozen=True)
class AgentRegistryEntry:
    """One agent entry defined in ``.codex/config.toml``."""

    name: str
    description: str
    config_file: Path


@dataclass(frozen=True)
class AgentConfig:
    """One agent prompt/config payload consumed by the supervisor."""

    model: str
    sandbox_mode: str
    approval_policy: str
    developer_instructions: str
    model_reasoning_effort: str | None = None


@dataclass(frozen=True)
class LoopPolicy:
    """Tracked policy for one autonomous loop lane."""

    lane: str
    branch: str
    research_agent: str
    implement_agent: str
    verify_agent: str
    runtime_subdir: str
    auto_commit: bool
    auto_push: bool
    sleep_seconds: int
    failure_backoff_seconds: int
    max_files_changed_per_loop: int
    roadmap_path: str
    allowed_paths: tuple[str, ...]
    disallowed_paths: tuple[str, ...]
    whitelist_domains: tuple[str, ...]
    extra_vendor_domains: tuple[str, ...]
    allowed_commands: tuple[str, ...]
    python_trigger_globs: tuple[str, ...]
    source_seed_urls: tuple[str, ...]
    always_verify_commands: tuple[str, ...]
    python_verify_commands: tuple[str, ...]
    cluster_name: str | None = None
    helm_release: str | None = None
    helm_namespace: str | None = None
    postgres_service: str | None = None
    postgres_local_port: int | None = None

    @property
    def allowed_domains(self) -> tuple[str, ...]:
        """Return the complete URL allowlist."""

        return self.whitelist_domains + self.extra_vendor_domains


@dataclass(frozen=True)
class LaneAgentSet:
    """Resolved research, implementation, and verification agents."""

    research: AgentConfig
    implement: AgentConfig
    verify: AgentConfig


@dataclass(frozen=True)
class LaneRuntimePaths:
    """Filesystem locations for one lane's runtime state."""

    root: Path
    state_path: Path
    heartbeat_path: Path
    current_task_path: Path
    runs_dir: Path
    worktrees_dir: Path
    source_cache_dir: Path
    port_forward_log_path: Path


def load_codex_agent_registry(config_path: Path) -> dict[str, AgentRegistryEntry]:
    """Load the tracked agent registry from ``.codex/config.toml``."""

    payload = tomllib.loads(config_path.read_text(encoding="utf-8"))
    agents_table = payload.get("agents")
    if not isinstance(agents_table, dict):
        raise ValueError(f"Missing [agents] table in {config_path}")

    registry: dict[str, AgentRegistryEntry] = {}
    for name, entry in agents_table.items():
        if not isinstance(entry, dict) or "config_file" not in entry:
            continue
        config_file = str(entry["config_file"])
        registry[name] = AgentRegistryEntry(
            name=name,
            description=str(entry.get("description", "")),
            config_file=(config_path.parent / config_file).resolve(),
        )
    return registry


def load_agent_config(path: Path) -> AgentConfig:
    """Load one agent prompt/config file."""

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    developer_instructions = payload.get("developer_instructions")
    if not isinstance(developer_instructions, str) or not developer_instructions:
        raise ValueError(f"Missing developer_instructions in {path}")
    return AgentConfig(
        model=str(payload.get("model", "gpt-5.4")),
        model_reasoning_effort=_optional_string(payload.get("model_reasoning_effort")),
        sandbox_mode=str(payload.get("sandbox_mode", "workspace-write")),
        approval_policy=str(payload.get("approval_policy", "on-request")),
        developer_instructions=developer_instructions.strip(),
    )


def load_loop_policy(path: Path) -> LoopPolicy:
    """Load the tracked loop policy for one lane."""

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        raise ValueError(f"Missing [verification] table in {path}")

    lane = str(payload.get("lane", _default_lane_from_policy_path(path)))
    research_agent, implement_agent, verify_agent = _default_agent_names_for_lane(lane)
    postgres_local_port = payload.get("postgres_local_port")

    return LoopPolicy(
        lane=lane,
        branch=str(payload["branch"]),
        research_agent=str(payload.get("research_agent", research_agent)),
        implement_agent=str(payload.get("implement_agent", implement_agent)),
        verify_agent=str(payload.get("verify_agent", verify_agent)),
        runtime_subdir=str(payload.get("runtime_subdir", lane)),
        auto_commit=bool(payload["auto_commit"]),
        auto_push=bool(payload["auto_push"]),
        sleep_seconds=int(payload["sleep_seconds"]),
        failure_backoff_seconds=int(payload["failure_backoff_seconds"]),
        max_files_changed_per_loop=int(payload["max_files_changed_per_loop"]),
        roadmap_path=str(payload["roadmap_path"]),
        allowed_paths=_string_tuple(payload.get("allowed_paths")),
        disallowed_paths=_string_tuple(payload.get("disallowed_paths")),
        whitelist_domains=_string_tuple(payload.get("whitelist_domains")),
        extra_vendor_domains=_string_tuple(payload.get("extra_vendor_domains")),
        allowed_commands=_string_tuple(payload.get("allowed_commands")),
        python_trigger_globs=_string_tuple(payload.get("python_trigger_globs")),
        source_seed_urls=_string_tuple(payload.get("source_seed_urls")),
        always_verify_commands=_string_tuple(verification.get("always")),
        python_verify_commands=_string_tuple(verification.get("python")),
        cluster_name=_optional_string(payload.get("cluster_name")),
        helm_release=_optional_string(payload.get("helm_release")),
        helm_namespace=_optional_string(payload.get("helm_namespace")),
        postgres_service=_optional_string(payload.get("postgres_service")),
        postgres_local_port=(
            None if postgres_local_port is None else int(postgres_local_port)
        ),
    )


def load_loop_policies(
    policy_dir: Path,
    lanes: Sequence[str],
    *,
    policy_overrides: dict[str, Path] | None = None,
) -> dict[str, LoopPolicy]:
    """Load one policy per enabled lane."""

    overrides = policy_overrides or {}
    return {
        lane: load_loop_policy(
            overrides.get(lane, policy_dir / f"{lane}-loop-policy.toml")
        )
        for lane in lanes
    }


def load_lane_agent_set(
    policy: LoopPolicy,
    registry: dict[str, AgentRegistryEntry],
) -> LaneAgentSet:
    """Resolve the configured agent triplet for one lane."""

    return LaneAgentSet(
        research=load_agent_config(registry[policy.research_agent].config_file),
        implement=load_agent_config(registry[policy.implement_agent].config_file),
        verify=load_agent_config(registry[policy.verify_agent].config_file),
    )


def lane_runtime_paths(runtime_root: Path, lane: str) -> LaneRuntimePaths:
    """Return the runtime paths for one lane."""

    lane_root = runtime_root / lane
    return LaneRuntimePaths(
        root=lane_root,
        state_path=lane_root / "state.json",
        heartbeat_path=lane_root / "heartbeat.json",
        current_task_path=lane_root / "current_task.json",
        runs_dir=lane_root / "runs",
        worktrees_dir=lane_root / "worktrees",
        source_cache_dir=lane_root / "approved-source-cache",
        port_forward_log_path=lane_root / "port-forward.log",
    )


def worktree_project_root(worktree_root: Path) -> Path:
    """Return the project-root path inside one detached git worktree."""

    if WORKTREE_PROJECT_SUBDIR == Path("."):
        return worktree_root
    return worktree_root / WORKTREE_PROJECT_SUBDIR


def ensure_lane_runtime_dirs(paths: LaneRuntimePaths) -> None:
    """Create the runtime directories for one lane."""

    paths.root.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    paths.worktrees_dir.mkdir(parents=True, exist_ok=True)
    paths.source_cache_dir.mkdir(parents=True, exist_ok=True)


def path_is_allowed(path: str, policy: LoopPolicy) -> bool:
    """Return whether a relative repo path is allowed by the loop policy."""

    normalized = path.replace("\\", "/").lstrip("./")
    pure_path = PurePosixPath(normalized)
    if any(pure_path.match(pattern) for pattern in policy.disallowed_paths):
        return False
    return any(pure_path.match(pattern) for pattern in policy.allowed_paths)


def validate_changed_paths(
    changed_paths: list[str],
    policy: LoopPolicy,
) -> list[str]:
    """Return changed paths that violate the allowed/disallowed path policy."""

    return [path for path in changed_paths if not path_is_allowed(path, policy)]


def url_uses_allowed_domain(url: str, policy: LoopPolicy) -> bool:
    """Return whether one HTTP(S) URL matches the policy allowlist."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    for entry in policy.allowed_domains:
        normalized = entry.strip().lower()
        if not normalized:
            continue
        allowed_host = normalized
        allowed_path: str | None = None
        if "/" in normalized:
            allowed_host, allowed_path = normalized.split("/", 1)
            allowed_path = "/" + allowed_path.strip("/")
        if host != allowed_host and not host.endswith(f".{allowed_host}"):
            continue
        if allowed_path is None:
            return True
        if path == allowed_path or path.startswith(f"{allowed_path}/"):
            return True
    return False


def citations_use_allowed_sources(
    citations: list[str],
    policy: LoopPolicy,
) -> list[str]:
    """Return citation strings that violate the URL allowlist."""

    violations: list[str] = []
    for citation in citations:
        if "://" not in citation:
            continue
        if not url_uses_allowed_domain(citation, policy):
            violations.append(citation)
    return violations


def select_verification_commands(
    changed_paths: list[str],
    policy: LoopPolicy,
    extra_commands: Sequence[str] | None = None,
) -> list[str]:
    """Return the verification commands for one changed-path set."""

    commands = list(policy.always_verify_commands)
    if any(
        PurePosixPath(path).match(pattern)
        for path in changed_paths
        for pattern in policy.python_trigger_globs
    ):
        commands.extend(policy.python_verify_commands)
    if extra_commands is not None:
        commands.extend(
            str(command)
            for command in extra_commands
            if str(command).strip()
        )
    return _dedupe_preserving_order(commands)


def build_codex_exec_command(
    *,
    prompt: str,
    agent: AgentConfig,
    workdir: Path,
    output_path: Path,
    output_schema_path: Path | None = None,
) -> list[str]:
    """Build the `codex exec` command for one loop role."""

    command = [
        "codex",
        "exec",
        "-C",
        str(workdir),
        "-m",
        agent.model,
        "-s",
        agent.sandbox_mode,
        "-c",
        f'approval_policy="{agent.approval_policy}"',
        "--color",
        "never",
        "-o",
        str(output_path),
    ]
    if agent.model_reasoning_effort is not None:
        command.extend(
            [
                "-c",
                f'model_reasoning_effort="{agent.model_reasoning_effort}"',
            ]
        )
    if output_schema_path is not None:
        command.extend(["--output-schema", str(output_schema_path)])
    command.append(prompt)
    return command


def run_subprocess(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run one subprocess command with text output enabled."""

    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def run_shell_command(
    command: str,
    *,
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    """Run one shell command string through `bash -lc`."""

    return run_subprocess(
        ["/bin/bash", "-lc", command],
        cwd=cwd,
    )


def ensure_command_available(command: str) -> None:
    """Raise when one required executable is missing from PATH."""

    if shutil.which(command) is None:
        raise FileNotFoundError(f"Required command is not on PATH: {command}")


def repo_is_clean(repo_root: Path) -> bool:
    """Return whether the primary repo worktree is clean."""

    result = run_subprocess(
        ["git", "status", "--short"],
        cwd=repo_root,
    )
    return result.stdout.strip() == ""


def ensure_local_branch(repo_root: Path, branch: str) -> None:
    """Create the dedicated local branch when it does not exist yet."""

    existing = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        cwd=repo_root,
        text=True,
        capture_output=True,
    )
    if existing.returncode == 0:
        return
    run_subprocess(
        ["git", "branch", branch, "HEAD"],
        cwd=repo_root,
    )


def create_detached_worktree(repo_root: Path, branch: str, worktree_path: Path) -> None:
    """Create a detached worktree from the current branch tip."""

    run_subprocess(
        ["git", "worktree", "prune"],
        cwd=repo_root,
    )
    run_subprocess(
        ["git", "worktree", "add", "--detach", str(worktree_path), branch],
        cwd=repo_root,
    )


def ensure_worktree_venv(repo_root: Path, worktree_path: Path) -> None:
    """Clone local-only runtime dependencies into one detached worktree."""

    source_venv = repo_root / ".venv"
    target_venv = worktree_path / ".venv"
    _validate_worktree_venv(source_venv, label="Primary repo")
    _remove_path(target_venv)
    shutil.copytree(source_venv, target_venv, symlinks=True)
    _rewrite_worktree_venv_paths(
        source_repo_root=repo_root,
        source_venv=source_venv,
        worktree_path=worktree_path,
        target_venv=target_venv,
    )
    _validate_worktree_venv(target_venv, label="Worktree")
    _mirror_worktree_support_paths(repo_root=repo_root, worktree_path=worktree_path)


def remove_worktree(repo_root: Path, worktree_path: Path) -> None:
    """Remove one detached worktree."""

    if not worktree_path.exists():
        return
    run_subprocess(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=repo_root,
    )


def advance_branch(repo_root: Path, branch: str, commit_sha: str) -> None:
    """Move the dedicated loop branch to one accepted detached-head commit."""

    run_subprocess(
        ["git", "branch", "-f", branch, commit_sha],
        cwd=repo_root,
    )


def changed_paths_for_worktree(worktree_path: Path) -> list[str]:
    """Return the changed relative paths in one worktree."""

    status = run_subprocess(
        ["git", "status", "--short", "--porcelain"],
        cwd=worktree_path,
    )
    paths: list[str] = []
    for raw_line in status.stdout.splitlines():
        line = raw_line.rstrip()
        if len(line) < 4:
            continue
        payload = line[3:]
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        paths.append(payload)
    return sorted(set(paths))


def commit_all(worktree_path: Path, message: str) -> None:
    """Commit all staged and unstaged changes in one detached worktree."""

    run_subprocess(
        ["git", "add", "-A"],
        cwd=worktree_path,
    )
    subject, body = split_commit_message(message)
    command = ["git", "commit", "-m", subject]
    for paragraph in body:
        command.extend(["-m", paragraph])
    run_subprocess(command, cwd=worktree_path)


def split_commit_message(message: str) -> tuple[str, list[str]]:
    """Split one commit message into a subject and optional body paragraphs."""

    paragraphs = [paragraph.strip() for paragraph in message.split("\n\n")]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    if not paragraphs:
        return "Update loop state", []
    first_paragraph_lines = [
        line.strip()
        for line in paragraphs[0].splitlines()
        if line.strip()
    ]
    subject = first_paragraph_lines[0] if first_paragraph_lines else paragraphs[0]
    body: list[str] = []
    if len(first_paragraph_lines) > 1:
        body.append("\n".join(first_paragraph_lines[1:]))
    body.extend(paragraphs[1:])
    return subject, [paragraph for paragraph in body if paragraph]


def port_is_open(host: str, port: int) -> bool:
    """Return whether one TCP port is accepting connections."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def pid_is_running(pid: int) -> bool:
    """Return whether one process is currently running."""

    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def ensure_single_supervisor(pid_path: Path, label: str) -> None:
    """Raise when a supervisor with the tracked PID is already running."""

    if not pid_path.exists():
        return
    existing_pid = int(pid_path.read_text(encoding="utf-8").strip())
    if pid_is_running(existing_pid):
        raise RuntimeError(f"{label} is already running with PID {existing_pid}.")
    pid_path.unlink()


def write_pid(path: Path) -> None:
    """Write one supervisor PID file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{os.getpid()}\n", encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write one JSON object with stable formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_json(path: Path) -> dict[str, Any]:
    """Read one JSON object from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def write_heartbeat(
    path: Path,
    *,
    phase: str,
    status: str,
    extra: dict[str, Any],
) -> None:
    """Write one heartbeat payload."""

    payload: dict[str, Any] = {
        "phase": phase,
        "status": status,
        "updated_at": utc_now_iso(),
    }
    payload.update(extra)
    write_json(path, payload)


def hydrate_approved_source_cache(policy: LoopPolicy, cache_dir: Path) -> list[Path]:
    """Fetch the seed approved-source URLs into a local cache directory."""

    cache_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for url in policy.source_seed_urls:
        if not url_uses_allowed_domain(url, policy):
            continue
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        entry_dir = cache_dir / digest
        entry_dir.mkdir(parents=True, exist_ok=True)
        metadata_path = entry_dir / "metadata.json"
        content_path = entry_dir / "content.txt"
        request = Request(
            url,
            headers={"User-Agent": "cbb-upsets-autonomous-loop/1.0"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                content = response.read().decode("utf-8", errors="replace")
                status = int(response.status)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            write_json(
                metadata_path,
                {
                    "ok": False,
                    "url": url,
                    "error": str(exc),
                },
            )
            continue
        content_path.write_text(content, encoding="utf-8")
        write_json(
            metadata_path,
            {
                "ok": True,
                "url": url,
                "status": status,
            },
        )
        written_paths.append(content_path)
    return written_paths


def policy_prompt_block(policy: LoopPolicy) -> str:
    """Render a concise policy summary for agent prompts."""

    lines = [
        f"- lane: `{policy.lane}`",
        f"- branch: `{policy.branch}`",
        f"- auto_commit: `{policy.auto_commit}`",
        f"- auto_push: `{policy.auto_push}`",
        f"- max_files_changed_per_loop: `{policy.max_files_changed_per_loop}`",
        f"- roadmap: `{policy.roadmap_path}`",
        "- allowed_paths:",
    ]
    lines.extend(f"  - `{path}`" for path in policy.allowed_paths)
    lines.append("- disallowed_paths:")
    lines.extend(f"  - `{path}`" for path in policy.disallowed_paths)
    lines.append("- whitelist_domains:")
    lines.extend(f"  - `{domain}`" for domain in policy.allowed_domains)
    return "\n".join(lines)


def utc_now_iso() -> str:
    """Return one UTC timestamp string."""

    return datetime.now(UTC).isoformat()


def _default_lane_from_policy_path(path: Path) -> str:
    stem = path.stem
    if stem.endswith("-loop-policy"):
        return stem.removesuffix("-loop-policy")
    return stem


def _default_agent_names_for_lane(lane: str) -> tuple[str, str, str]:
    if lane == "infra":
        return ("infra_researcher", "infra_implementer", "infra_verifier")
    if lane == "model":
        return ("roadmap_researcher", "implementer", "model_verifier")
    if lane == "ux":
        return ("ux_researcher", "implementer", "ux_verifier")
    return (f"{lane}_researcher", f"{lane}_implementer", f"{lane}_verifier")


def _dedupe_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError(f"Expected list value, got {type(value).__name__}")
    return tuple(str(item) for item in value)


def _validate_worktree_venv(venv_path: Path, *, label: str) -> None:
    missing = [
        str(venv_path / "bin" / command)
        for command in REQUIRED_WORKTREE_VENV_TOOLS
        if not (venv_path / "bin" / command).exists()
    ]
    if missing:
        raise RuntimeError(
            f"{label} virtualenv is missing required executables: "
            + ", ".join(missing)
        )


def _remove_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def _mirror_worktree_support_paths(*, repo_root: Path, worktree_path: Path) -> None:
    """Mirror local-only support paths that detached git worktrees do not carry."""

    for relative_path in WORKTREE_MIRRORED_PATHS:
        source_path = repo_root / relative_path
        target_path = worktree_path / relative_path
        _remove_path(target_path)
        if not source_path.exists():
            continue
        if source_path.is_file():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            continue
        shutil.copytree(source_path, target_path)


def _rewrite_worktree_venv_paths(
    *,
    source_repo_root: Path,
    source_venv: Path,
    worktree_path: Path,
    target_venv: Path,
) -> None:
    replacements = (
        (source_venv.as_posix(), target_venv.as_posix()),
        (source_repo_root.as_posix(), worktree_path.as_posix()),
    )
    candidate_paths = [target_venv / "pyvenv.cfg"]
    bin_dir = target_venv / "bin"
    if bin_dir.exists():
        candidate_paths.extend(sorted(bin_dir.iterdir()))
    for site_packages_dir in _site_packages_dirs(target_venv):
        candidate_paths.extend(sorted(site_packages_dir.glob("*.pth")))
        candidate_paths.extend(sorted(site_packages_dir.glob("*.egg-link")))
        candidate_paths.extend(sorted(site_packages_dir.rglob("direct_url.json")))
    for path in candidate_paths:
        _rewrite_text_file(path, replacements)


def _site_packages_dirs(venv_path: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            list(venv_path.glob("lib/python*/site-packages"))
            + list(venv_path.glob("lib64/python*/site-packages"))
        )
    )


def _rewrite_text_file(path: Path, replacements: tuple[tuple[str, str], ...]) -> None:
    if not path.exists() or path.is_dir() or path.is_symlink():
        return
    try:
        original = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return
    updated = original
    for old, new in replacements:
        updated = updated.replace(old, new)
    if updated != original:
        path.write_text(updated, encoding="utf-8")


__all__ = [
    "AgentConfig",
    "AgentRegistryEntry",
    "DEFAULT_CODEX_CONFIG_PATH",
    "DEFAULT_POLICY_DIR",
    "DEFAULT_SUPERVISOR_RUNTIME_ROOT",
    "GIT_REPO_ROOT",
    "LaneAgentSet",
    "LaneRuntimePaths",
    "LoopPolicy",
    "REPO_ROOT",
    "WORKTREE_PROJECT_SUBDIR",
    "advance_branch",
    "build_codex_exec_command",
    "changed_paths_for_worktree",
    "citations_use_allowed_sources",
    "commit_all",
    "create_detached_worktree",
    "ensure_command_available",
    "ensure_lane_runtime_dirs",
    "ensure_local_branch",
    "ensure_single_supervisor",
    "ensure_worktree_venv",
    "hydrate_approved_source_cache",
    "lane_runtime_paths",
    "load_agent_config",
    "load_codex_agent_registry",
    "load_lane_agent_set",
    "load_loop_policies",
    "load_loop_policy",
    "path_is_allowed",
    "pid_is_running",
    "policy_prompt_block",
    "port_is_open",
    "read_json",
    "remove_worktree",
    "repo_is_clean",
    "run_shell_command",
    "run_subprocess",
    "select_verification_commands",
    "split_commit_message",
    "url_uses_allowed_domain",
    "utc_now_iso",
    "validate_changed_paths",
    "worktree_project_root",
    "write_heartbeat",
    "write_json",
    "write_pid",
]
