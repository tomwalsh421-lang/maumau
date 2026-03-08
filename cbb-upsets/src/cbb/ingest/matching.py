"""Team-name matching helpers for cross-provider ingest workflows."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from itertools import product


_NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class TeamPairCandidate:
    """Candidate game identity used for team-pair matching.

    Args:
        candidate_id: Unique identifier for the candidate row.
        home_team_name: Stored home team name.
        away_team_name: Stored away team name.
    """

    candidate_id: int
    home_team_name: str
    away_team_name: str


def match_team_pair(
    home_team_name: str,
    away_team_name: str,
    candidates: list[TeamPairCandidate],
) -> int | None:
    """Match a provider home/away team pair to one stored candidate.

    Args:
        home_team_name: Provider home team name.
        away_team_name: Provider away team name.
        candidates: Candidate stored games for the same tipoff slot.

    Returns:
        The matched candidate ID when the best match is unique, otherwise ``None``.
    """
    provider_home_aliases = build_team_aliases(home_team_name)
    provider_away_aliases = build_team_aliases(away_team_name)
    scored_candidates: list[tuple[int, int, int]] = []

    for candidate in candidates:
        home_score = _best_alias_score(
            provider_home_aliases,
            build_team_aliases(candidate.home_team_name),
        )
        away_score = _best_alias_score(
            provider_away_aliases,
            build_team_aliases(candidate.away_team_name),
        )
        if home_score == 0 or away_score == 0:
            continue
        scored_candidates.append(
            (home_score + away_score, min(home_score, away_score), candidate.candidate_id)
        )

    if not scored_candidates:
        return None

    scored_candidates.sort(reverse=True)
    best_score = scored_candidates[0][:2]
    tied_candidates = [
        candidate_id
        for total_score, weakest_side_score, candidate_id in scored_candidates
        if (total_score, weakest_side_score) == best_score
    ]
    if len(tied_candidates) != 1:
        return None
    return tied_candidates[0]


@lru_cache(maxsize=2048)
def build_team_aliases(team_name: str) -> frozenset[str]:
    """Build normalized prefix aliases for a team name.

    Args:
        team_name: Provider-specific team name.

    Returns:
        A frozen set of normalized aliases ordered from full name down to school-only
        prefixes. The alias set includes common abbreviation variants such as
        ``st``/``state`` and optional removal of ``u``/``university`` tokens.
    """
    token_options = [_expand_token(token) for token in _tokenize_team_name(team_name)]
    aliases: set[str] = set()

    for variant in product(*token_options):
        filtered_tokens = tuple(token for token in variant if token not in {"", "the"})
        if not filtered_tokens:
            continue
        for index in range(len(filtered_tokens), 0, -1):
            aliases.add(" ".join(filtered_tokens[:index]))

    return frozenset(aliases)


def _best_alias_score(left_aliases: frozenset[str], right_aliases: frozenset[str]) -> int:
    smaller_aliases, larger_aliases = (
        (left_aliases, right_aliases)
        if len(left_aliases) <= len(right_aliases)
        else (right_aliases, left_aliases)
    )
    best_score = 0

    for alias in smaller_aliases:
        if alias in larger_aliases:
            best_score = max(best_score, alias.count(" ") + 1)

    return best_score


def _tokenize_team_name(team_name: str) -> tuple[str, ...]:
    normalized = (
        unicodedata.normalize("NFKD", team_name)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .replace("&", " and ")
    )
    tokens = tuple(
        token for token in _NON_ALNUM_PATTERN.sub(" ", normalized).split() if token
    )
    if not tokens:
        raise ValueError(f"Could not tokenize team name {team_name!r}")
    return tokens


def _expand_token(token: str) -> tuple[str, ...]:
    if token == "st":
        return ("st", "state", "saint")
    if token == "state":
        return ("state", "st")
    if token == "saint":
        return ("saint", "st")
    if token in {"u", "university"}:
        return (token, "")
    return (token,)
