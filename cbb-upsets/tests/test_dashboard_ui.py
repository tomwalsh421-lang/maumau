import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from cbb.dashboard.cache import TtlCache
from cbb.dashboard.service import (
    DashboardConfig,
    DashboardPage,
    DashboardService,
    MetricDefinition,
    ModelArtifactCard,
    ModelsPage,
    OverviewCard,
    PerformancePage,
    PerformanceWindowSummary,
    PickHistoryFilters,
    PicksPage,
    PickTableRow,
    SeasonSummaryCard,
    TeamDetailPage,
    TeamResultRow,
    TeamSearchResult,
    TeamsPage,
    UpcomingPage,
    WindowOption,
)
from cbb.modeling.backtest import BacktestSummary, ClosingLineValueSummary
from cbb.modeling.infer import PredictionSummary, UpcomingGamePrediction
from cbb.modeling.policy import PlacedBet
from cbb.modeling.report import BestBacktestReport
from cbb.ui.app import DashboardApp, run_dashboard_server


def test_ttl_cache_reuses_values_until_expiry(monkeypatch) -> None:
    cache = TtlCache()
    now = {"value": 100.0}
    calls: list[str] = []

    monkeypatch.setattr("cbb.dashboard.cache.monotonic", lambda: now["value"])

    def loader() -> str:
        calls.append("load")
        return f"value-{len(calls)}"

    first = cache.get_or_set("report", ttl_seconds=10, loader=loader)
    second = cache.get_or_set("report", ttl_seconds=10, loader=loader)
    now["value"] = 111.0
    third = cache.get_or_set("report", ttl_seconds=10, loader=loader)

    assert first == "value-1"
    assert second == "value-1"
    assert third == "value-2"
    assert calls == ["load", "load"]


def test_ttl_cache_can_return_stale_values(monkeypatch) -> None:
    cache = TtlCache()
    now = {"value": 100.0}

    monkeypatch.setattr("cbb.dashboard.cache.monotonic", lambda: now["value"])

    cache.set("prediction", ttl_seconds=10, stale_ttl_seconds=5, value="cached")

    now["value"] = 111.0

    assert cache.peek("prediction") is None
    assert cache.peek_stale("prediction") == "cached"

    now["value"] = 116.0

    assert cache.peek_stale("prediction") is None


def test_dashboard_service_returns_stale_report_while_refreshing(monkeypatch) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(report_ttl_seconds=10))
    report = _best_report()
    now = {"value": 100.0}
    warmups: list[str] = []

    monkeypatch.setattr("cbb.dashboard.cache.monotonic", lambda: now["value"])
    monkeypatch.setattr(service, "_start_report_warmup", lambda: warmups.append("run"))

    service._cache.set(
        "report",
        ttl_seconds=10,
        stale_ttl_seconds=10,
        value=report,
    )

    now["value"] = 111.0

    assert service._get_report() is report
    assert warmups == ["run"]


def test_dashboard_service_returns_stale_prediction_while_refreshing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(prediction_ttl_seconds=10))
    prediction = _prediction_summary()
    now = {"value": 100.0}
    refreshes: list[str] = []

    monkeypatch.setattr("cbb.dashboard.cache.monotonic", lambda: now["value"])
    monkeypatch.setattr(
        service,
        "_start_prediction_refresh",
        lambda: refreshes.append("run"),
    )

    service._cache.set(
        "prediction",
        ttl_seconds=10,
        stale_ttl_seconds=10,
        value=prediction,
    )

    now["value"] = 111.0

    assert service._get_prediction_summary() is prediction
    assert refreshes == ["run"]


def test_dashboard_service_searches_team_aliases(monkeypatch) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig())

    monkeypatch.setattr(
        service,
        "_all_team_entries",
        lambda: (
            SimpleNamespace(
                team_key="saint-marys-gaels",
                team_name="Saint Mary's Gaels",
                match_name="St. Mary's",
                is_alias=True,
            ),
            SimpleNamespace(
                team_key="saint-marys-gaels",
                team_name="Saint Mary's Gaels",
                match_name="Saint Mary's Gaels",
                is_alias=False,
            ),
        ),
    )

    results = service.search_teams("stmarys", limit=5)

    assert results[0].team_key == "saint-marys-gaels"
    assert results[0].match_hint == "Alias: St. Mary's"


