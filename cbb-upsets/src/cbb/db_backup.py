"""Database backup and restore helpers for the local Postgres workflow."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from cbb.db import REPO_ROOT, resolve_database_url

DEFAULT_BACKUP_DIR = REPO_ROOT / "backups"
DEFAULT_BACKUP_PREFIX = "cbb_upsets"
BACKUP_SUFFIX = ".sql"
BACKUP_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
POSTGRES_COMMAND_MAX_ATTEMPTS = 3
POSTGRES_DEADLOCK_MARKER = "deadlock detected"
LIBPQ_BIN_DIRECTORIES = (
    Path("/opt/homebrew/opt/libpq/bin"),
    Path("/usr/local/opt/libpq/bin"),
)


@dataclass(frozen=True)
class DatabaseBackupArtifact:
    """Metadata for a created SQL backup file."""

    path: Path
    size_bytes: int


@dataclass(frozen=True)
class DatabaseImportArtifact:
    """Metadata for an imported SQL backup file."""

    path: Path


def create_database_backup(
    *,
    database_url: str | None = None,
    backup_name: str | None = None,
    backup_dir: Path | None = None,
    now: datetime | None = None,
) -> DatabaseBackupArtifact:
    """Create a plain SQL backup using ``pg_dump``.

    Args:
        database_url: Optional PostgreSQL URL override.
        backup_name: Optional file name stem. ``.sql`` is added automatically.
        backup_dir: Optional directory override for the output file.
        now: Optional current time override for deterministic tests.

    Returns:
        Metadata for the created backup file.

    Raises:
        FileExistsError: If the target backup file already exists.
        RuntimeError: If ``pg_dump`` is unavailable or returns an error.
        ValueError: If the configured database is not PostgreSQL or the backup
            name is invalid.
    """
    resolved_database_url = resolve_database_url(database_url)
    output_path = _build_backup_path(
        backup_name=backup_name,
        backup_dir=backup_dir,
        now=now,
    )
    if output_path.exists():
        raise FileExistsError(f"Backup already exists at {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        _resolve_postgres_client("pg_dump"),
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        "--format=plain",
        "--encoding=UTF8",
        f"--file={output_path}",
    ]
    _run_postgres_command(
        command,
        env=_build_postgres_env(resolved_database_url),
        tool_name="pg_dump",
    )
    return DatabaseBackupArtifact(
        path=output_path,
        size_bytes=output_path.stat().st_size,
    )


def import_database_backup(
    backup_name_or_path: str,
    *,
    database_url: str | None = None,
    backup_dir: Path | None = None,
) -> DatabaseImportArtifact:
    """Import a plain SQL backup using ``psql``.

    Args:
        backup_name_or_path: Backup file name from ``backups/`` or a full path.
        database_url: Optional PostgreSQL URL override.
        backup_dir: Optional directory override used for repo-local backups.

    Returns:
        Metadata for the imported backup file.

    Raises:
        FileNotFoundError: If the backup file cannot be resolved.
        RuntimeError: If ``psql`` is unavailable or returns an error.
        ValueError: If the configured database is not PostgreSQL.
    """
    resolved_database_url = resolve_database_url(database_url)
    backup_path = resolve_backup_path(
        backup_name_or_path,
        backup_dir=backup_dir,
    )
    command = [
        _resolve_postgres_client("psql"),
        "-v",
        "ON_ERROR_STOP=1",
        "-f",
        str(backup_path),
    ]
    _run_postgres_command(
        command,
        env=_build_postgres_env(resolved_database_url),
        tool_name="psql",
    )
    return DatabaseImportArtifact(path=backup_path)


def resolve_backup_path(
    backup_name_or_path: str,
    *,
    backup_dir: Path | None = None,
) -> Path:
    """Resolve a backup file name or path to an existing SQL dump.

    Args:
        backup_name_or_path: Backup file name from ``backups/`` or a file path.
        backup_dir: Optional directory override used for repo-local backups.

    Returns:
        The resolved existing backup path.

    Raises:
        FileNotFoundError: If no matching SQL dump exists.
    """
    candidate = Path(backup_name_or_path).expanduser()
    repo_backup_dir = (backup_dir or DEFAULT_BACKUP_DIR).resolve()
    candidate_paths = _candidate_backup_paths(candidate, repo_backup_dir)

    for path in candidate_paths:
        if path.exists():
            return path.resolve()

    available_backups = _list_available_backups(repo_backup_dir)
    if available_backups:
        available_names = ", ".join(path.name for path in available_backups[:5])
        raise FileNotFoundError(
            f"Backup {backup_name_or_path!r} was not found. "
            f"Available backups: {available_names}"
        )
    raise FileNotFoundError(
        f"Backup {backup_name_or_path!r} was not found in {repo_backup_dir}"
    )


def _build_backup_path(
    *,
    backup_name: str | None,
    backup_dir: Path | None,
    now: datetime | None,
) -> Path:
    """Build the output path for a new backup file."""
    resolved_backup_dir = (backup_dir or DEFAULT_BACKUP_DIR).resolve()
    if backup_name is None:
        timestamp = (now or datetime.now(UTC)).strftime(BACKUP_TIMESTAMP_FORMAT)
        file_stem = f"{DEFAULT_BACKUP_PREFIX}_{timestamp}"
    else:
        file_stem = _normalize_backup_name(backup_name)
    return resolved_backup_dir / f"{file_stem}{BACKUP_SUFFIX}"


def _normalize_backup_name(backup_name: str) -> str:
    """Normalize and validate a user-provided backup file name."""
    stripped_name = backup_name.strip()
    if not stripped_name:
        raise ValueError("Backup name cannot be empty.")

    path_name = Path(stripped_name)
    if path_name.name != stripped_name:
        raise ValueError("Backup name must be a file name, not a path.")

    file_stem = (
        stripped_name[: -len(BACKUP_SUFFIX)]
        if stripped_name.endswith(BACKUP_SUFFIX)
        else stripped_name
    )
    if not re.fullmatch(r"[A-Za-z0-9._-]+", file_stem):
        raise ValueError(
            "Backup name may only contain letters, numbers, dots, underscores, "
            "and dashes."
        )
    return file_stem


def _candidate_backup_paths(candidate: Path, repo_backup_dir: Path) -> list[Path]:
    """Build candidate paths for a backup file lookup."""
    if candidate.is_absolute() or candidate.parent != Path("."):
        return _with_optional_sql_suffix(candidate)

    repo_candidate = repo_backup_dir / candidate.name
    if candidate.suffix == BACKUP_SUFFIX:
        return [repo_candidate]
    return [repo_candidate.with_suffix(BACKUP_SUFFIX), repo_candidate]


def _with_optional_sql_suffix(path: Path) -> list[Path]:
    """Return possible SQL file paths for a user-provided path."""
    if path.suffix == BACKUP_SUFFIX:
        return [path]
    return [path, path.with_suffix(BACKUP_SUFFIX)]


def _list_available_backups(backup_dir: Path) -> list[Path]:
    """Return repo-local SQL backups ordered newest-first."""
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob(f"*{BACKUP_SUFFIX}"), reverse=True)


def _build_postgres_env(database_url: str) -> dict[str, str]:
    """Convert a PostgreSQL URL into ``pg_dump`` / ``psql`` environment vars.

    Args:
        database_url: PostgreSQL connection URL.

    Returns:
        A subprocess environment with PostgreSQL connection variables.

    Raises:
        ValueError: If the URL is not PostgreSQL or does not include a database.
    """
    parsed_url = make_url(database_url)
    driver_name = parsed_url.drivername.split("+", maxsplit=1)[0]
    if driver_name != "postgresql":
        raise ValueError("Backup and import only support PostgreSQL databases.")

    if not parsed_url.database:
        raise ValueError("DATABASE_URL must include a database name.")

    environment = os.environ.copy()
    environment["PGDATABASE"] = parsed_url.database
    if parsed_url.host:
        environment["PGHOST"] = parsed_url.host
    if parsed_url.port is not None:
        environment["PGPORT"] = str(parsed_url.port)
    if parsed_url.username:
        environment["PGUSER"] = parsed_url.username
    if parsed_url.password:
        environment["PGPASSWORD"] = parsed_url.password

    ssl_mode = _extract_query_value(parsed_url.query.get("sslmode"))
    if ssl_mode is not None:
        environment["PGSSLMODE"] = ssl_mode
    return environment


def _extract_query_value(value: str | tuple[str, ...] | None) -> str | None:
    """Normalize a SQLAlchemy URL query value into a string."""
    if value is None:
        return None
    if isinstance(value, tuple):
        if not value:
            return None
        return value[0]
    return value


def _run_postgres_command(
    command: list[str],
    *,
    env: dict[str, str],
    tool_name: str,
) -> None:
    """Run one PostgreSQL client command and raise readable failures.

    Args:
        command: Shell-free subprocess command list.
        env: Subprocess environment with PostgreSQL connection details.
        tool_name: Human-readable executable name used in error messages.

    Raises:
        RuntimeError: If the executable is missing or returns a non-zero code.
    """
    for attempt in range(1, POSTGRES_COMMAND_MAX_ATTEMPTS + 1):
        try:
            subprocess.run(
                command,
                check=True,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            return
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"{tool_name} is not installed. Install PostgreSQL client tools."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.strip()
            if _should_retry_postgres_command(stderr, attempt):
                time.sleep(float(attempt))
                continue
            if stderr:
                raise RuntimeError(stderr) from exc
            raise RuntimeError(
                f"{tool_name} exited with code {exc.returncode}"
            ) from exc

    raise RuntimeError(
        f"{tool_name} failed after {POSTGRES_COMMAND_MAX_ATTEMPTS} attempts"
    )


def _resolve_postgres_client(tool_name: str) -> str:
    """Resolve a PostgreSQL client executable from PATH or common libpq paths.

    Args:
        tool_name: Executable name, such as ``pg_dump`` or ``psql``.

    Returns:
        The executable path to use for the subprocess call.

    Raises:
        RuntimeError: If the executable cannot be found.
    """
    executable = shutil.which(tool_name)
    if executable is not None:
        return executable

    for directory in LIBPQ_BIN_DIRECTORIES:
        candidate = directory / tool_name
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        f"{tool_name} is not installed. Install PostgreSQL client tools."
    )


def _should_retry_postgres_command(stderr: str, attempt: int) -> bool:
    """Return whether a PostgreSQL client command should be retried.

    Args:
        stderr: Captured standard error from the subprocess.
        attempt: Current attempt number starting at 1.

    Returns:
        ``True`` when the failure looks transient and another retry remains.
    """
    return (
        POSTGRES_DEADLOCK_MARKER in stderr.casefold()
        and attempt < POSTGRES_COMMAND_MAX_ATTEMPTS
    )
