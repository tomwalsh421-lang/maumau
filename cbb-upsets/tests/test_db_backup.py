from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cbb.db_backup import create_database_backup, import_database_backup

TEST_DATABASE_URL = "postgresql://cbb:cbbpass@localhost:5432/cbb_upsets"


def test_create_database_backup_uses_repo_local_sql_dump(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        check: bool,
        env: dict[str, str],
        stdout: int,
        stderr: int,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is True
        assert stdout == subprocess.DEVNULL
        assert stderr == subprocess.PIPE
        assert text is True
        captured["command"] = command
        captured["env"] = env

        output_flag = next(item for item in command if item.startswith("--file="))
        output_path = Path(output_flag.split("=", maxsplit=1)[1])
        output_path.write_text("-- test backup\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stderr="")

    monkeypatch.setattr("cbb.db_backup.subprocess.run", fake_run)
    monkeypatch.setattr(
        "cbb.db_backup._resolve_postgres_client",
        lambda tool_name: tool_name,
    )

    artifact = create_database_backup(
        database_url=TEST_DATABASE_URL,
        backup_name="season-2026",
        backup_dir=tmp_path,
        now=datetime(2026, 3, 8, tzinfo=UTC),
    )

    assert artifact.path == tmp_path / "season-2026.sql"
    assert artifact.size_bytes == len("-- test backup\n")

    command = captured["command"]
    assert isinstance(command, list)
    assert command[:4] == ["pg_dump", "--clean", "--if-exists", "--no-owner"]
    assert "--no-privileges" in command
    assert "--format=plain" in command
    assert f"--file={tmp_path / 'season-2026.sql'}" in command

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PGHOST"] == "localhost"
    assert env["PGPORT"] == "5432"
    assert env["PGUSER"] == "cbb"
    assert env["PGPASSWORD"] == "cbbpass"
    assert env["PGDATABASE"] == "cbb_upsets"


def test_import_database_backup_resolves_repo_backup_name(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    backup_path = tmp_path / "season-2026.sql"
    backup_path.write_text("-- restore\n", encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(
        command: list[str],
        *,
        check: bool,
        env: dict[str, str],
        stdout: int,
        stderr: int,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is True
        assert stdout == subprocess.DEVNULL
        assert stderr == subprocess.PIPE
        assert text is True
        captured["command"] = command
        captured["env"] = env
        return subprocess.CompletedProcess(command, 0, stderr="")

    monkeypatch.setattr("cbb.db_backup.subprocess.run", fake_run)
    monkeypatch.setattr(
        "cbb.db_backup._resolve_postgres_client",
        lambda tool_name: tool_name,
    )

    artifact = import_database_backup(
        "season-2026",
        database_url=TEST_DATABASE_URL,
        backup_dir=tmp_path,
    )

    assert artifact.path == backup_path.resolve()

    command = captured["command"]
    assert isinstance(command, list)
    assert command == [
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        str(backup_path.resolve()),
    ]

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PGDATABASE"] == "cbb_upsets"


def test_import_database_backup_lists_available_files_on_missing_file(
    tmp_path: Path,
) -> None:
    (tmp_path / "first.sql").write_text("-- first\n", encoding="utf-8")
    (tmp_path / "second.sql").write_text("-- second\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError) as exc_info:
        import_database_backup(
            "missing",
            database_url=TEST_DATABASE_URL,
            backup_dir=tmp_path,
        )

    error_message = str(exc_info.value)
    assert "missing" in error_message
    assert "first.sql" in error_message
    assert "second.sql" in error_message


def test_create_database_backup_retries_deadlock_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = {"count": 0}

    def fake_run(
        command: list[str],
        *,
        check: bool,
        env: dict[str, str],
        stdout: int,
        stderr: int,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is True
        assert stdout == subprocess.DEVNULL
        assert stderr == subprocess.PIPE
        assert text is True
        calls["count"] += 1
        if calls["count"] == 1:
            raise subprocess.CalledProcessError(
                returncode=1,
                cmd=command,
                stderr="pg_dump: error: deadlock detected",
            )

        output_flag = next(item for item in command if item.startswith("--file="))
        output_path = Path(output_flag.split("=", maxsplit=1)[1])
        output_path.write_text("-- recovered backup\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stderr="")

    monkeypatch.setattr("cbb.db_backup.subprocess.run", fake_run)
    monkeypatch.setattr("cbb.db_backup.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "cbb.db_backup._resolve_postgres_client",
        lambda tool_name: tool_name,
    )

    artifact = create_database_backup(
        database_url=TEST_DATABASE_URL,
        backup_name="retry-deadlock",
        backup_dir=tmp_path,
    )

    assert artifact.path == tmp_path / "retry-deadlock.sql"
    assert calls["count"] == 2