def test_dashboard_service_returns_pending_dashboard_when_report_is_cold(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig())

    monkeypatch.setattr(service, "_get_ready_report", lambda: None)
    monkeypatch.setattr(
        service,
        "_get_prediction_summary",
        lambda: PredictionSummary(
            market="best",
            available_games=1,
            candidates_considered=1,
            bets_placed=1,
            recommendations=[_placed_bet()],
            upcoming_games=[],
        ),
    )

    page = service.get_dashboard_page(window_key="14")

    assert page.report_pending is True
    assert "progress" in (page.report_message or "").lower()
    assert page.upcoming_rows[0].status_label == "Bet"


def test_dashboard_service_reuses_recent_window_snapshot_across_views(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(report_ttl_seconds=60))
    report = _best_report()
    calls: list[str] = []

    monkeypatch.setattr(service, "_get_report", lambda: report)
    monkeypatch.setattr(service, "_get_ready_report", lambda: report)
    monkeypatch.setattr(
        service,
        "_get_upcoming_snapshot",
        lambda: SimpleNamespace(
            generated_at_label="",
            expires_at_label="",
            recommendation_rows=(
                _pick_row(status_label="Bet", profit_label="Pending"),
            ),
            watch_rows=(),
            board_rows=(),
        ),
    )
    monkeypatch.setattr(service, "_get_dashboard_recent_rows", lambda _: (_pick_row(),))

    def fake_snapshot(*, report, window_key):
        _ = report, window_key
        calls.append("build")
        return SimpleNamespace(
            summary=_performance_summary(),
            table_rows=(_pick_row(),),
        )

    monkeypatch.setattr(service, "_build_recent_window_snapshot", fake_snapshot)

    dashboard = service.get_dashboard_page(window_key="14")
    performance = service.get_performance_page(window_key="14")

    assert dashboard.recent_summary.label == "14 days"
    assert performance.summary.label == "14 days"
    assert calls == ["build"]


def test_dashboard_service_reuses_upcoming_snapshot(monkeypatch) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(
        DashboardConfig(
            prediction_ttl_seconds=60,
            now=datetime(2026, 3, 11, 19, 0, tzinfo=UTC),
        )
    )
    prediction = _prediction_summary()
    calls: list[str] = []

    monkeypatch.setattr(service, "_get_prediction_summary", lambda: prediction)

    original_builder = service._build_upcoming_snapshot

    def counted_builder(prediction_summary: PredictionSummary):
        calls.append("build")
        return original_builder(prediction_summary)

    monkeypatch.setattr(service, "_build_upcoming_snapshot", counted_builder)

    first = service.get_upcoming_page()
    second = service.get_upcoming_page()

    assert first.recommendation_rows[0].status_label == "Bet"
    assert second.board_rows[0].status_label == "Bet"
    assert calls == ["build"]


def test_dashboard_service_loads_snapshot_backed_report(monkeypatch) -> None:
    service = DashboardService(
        DashboardConfig(report_ttl_seconds=60, snapshot_path=Path("snapshot.json"))
    )
    report = _best_report()
    calls: list[Path] = []

    class _FakeSnapshot:
        def to_report(self) -> BestBacktestReport:
            calls.append(Path("snapshot.json"))
            return report

    monkeypatch.setattr(
        "cbb.dashboard.service.load_dashboard_snapshot",
        lambda path: _FakeSnapshot() if path == Path("snapshot.json") else None,
    )

    first = service.prime_historical_report()
    second = service._get_report()

    assert first is report
    assert second is report
    assert calls == [Path("snapshot.json")]


