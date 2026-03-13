"""The Odds API client used by the current odds ingest workflow."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import orjson
import requests

from cbb.config import get_settings
from cbb.ingest.models import ApiQuota, HistoricalOddsResponse, OddsApiResponse
from cbb.ingest.utils import DEFAULT_CBB_SPORT

DEFAULT_ODDS_SPORT = DEFAULT_CBB_SPORT
DEFAULT_ODDS_REGIONS = "us"
DEFAULT_ODDS_MARKETS = "h2h,spreads,totals"

RequestParamValue = str | int | float | bytes | None


class OddsApiClient:
    """Minimal client for The Odds API v4."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        """Initialize the Odds API client.

        Args:
            api_key: Optional API key override.
            base_url: Optional API base URL override.
            session: Optional requests session.

        Raises:
            RuntimeError: If no API key is configured.
        """
        settings = get_settings()
        self.api_key = api_key or settings.odds_api_key
        self.base_url = (base_url or settings.odds_api_base_url).rstrip("/")
        self.session = session or requests.Session()

        if not self.api_key:
            raise RuntimeError(
                "ODDS_API_KEY is not set. Add it to .env before calling "
                "`cbb ingest odds`."
            )

    def get_odds(
        self,
        sport: str = DEFAULT_ODDS_SPORT,
        regions: str = DEFAULT_ODDS_REGIONS,
        markets: str = DEFAULT_ODDS_MARKETS,
        bookmakers: str | None = None,
        odds_format: str = "american",
    ) -> OddsApiResponse:
        """Fetch odds markets for a sport.

        Args:
            sport: The Odds API sport key.
            regions: Comma-separated region filter.
            markets: Comma-separated market filter.
            bookmakers: Optional bookmaker filter.
            odds_format: ``american`` or ``decimal``.

        Returns:
            The parsed API response and quota metadata.
        """
        return self._get(
            path=f"/sports/{sport}/odds",
            params={
                "regions": regions,
                "markets": markets,
                "bookmakers": bookmakers,
                "oddsFormat": odds_format,
                "dateFormat": "iso",
            },
        )

    def get_scores(
        self,
        sport: str = DEFAULT_ODDS_SPORT,
        days_from: int = 3,
    ) -> OddsApiResponse:
        """Fetch recent or live scores for a sport.

        Args:
            sport: The Odds API sport key.
            days_from: Days of recent scores to include.

        Returns:
            The parsed API response and quota metadata.
        """
        return self._get(
            path=f"/sports/{sport}/scores",
            params={"daysFrom": days_from, "dateFormat": "iso"},
        )

    def get_historical_odds(
        self,
        *,
        date: datetime,
        sport: str = DEFAULT_ODDS_SPORT,
        regions: str = DEFAULT_ODDS_REGIONS,
        markets: str = DEFAULT_ODDS_MARKETS,
        bookmakers: str | None = None,
        odds_format: str = "american",
    ) -> HistoricalOddsResponse:
        """Fetch a historical odds snapshot for a sport.

        Args:
            date: Snapshot timestamp used by the historical endpoint.
            sport: The Odds API sport key.
            regions: Comma-separated region filter.
            markets: Comma-separated market filter.
            bookmakers: Optional comma-separated bookmaker key filter.
            odds_format: ``american`` or ``decimal``.

        Returns:
            The parsed historical snapshot payload and quota metadata.

        Raises:
            RuntimeError: If the response payload is not the expected shape.
        """
        response = self._get(
            path=f"/historical/sports/{sport}/odds",
            params={
                "date": _format_historical_timestamp(date),
                "regions": regions,
                "markets": markets,
                "bookmakers": bookmakers,
                "oddsFormat": odds_format,
                "dateFormat": "iso",
            },
        )

        payload = _required_mapping(response.data)
        timestamp = _required_string(payload, "timestamp")
        return HistoricalOddsResponse(
            timestamp=timestamp,
            previous_timestamp=_optional_string(payload.get("previous_timestamp")),
            next_timestamp=_optional_string(payload.get("next_timestamp")),
            data=_as_event_list(payload.get("data")),
            quota=response.quota,
        )

    def _get(
        self,
        path: str,
        params: Mapping[str, RequestParamValue] | None = None,
    ) -> OddsApiResponse:
        """Execute a GET request against The Odds API.

        Args:
            path: API path beginning with ``/``.
            params: Optional query parameters.

        Returns:
            The parsed response payload and quota metadata.

        Raises:
            RuntimeError: If the API responds with an error status or payload.
        """
        request_params: dict[str, RequestParamValue] = {"apiKey": self.api_key or ""}
        if params is not None:
            request_params.update(
                {key: value for key, value in params.items() if value not in (None, "")}
            )

        response = self.session.get(
            f"{self.base_url}{path}",
            params=request_params,
            timeout=30,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text[:300].strip()
            raise RuntimeError(
                f"Odds API request failed for {path} with status "
                f"{response.status_code}: {detail}"
            ) from exc

        return OddsApiResponse(
            data=orjson.loads(response.content),
            quota=_quota_from_headers(response),
        )


def _quota_from_headers(response: requests.Response) -> ApiQuota:
    return ApiQuota(
        remaining=_parse_header_int(response.headers.get("x-requests-remaining")),
        used=_parse_header_int(response.headers.get("x-requests-used")),
        last_cost=_parse_header_int(response.headers.get("x-requests-last")),
    )


def _parse_header_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _required_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    raise RuntimeError("Expected mapping payload from The Odds API.")


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected {key!r} to be a string")


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise RuntimeError(f"Expected optional string value, got {type(value).__name__}")


def _as_event_list(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    raise RuntimeError("Expected historical odds data to be a list")


def _format_historical_timestamp(value: datetime) -> str:
    normalized_value = (
        value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    )
    return normalized_value.isoformat().replace("+00:00", "Z")
