"""Parsers for captured official NCAA availability report files."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import orjson

from cbb.ingest.utils import parse_timestamp

OFFICIAL_NCAA_AVAILABILITY_SOURCE = "official_ncaa_availability"
_ALLOWED_AVAILABILITY_STATUSES = frozenset({"available", "questionable", "out"})
_ALLOWED_CAPTURE_SUFFIXES = frozenset({".json"})


@dataclass(frozen=True)
class OfficialNcaaAvailabilityTeam:
    """One team identity carried in a captured NCAA availability report."""

    name: str
    ncaa_team_code: str | None


@dataclass(frozen=True)
class OfficialNcaaAvailabilityGame:
    """Game identity metadata carried in a captured NCAA availability report."""

    ncaa_game_code: str | None
    source_event_id: str | None
    scheduled_start: str
    home_team: OfficialNcaaAvailabilityTeam
    away_team: OfficialNcaaAvailabilityTeam


@dataclass(frozen=True)
class OfficialNcaaAvailabilityRow:
    """One normalized player-status row from a captured NCAA report."""

    row_number: int
    team: OfficialNcaaAvailabilityTeam
    player_name: str
    status: str
    jersey_number: str | None
    position: str | None
    note: str | None
    updated_at: str | None
    raw_payload: Mapping[str, object]


@dataclass(frozen=True)
class OfficialNcaaAvailabilityReport:
    """One captured official NCAA availability report ready for persistence."""

    source_name: str
    source_url: str
    captured_at: str
    published_at: str
    effective_at: str | None
    game: OfficialNcaaAvailabilityGame
    rows: tuple[OfficialNcaaAvailabilityRow, ...]
    source_path: Path
    raw_payload: Mapping[str, object]


def expand_official_ncaa_capture_paths(
    paths: Sequence[Path | str],
) -> tuple[Path, ...]:
    """Expand one or more file or directory paths into sorted JSON captures."""

    expanded_paths: list[Path] = []
    for raw_path in paths:
        capture_path = Path(raw_path).expanduser().resolve()
        if not capture_path.exists():
            raise FileNotFoundError(
                f"Availability capture path not found: {capture_path}"
            )
        if capture_path.is_dir():
            expanded_paths.extend(
                sorted(
                    (
                        candidate.resolve()
                        for candidate in capture_path.rglob("*")
                        if candidate.is_file()
                        and candidate.suffix.lower() in _ALLOWED_CAPTURE_SUFFIXES
                    ),
                    key=lambda candidate: candidate.as_posix(),
                )
            )
            continue
        if capture_path.suffix.lower() not in _ALLOWED_CAPTURE_SUFFIXES:
            raise ValueError(
                "Availability capture files must be JSON: "
                f"{capture_path.name}"
            )
        expanded_paths.append(capture_path)

    unique_paths = tuple(
        sorted(
            set(expanded_paths),
            key=lambda candidate: candidate.as_posix(),
        )
    )
    if not unique_paths:
        raise ValueError("No official NCAA availability capture JSON files found.")
    return unique_paths


def load_official_ncaa_availability_capture(
    path: Path | str,
) -> OfficialNcaaAvailabilityReport:
    """Load and normalize one captured official NCAA availability report."""

    capture_path = Path(path).expanduser().resolve()
    try:
        payload = orjson.loads(capture_path.read_bytes())
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Availability capture path not found: {capture_path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Could not read availability capture file: {capture_path}"
        ) from exc
    except orjson.JSONDecodeError as exc:
        raise ValueError(
            f"Availability capture file is not valid JSON: {capture_path}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError(
            "Availability capture payload must be a JSON object: "
            f"{capture_path}"
        )

    source_payload = _required_mapping(payload, "source", capture_path)
    report_payload = _required_mapping(payload, "report", capture_path)
    game_payload = _required_mapping(report_payload, "game", capture_path)
    row_payloads = _required_mapping_list(report_payload, "statuses", capture_path)

    source_name = _required_string(source_payload, "source_name", capture_path)
    if source_name != OFFICIAL_NCAA_AVAILABILITY_SOURCE:
        raise ValueError(
            "Unsupported availability source_name in "
            f"{capture_path}: {source_name!r}"
        )

    return OfficialNcaaAvailabilityReport(
        source_name=source_name,
        source_url=_required_string(source_payload, "source_url", capture_path),
        captured_at=_required_timestamp(source_payload, "captured_at", capture_path),
        published_at=_required_timestamp(source_payload, "published_at", capture_path),
        effective_at=_optional_timestamp(
            source_payload.get("effective_at"),
            capture_path,
        ),
        game=_parse_game(game_payload, capture_path),
        rows=tuple(
            _parse_row(row_payload, row_number, capture_path)
            for row_number, row_payload in enumerate(row_payloads, start=1)
        ),
        source_path=capture_path,
        raw_payload=payload,
    )


def _parse_game(
    payload: Mapping[str, object],
    source_path: Path,
) -> OfficialNcaaAvailabilityGame:
    return OfficialNcaaAvailabilityGame(
        ncaa_game_code=_optional_string(payload.get("ncaa_game_code")),
        source_event_id=_optional_string(payload.get("source_event_id")),
        scheduled_start=_required_timestamp(payload, "scheduled_start", source_path),
        home_team=_parse_team(
            _required_mapping(payload, "home_team", source_path),
            source_path,
            field_name="home_team",
        ),
        away_team=_parse_team(
            _required_mapping(payload, "away_team", source_path),
            source_path,
            field_name="away_team",
        ),
    )


def _parse_team(
    payload: Mapping[str, object],
    source_path: Path,
    *,
    field_name: str,
) -> OfficialNcaaAvailabilityTeam:
    return OfficialNcaaAvailabilityTeam(
        name=_required_string(payload, "name", source_path, prefix=field_name),
        ncaa_team_code=_optional_string(payload.get("ncaa_team_code")),
    )


def _parse_row(
    payload: Mapping[str, object],
    row_number: int,
    source_path: Path,
) -> OfficialNcaaAvailabilityRow:
    raw_status = _required_string(payload, "status", source_path, prefix="statuses")
    status = raw_status.lower()
    if status not in _ALLOWED_AVAILABILITY_STATUSES:
        allowed_statuses = ", ".join(sorted(_ALLOWED_AVAILABILITY_STATUSES))
        raise ValueError(
            "Unsupported availability status in "
            f"{source_path} row {row_number}: {raw_status!r}. "
            f"Expected one of: {allowed_statuses}"
        )

    return OfficialNcaaAvailabilityRow(
        row_number=row_number,
        team=OfficialNcaaAvailabilityTeam(
            name=_required_string(
                payload,
                "team_name",
                source_path,
                prefix="statuses",
            ),
            ncaa_team_code=_optional_string(payload.get("team_ncaa_code")),
        ),
        player_name=_required_string(
            payload,
            "player_name",
            source_path,
            prefix="statuses",
        ),
        status=status,
        jersey_number=_optional_string(payload.get("jersey_number")),
        position=_optional_string(payload.get("position")),
        note=_optional_string(payload.get("note")),
        updated_at=_optional_timestamp(payload.get("updated_at"), source_path),
        raw_payload=payload,
    )


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
    normalized_rows: list[Mapping[str, object]] = []
    for index, row in enumerate(value, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(
                "Availability capture "
                f"{source_path} has a non-object row at {field_name}[{index - 1}]."
            )
        normalized_rows.append(row)
    return tuple(normalized_rows)


def _required_string(
    payload: Mapping[str, object],
    field_name: str,
    source_path: Path,
    *,
    prefix: str | None = None,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        field_label = f"{prefix}.{field_name}" if prefix is not None else field_name
        raise ValueError(
            "Availability capture "
            f"{source_path} is missing string field {field_label!r}."
        )
    return value.strip()


def _required_timestamp(
    payload: Mapping[str, object],
    field_name: str,
    source_path: Path,
) -> str:
    value = _required_string(payload, field_name, source_path)
    return _normalize_timestamp(value, source_path, field_name=field_name)


def _optional_timestamp(value: object, source_path: Path) -> str | None:
    optional_value = _optional_string(value)
    if optional_value is None:
        return None
    return _normalize_timestamp(
        optional_value,
        source_path,
        field_name="optional timestamp",
    )


def _normalize_timestamp(
    value: str,
    source_path: Path,
    *,
    field_name: str,
) -> str:
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
    "OFFICIAL_NCAA_AVAILABILITY_SOURCE",
    "OfficialNcaaAvailabilityGame",
    "OfficialNcaaAvailabilityReport",
    "OfficialNcaaAvailabilityRow",
    "OfficialNcaaAvailabilityTeam",
    "expand_official_ncaa_capture_paths",
    "load_official_ncaa_availability_capture",
]
