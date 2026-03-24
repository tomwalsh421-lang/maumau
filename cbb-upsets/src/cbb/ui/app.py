"""Tiny WSGI app and CLI launcher for the local dashboard UI."""

from __future__ import annotations

import json
import mimetypes
import webbrowser
from dataclasses import asdict, dataclass, is_dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import parse_qs
from wsgiref.simple_server import WSGIRequestHandler, make_server

from jinja2 import Environment, FileSystemLoader, select_autoescape

from cbb.dashboard import build_dashboard_middleware, prepare_dashboard_backend
from cbb.dashboard.service import (
    DashboardMiddleware,
    DashboardPage,
    ModelsPage,
    PerformancePage,
    PicksPage,
    TeamDetailPage,
    TeamsPage,
    UpcomingPage,
    parse_pick_history_filters,
    resolve_window_key,
)


@dataclass(frozen=True)
class _Request:
    path: str
    query: dict[str, str]


@dataclass(frozen=True)
class _Response:
    status: str
    body: bytes
    content_type: str = "text/html; charset=utf-8"


class _Announcer(Protocol):
    def __call__(self, message: str) -> None: ...


PRIMARY_NAV_ITEMS = (
    ("dashboard", "/", "Overview"),
    ("performance", "/performance", "Performance"),
    ("upcoming", "/upcoming", "Recommendations"),
    ("picks", "/picks", "Bet History"),
)

SECONDARY_NAV_ITEMS = (
    ("models", "/models", "Model Review"),
    ("teams", "/teams", "Team Explorer"),
)


