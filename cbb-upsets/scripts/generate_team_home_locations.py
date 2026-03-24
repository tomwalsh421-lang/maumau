"""Generate tracked team home-location data from stored home venues."""

from __future__ import annotations

import csv
from pathlib import Path

import requests
from sqlalchemy import text

from cbb.db import REPO_ROOT, get_engine

OUTPUT_PATH = REPO_ROOT / "data" / "team_home_locations.csv"
SOURCE_NAME = "dominant_home_venue_open_meteo_v1"
STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}
FETCH_DOMINANT_HOME_VENUES_SQL = text(
    """
    WITH home_venues AS (
        SELECT
            g.team1_id AS team_id,
            COALESCE(g.venue_name, '') AS venue_name,
            g.venue_city,
            g.venue_state,
            COUNT(*) AS home_games,
            MAX(g.commence_time) AS latest_commence_time
        FROM games g
        WHERE COALESCE(g.neutral_site, FALSE) = FALSE
          AND g.venue_city IS NOT NULL
          AND g.venue_state IS NOT NULL
        GROUP BY g.team1_id, COALESCE(g.venue_name, ''), g.venue_city, g.venue_state
    ),
    ranked AS (
        SELECT
            team_id,
            venue_name,
            venue_city,
            venue_state,
            home_games,
            latest_commence_time,
            ROW_NUMBER() OVER (
                PARTITION BY team_id
                ORDER BY home_games DESC, latest_commence_time DESC,
                         venue_name ASC, venue_city ASC, venue_state ASC
            ) AS row_number
        FROM home_venues
    )
    SELECT
        t.team_key,
        t.name,
        r.venue_name,
        r.venue_city,
        r.venue_state,
        r.home_games
    FROM ranked r
    JOIN teams t ON t.team_id = r.team_id
    WHERE r.row_number = 1
    ORDER BY t.team_key
    """
)


def main() -> None:
    """Write the tracked team home-location CSV from the current database."""
    engine = get_engine()
    with engine.connect() as connection:
        rows = [
            dict(row)
            for row in connection.execute(
                FETCH_DOMINANT_HOME_VENUES_SQL
            ).mappings().all()
        ]

    geocoder = requests.Session()
    cache: dict[tuple[str, str], dict[str, object]] = {}
    output_rows: list[dict[str, object]] = []
    for row in rows:
        city = str(row["venue_city"]).strip()
        state = str(row["venue_state"]).strip().upper()
        location = cache.setdefault(
            (city, state),
            _fetch_city_location(
                geocoder=geocoder,
                city=city,
                state=state,
            ),
        )
        output_rows.append(
            {
                "team_key": row["team_key"],
                "team_name": row["name"],
                "venue_name": row["venue_name"],
                "city": city,
                "state": state,
                "latitude": f"{float(location['latitude']):.6f}",
                "longitude": f"{float(location['longitude']):.6f}",
                "timezone_name": str(location["timezone_name"]),
                "elevation_m": (
                    f"{float(location['elevation_m']):.1f}"
                    if location["elevation_m"] is not None
                    else ""
                ),
                "home_games": int(row["home_games"]),
                "source_name": SOURCE_NAME,
            }
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "team_key",
                "team_name",
                "venue_name",
                "city",
                "state",
                "latitude",
                "longitude",
                "timezone_name",
                "elevation_m",
                "home_games",
                "source_name",
            ),
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print(
        f"Wrote {len(output_rows)} team home locations to "
        f"{Path(OUTPUT_PATH).resolve()}"
    )


def _fetch_city_location(
    *,
    geocoder: requests.Session,
    city: str,
    state: str,
) -> dict[str, object]:
    response = geocoder.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={
            "name": city,
            "count": 100,
            "language": "en",
            "format": "json",
            "countryCode": "US",
        },
        timeout=30,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    state_name = STATE_NAMES[state]
    exact_matches = [
        result
        for result in results
        if result.get("name") == city and result.get("admin1") == state_name
    ]
    state_matches = [
        result for result in results if result.get("admin1") == state_name
    ]
    if exact_matches:
        chosen = max(
            exact_matches,
            key=lambda item: int(item.get("population") or 0),
        )
    elif state_matches:
        chosen = max(
            state_matches,
            key=lambda item: int(item.get("population") or 0),
        )
    else:
        raise RuntimeError(f"No geocode result for {city}, {state}")
    return {
        "latitude": float(chosen["latitude"]),
        "longitude": float(chosen["longitude"]),
        "timezone_name": str(chosen["timezone"]),
        "elevation_m": (
            float(chosen["elevation"])
            if chosen.get("elevation") is not None
            else None
        ),
    }


if __name__ == "__main__":
    main()
