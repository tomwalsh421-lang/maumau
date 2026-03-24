from __future__ import annotations

from datetime import UTC, datetime

import pytest

from cbb.team_home_locations import (
    build_matchup_travel_context,
    load_team_home_locations,
)


def test_team_home_location_catalog_covers_tracked_teams() -> None:
    locations = load_team_home_locations()

    assert len(locations) == 365
    assert len(set(locations)) == len(locations)
    assert all(location.point.timezone_name for location in locations.values())
    assert all(location.home_games > 0 for location in locations.values())


def test_build_matchup_travel_context_handles_home_and_neutral_sites() -> None:
    commence_time = datetime(2026, 3, 20, 23, 0, tzinfo=UTC)

    home_context, away_context = build_matchup_travel_context(
        home_team_key="duke-blue-devils",
        away_team_key="north-carolina-tar-heels",
        neutral_site=False,
        venue_city="Durham",
        venue_state="NC",
        commence_time=commence_time,
    )

    assert home_context.distance_miles == pytest.approx(0.0, abs=1.0)
    assert home_context.timezone_crossings == 0
    assert away_context.distance_miles is not None
    assert away_context.distance_miles > 5.0
    assert away_context.timezone_crossings == 0

    neutral_home_context, neutral_away_context = build_matchup_travel_context(
        home_team_key="duke-blue-devils",
        away_team_key="ucla-bruins",
        neutral_site=True,
        venue_city="Las Vegas",
        venue_state="NV",
        commence_time=commence_time,
    )

    assert neutral_home_context.distance_miles is not None
    assert neutral_away_context.distance_miles is not None
    assert neutral_home_context.distance_miles > 1500.0
    assert neutral_away_context.distance_miles > 200.0
    assert neutral_home_context.timezone_crossings == 3
    assert neutral_away_context.timezone_crossings == 0
