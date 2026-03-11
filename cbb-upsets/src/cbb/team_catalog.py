"""Canonical NCAA men's D1 team catalog and alias resolution."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.engine import Connection

from cbb.ingest.clients.espn import EspnScoreboardClient
from cbb.ingest.matching import (
    best_alias_score,
    build_team_aliases,
    build_team_name_variants,
)
from cbb.ingest.utils import normalize_team_key

MIN_TEAM_MATCH_SCORE = 2

CREATE_TEAM_ALIASES_SQL = text(
    """
    CREATE TABLE IF NOT EXISTS team_aliases (
        team_alias_id SERIAL PRIMARY KEY,
        team_id INT NOT NULL REFERENCES teams(team_id) ON DELETE CASCADE,
        alias_key VARCHAR(160) NOT NULL UNIQUE,
        alias_name VARCHAR(255) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    )
    """
)

ALTER_TEAMS_ADD_CONFERENCE_KEY_SQL = text(
    """
    ALTER TABLE teams ADD COLUMN conference_key VARCHAR(120)
    """
)

ALTER_TEAMS_ADD_CONFERENCE_NAME_SQL = text(
    """
    ALTER TABLE teams ADD COLUMN conference_name VARCHAR(120)
    """
)

UPSERT_CANONICAL_TEAM_SQL = text(
    """
    INSERT INTO teams (team_key, name, conference_key, conference_name)
    VALUES (:team_key, :name, :conference_key, :conference_name)
    ON CONFLICT (team_key) DO UPDATE SET
        name = excluded.name,
        conference_key = excluded.conference_key,
        conference_name = excluded.conference_name
    RETURNING team_id
    """
)

UPSERT_TEAM_ALIAS_SQL = text(
    """
    INSERT INTO team_aliases (team_id, alias_key, alias_name)
    VALUES (:team_id, :alias_key, :alias_name)
    ON CONFLICT (alias_key) DO UPDATE SET
        team_id = excluded.team_id,
        alias_name = excluded.alias_name
    """
)

FETCH_TEAMS_BY_KEY_SQL = text(
    """
    SELECT team_id, team_key
    FROM teams
    WHERE team_key IN :team_keys
    """
).bindparams(bindparam("team_keys", expanding=True))

FETCH_TEAM_ALIAS_SQL = text(
    """
    SELECT team_id
    FROM team_aliases
    WHERE alias_key = :alias_key
    """
)


SUPPLEMENTAL_TEAMS = (
    ("Lindenwood", "Lindenwood Lions"),
    ("Queens University", "Queens University Royals"),
    ("Southern Indiana", "Southern Indiana Screaming Eagles"),
)

MANUAL_TEAM_ALIASES: dict[str, tuple[str, ...]] = {
    "app-state-mountaineers": (
        "Appalachian State Mountaineers",
        "Appalachian St Mountaineers",
    ),
    "california-baptist-lancers": ("Cal Baptist Lancers",),
    "cal-state-bakersfield-roadrunners": ("CSU Bakersfield Roadrunners",),
    "cal-state-fullerton-titans": ("CSU Fullerton Titans",),
    "cal-state-northridge-matadors": ("CSU Northridge Matadors",),
    "east-tennessee-state-buccaneers": ("ETSU Buccaneers",),
    "florida-atlantic-owls": ("FAU Owls", "Fla Atlantic Owls"),
    "florida-gulf-coast-eagles": ("FGCU Eagles",),
    "florida-international-panthers": (
        "FIU Panthers",
        "Florida Int'l Panthers",
        "Florida Intl Panthers",
        "Florida Int'l Golden Panthers",
    ),
    "george-washington-revolutionaries": (
        "GW Revolutionaries",
        "George Washington Colonials",
    ),
    "iu-indianapolis-jaguars": ("IU Indy Jaguars", "IUPUI Jaguars"),
    "little-rock-trojans": ("Arkansas-Little Rock Trojans",),
    "long-island-university-sharks": ("LIU Sharks",),
    "loyola-chicago-ramblers": ("Loyola (Chi) Ramblers",),
    "loyola-marymount-lions": ("LMU Lions",),
    "miami-hurricanes": ("Miami (FL) Hurricanes",),
    "north-carolina-a-t-aggies": ("N.C. A&T Aggies",),
    "north-carolina-central-eagles": ("N.C. Central Eagles",),
    "pennsylvania-quakers": ("Penn Quakers",),
    "saint-francis-red-flash": ("Saint Francis (PA) Red Flash",),
    "se-louisiana-lions": ("SE Louisiana Lions", "Southeastern Louisiana Lions"),
    "siu-edwardsville-cougars": ("SIUE Cougars",),
    "southeast-missouri-state-redhawks": ("SE Missouri St Redhawks",),
    "south-carolina-upstate-spartans": ("USC Upstate Spartans",),
    "south-florida-bulls": ("South Fla Bulls",),
    "st-thomas-minnesota-tommies": ("St. Thomas (MN) Tommies",),
    "stephen-f-austin-lumberjacks": ("SFA Lumberjacks",),
    "unc-greensboro-spartans": ("UNCG Spartans",),
    "unc-wilmington-seahawks": ("UNCW Seahawks",),
    "usc-trojans": ("Southern California Trojans",),
    "ut-martin-skyhawks": ("Tenn-Martin Skyhawks",),
    "ut-rio-grande-valley-vaqueros": ("UTRGV Vaqueros",),
}


@dataclass(frozen=True)
class CanonicalTeam:
    """Canonical D1 team record used for seeding and resolution."""

    team_key: str
    school_name: str
    display_name: str
    alias_names: tuple[str, ...]
    conference_key: str | None = None
    conference_name: str | None = None


class TeamCatalog:
    """In-memory D1 team catalog with canonical display names and aliases."""

    def __init__(self, records: Sequence[CanonicalTeam]) -> None:
        self.records = tuple(sorted(records, key=lambda record: record.team_key))
        self.teams_by_key = {record.team_key: record for record in self.records}
        self.aliases_by_team_key = {
            record.team_key: _build_record_aliases(record) for record in self.records
        }
        self.exact_alias_lookup = _build_exact_alias_lookup(self.records)

    def resolve_team_name(self, team_name: str) -> CanonicalTeam | None:
        """Resolve a provider team name to one canonical D1 team.

        Args:
            team_name: Provider-specific team name.

        Returns:
            The matched canonical team, or ``None`` when no unique D1 match exists.
        """
        exact_match = self.exact_alias_lookup.get(normalize_team_key(team_name))
        if exact_match is not None:
            return exact_match

        provider_aliases = build_team_aliases(team_name)
        scored_records: list[tuple[int, str]] = []

        for record in self.records:
            score = best_alias_score(
                provider_aliases,
                self.aliases_by_team_key[record.team_key],
            )
            if score >= MIN_TEAM_MATCH_SCORE:
                scored_records.append((score, record.team_key))

        if not scored_records:
            return None

        scored_records.sort(reverse=True)
        best_score = scored_records[0][0]
        best_team_keys = [
            team_key for score, team_key in scored_records if score == best_score
        ]
        if len(best_team_keys) != 1:
            return None
        return self.teams_by_key[best_team_keys[0]]


def load_team_catalog(client: EspnScoreboardClient | None = None) -> TeamCatalog:
    """Fetch the current D1 team directory and build a canonical catalog.

    Args:
        client: Optional ESPN client override.

    Returns:
        The canonical D1 team catalog.
    """
    espn_client = client or EspnScoreboardClient()
    records: dict[str, CanonicalTeam] = {}

    for team_payload in espn_client.get_teams():
        school_name = _required_string(team_payload, "location")
        display_name = _required_string(team_payload, "displayName")
        team_key = normalize_team_key(display_name)
        conference_key, conference_name = _load_conference_metadata(
            espn_client=espn_client,
            team_id=_optional_string(team_payload, "id"),
        )
        records[team_key] = CanonicalTeam(
            team_key=team_key,
            school_name=school_name,
            display_name=display_name,
            alias_names=_build_alias_names(team_key, school_name, display_name),
            conference_key=conference_key,
            conference_name=conference_name,
        )

    for school_name, display_name in SUPPLEMENTAL_TEAMS:
        team_key = normalize_team_key(display_name)
        records.setdefault(
            team_key,
            CanonicalTeam(
                team_key=team_key,
                school_name=school_name,
                display_name=display_name,
                alias_names=_build_alias_names(team_key, school_name, display_name),
            ),
        )

    return TeamCatalog(tuple(records.values()))


def seed_team_catalog(
    connection: Connection,
    catalog: TeamCatalog,
) -> dict[str, int]:
    """Ensure canonical teams and aliases exist in the database.

    Args:
        connection: Open SQLAlchemy connection.
        catalog: Canonical team catalog.

    Returns:
        Mapping of canonical team keys to database team IDs.
    """
    ensure_team_catalog_schema(connection)
    for record in catalog.records:
        connection.execute(
            UPSERT_CANONICAL_TEAM_SQL,
            {
                "team_key": record.team_key,
                "name": record.display_name,
                "conference_key": record.conference_key,
                "conference_name": record.conference_name,
            },
        )

    rows = connection.execute(
        FETCH_TEAMS_BY_KEY_SQL,
        {"team_keys": [record.team_key for record in catalog.records]},
    ).mappings()
    team_ids_by_key = {str(row["team_key"]): int(row["team_id"]) for row in rows}

    for record in catalog.records:
        team_id = team_ids_by_key[record.team_key]
        for alias_name in record.alias_names:
            connection.execute(
                UPSERT_TEAM_ALIAS_SQL,
                {
                    "team_id": team_id,
                    "alias_key": normalize_team_key(alias_name),
                    "alias_name": alias_name,
                },
            )

    return team_ids_by_key


def ensure_team_catalog_schema(connection: Connection) -> None:
    """Ensure the team alias schema exists.

    Args:
        connection: Open SQLAlchemy connection.
    """
    inspector = inspect(connection)
    table_names = set(inspector.get_table_names())
    if "teams" in table_names:
        team_columns = {
            str(column["name"]) for column in inspector.get_columns("teams")
        }
        if "conference_key" not in team_columns:
            connection.execute(ALTER_TEAMS_ADD_CONFERENCE_KEY_SQL)
        if "conference_name" not in team_columns:
            connection.execute(ALTER_TEAMS_ADD_CONFERENCE_NAME_SQL)
    if "team_aliases" not in inspector.get_table_names():
        connection.execute(CREATE_TEAM_ALIASES_SQL)


def resolve_team_id(
    connection: Connection,
    *,
    team_name: str,
    catalog: TeamCatalog,
    team_ids_by_key: Mapping[str, int],
) -> int | None:
    """Resolve a provider team name to a canonical database team ID.

    Args:
        connection: Open SQLAlchemy connection.
        team_name: Provider-specific team name.
        catalog: Canonical team catalog.
        team_ids_by_key: Preloaded mapping of canonical team keys to DB IDs.

    Returns:
        The canonical database team ID, or ``None`` when unresolved.
    """
    alias_key = normalize_team_key(team_name)
    existing_row = (
        connection.execute(
            FETCH_TEAM_ALIAS_SQL,
            {"alias_key": alias_key},
        )
        .mappings()
        .first()
    )
    if existing_row is not None:
        return int(existing_row["team_id"])

    resolved_team = catalog.resolve_team_name(team_name)
    if resolved_team is None:
        return None

    team_id = team_ids_by_key[resolved_team.team_key]
    connection.execute(
        UPSERT_TEAM_ALIAS_SQL,
        {"team_id": team_id, "alias_key": alias_key, "alias_name": team_name},
    )
    return team_id


def _build_alias_names(
    team_key: str,
    school_name: str,
    display_name: str,
) -> tuple[str, ...]:
    alias_names = {school_name, display_name}
    mascot_suffix = _extract_mascot_suffix(school_name, display_name)
    if mascot_suffix is not None:
        for school_variant in build_team_name_variants(school_name):
            alias_names.add(_title_case_alias(f"{school_variant} {mascot_suffix}"))

    alias_names.update(MANUAL_TEAM_ALIASES.get(team_key, ()))
    return tuple(sorted(alias_names))


def _extract_mascot_suffix(school_name: str, display_name: str) -> str | None:
    prefix = f"{school_name} "
    if display_name.startswith(prefix):
        return display_name.removeprefix(prefix).strip()
    return None


def _title_case_alias(alias_name: str) -> str:
    return " ".join(token.capitalize() for token in alias_name.split())


def _build_record_aliases(record: CanonicalTeam) -> frozenset[str]:
    aliases: set[str] = set()
    for alias_name in record.alias_names:
        aliases.update(build_team_aliases(alias_name))
    return frozenset(aliases)


def _build_exact_alias_lookup(
    records: Sequence[CanonicalTeam],
) -> dict[str, CanonicalTeam]:
    candidates: dict[str, list[CanonicalTeam]] = defaultdict(list)

    for record in records:
        for alias_name in record.alias_names:
            candidates[normalize_team_key(alias_name)].append(record)

    exact_alias_lookup: dict[str, CanonicalTeam] = {}
    for alias_key, matching_records in candidates.items():
        unique_team_keys = {record.team_key for record in matching_records}
        if len(unique_team_keys) == 1:
            exact_alias_lookup[alias_key] = matching_records[0]
    return exact_alias_lookup


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected ESPN team payload {key!r} to be a string")


def _optional_string(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    return None


def _load_conference_metadata(
    *,
    espn_client: EspnScoreboardClient,
    team_id: str | None,
) -> tuple[str | None, str | None]:
    if team_id is None:
        return None, None

    try:
        detail_payload = espn_client.get_team_details(team_id)
    except RuntimeError:
        return None, None

    conference_name = _conference_name_from_detail(detail_payload)
    if conference_name is None:
        return None, None
    return normalize_team_key(conference_name), conference_name


def _conference_name_from_detail(team_payload: Mapping[str, object]) -> str | None:
    standing_summary = team_payload.get("standingSummary")
    if isinstance(standing_summary, str) and " in " in standing_summary:
        return standing_summary.rsplit(" in ", maxsplit=1)[-1].strip() or None
    return None
