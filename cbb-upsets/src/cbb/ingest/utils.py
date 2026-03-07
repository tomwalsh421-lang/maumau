"""Shared helpers for ingest modules."""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime


DEFAULT_CBB_SPORT = "basketball_ncaab"


def normalize_team_key(team_name: str) -> str:
    """Normalize a team name into a stable slug key.

    Args:
        team_name: Raw team name from an upstream provider.

    Returns:
        A lowercase slug suitable for uniqueness and joins.

    Raises:
        ValueError: If a slug cannot be derived from the input.
    """
    normalized = (
        unicodedata.normalize("NFKD", team_name)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    team_key = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    if not team_key:
        raise ValueError(f"Could not derive team key from {team_name!r}")
    return team_key


def parse_timestamp(value: str | datetime) -> datetime:
    """Parse an ISO timestamp into a timezone-aware datetime.

    Args:
        value: ISO-8601 timestamp string or datetime object.

    Returns:
        A timezone-aware datetime.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    return datetime.fromisoformat(normalized_value)


def parse_timestamp_or_none(value: object) -> str | None:
    """Parse a timestamp and return it in ISO format.

    Args:
        value: Timestamp-like value.

    Returns:
        The normalized ISO timestamp string, or ``None`` when unavailable.
    """
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise TypeError(
            f"Expected timestamp to be a string, got {type(value).__name__}"
        )
    return parse_timestamp(value).isoformat()


def derive_cbb_season(commence_time: str | datetime) -> int:
    """Derive the NCAA season year from a game timestamp.

    Args:
        commence_time: Game start time.

    Returns:
        The season year, where November 2025 belongs to season 2026.
    """
    timestamp = parse_timestamp(commence_time)
    if timestamp.month >= 10:
        return timestamp.year + 1
    return timestamp.year


def determine_result(
    home_score: int | None,
    away_score: int | None,
    completed: bool,
) -> str | None:
    """Translate final scores into the persisted game result code.

    Args:
        home_score: Final score for the home team.
        away_score: Final score for the away team.
        completed: Whether the game is final.

    Returns:
        ``"W"`` or ``"L"`` for the home team, or ``None`` when incomplete.
    """
    if not completed or home_score is None or away_score is None:
        return None
    if home_score > away_score:
        return "W"
    if home_score < away_score:
        return "L"
    return None


def to_float_or_none(value: object) -> float | None:
    """Convert a scalar value to float when possible.

    Args:
        value: Scalar value from an upstream payload.

    Returns:
        A float value or ``None``.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"Expected float-compatible value, got {type(value).__name__}")


def safe_int(value: object) -> int | None:
    """Convert a scalar value to int when possible.

    Args:
        value: Scalar value from an upstream payload.

    Returns:
        An int value or ``None``.
    """
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"Expected int-compatible value, got {type(value).__name__}")
