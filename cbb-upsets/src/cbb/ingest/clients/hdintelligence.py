"""Parsers for wrapped HD Intelligence availability archive captures."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cbb.ingest.clients.availability_types import (
    OfficialAvailabilityGame,
    OfficialAvailabilityReport,
    OfficialAvailabilityRow,
    OfficialAvailabilityTeam,
)
from cbb.ingest.utils import normalize_team_key, parse_timestamp

ACC_MBB_AVAILABILITY_ARCHIVE_SOURCE = "acc_mbb_availability_archive"
ATLANTIC10_MBB_AVAILABILITY_ARCHIVE_SOURCE = (
    "atlantic10_mbb_availability_archive"
)
BIG12_MBB_AVAILABILITY_ARCHIVE_SOURCE = "big12_mbb_availability_archive"
BIG_EAST_MBB_AVAILABILITY_ARCHIVE_SOURCE = "big_east_mbb_availability_archive"
BIG_TEN_MBB_AVAILABILITY_ARCHIVE_SOURCE = "big_ten_mbb_availability_archive"
MVC_MBB_AVAILABILITY_ARCHIVE_SOURCE = "mvc_mbb_availability_archive"
NCAA_MBB_AVAILABILITY_ARCHIVE_SOURCE = "ncaa_mbb_availability_archive"
SEC_MBB_AVAILABILITY_ARCHIVE_SOURCE = "sec_mbb_availability_archive"
HD_INTELLIGENCE_ARCHIVE_SOURCE_NAMES = frozenset(
    {
        ACC_MBB_AVAILABILITY_ARCHIVE_SOURCE,
        ATLANTIC10_MBB_AVAILABILITY_ARCHIVE_SOURCE,
        BIG12_MBB_AVAILABILITY_ARCHIVE_SOURCE,
        BIG_EAST_MBB_AVAILABILITY_ARCHIVE_SOURCE,
        BIG_TEN_MBB_AVAILABILITY_ARCHIVE_SOURCE,
        MVC_MBB_AVAILABILITY_ARCHIVE_SOURCE,
        NCAA_MBB_AVAILABILITY_ARCHIVE_SOURCE,
        SEC_MBB_AVAILABILITY_ARCHIVE_SOURCE,
    }
)
_REPORT_VARIANTS = (
    ("initial", "InitialStatus"),
    ("gameday", "GamedayStatus"),
)
_IGNORED_STATUS_VALUES = frozenset({"-", "n/a", "none"})
_STATUS_MAP = {
    "available": ("available", None),
    "exempt": ("available", "Exempt"),
    "probable": ("probable", None),
    "questionable": ("questionable", None),
    "doubtful": ("questionable", "Doubtful"),
    "game time decision": ("questionable", "Game Time Decision"),
    "out": ("out", None),
    "out - (1st half)": ("out", "Out - (1st Half)"),
}


@dataclass(frozen=True)
class _ArchivePendingRow:
    """One grouped row waiting to be emitted as a normalized report row."""

    row_number: int
    team_name: str
    player_name: str
    normalized_status: str
    status_note: str | None
    jersey_number: str | None
    raw_payload: Mapping[str, object]


def is_hdintelligence_archive_source_name(source_name: str) -> bool:
    """Return whether a source name is supported by the archive parser."""

    return source_name in HD_INTELLIGENCE_ARCHIVE_SOURCE_NAMES


def load_hdintelligence_archive_capture_payload(
    payload: Mapping[str, object],
    source_path: Path,
) -> tuple[OfficialAvailabilityReport, ...]:
    """Normalize one wrapped HD Intelligence archive capture file."""

    source_payload = _required_mapping(payload, "source", source_path)
    source_name = _required_string(source_payload, "source_name", source_path)
    if not is_hdintelligence_archive_source_name(source_name):
        raise ValueError(
            "Unsupported HD Intelligence availability source_name in "
            f"{source_path}: {source_name!r}"
        )

    source_url = _required_string(source_payload, "source_url", source_path)
    captured_at = _required_timestamp(source_payload, "captured_at", source_path)
    row_payloads = _required_mapping_list(payload, "payload", source_path)

    grouped_rows: dict[
        tuple[str, str, str, str],
        list[_ArchivePendingRow],
    ] = defaultdict(list)
    report_context_by_key: dict[
        tuple[str, str, str, str],
        tuple[str, str, str],
    ] = {}

    for row_number, row_payload in enumerate(row_payloads, start=1):
        team_name = _required_string(row_payload, "Team", source_path).strip()
        opponent_label = _required_string(row_payload, "Opponent", source_path)
        game_date = _archive_game_date(row_payload, source_path)
        opponent_name, home_team_name, away_team_name = _derive_game_context(
            team_name=team_name,
            opponent_label=opponent_label,
        )

        for variant_key, status_field in _REPORT_VARIANTS:
            raw_status = _optional_string(row_payload.get(status_field))
            if raw_status is None:
                continue
            if raw_status.lower() in _IGNORED_STATUS_VALUES:
                continue
            normalized_status, status_note = _normalize_archive_status(
                raw_status,
                source_path=source_path,
                field_name=status_field,
            )
            report_key = (
                variant_key,
                game_date,
                team_name,
                opponent_name,
            )
            grouped_rows[report_key].append(
                _ArchivePendingRow(
                    row_number=row_number,
                    team_name=team_name,
                    player_name=_required_string(
                        row_payload,
                        "Player",
                        source_path,
                    ),
                    normalized_status=normalized_status,
                    status_note=status_note,
                    jersey_number=_normalize_jersey_number(row_payload.get("Number")),
                    raw_payload=row_payload,
                )
            )
            report_context_by_key[report_key] = (
                home_team_name,
                away_team_name,
                game_date,
            )

    reports: list[OfficialAvailabilityReport] = []
    for report_key in sorted(grouped_rows):
        variant_key, game_date, team_name, opponent_name = report_key
        home_team_name, away_team_name, scheduled_date = report_context_by_key[
            report_key
        ]
        source_report_id = (
            f"{source_name}:{variant_key}:{scheduled_date}:"
            f"{normalize_team_key(team_name)}:{normalize_team_key(opponent_name)}"
        )
        grouped_payload_rows = grouped_rows[report_key]
        reports.append(
            OfficialAvailabilityReport(
                source_name=source_name,
                source_url=source_url,
                captured_at=captured_at,
                published_at=None,
                effective_at=None,
                game=OfficialAvailabilityGame(
                    ncaa_game_code=None,
                    source_event_id=source_report_id,
                    scheduled_start=f"{scheduled_date}T00:00:00+00:00",
                    home_team=OfficialAvailabilityTeam(
                        name=home_team_name,
                        ncaa_team_code=None,
                    ),
                    away_team=OfficialAvailabilityTeam(
                        name=away_team_name,
                        ncaa_team_code=None,
                    ),
                ),
                rows=tuple(
                    OfficialAvailabilityRow(
                        row_number=grouped_row.row_number,
                        team=OfficialAvailabilityTeam(
                            name=grouped_row.team_name,
                            ncaa_team_code=None,
                        ),
                        player_name=grouped_row.player_name,
                        status=grouped_row.normalized_status,
                        jersey_number=grouped_row.jersey_number,
                        position=None,
                        note=grouped_row.status_note,
                        updated_at=None,
                        raw_payload=grouped_row.raw_payload,
                    )
                    for grouped_row in sorted(
                        grouped_payload_rows,
                        key=lambda row: row.row_number,
                    )
                ),
                source_path=source_path,
                raw_payload={
                    "source": dict(source_payload),
                    "report_variant": variant_key,
                    "game_date": scheduled_date,
                    "team_name": team_name,
                    "opponent_name": opponent_name,
                    "rows": [
                        dict(grouped_row.raw_payload)
                        for grouped_row in sorted(
                            grouped_payload_rows,
                            key=lambda row: row.row_number,
                        )
                    ],
                },
            )
        )

    return tuple(reports)


def _archive_game_date(
    row_payload: Mapping[str, object],
    source_path: Path,
) -> str:
    for field_name in ("Week", "Date"):
        raw_value = _optional_string(row_payload.get(field_name))
        if raw_value is None:
            continue
        return _normalize_archive_date(raw_value, source_path, field_name=field_name)
    raise ValueError(
        "Availability archive row in "
        f"{source_path} is missing a supported game-date field."
    )


def _normalize_archive_date(
    value: str,
    source_path: Path,
    *,
    field_name: str,
) -> str:
    normalized_value = value.strip()
    for parser in (
        _parse_rfc1123_date,
        _parse_iso_date,
    ):
        parsed = parser(normalized_value)
        if parsed is not None:
            return parsed
    raise ValueError(
        "Availability archive "
        f"{source_path} field {field_name!r} is not a supported date: "
        f"{value!r}"
    )


def _parse_rfc1123_date(value: str) -> str | None:
    try:
        parsed = datetime.strptime(value, "%a, %d %b %Y %H:%M:%S GMT")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC).date().isoformat()


def _parse_iso_date(value: str) -> str | None:
    try:
        return parse_timestamp(value).date().isoformat()
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _derive_game_context(
    *,
    team_name: str,
    opponent_label: str,
) -> tuple[str, str, str]:
    normalized_label = opponent_label.strip()
    lower_label = normalized_label.lower()
    if lower_label.startswith("vs. "):
        opponent_name = normalized_label[4:].strip()
        return opponent_name, team_name, opponent_name
    if lower_label.startswith("at "):
        opponent_name = normalized_label[3:].strip()
        return opponent_name, opponent_name, team_name
    opponent_name = normalized_label
    return opponent_name, team_name, opponent_name


def _normalize_archive_status(
    value: str,
    *,
    source_path: Path,
    field_name: str,
) -> tuple[str, str | None]:
    normalized_value = value.strip()
    if not normalized_value:
        raise ValueError(
            "Availability archive "
            f"{source_path} field {field_name!r} cannot be empty."
        )
    mapped = _STATUS_MAP.get(normalized_value.lower())
    if mapped is None:
        raise ValueError(
            "Availability archive "
            f"{source_path} field {field_name!r} has unsupported status "
            f"{value!r}."
        )
    normalized_status, default_note = mapped
    if default_note is not None:
        return normalized_status, default_note
    return normalized_status, None


def _normalize_jersey_number(value: object) -> str | None:
    normalized = _optional_string(value)
    if normalized is None:
        return None
    return normalized.lstrip("#").strip() or None


def _required_mapping(
    payload: Mapping[str, object],
    field_name: str,
    source_path: Path,
) -> Mapping[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(
            "Availability capture "
            f"{source_path} is missing object field {field_name!r}."
        )
    return value


def _required_mapping_list(
    payload: Mapping[str, object],
    field_name: str,
    source_path: Path,
) -> tuple[Mapping[str, object], ...]:
    value = payload.get(field_name)
    if not isinstance(value, list):
        raise ValueError(
            f"Availability capture {source_path} is missing list field {field_name!r}."
        )
    rows: list[Mapping[str, object]] = []
    for index, row in enumerate(value, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(
                "Availability capture "
                f"{source_path} has a non-object row at {field_name}[{index - 1}]."
            )
        rows.append(row)
    return tuple(rows)


def _required_string(
    payload: Mapping[str, object],
    field_name: str,
    source_path: Path,
) -> str:
    value = _optional_string(payload.get(field_name))
    if value is None:
        raise ValueError(
            "Availability capture "
            f"{source_path} is missing string field {field_name!r}."
        )
    return value


def _required_timestamp(
    payload: Mapping[str, object],
    field_name: str,
    source_path: Path,
) -> str:
    value = _required_string(payload, field_name, source_path)
    parsed = parse_timestamp(value)
    if parsed.tzinfo is None:
        raise ValueError(
            "Availability capture "
            f"{source_path} field {field_name!r} must include a timezone."
        )
    return parsed.isoformat()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(
            "Availability capture optional fields must be strings when provided."
        )
    normalized = value.strip()
    return normalized or None


__all__ = [
    "ACC_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "ATLANTIC10_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "BIG12_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "BIG_EAST_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "BIG_TEN_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "HD_INTELLIGENCE_ARCHIVE_SOURCE_NAMES",
    "MVC_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "NCAA_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "SEC_MBB_AVAILABILITY_ARCHIVE_SOURCE",
    "is_hdintelligence_archive_source_name",
    "load_hdintelligence_archive_capture_payload",
]
