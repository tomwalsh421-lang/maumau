"""Dashboard backend package for middleware, caching, and snapshot helpers."""

from cbb.dashboard.bootstrap import (
    build_dashboard_middleware,
    prepare_dashboard_backend,
)
from cbb.dashboard.service import DashboardConfig, DashboardMiddleware, DashboardService

__all__ = [
    "DashboardConfig",
    "DashboardMiddleware",
    "DashboardService",
    "build_dashboard_middleware",
    "prepare_dashboard_backend",
]
