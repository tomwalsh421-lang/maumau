from __future__ import annotations

from pathlib import Path

import pytest

from cbb.infra_loop import (
    GIT_REPO_ROOT,
    REPO_ROOT,
    build_codex_exec_command,
    citations_use_allowed_sources,
    ensure_worktree_venv,
    lane_runtime_paths,
    load_agent_config,
    load_codex_agent_registry,
    load_lane_agent_set,
    load_loop_policies,
    load_loop_policy,
    path_is_allowed,
    select_verification_commands,
    split_commit_message,
    url_uses_allowed_domain,
    validate_changed_paths,
    worktree_project_root,
)


def _write_seed_venv(repo_root: Path) -> Path:
    venv_path = repo_root / ".venv"
    bin_dir = venv_path / "bin"
    site_packages_dir = venv_path / "lib" / "python3.14" / "site-packages"
    src_dir = repo_root / "src"

    bin_dir.mkdir(parents=True, exist_ok=True)
    site_packages_dir.mkdir(parents=True, exist_ok=True)
    src_dir.mkdir(parents=True, exist_ok=True)

    (venv_path / "pyvenv.cfg").write_text(
        (
            f"home = /opt/homebrew/bin\n"
            f"command = {venv_path.as_posix()}/bin/python -m venv "
            f"{venv_path.as_posix()}\n"
        ),
        encoding="utf-8",
    )
    (bin_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "ruff").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "pytest").write_text(
        f"#!{venv_path.as_posix()}/bin/python\n",
        encoding="utf-8",
    )
    (bin_dir / "mypy").write_text(
        f"#!{venv_path.as_posix()}/bin/python\n",
        encoding="utf-8",
    )
    (bin_dir / "activate").write_text(
        f'VIRTUAL_ENV="{venv_path.as_posix()}"\n',
        encoding="utf-8",
    )
    (
        site_packages_dir / "__editable__.cbb_upsets-0.1.0.pth"
    ).write_text(
        f"{src_dir.as_posix()}\n",
        encoding="utf-8",
    )
    return venv_path


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


def test_select_verification_commands_appends_task_commands() -> None:
    policy = load_loop_policy(
        Path("ops/model-loop-policy.toml")
    )

    commands = select_verification_commands(
        ["src/cbb/modeling/train.py"],
        policy,
        ["./.venv/bin/pytest -q tests/test_report.py"],
    )

    assert commands[-1] == "./.venv/bin/pytest -q tests/test_report.py"
    assert "./.venv/bin/mypy src" in commands


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


def test_load_loop_policies_support_multiple_lanes() -> None:
    policies = load_loop_policies(
        Path("ops"),
        ("infra", "model", "ux"),
    )

    assert policies["infra"].branch == "auto/infra-loop"
    assert policies["model"].verify_agent == "model_verifier"
    assert policies["ux"].verify_agent == "ux_verifier"


def test_lane_runtime_paths_use_lane_subdirectories(tmp_path: Path) -> None:
    runtime = lane_runtime_paths(tmp_path, "model")

    assert runtime.root == tmp_path / "model"
    assert runtime.state_path == tmp_path / "model" / "state.json"
    assert runtime.worktrees_dir == tmp_path / "model" / "worktrees"


def test_worktree_project_root_tracks_nested_project_path() -> None:
    worktree_root = Path("/tmp/worktree-root")

    if REPO_ROOT == GIT_REPO_ROOT:
        assert worktree_project_root(worktree_root) == worktree_root
    else:
        assert worktree_project_root(worktree_root) == (
            worktree_root / REPO_ROOT.relative_to(GIT_REPO_ROOT)
        )


def test_load_lane_agent_set_resolves_policy_agent_names() -> None:
    registry = load_codex_agent_registry(Path(".codex/config.toml"))
    policy = load_loop_policy(Path("ops/model-loop-policy.toml"))

    agent_set = load_lane_agent_set(policy, registry)

    assert agent_set.research.model == "gpt-5.4"
    assert agent_set.verify.approval_policy == "never"


def test_ensure_worktree_venv_clones_and_rewrites_repo_paths(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    worktree_path = tmp_path / "worktree"
    repo_root.mkdir()
    worktree_path.mkdir()
    _write_seed_venv(repo_root)

    ensure_worktree_venv(repo_root, worktree_path)

    worktree_venv = worktree_path / ".venv"
    assert worktree_venv.exists()
    assert (
        worktree_venv / "bin" / "pytest"
    ).read_text(encoding="utf-8") == (
        f"#!{worktree_venv.as_posix()}/bin/python\n"
    )
    assert (
        worktree_venv / "bin" / "activate"
    ).read_text(encoding="utf-8") == (
        f'VIRTUAL_ENV="{worktree_venv.as_posix()}"\n'
    )
    assert (
        worktree_venv
        / "lib"
        / "python3.14"
        / "site-packages"
        / "__editable__.cbb_upsets-0.1.0.pth"
    ).read_text(encoding="utf-8") == f"{worktree_path.as_posix()}/src\n"
    pyvenv_cfg = (worktree_venv / "pyvenv.cfg").read_text(encoding="utf-8")
    assert worktree_venv.as_posix() in pyvenv_cfg
    assert repo_root.as_posix() not in pyvenv_cfg


def test_ensure_worktree_venv_replaces_stale_copy(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_path = tmp_path / "worktree"
    repo_root.mkdir()
    worktree_path.mkdir()
    _write_seed_venv(repo_root)
    stale_marker = worktree_path / ".venv" / "stale.txt"
    stale_marker.parent.mkdir(parents=True, exist_ok=True)
    stale_marker.write_text("stale\n", encoding="utf-8")

    ensure_worktree_venv(repo_root, worktree_path)

    assert stale_marker.exists() is False
    assert (worktree_path / ".venv" / "bin" / "ruff").exists()


def test_ensure_worktree_venv_mirrors_chart_dependencies(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_path = tmp_path / "worktree"
    repo_root.mkdir()
    worktree_path.mkdir()
    _write_seed_venv(repo_root)
    source_chart_dir = repo_root / "chart" / "cbb-upsets" / "charts"
    source_chart_dir.mkdir(parents=True, exist_ok=True)
    (source_chart_dir / "postgresql-13.2.26.tgz").write_text(
        "dependency\n",
        encoding="utf-8",
    )
    stale_chart_dir = worktree_path / "chart" / "cbb-upsets" / "charts"
    stale_chart_dir.mkdir(parents=True, exist_ok=True)
    (stale_chart_dir / "stale.tgz").write_text("stale\n", encoding="utf-8")

    ensure_worktree_venv(repo_root, worktree_path)

    assert (worktree_path / ".venv").exists()
    assert (worktree_path / "chart" / "cbb-upsets" / "charts").exists()
    assert (
        worktree_path / "chart" / "cbb-upsets" / "charts" / "postgresql-13.2.26.tgz"
    ).read_text(encoding="utf-8") == "dependency\n"
    assert (
        worktree_path / "chart" / "cbb-upsets" / "charts" / "stale.tgz"
    ).exists() is False


def test_ensure_worktree_venv_requires_seeded_tools(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    worktree_path = tmp_path / "worktree"
    repo_root.mkdir()
    worktree_path.mkdir()
    seed_venv = _write_seed_venv(repo_root)
    (seed_venv / "bin" / "ruff").unlink()

    with pytest.raises(
        RuntimeError,
        match="Primary repo virtualenv is missing required executables",
    ):
        ensure_worktree_venv(repo_root, worktree_path)
