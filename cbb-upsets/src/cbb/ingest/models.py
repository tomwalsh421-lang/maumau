"""Shared data models for ingest workflows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApiQuota:
    """Request quota metadata returned by an upstream API."""

    remaining: int | None
    used: int | None
    last_cost: int | None


@dataclass(frozen=True)
class OddsApiResponse:
    """Typed Odds API response payload and quota metadata."""

    data: object
    quota: ApiQuota


@dataclass(frozen=True)
class OddsIngestSummary:
    """Summary of records loaded from The Odds API into the database."""

    sport: str
    teams_seen: int
    games_upserted: int
    odds_snapshots_upserted: int
    completed_games_updated: int
    odds_quota: ApiQuota
    scores_quota: ApiQuota | None = None


@dataclass(frozen=True)
class HistoricalIngestSummary:
    """Summary of a historical game backfill run."""

    sport: str
    start_date: str
    end_date: str
    dates_requested: int
    dates_skipped: int
    dates_completed: int
    teams_seen: int
    games_seen: int
    games_inserted: int