def test_dashboard_app_renders_routes() -> None:
    app = DashboardApp(cast(DashboardService, _FakeService()))

    dashboard_status, dashboard_headers, dashboard_body = _call_app(app, "/")
    assert dashboard_status == "200 OK"
    assert "text/html" in dashboard_headers["Content-Type"]
    assert "Execution-aware NCAA spread tracking" in dashboard_body
    assert "Overview" in dashboard_body
    assert "Open live board" in dashboard_body

    api_status, api_headers, api_body = _call_app(
        app, "/api/teams/search", query="q=duke"
    )
    assert api_status == "200 OK"
    assert "application/json" in api_headers["Content-Type"]
    payload = json.loads(api_body)
    assert payload[0]["team_key"] == "duke-blue-devils"
    assert payload[0]["url"] == "/teams/duke-blue-devils"

    dashboard_api_status, _, dashboard_api_body = _call_app(
        app,
        "/api/dashboard",
        query="window=14",
    )
    assert dashboard_api_status == "200 OK"
    dashboard_payload = json.loads(dashboard_api_body)
    assert dashboard_payload["selected_window"] == "14"
    assert dashboard_payload["page"]["overview_cards"][0]["label"] == "Three-season ROI"

    upcoming_api_status, _, upcoming_api_body = _call_app(app, "/api/upcoming")
    assert upcoming_api_status == "200 OK"
    upcoming_payload = json.loads(upcoming_api_body)
    assert upcoming_payload["page"]["policy_note"] == "Execution-aware board."

    team_api_status, _, team_api_body = _call_app(
        app,
        "/api/teams/duke-blue-devils",
    )
    assert team_api_status == "200 OK"
    team_payload = json.loads(team_api_body)
    assert team_payload["page"]["team"]["team_name"] == "Duke Blue Devils"

    team_status, _, team_body = _call_app(app, "/teams/duke-blue-devils")
    assert team_status == "200 OK"
    assert "Duke Blue Devils" in team_body
    assert "Board involvement" in team_body

    static_status, static_headers, static_body = _call_app(app, "/static/dashboard.css")
    assert static_status == "200 OK"
    assert "text/css" in static_headers["Content-Type"]
    assert ":root" in static_body


def test_run_dashboard_server_refreshes_snapshot_before_serving(monkeypatch) -> None:
    call_order: list[str] = []
    messages: list[str] = []

    class _FakeServer:
        server_port = 8765

        def __enter__(self):
            call_order.append("server-enter")
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb
            call_order.append("server-exit")

        def serve_forever(self) -> None:
            call_order.append("serve")

    monkeypatch.setattr(
        "cbb.ui.app.prepare_dashboard_backend",
        lambda **kwargs: call_order.append("ensure"),
    )
    monkeypatch.setattr(
        "cbb.ui.app.build_dashboard_app",
        lambda **kwargs: call_order.append("build") or _FakeApp(),
    )
    monkeypatch.setattr("cbb.ui.app.make_server", lambda *args, **kwargs: _FakeServer())

    run_dashboard_server(
        host="127.0.0.1",
        port=8765,
        open_browser=False,
        announce=messages.append,
    )

    assert call_order[:3] == ["ensure", "build", "server-enter"]
    assert "Dashboard available at http://127.0.0.1:8765/" in messages[-1]


def _call_app(
    app: DashboardApp,
    path: str,
    *,
    query: str = "",
) -> tuple[str, dict[str, str], str]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        captured["status"] = status
        captured["headers"] = dict(headers)

    body = b"".join(
        app(
            {
                "PATH_INFO": path,
                "QUERY_STRING": query,
            },
            start_response,
        )
    )
    return (
        str(captured["status"]),
        cast(dict[str, str], captured["headers"]),
        body.decode("utf-8"),
    )


class _FakeApp:
    def __call__(self, environ, start_response):
        _ = environ
        start_response("200 OK", [("Content-Type", "text/plain")])
        return [b"ok"]


