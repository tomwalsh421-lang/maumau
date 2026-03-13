"""Loader helpers for wrapped official availability captures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

import orjson

from cbb.ingest.clients.availability_types import OfficialAvailabilityReport
from cbb.ingest.clients.hdintelligence import (
    is_hdintelligence_archive_source_name,
    load_hdintelligence_archive_capture_payload,
)
from cbb.ingest.clients.ncaa import (
    OFFICIAL_NCAA_AVAILABILITY_SOURCE,
    load_official_ncaa_availability_payload,
)

_ALLOWED_CAPTURE_SUFFIXES = frozenset({".json"})


def expand_official_availability_capture_paths(
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
        raise ValueError("No official availability capture JSON files found.")
    return unique_paths


def load_official_availability_captures(
    path: Path | str,
) -> tuple[OfficialAvailabilityReport, ...]:
    """Load one wrapped availability capture file into normalized reports."""

    capture_path = Path(path).expanduser().resolve()
    payload = _load_capture_payload(capture_path)
    source_payload = _required_mapping(payload, "source", capture_path)
    source_name = _required_source_name(source_payload, capture_path)

    if source_name == OFFICIAL_NCAA_AVAILABILITY_SOURCE:
        return (load_official_ncaa_availability_payload(payload, capture_path),)
    if is_hdintelligence_archive_source_name(source_name):
        return load_hdintelligence_archive_capture_payload(payload, capture_path)

    raise ValueError(
        "Unsupported availability source_name in "
        f"{capture_path}: {source_name!r}"
    )


def _load_capture_payload(path: Path) -> Mapping[str, object]:
    try:
        payload = orjson.loads(path.read_bytes())
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Availability capture path not found: {path}") from exc
    except OSError as exc:
        raise RuntimeError(
            f"Could not read availability capture file: {path}"
        ) from exc
    except orjson.JSONDecodeError as exc:
        raise ValueError(
            f"Availability capture file is not valid JSON: {path}"
        ) from exc

    if not isinstance(payload, Mapping):
        raise ValueError(
            "Availability capture payload must be a JSON object: "
            f"{path}"
        )
    return payload


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


def _required_source_name(
    source_payload: Mapping[str, object],
    source_path: Path,
) -> str:
    value = source_payload.get("source_name")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "Availability capture "
            f"{source_path} is missing string field 'source.source_name'."
        )
    return value.strip()


__all__ = [
    "expand_official_availability_capture_paths",
    "load_official_availability_captures",
]
