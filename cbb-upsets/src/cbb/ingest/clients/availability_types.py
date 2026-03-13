"""Shared value objects for normalized availability captures."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OfficialAvailabilityTeam:
    """One team identity carried in a normalized availability report."""

    name: str
    ncaa_team_code: str | None


@dataclass(frozen=True)
class OfficialAvailabilityGame:
    """Game identity metadata carried in a normalized availability report."""

    ncaa_game_code: str | None
    source_event_id: str | None
    scheduled_start: str
    home_team: OfficialAvailabilityTeam
    away_team: OfficialAvailabilityTeam


@dataclass(frozen=True)
class OfficialAvailabilityRow:
    """One normalized player-status row from a captured availability report."""

    row_number: int
    team: OfficialAvailabilityTeam
    player_name: str
    status: str
    jersey_number: str | None
    position: str | None
    note: str | None
    updated_at: str | None
    raw_payload: Mapping[str, object]


@dataclass(frozen=True)
class OfficialAvailabilityReport:
    """One captured official availability report ready for persistence."""

    source_name: str
    source_url: str
    captured_at: str
    published_at: str | None
    effective_at: str | None
    game: OfficialAvailabilityGame
    rows: tuple[OfficialAvailabilityRow, ...]
    source_path: Path
    raw_payload: object