class _FakeService:
    def default_window_key(self) -> str:
        return "14"

    def get_dashboard_page(self, *, window_key: str | None = None) -> DashboardPage:
        _ = window_key
        return DashboardPage(
            overview_cards=(_overview_card(),),
            season_cards=(_season_card(),),
            recent_summary=_performance_summary(),
            recent_rows=(_pick_row(),),
            upcoming_rows=(_pick_row(status_label="Bet", profit_label="Pending"),),
            metric_definitions=(_metric_definition(),),
            strategy_note="Current strategy note.",
            board_note="Current board note.",
        )

    def get_models_page(self) -> ModelsPage:
        return ModelsPage(
            overview_cards=(_overview_card(),),
            season_cards=(_season_card(),),
            artifacts=(
                ModelArtifactCard(
                    market="spread",
                    artifact_name="latest",
                    model_family="logistic",
                    role_label="active best-path artifact",
                    trained_range="2024-2026",
                    trained_at_label="Mar 11, 2026 01:00 PM EDT",
                    feature_count=42,
                    market_blend_weight_label="+35.00%",
                    max_market_delta_label="+4.00%",
                ),
            ),
            metric_definitions=(_metric_definition(),),
            strategy_note="Spread first.",
        )

    def get_performance_page(self, *, window_key: str | None = None) -> PerformancePage:
        _ = window_key
        return PerformancePage(
            windows=(
                WindowOption(key="14", label="14 days", selected=True),
                WindowOption(key="30", label="30 days", selected=False),
            ),
            summary=_performance_summary(),
            rows=(_pick_row(),),
        )

    def get_upcoming_page(self) -> UpcomingPage:
        return UpcomingPage(
            generated_at_label="Mar 11, 2026 01:00 PM EDT",
            expires_at_label="Mar 11, 2026 02:00 PM EDT",
            policy_note="Execution-aware board.",
            recommendation_rows=(
                _pick_row(status_label="Bet", profit_label="Pending"),
            ),
            watch_rows=(_pick_row(status_label="Watch", profit_label="+58.00%"),),
            board_rows=(_pick_row(status_label="Wait", profit_label="Late line"),),
        )

    def get_picks_page(self, *, filters: PickHistoryFilters) -> PicksPage:
        return PicksPage(
            filters=filters,
            sportsbooks=("draftkings",),
            rows=(_pick_row(),),
            total_rows=1,
            truncated=False,
        )

    def get_teams_page(self, *, query: str) -> TeamsPage:
        _ = query
        team = TeamSearchResult(
            team_key="duke-blue-devils",
            team_name="Duke Blue Devils",
        )
        return TeamsPage(query=query, results=(team,), featured=(team,))

    def get_team_detail_page(self, team_key: str) -> TeamDetailPage:
        assert team_key == "duke-blue-devils"
        team = TeamSearchResult(
            team_key="duke-blue-devils",
            team_name="Duke Blue Devils",
        )
        return TeamDetailPage(
            team=team,
            recent_results=(
                TeamResultRow(
                    commence_label="Mar 10, 2026 07:00 PM EDT",
                    opponent_name="North Carolina Tar Heels",
                    venue_label="vs",
                    score_label="76-61",
                    result_label="W",
                    result_tone="good",
                ),
            ),
            scheduled_games=(),
            history_rows=(_pick_row(),),
            upcoming_rows=(_pick_row(status_label="Bet", profit_label="Pending"),),
            pick_summary="Two backtest picks involving Duke.",
        )

    def search_teams(self, query: str, *, limit: int = 8) -> list[TeamSearchResult]:
        _ = limit
        if not query:
            return []
        return [
            TeamSearchResult(
                team_key="duke-blue-devils",
                team_name="Duke Blue Devils",
            )
        ]


def _overview_card() -> OverviewCard:
    return OverviewCard(
        label="Three-season ROI",
        value="+7.34%",
        detail="+$282.70 across 569 bets",
        why_it_matters="Baseline deployable edge check.",
    )


def _season_card() -> SeasonSummaryCard:
    return SeasonSummaryCard(
        season=2026,
        bets=206,
        profit_label="+$143.34",
        roi_label="+10.11%",
        drawdown_label="+6.79%",
        close_ev_label="+0.094",
        tone="good",
    )


def _performance_summary() -> PerformanceWindowSummary:
    return PerformanceWindowSummary(
        key="14",
        label="14 days",
        anchor_label="Mar 11, 2026 09:00 PM EDT",
        bets=12,
        wins=8,
        losses=4,
        pushes=0,
        profit_label="+$48.00",
        roi_label="+8.00%",
        total_staked_label="+$600.00",
        drawdown_label="+3.00%",
        bankroll_exposure_label="+60.00%",
        average_edge_label="+4.20%",
        average_ev_label="+5.10%",
        close_ev_label="+0.090",
        price_clv_label="+1.40 pp",
        line_clv_label="-0.10",
        positive_clv_rate_label="+66.67%",
        sparkline_points=("0.00,40.00", "50.00,22.00", "100.00,0.00"),
        sparkline_min_label="+$1,000.00",
        sparkline_max_label="+$1,048.00",
        explanation="Anchored to the latest settled bet.",
    )


