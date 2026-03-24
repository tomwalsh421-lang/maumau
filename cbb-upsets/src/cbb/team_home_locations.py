"""Tracked team home-location data and travel-context helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cbb.db import REPO_ROOT

TEAM_HOME_LOCATIONS_PATH = REPO_ROOT / "data" / "team_home_locations.csv"
EARTH_RADIUS_MILES = 3958.7613


@dataclass(frozen=True)
class LocationPoint:
    """One geocoded city/state point with timezone metadata."""

    city: str
    state: str
    latitude: float
    longitude: float
    timezone_name: str
    elevation_m: float | None = None


@dataclass(frozen=True)
class TeamHomeLocation:
    """Auditable tracked home location for one canonical team."""

    team_key: str
    team_name: str
    venue_name: str
    home_games: int
    source_name: str
    point: LocationPoint


@dataclass(frozen=True)
class TravelContext:
    """Side-specific travel context for one game."""

    distance_miles: float | None = None
    timezone_crossings: int | None = None


def normalize_location_key(city: str, state: str) -> tuple[str, str]:
    """Return a stable lowercase key for one city/state pair."""
    return (city.strip().lower(), state.strip().upper())


@lru_cache(maxsize=1)
def load_team_home_locations(
    path: Path = TEAM_HOME_LOCATIONS_PATH,
) -> dict[str, TeamHomeLocation]:
    """Load the tracked team home-location catalog."""
    if not path.exists():
        raise FileNotFoundError(
            f"Tracked team home locations are missing: {path}"
        )

    locations: dict[str, TeamHomeLocation] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            team_key = str(row["team_key"]).strip()
            if not team_key:
                continue
            locations[team_key] = TeamHomeLocation(
                team_key=team_key,
                team_name=str(row["team_name"]).strip(),
                venue_name=str(row["venue_name"]).strip(),
                home_games=int(row["home_games"]),
                source_name=str(row["source_name"]).strip(),
                point=LocationPoint(
                    city=str(row["city"]).strip(),
                    state=str(row["state"]).strip(),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    timezone_name=str(row["timezone_name"]).strip(),
                    elevation_m=(
                        float(row["elevation_m"])
                        if row.get("elevation_m")
                        else None
                    ),
                ),
            )
    return locations


@lru_cache(maxsize=1)
def load_city_location_index(
    path: Path = TEAM_HOME_LOCATIONS_PATH,
) -> dict[tuple[str, str], LocationPoint]:
    """Load the unique city/state geocode index from the tracked team file."""
    city_locations: dict[tuple[str, str], LocationPoint] = {}
    for location in load_team_home_locations(path).values():
        city_locations.setdefault(
            normalize_location_key(location.point.city, location.point.state),
            location.point,
        )
    return city_locations


def build_matchup_travel_context(
    *,
    home_team_key: str | None,
    away_team_key: str | None,
    neutral_site: bool | None,
    venue_city: str | None,
    venue_state: str | None,
    commence_time: datetime,
) -> tuple[TravelContext, TravelContext]:
    """Return side travel context for the home and away teams."""
    team_locations = load_team_home_locations()
    venue_locations = load_city_location_index()
    venue_point = _location_point_for_city(
        city=venue_city,
        state=venue_state,
        city_locations=venue_locations,
    )
    home_point = _team_point(home_team_key, team_locations)
    away_point = _team_point(away_team_key, team_locations)
    return (
        _travel_context_for_side(
            home_point=home_point,
            venue_point=venue_point,
            commence_time=commence_time,
        ),
        _travel_context_for_side(
            home_point=away_point,
            venue_point=venue_point,
            commence_time=commence_time,
        ),
    )


def _team_point(
    team_key: str | None,
    team_locations: dict[str, TeamHomeLocation],
) -> LocationPoint | None:
    if team_key is None:
        return None
    location = team_locations.get(team_key)
    return location.point if location is not None else None


def _location_point_for_city(
    *,
    city: str | None,
    state: str | None,
    city_locations: dict[tuple[str, str], LocationPoint],
) -> LocationPoint | None:
    if city is None or state is None:
        return None
    return city_locations.get(normalize_location_key(city, state))


def _travel_context_for_side(
    *,
    home_point: LocationPoint | None,
    venue_point: LocationPoint | None,
    commence_time: datetime,
) -> TravelContext:
    if home_point is None or venue_point is None:
        return TravelContext()
    return TravelContext(
        distance_miles=_haversine_miles(
            home_point.latitude,
            home_point.longitude,
            venue_point.latitude,
            venue_point.longitude,
        ),
        timezone_crossings=_timezone_crossings(
            home_timezone_name=home_point.timezone_name,
            venue_timezone_name=venue_point.timezone_name,
            commence_time=commence_time,
        ),
    )


def _haversine_miles(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    latitude_delta = radians(latitude_b - latitude_a)
    longitude_delta = radians(longitude_b - longitude_a)
    latitude_a_rad = radians(latitude_a)
    latitude_b_rad = radians(latitude_b)
    haversine_value = (
        sin(latitude_delta / 2.0) ** 2
        + cos(latitude_a_rad)
        * cos(latitude_b_rad)
        * sin(longitude_delta / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_MILES * asin(sqrt(haversine_value))


def _timezone_crossings(
    *,
    home_timezone_name: str,
    venue_timezone_name: str,
    commence_time: datetime,
) -> int | None:
    try:
        home_timezone = ZoneInfo(home_timezone_name)
        venue_timezone = ZoneInfo(venue_timezone_name)
    except ZoneInfoNotFoundError:
        return None
    home_offset = commence_time.astimezone(home_timezone).utcoffset()
    venue_offset = commence_time.astimezone(venue_timezone).utcoffset()
    if home_offset is None or venue_offset is None:
        return None
    difference_hours = abs(
        (venue_offset.total_seconds() - home_offset.total_seconds()) / 3600.0
    )
    return int(round(difference_hours))
