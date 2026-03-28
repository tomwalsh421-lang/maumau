"""Dashboard backend bootstrap helpers."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cbb.dashboard.service import (
    DashboardConfig,
    DashboardService,
    PredictionSource,
    resolve_window_key,
)
from cbb.dashboard.snapshot import (
    DEFAULT_DASHBOARD_SNAPSHOT_PATH,
    ensure_dashboard_snapshot_fresh,
)


def build_dashboard_middleware(
    *,
    window_days: int = 14,
    database_url: str | None = None,
    artifacts_dir: Path | None = None,
    snapshot_path: Path | None = None,
    report_ttl_seconds: int = 300,
    prediction_ttl_seconds: int = 90,
    team_ttl_seconds: int = 600,
    prediction_source: PredictionSource = "live",
    prime_historical: bool = False,
) -> DashboardService:
    """Build the dashboard middleware used by the presentation layer."""
    service = DashboardService(
        DashboardConfig(
            default_window_key=resolve_window_key(str(window_days)),
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            snapshot_path=snapshot_path,
            report_ttl_seconds=report_ttl_seconds,
            prediction_ttl_seconds=prediction_ttl_seconds,
            team_ttl_seconds=team_ttl_seconds,
            prediction_source=prediction_source,
        )
    )
    if prime_historical:
        service.prime_historical_report()
    return service


def prepare_dashboard_backend(
    *,
    database_url: str | None = None,
    artifacts_dir: Path | None = None,
    snapshot_path: Path | None = None,
    progress: Callable[[str], None] | None = None,
) -> None:
    """Ensure the canonical dashboard snapshot is ready before serving UI traffic."""
    ensure_dashboard_snapshot_fresh(
        database_url=database_url,
        artifacts_dir=artifacts_dir,
        snapshot_path=snapshot_path or DEFAULT_DASHBOARD_SNAPSHOT_PATH,
        progress=progress,
    )