class DashboardApp:
    """Small server-rendered dashboard app."""

    def __init__(self, service: DashboardMiddleware) -> None:
        template_root = resources.files("cbb.ui").joinpath("templates")
        self._templates = Environment(
            loader=FileSystemLoader(str(template_root)),
            autoescape=select_autoescape(("html",)),
        )
        self._service = service

    def __call__(self, environ: dict[str, object], start_response) -> list[bytes]:
        request = _Request(
            path=str(environ.get("PATH_INFO", "/")) or "/",
            query=_query_params(str(environ.get("QUERY_STRING", ""))),
        )
        try:
            response = self._dispatch(request)
        except KeyError:
            response = self._render(
                "error.html",
                status="404 Not Found",
                page_title="Team not found",
                page_key="teams",
                message="That team page does not exist in the local database.",
            )
        except Exception as exc:  # pragma: no cover - defensive runtime safety
            response = self._render(
                "error.html",
                status="500 Internal Server Error",
                page_title="Dashboard error",
                page_key="dashboard",
                message=str(exc),
            )
        start_response(
            response.status,
            [
                ("Content-Type", response.content_type),
                ("Content-Length", str(len(response.body))),
            ],
        )
        return [response.body]

    def _dispatch(self, request: _Request) -> _Response:
        if request.path == "/":
            return self._dashboard(request)
        if request.path == "/models":
            return self._models()
        if request.path == "/performance":
            return self._performance(request)
        if request.path == "/upcoming":
            return self._upcoming()
        if request.path == "/picks":
            return self._picks(request)
        if request.path == "/teams":
            return self._teams(request)
        if request.path == "/api/dashboard":
            return self._dashboard_json(request)
        if request.path == "/api/models":
            return self._models_json()
        if request.path == "/api/performance":
            return self._performance_json(request)
        if request.path == "/api/upcoming":
            return self._upcoming_json()
        if request.path == "/api/picks":
            return self._picks_json(request)
        if request.path == "/api/teams":
            return self._teams_json(request)
        if request.path.startswith("/teams/"):
            team_key = request.path.removeprefix("/teams/").strip("/")
            return self._team_detail(team_key)
        if request.path == "/api/teams/search":
            return self._team_search_json(request)
        if request.path.startswith("/api/teams/"):
            team_key = request.path.removeprefix("/api/teams/").strip("/")
            return self._team_detail_json(team_key)
        if request.path.startswith("/static/"):
            return self._static(request.path.removeprefix("/static/"))
        return self._render(
            "error.html",
            status="404 Not Found",
            page_title="Not found",
            page_key="dashboard",
            message="That page does not exist.",
        )

    def _dashboard(self, request: _Request) -> _Response:
        selected_window = resolve_window_key(
            request.query.get("window"),
            fallback=self._service.default_window_key(),
        )
        page = self._service.get_dashboard_page(window_key=selected_window)
        return self._render_page(
            "dashboard.html",
            page,
            page_title="CBB Dashboard",
            page_key="dashboard",
            selected_window=selected_window,
        )

    def _models(self) -> _Response:
        page = self._service.get_models_page()
        return self._render_page(
            "models.html",
            page,
            page_title="Model Overview",
            page_key="models",
        )

    def _performance(self, request: _Request) -> _Response:
        selected_window = resolve_window_key(
            request.query.get("window"),
            fallback=self._service.default_window_key(),
        )
        page = self._service.get_performance_page(window_key=selected_window)
        return self._render_page(
            "performance.html",
            page,
            page_title="Recent Performance",
            page_key="performance",
        )

    def _upcoming(self) -> _Response:
        page = self._service.get_upcoming_page()
        return self._render_page(
            "upcoming.html",
            page,
            page_title="Recommendations",
            page_key="upcoming",
        )

    def _picks(self, request: _Request) -> _Response:
        filters = parse_pick_history_filters(request.query)
        page = self._service.get_picks_page(filters=filters)
        return self._render_page(
            "picks.html",
            page,
            page_title="Pick History",
            page_key="picks",
        )

    def _teams(self, request: _Request) -> _Response:
        page = self._service.get_teams_page(query=request.query.get("q", ""))
        return self._render_page(
            "teams.html",
            page,
            page_title="Team Explorer",
            page_key="teams",
        )

    def _team_detail(self, team_key: str) -> _Response:
        page = self._service.get_team_detail_page(team_key)
        return self._render_page(
            "team_detail.html",
            page,
            page_title=page.team.team_name,
            page_key="teams",
        )

    def _team_search_json(self, request: _Request) -> _Response:
        payload = [
            {
                "team_key": result.team_key,
                "team_name": result.team_name,
                "match_hint": result.match_hint,
                "url": f"/teams/{result.team_key}",
            }
            for result in self._service.search_teams(request.query.get("q", ""))
        ]
        return _Response(
            status="200 OK",
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )

    def _dashboard_json(self, request: _Request) -> _Response:
        selected_window = resolve_window_key(
            request.query.get("window"),
            fallback=self._service.default_window_key(),
        )
        page = self._service.get_dashboard_page(window_key=selected_window)
        return self._json_response({"selected_window": selected_window, "page": page})

    def _models_json(self) -> _Response:
        return self._json_response({"page": self._service.get_models_page()})

    def _performance_json(self, request: _Request) -> _Response:
        selected_window = resolve_window_key(
            request.query.get("window"),
            fallback=self._service.default_window_key(),
        )
        page = self._service.get_performance_page(window_key=selected_window)
        return self._json_response({"selected_window": selected_window, "page": page})

    def _upcoming_json(self) -> _Response:
        return self._json_response({"page": self._service.get_upcoming_page()})

    def _picks_json(self, request: _Request) -> _Response:
        filters = parse_pick_history_filters(request.query)
        return self._json_response(
            {"page": self._service.get_picks_page(filters=filters)}
        )

    def _teams_json(self, request: _Request) -> _Response:
        return self._json_response(
            {"page": self._service.get_teams_page(query=request.query.get("q", ""))}
        )

    def _team_detail_json(self, team_key: str) -> _Response:
        return self._json_response(
            {"page": self._service.get_team_detail_page(team_key)}
        )

    def _static(self, asset_name: str) -> _Response:
        asset_path = resources.files("cbb.ui").joinpath("static", asset_name)
        if not asset_path.is_file():
            return self._render(
                "error.html",
                status="404 Not Found",
                page_title="Missing asset",
                page_key="dashboard",
                message="Static asset not found.",
            )
        content_type = mimetypes.guess_type(asset_name)[0] or "application/octet-stream"
        return _Response(
            status="200 OK",
            body=asset_path.read_bytes(),
            content_type=content_type,
        )

    def _render_page(
        self,
        template_name: str,
        page: DashboardPage
        | ModelsPage
        | PerformancePage
        | UpcomingPage
        | PicksPage
        | TeamsPage
        | TeamDetailPage,
        *,
        page_title: str,
        page_key: str,
        **extra_context: object,
    ) -> _Response:
        return self._render(
            template_name,
            status="200 OK",
            page_title=page_title,
            page_key=page_key,
            page=page,
            **extra_context,
        )

    def _render(
        self,
        template_name: str,
        *,
        status: str,
        page_title: str,
        page_key: str,
        **context: object,
    ) -> _Response:
        template = self._templates.get_template(template_name)
        html = template.render(
            nav_items=[
                {
                    "key": key,
                    "href": href,
                    "label": label,
                    "active": key == page_key,
                }
                for key, href, label in PRIMARY_NAV_ITEMS
            ],
            utility_nav_items=[
                {
                    "key": key,
                    "href": href,
                    "label": label,
                    "active": key == page_key,
                }
                for key, href, label in SECONDARY_NAV_ITEMS
            ],
            page_title=page_title,
            page_key=page_key,
            **context,
        )
        return _Response(status=status, body=html.encode("utf-8"))

    def _json_response(self, payload: object) -> _Response:
        return _Response(
            status="200 OK",
            body=json.dumps(_json_payload(payload)).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )


