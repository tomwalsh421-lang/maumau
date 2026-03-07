"""Ingest workflows and API clients."""

from cbb.ingest.clients import (
    DEFAULT_ODDS_MARKETS,
    DEFAULT_ODDS_REGIONS,
    DEFAULT_ODDS_SPORT,
    EspnScoreboardClient,
    OddsApiClient,
)
from cbb.ingest.historical import (
    DEFAULT_HISTORICAL_YEARS,
    HistoricalIngestOptions,
    build_historical_game,
    ingest_historical_games,
)
from cbb.ingest.models import (
    ApiQuota,
    HistoricalIngestSummary,
    OddsApiResponse,
    OddsIngestSummary,
)
from cbb.ingest.odds import (
    OddsIngestOptions,
    OddsPersistenceInput,
    build_odds_game,
    ingest_current_odds,
    persist_odds_data,
)
from cbb.ingest.utils import DEFAULT_CBB_SPORT, derive_cbb_season, normalize_team_key

__all__ = [
    "ApiQuota",
    "DEFAULT_CBB_SPORT",
    "DEFAULT_HISTORICAL_YEARS",
    "DEFAULT_ODDS_MARKETS",
    "DEFAULT_ODDS_REGIONS",
    "DEFAULT_ODDS_SPORT",
    "EspnScoreboardClient",
    "HistoricalIngestOptions",
    "HistoricalIngestSummary",
    "OddsApiClient",
    "OddsApiResponse",
    "OddsIngestOptions",
    "OddsIngestSummary",
    "OddsPersistenceInput",
    "build_historical_game",
    "build_odds_game",
    "derive_cbb_season",
    "ingest_current_odds",
    "ingest_historical_games",
    "normalize_team_key",
    "persist_odds_data",
]
