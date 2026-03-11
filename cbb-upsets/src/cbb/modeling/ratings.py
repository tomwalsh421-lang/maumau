"""Rolling team-state features used by the betting models."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

DEFAULT_ELO = 1500.0
ELO_K_FACTOR = 20.0
ROLLING_WINDOW = 10


@dataclass(frozen=True)
class TeamSnapshot:
    """Pregame snapshot of one team's rolling state."""

    games_played: int
    win_pct: float
    average_margin: float
    average_points_for: float
    average_points_against: float
    elo: float
    rest_days: float
    season_opening_elo: float


@dataclass
class TeamState:
    """Mutable rolling state for one team while traversing games."""

    results: deque[int] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    margins: deque[float] = field(default_factory=lambda: deque(maxlen=ROLLING_WINDOW))
    points_for: deque[float] = field(
        default_factory=lambda: deque(maxlen=ROLLING_WINDOW)
    )
    points_against: deque[float] = field(
        default_factory=lambda: deque(maxlen=ROLLING_WINDOW)
    )
    elo: float = DEFAULT_ELO
    last_game_time: datetime | None = None
    season: int | None = None
    season_opening_elo: float = DEFAULT_ELO


def prepare_team_state_for_game(*, state: TeamState, season: int) -> None:
    """Reset season-local rolling state while preserving Elo carryover."""
    if state.season == season:
        return

    state.results.clear()
    state.margins.clear()
    state.points_for.clear()
    state.points_against.clear()
    state.last_game_time = None
    state.season = season
    state.season_opening_elo = state.elo


def build_team_snapshot(state: TeamState, commence_time: datetime) -> TeamSnapshot:
    """Build a pregame feature snapshot for one team."""
    games_played = len(state.results)
    if games_played == 0:
        return TeamSnapshot(
            games_played=0,
            win_pct=0.5,
            average_margin=0.0,
            average_points_for=0.0,
            average_points_against=0.0,
            elo=state.elo,
            rest_days=7.0,
            season_opening_elo=state.season_opening_elo,
        )

    rest_days = 7.0
    if state.last_game_time is not None:
        rest_days = max(
            0.0,
            (commence_time - state.last_game_time).total_seconds() / 86400.0,
        )

    return TeamSnapshot(
        games_played=games_played,
        win_pct=sum(state.results) / games_played,
        average_margin=sum(state.margins) / games_played,
        average_points_for=sum(state.points_for) / games_played,
        average_points_against=sum(state.points_against) / games_played,
        elo=state.elo,
        rest_days=rest_days,
        season_opening_elo=state.season_opening_elo,
    )


def update_team_states(
    *,
    home_state: TeamState,
    away_state: TeamState,
    home_score: int,
    away_score: int,
    commence_time: datetime,
) -> None:
    """Apply one completed game result to the rolling team states."""
    home_margin = float(home_score - away_score)
    away_margin = -home_margin
    home_result = 1 if home_margin > 0 else 0
    away_result = 1 - home_result

    home_expected = _elo_expected_score(home_state.elo, away_state.elo)
    away_expected = 1.0 - home_expected

    home_state.results.append(home_result)
    away_state.results.append(away_result)
    home_state.margins.append(home_margin)
    away_state.margins.append(away_margin)
    home_state.points_for.append(float(home_score))
    home_state.points_against.append(float(away_score))
    away_state.points_for.append(float(away_score))
    away_state.points_against.append(float(home_score))
    home_state.elo += ELO_K_FACTOR * (home_result - home_expected)
    away_state.elo += ELO_K_FACTOR * (away_result - away_expected)
    home_state.last_game_time = commence_time
    away_state.last_game_time = commence_time


def _elo_expected_score(team_elo: float, opponent_elo: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((opponent_elo - team_elo) / 400.0))
