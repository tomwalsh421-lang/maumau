"""ESPN client helpers for historical game ingest."""

from __future__ import annotations

from datetime import date

import orjson
import requests

DEFAULT_SCOREBOARD_GROUP = "50"
DEFAULT_SCOREBOARD_LIMIT = 500
DEFAULT_SCOREBOARD_BASE_URL = (
    "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"
)


class EspnScoreboardClient:
    """Fetch NCAA Division I scoreboard slices from ESPN."""

    def __init__(
        self,
        base_url: str = DEFAULT_SCOREBOARD_BASE_URL,
        session: requests.Session | None = None,
    ) -> None:
        """Initialize the ESPN scoreboard client.

        Args:
            base_url: Base URL for the ESPN scoreboard API.
            session: Optional requests session.
        """
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def get_scoreboard(
        self,
        game_date: date,
        *,
        group: str = DEFAULT_SCOREBOARD_GROUP,
        limit: int = DEFAULT_SCOREBOARD_LIMIT,
    ) -> list[dict[str, object]]:
        """Fetch the daily D1 scoreboard payload for a single date.

        Args:
            game_date: Target game date.
            group: ESPN group code for NCAA Division I.
            limit: Maximum number of events to request.

        Returns:
            A list of raw event payloads.

        Raises:
            RuntimeError: If the request fails or returns an invalid payload.
        """
        request_params: dict[str, str | int] = {
            "dates": game_date.strftime("%Y%m%d"),
            "groups": group,
            "limit": limit,
        }

        response = self.session.get(
            f"{self.base_url}/scoreboard",
            params=request_params,
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text[:300].strip()
            raise RuntimeError(
                f"ESPN scoreboard request failed for {game_date.isoformat()} with "
                f"status {response.status_code}: {detail}"
            ) from exc

        payload = orjson.loads(response.content)
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected ESPN scoreboard payload for {game_date.isoformat()}"
            )

        events = payload.get("events")
        if not isinstance(events, list):
            raise RuntimeError(
                f"Unexpected ESPN scoreboard payload for {game_date.isoformat()}"
            )

        return [event for event in events if isinstance(event, dict)]

    def get_teams(
        self,
        *,
        group: str = DEFAULT_SCOREBOARD_GROUP,
        limit: int = DEFAULT_SCOREBOARD_LIMIT,
    ) -> list[dict[str, object]]:
        """Fetch the current ESPN D1 team directory.

        Args:
            group: ESPN group code for NCAA Division I.
            limit: Maximum number of teams to request.

        Returns:
            A list of raw ESPN team payloads.

        Raises:
            RuntimeError: If the request fails or returns an invalid payload.
        """
        request_params: dict[str, str | int] = {"groups": group, "limit": limit}
        response = self.session.get(
            f"{self.base_url}/teams",
            params=request_params,
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text[:300].strip()
            raise RuntimeError(
                "ESPN team directory request failed with status "
                f"{response.status_code}: {detail}"
            ) from exc

        payload = orjson.loads(response.content)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected ESPN team directory payload")

        sports = payload.get("sports")
        if not isinstance(sports, list) or not sports:
            raise RuntimeError("Unexpected ESPN team directory payload")
        leagues = sports[0].get("leagues")
        if not isinstance(leagues, list) or not leagues:
            raise RuntimeError("Unexpected ESPN team directory payload")
        teams = leagues[0].get("teams")
        if not isinstance(teams, list):
            raise RuntimeError("Unexpected ESPN team directory payload")

        team_payloads: list[dict[str, object]] = []
        for item in teams:
            if not isinstance(item, dict):
                continue
            team = item.get("team")
            if isinstance(team, dict):
                team_payloads.append(team)

        return team_payloads

    def get_team_details(self, team_id: str) -> dict[str, object]:
        """Fetch one ESPN team detail payload.

        Args:
            team_id: ESPN team identifier from the team directory.

        Returns:
            The raw nested ``team`` payload for the requested team.

        Raises:
            RuntimeError: If the request fails or returns an invalid payload.
        """
        response = self.session.get(
            f"{self.base_url}/teams/{team_id}",
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text[:300].strip()
            raise RuntimeError(
                "ESPN team detail request failed for "
                f"team_id={team_id} with status {response.status_code}: {detail}"
            ) from exc

        payload = orjson.loads(response.content)
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected ESPN team detail payload for team_id={team_id}"
            )
        team_payload = payload.get("team")
        if not isinstance(team_payload, dict):
            raise RuntimeError(
                f"Unexpected ESPN team detail payload for team_id={team_id}"
            )
        return team_payload
