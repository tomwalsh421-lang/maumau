from __future__ import annotations

from cbb.ingest.utils import normalize_team_key
from cbb.team_catalog import CanonicalTeam, TeamCatalog


def make_team_catalog(
    definitions: list[tuple[str, str, tuple[str, ...] | None]],
) -> TeamCatalog:
    records = []
    for school_name, display_name, extra_aliases in definitions:
        aliases = tuple(sorted({school_name, display_name, *(extra_aliases or ())}))
        records.append(
            CanonicalTeam(
                team_key=normalize_team_key(display_name),
                school_name=school_name,
                display_name=display_name,
                alias_names=aliases,
            )
        )
    return TeamCatalog(tuple(records))
