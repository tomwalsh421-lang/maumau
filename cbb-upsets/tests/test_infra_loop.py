from __future__ import annotations

from pathlib import Path

from cbb.infra_loop import (
    build_codex_exec_command,
    citations_use_allowed_sources,
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
)


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


def test_load_lane_agent_set_resolves_policy_agent_names() -> None:
    registry = load_codex_agent_registry(Path(".codex/config.toml"))
    policy = load_loop_policy(Path("ops/model-loop-policy.toml"))

    agent_set = load_lane_agent_set(policy, registry)

    assert agent_set.research.model == "gpt-5.4"
    assert agent_set.verify.approval_policy == "never"