def _pick_row(
    *,
    status_label: str = "Win",
    profit_label: str = "+$18.00",
) -> PickTableRow:
    return PickTableRow(
        game_id=401,
        season_label="2026",
        commence_label="Mar 11, 2026 07:00 PM EDT",
        matchup_label="Duke Blue Devils vs Virginia Cavaliers",
        market_label="Spread",
        side_label="Duke Blue Devils -4.5",
        sportsbook_label="draftkings",
        line_label="-4.5",
        price_label="-110",
        edge_label="+4.40%",
        expected_value_label="+5.00%",
        stake_label="+$20.00",
        status_label=status_label,
        status_tone=(
            "good" if status_label == "Bet" or status_label == "Win" else "warn"
        ),
        profit_label=profit_label,
        coverage_label="+80.00%",
        books_label="3/5",
    )


def _metric_definition() -> MetricDefinition:
    return MetricDefinition(
        slug="close-ev",
        label="Close EV",
        summary="Expected value against the closing market.",
        repo_meaning="Execution-aware signal matters here.",
    )


def _placed_bet() -> PlacedBet:
    return PlacedBet(
        game_id=401,
        commence_time="2026-03-11T19:00:00+00:00",
        market="spread",
        team_name="Duke Blue Devils",
        opponent_name="Virginia Cavaliers",
        side="home",
        market_price=-110.0,
        line_value=-4.5,
        model_probability=0.542,
        implied_probability=0.500,
        probability_edge=0.042,
        expected_value=0.050,
        stake_fraction=0.02,
        stake_amount=20.0,
        settlement="win",
        sportsbook="draftkings",
        eligible_books=5,
        positive_ev_books=3,
        coverage_rate=0.8,
    )


def _prediction_summary() -> PredictionSummary:
    now = datetime(2026, 3, 11, 19, 0, tzinfo=UTC)
    return PredictionSummary(
        market="best",
        available_games=2,
        candidates_considered=2,
        bets_placed=1,
        recommendations=[
            _placed_bet(),
        ],
        deferred_recommendations=[],
        upcoming_games=[
            UpcomingGamePrediction(
                game_id=401,
                commence_time=(now + timedelta(hours=2)).isoformat(),
                team_name="Duke Blue Devils",
                opponent_name="Virginia Cavaliers",
                status="bet",
                market="spread",
                side="home",
                sportsbook="draftkings",
                market_price=-110.0,
                line_value=-4.5,
                eligible_books=5,
                positive_ev_books=3,
                coverage_rate=0.8,
                probability_edge=0.042,
                expected_value=0.05,
                stake_amount=20.0,
                note="ready",
            ),
        ],
        generated_at=now,
        expires_at=now + timedelta(minutes=15),
    )


def _best_report() -> BestBacktestReport:
    bet = _placed_bet()
    summary = BacktestSummary(
        market="best",
        start_season=2024,
        end_season=2026,
        evaluation_season=2026,
        blocks=12,
        candidates_considered=48,
        bets_placed=1,
        wins=1,
        losses=0,
        pushes=0,
        total_staked=bet.stake_amount,
        profit=18.0,
        roi=0.9,
        units_won=0.72,
        starting_bankroll=1000.0,
        ending_bankroll=1018.0,
        max_drawdown=0.02,
        sample_bets=[bet],
        placed_bets=[bet],
        clv=ClosingLineValueSummary(
            bets_evaluated=1,
            positive_bets=1,
            spread_bets_evaluated=1,
            total_spread_line_delta=-0.1,
            spread_price_bets_evaluated=1,
            total_spread_price_probability_delta=0.01,
            spread_closing_ev_bets_evaluated=1,
            total_spread_closing_expected_value=0.08,
        ),
    )
    return BestBacktestReport(
        output_path=Path("docs/results/best-model-3y-backtest.md"),
        history_output_path=None,
        selected_seasons=(2026,),
        summaries=(summary,),
        aggregate_bets=1,
        aggregate_profit=18.0,
        aggregate_roi=0.9,
        aggregate_units=0.72,
        max_drawdown=0.02,
        zero_bet_seasons=(),
        latest_summary=summary,
        markdown="report",
        aggregate_clv=summary.clv,
    )