class _QuietHandler(WSGIRequestHandler):
    """Suppress default request logging for the local dashboard."""

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        _ = format, args


def build_dashboard_app(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    window_days: int = 14,
    database_url: str | None = None,
    artifacts_dir: Path | None = None,
    snapshot_path: Path | None = None,
    report_ttl_seconds: int = 300,
    prediction_ttl_seconds: int = 90,
    team_ttl_seconds: int = 600,
    prime_historical: bool = False,
) -> DashboardApp:
    """Build the WSGI app used by the CLI dashboard command."""
    del host, port
    return DashboardApp(
        build_dashboard_middleware(
            window_days=window_days,
            database_url=database_url,
            artifacts_dir=artifacts_dir,
            snapshot_path=snapshot_path,
            report_ttl_seconds=report_ttl_seconds,
            prediction_ttl_seconds=prediction_ttl_seconds,
            team_ttl_seconds=team_ttl_seconds,
            prime_historical=prime_historical,
        )
    )


def run_dashboard_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    window_days: int = 14,
    database_url: str | None = None,
    artifacts_dir: Path | None = None,
    snapshot_path: Path | None = None,
    report_ttl_seconds: int = 300,
    prediction_ttl_seconds: int = 90,
    team_ttl_seconds: int = 600,
    announce: _Announcer | None = None,
) -> None:
    """Serve the local dashboard until interrupted."""
    announcer = announce or print
    prepare_dashboard_backend(
        database_url=database_url,
        artifacts_dir=artifacts_dir,
        snapshot_path=snapshot_path,
        progress=announcer,
    )
    app = build_dashboard_app(
        host=host,
        port=port,
        window_days=window_days,
        database_url=database_url,
        artifacts_dir=artifacts_dir,
        snapshot_path=snapshot_path,
        report_ttl_seconds=report_ttl_seconds,
        prediction_ttl_seconds=prediction_ttl_seconds,
        team_ttl_seconds=team_ttl_seconds,
        prime_historical=True,
    )
    with make_server(host, port, app, handler_class=_QuietHandler) as server:
        browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        url = f"http://{browser_host}:{server.server_port}/"
        announcer(f"Dashboard available at {url}")
        if open_browser:
            webbrowser.open_new_tab(url)
        server.serve_forever()


def _query_params(raw_query: str) -> dict[str, str]:
    parsed = parse_qs(raw_query, keep_blank_values=True)
    return {key: values[-1] for key, values in parsed.items() if values}


def _json_payload(value: object) -> object:
    if not isinstance(value, type) and is_dataclass(value):
        return asdict(cast(Any, value))
    if isinstance(value, tuple):
        return [_json_payload(item) for item in value]
    if isinstance(value, list):
        return [_json_payload(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_payload(item) for key, item in value.items()}
    return value
