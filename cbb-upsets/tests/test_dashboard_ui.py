import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from cbb.dashboard.cache import TtlCache
from cbb.dashboard.service import (
    AvailabilityDiagnosticsSection,
    AvailabilityDiagnosticStat,
    AvailabilityStatusBadge,
    AvailabilityUsageView,
    DashboardConfig,
    DashboardPage,
    DashboardService,
    LiveBoardRow,
    MetricDefinition,
    ModelArtifactCard,
    ModelsPage,
    OverviewCard,
    PerformanceChartMarker,
    PerformanceChartPoint,
    PerformanceChartSeries,
    PerformanceHistoryChart,
    PerformancePage,
    PerformanceWindowSummary,
    PickHistoryFilters,
    PicksPage,
    PickTableRow,
    SeasonChartBar,
    SeasonSummaryCard,
    TeamDetailPage,
    TeamResultRow,
    TeamSearchResult,
    TeamsPage,
    UpcomingAvailabilitySummary,
    UpcomingPage,
    WindowOption,
)
from cbb.dashboard.snapshot import (
    build_dashboard_snapshot,
    canonical_dashboard_report_options,
    load_dashboard_snapshot,
)
from cbb.db import AvailabilityShadowStatusCount, AvailabilityShadowSummary
from cbb.modeling.backtest import BacktestSummary, ClosingLineValueSummary
from cbb.modeling.infer import (
    AvailabilityGameContext,
    AvailabilitySideContext,
    LiveBoardGame,
    PredictionAvailabilitySummary,
    PredictionSummary,
    UpcomingGamePrediction,
)
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
        "_get_upcoming_snapshot",
        lambda: SimpleNamespace(
            generated_at_label="Mar 13, 2026 12:00 PM EDT",
            expires_at_label="Mar 13, 2026 12:15 PM EDT",
            recommendation_rows=(
                _pick_row(status_label="Bet", profit_label="Pending"),
            ),
            watch_rows=(),
            board_rows=(),
            live_board_rows=(),
            availability_summary=None,
        ),
    )

    page = service.get_dashboard_page(window_key="14")

    assert page.report_pending is True
    assert "progress" in (page.report_message or "").lower()
    assert page.upcoming_rows[0].status_label == "Bet"


def test_dashboard_service_reads_cached_upcoming_snapshot(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(prediction_source="cache"))

    monkeypatch.setattr(
        "cbb.dashboard.service.load_upcoming_prediction_cache",
        lambda **_kwargs: SimpleNamespace(
            generated_at_label="Mar 13, 2026 12:00 PM EDT",
            expires_at_label="Mar 13, 2026 12:15 PM EDT",
            recommendation_rows=(
                _pick_row(status_label="Bet", profit_label="Pending"),
            ),
            watch_rows=(),
            board_rows=(),
            live_board_rows=(),
            availability_summary=None,
        ),
    )
    monkeypatch.setattr(
        service,
        "_get_prediction_summary",
        lambda: (_ for _ in ()).throw(AssertionError("live prediction should not run")),
    )

    upcoming = service.get_upcoming_page()

    assert upcoming.recommendation_rows[0].status_label == "Bet"
    assert "cached job output" in upcoming.policy_note


def test_dashboard_service_surfaces_cached_recommendations_across_views(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(prediction_source="cache"))
    report = _best_report()

    monkeypatch.setattr(
        "cbb.dashboard.service.load_upcoming_prediction_cache",
        lambda **_kwargs: SimpleNamespace(
            generated_at_label="Mar 28, 2026 03:04 PM EDT",
            expires_at_label="Mar 28, 2026 03:19 PM EDT",
            recommendation_rows=(
                replace(
                    _pick_row(
                        status_label="Bet",
                        profit_label="Pending",
                    ),
                    commence_label="Apr 03, 2026 01:30 AM UTC",
                    matchup_label="Illinois State Redbirds vs Auburn Tigers",
                ),
            ),
            watch_rows=(),
            board_rows=(),
            live_board_rows=(),
            availability_summary=None,
        ),
    )
    monkeypatch.setattr(service, "_get_ready_report", lambda: report)
    monkeypatch.setattr(service, "_get_report", lambda: report)
    monkeypatch.setattr(
        service,
        "_peek_snapshot",
        lambda: SimpleNamespace(availability_usage=_availability_usage()),
    )
    monkeypatch.setattr(
        service,
        "_get_snapshot",
        lambda: SimpleNamespace(availability_usage=_availability_usage()),
    )
    monkeypatch.setattr(
        service,
        "_get_recent_window_snapshot",
        lambda **_kwargs: SimpleNamespace(
            summary=_performance_summary(),
            table_rows=(_pick_row(),),
        ),
    )
    monkeypatch.setattr(service, "_get_dashboard_recent_rows", lambda _: (_pick_row(),))

    dashboard = service.get_dashboard_page(window_key="14")
    picks = service.get_picks_page(
        filters=PickHistoryFilters(
            start="",
            end="",
            season="all",
            team="",
            result="all",
            market="all",
            sportsbook="all",
        )
    )

    assert dashboard.cached_rows[0].matchup_label == (
        "Illinois State Redbirds vs Auburn Tigers"
    )
    assert dashboard.cached_generated_at_label == "Mar 28, 2026 03:04 PM EDT"
    assert picks.cached_rows[0].status_label == "Bet"
    assert picks.cached_generated_at_label == "Mar 28, 2026 03:04 PM EDT"


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
    monkeypatch.setattr(
        service,
        "_get_snapshot",
        lambda: SimpleNamespace(availability_usage=_availability_usage()),
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


def test_dashboard_service_builds_multi_season_performance_charts(monkeypatch) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(report_ttl_seconds=60))
    report = _multi_season_best_report()

    monkeypatch.setattr(service, "_get_report", lambda: report)

    performance = service.get_performance_page(window_key="30")

    assert performance.full_history_chart is not None
    assert performance.full_history_chart.series[0].value_label == "+$24.00"
    assert performance.full_history_chart.series[0].interactive_points[0].label == (
        "Start of report window"
    )
    assert tuple(
        marker.label for marker in performance.full_history_chart.markers
    ) == ("2024", "2025", "2026")
    assert performance.season_comparison_chart is not None
    assert tuple(
        series.label for series in performance.season_comparison_chart.series
    ) == ("2024", "2025", "2026")
    assert (
        performance.season_comparison_chart.series[0].interactive_points[0].detail
        == "Zero-profit baseline"
    )
    assert tuple(card.season for card in performance.season_cards) == (2024, 2025, 2026)


def test_dashboard_service_surfaces_min_and_max_bets_for_each_window(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(report_ttl_seconds=60))
    report = _report_with_window_stakes()

    monkeypatch.setattr(service, "_get_report", lambda: report)

    performance = service.get_performance_page(window_key="14")

    window_ranges = {
        window.key: (window.min_stake_label, window.max_stake_label)
        for window in performance.windows
    }

    assert window_ranges["7"] == ("+$10.00", "+$35.00")
    assert window_ranges["14"] == ("+$10.00", "+$40.00")
    assert window_ranges["30"] == ("+$10.00", "+$50.00")
    assert performance.summary.min_stake_label == "+$10.00"
    assert performance.summary.max_stake_label == "+$40.00"


def test_dashboard_service_filters_pick_history_by_season(monkeypatch) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(report_ttl_seconds=60))
    report = _multi_season_best_report()

    monkeypatch.setattr(service, "_get_report", lambda: report)

    page = service.get_picks_page(
        filters=PickHistoryFilters(
            start="",
            end="",
            season="2025",
            team="",
            result="all",
            market="all",
            sportsbook="all",
        )
    )

    assert page.seasons == ("2026", "2025", "2024")
    assert page.total_rows == 1
    assert tuple(row.season_label for row in page.rows) == ("2025",)


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
    assert second.live_board_rows[1].game_status_label == "Final"
    assert second.live_board_rows[1].result_label == "Final 71-64"
    assert calls == ["build"]


def test_dashboard_service_surfaces_availability_shadow_on_overview_cards(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(report_ttl_seconds=60))
    report = replace(
        _best_report(),
        availability_shadow_summary=AvailabilityShadowSummary(
            reports_loaded=3,
            player_rows_loaded=11,
            games_covered=2,
            unmatched_player_rows=2,
            latest_minutes_before_tip=85.0,
            status_counts=(
                AvailabilityShadowStatusCount(status="available", row_count=6),
            ),
        ),
    )

    monkeypatch.setattr(service, "_get_report", lambda: report)
    monkeypatch.setattr(service, "_get_ready_report", lambda: report)
    monkeypatch.setattr(
        service,
        "_get_snapshot",
        lambda: SimpleNamespace(
            availability_usage=SimpleNamespace(
                state="shadow_only",
                note=(
                    "Official availability is stored for diagnostics only. "
                    "It does not change the promoted live board, backtest, "
                    "or betting-policy path."
                ),
            )
        ),
    )
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
    monkeypatch.setattr(
        service,
        "_get_recent_window_snapshot",
        lambda **_: SimpleNamespace(
            summary=_performance_summary(),
            table_rows=(_pick_row(),),
        ),
    )

    dashboard = service.get_dashboard_page(window_key="14")
    models = service.get_models_page()

    dashboard_card = next(
        card for card in dashboard.overview_cards if card.label == "Availability usage"
    )
    models_card = next(
        card for card in models.overview_cards if card.label == "Availability usage"
    )

    assert dashboard.availability_usage is not None
    assert dashboard.availability_usage.state == "shadow_only"
    assert dashboard_card.value == "Shadow only"
    assert "2 games, 11 status rows, 2 unmatched, 85 min before tip" in (
        dashboard_card.detail
    )
    assert "diagnostics only" in dashboard_card.why_it_matters.lower()
    assert models_card.value == "Shadow only"
    assert models.availability_diagnostics is not None
    assert models.availability_diagnostics.usage.state == "shadow_only"
    assert models.availability_diagnostics.stats[0] == AvailabilityDiagnosticStat(
        label="Games covered",
        value="2",
    )
    assert models.availability_diagnostics.status_badges[0] == AvailabilityStatusBadge(
        label="Available",
        value="6",
    )
    assert dashboard.recent_summary.explanation == "Anchored to the latest settled bet."


def test_dashboard_service_surfaces_availability_usage_on_upcoming_page(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(prediction_ttl_seconds=60))

    monkeypatch.setattr(
        service,
        "_get_upcoming_snapshot",
        lambda: SimpleNamespace(
            generated_at_label="Mar 11, 2026 01:00 PM EDT",
            expires_at_label="Mar 11, 2026 02:00 PM EDT",
            recommendation_rows=(
                _pick_row(status_label="Bet", profit_label="Pending"),
            ),
            watch_rows=(),
            board_rows=(),
            availability_summary=SimpleNamespace(
                label="0 of 1 current upcoming rows have stored official coverage.",
                detail="Breakdown: both 0, team only 0, opponent only 0.",
                freshness_note=None,
                matching_note=None,
                status_note=None,
                source_note=None,
            ),
            live_board_rows=(),
        ),
    )
    monkeypatch.setattr(
        service,
        "_peek_snapshot",
        lambda: SimpleNamespace(
            availability_usage=SimpleNamespace(
                state="research_only",
                note=(
                    "Official availability is active in bounded research "
                    "analysis, but it is not part of the promoted live board."
                ),
            )
        ),
    )

    upcoming = service.get_upcoming_page()

    assert upcoming.availability_usage is not None
    assert upcoming.availability_usage.state == "research_only"
    assert upcoming.availability_usage.label == "Research only"
    assert "bounded research analysis" in upcoming.availability_usage.note
    assert upcoming.availability_summary is not None
    assert upcoming.availability_summary.label == (
        "0 of 1 current upcoming rows have stored official coverage."
    )
    assert upcoming.availability_summary.detail == (
        "Breakdown: both 0, team only 0, opponent only 0."
    )
    assert upcoming.availability_summary.freshness_note is None
    assert upcoming.availability_summary.matching_note is None
    assert upcoming.availability_summary.status_note is None
    assert upcoming.availability_summary.source_note is None


def test_dashboard_service_surfaces_live_board_availability_context(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(prediction_ttl_seconds=60))

    monkeypatch.setattr(service, "_get_prediction_summary", _prediction_summary)
    monkeypatch.setattr(
        service,
        "_peek_snapshot",
        lambda: SimpleNamespace(availability_usage=_availability_usage()),
    )

    upcoming = service.get_upcoming_page()

    assert upcoming.live_board_rows[0].availability_label == "Both reports"
    assert "Duke Blue Devils: 1 out, 90m pre-tip" in (
        upcoming.live_board_rows[0].availability_note or ""
    )
    assert "Virginia Cavaliers: 1 questionable, 1 unmatched, 105m pre-tip" in (
        upcoming.live_board_rows[0].availability_note or ""
    )


def test_dashboard_service_surfaces_clean_upcoming_matching_quality(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(prediction_ttl_seconds=60))

    prediction = replace(
        _prediction_summary(),
        availability_summary=PredictionAvailabilitySummary(
            games_with_context=1,
            games_with_both_reports=1,
            games_with_unmatched_rows=0,
            team_sides_with_unmatched_rows=0,
            opponent_sides_with_unmatched_rows=0,
            latest_report_update_at="2026-03-11T20:30:00+00:00",
            closest_report_minutes_before_tip=90.0,
        ),
    )
    monkeypatch.setattr(service, "_get_prediction_summary", lambda: prediction)
    monkeypatch.setattr(
        service,
        "_peek_snapshot",
        lambda: SimpleNamespace(availability_usage=_availability_usage()),
    )

    upcoming = service.get_upcoming_page()

    assert upcoming.availability_summary is not None
    assert upcoming.availability_summary.matching_note == (
        "Matching quality: no unmatched availability rows on covered upcoming "
        "rows."
    )
    assert upcoming.availability_summary.status_note == (
        "Status mix: no out/questionable statuses on covered upcoming rows."
    )
    assert upcoming.availability_summary.source_note == (
        "Sources: none recorded on covered upcoming rows."
    )


def test_dashboard_service_surfaces_stake_range_on_overview_cards(
    monkeypatch,
) -> None:
    monkeypatch.setattr(DashboardService, "_start_report_warmup", lambda self: None)
    service = DashboardService(DashboardConfig(report_ttl_seconds=60))
    report = _best_report()

    monkeypatch.setattr(service, "_get_report", lambda: report)
    monkeypatch.setattr(service, "_get_ready_report", lambda: report)
    monkeypatch.setattr(
        service,
        "_get_snapshot",
        lambda: SimpleNamespace(
            availability_usage=SimpleNamespace(
                state="shadow_only",
                note=(
                    "Official availability is stored for diagnostics only. "
                    "It does not change the promoted live board, backtest, "
                    "or betting-policy path."
                ),
            )
        ),
    )
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
    monkeypatch.setattr(
        service,
        "_get_recent_window_snapshot",
        lambda **_: SimpleNamespace(
            summary=_performance_summary(),
            table_rows=(_pick_row(),),
        ),
    )

    dashboard = service.get_dashboard_page(window_key="14")
    models = service.get_models_page()

    dashboard_card = next(
        card for card in dashboard.overview_cards if card.label == "Stake range"
    )
    models_card = next(
        card for card in models.overview_cards if card.label == "Stake range"
    )

    assert dashboard_card.value == "+$20.00"
    assert dashboard_card.detail == "Smallest +$20.00; largest +$20.00"
    assert "around one $25 unit" in dashboard_card.why_it_matters
    assert models_card.value == "+$20.00"


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


def test_load_dashboard_snapshot_defaults_missing_availability_usage(
    tmp_path: Path,
) -> None:
    snapshot = build_dashboard_snapshot(
        _best_report(),
        report_options=canonical_dashboard_report_options(),
        artifacts_dir=tmp_path,
        generated_at="2026-03-12T12:00:00+00:00",
    )
    payload = asdict(snapshot)
    payload.pop("availability_usage", None)
    snapshot_path = tmp_path / "dashboard-snapshot.json"
    snapshot_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = load_dashboard_snapshot(snapshot_path)

    assert loaded.availability_usage.state == "shadow_only"
    assert "diagnostics only" in loaded.availability_usage.note.lower()


def test_dashboard_app_renders_routes() -> None:
    app = DashboardApp(cast(DashboardService, _FakeService()))

    dashboard_status, dashboard_headers, dashboard_body = _call_app(app, "/")
    assert dashboard_status == "200 OK"
    assert "text/html" in dashboard_headers["Content-Type"]
    assert 'id="react-dashboard-root"' in dashboard_body
    assert 'data-app-path="/"' in dashboard_body
    assert 'data-dashboard-api="/api/dashboard"' in dashboard_body
    assert 'data-classic-href="/classic"' in dashboard_body
    assert "Open the server-rendered dashboard fallback" in dashboard_body

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
    assert dashboard_payload["page"]["availability_usage"]["state"] == "shadow_only"
    assert any(
        card["label"] == "Availability usage"
        for card in dashboard_payload["page"]["overview_cards"]
    )

    models_api_status, _, models_api_body = _call_app(app, "/api/models")
    assert models_api_status == "200 OK"
    models_payload = json.loads(models_api_body)
    assert models_payload["page"]["availability_usage"]["state"] == "shadow_only"
    assert (
        models_payload["page"]["availability_diagnostics"]["usage"]["state"]
        == "shadow_only"
    )

    upcoming_api_status, _, upcoming_api_body = _call_app(app, "/api/upcoming")
    assert upcoming_api_status == "200 OK"
    upcoming_payload = json.loads(upcoming_api_body)
    assert upcoming_payload["page"]["policy_note"] == "Execution-aware board."
    assert upcoming_payload["page"]["availability_usage"]["state"] == "shadow_only"
    assert upcoming_payload["page"]["availability_summary"]["label"] == (
        "1 of 1 current upcoming rows have stored official coverage."
    )
    assert upcoming_payload["page"]["availability_summary"]["freshness_note"] == (
        "Latest update Mar 11, 2026 04:30 PM EDT | Closest report 90 min before tip"
    )
    assert upcoming_payload["page"]["availability_summary"]["matching_note"] == (
        "Matching quality: unmatched availability rows appear on 1 covered "
        "upcoming row (team sides 0, opponent sides 1)."
    )
    assert upcoming_payload["page"]["availability_summary"]["status_note"] == (
        "Status mix: any out on 1 covered upcoming row; any questionable on 1 "
        "covered upcoming row."
    )
    assert upcoming_payload["page"]["availability_summary"]["source_note"] == (
        "Sources: ncaa."
    )
    assert upcoming_payload["page"]["live_board_rows"][0]["result_label"] == "Win 71-64"
    assert (
        upcoming_payload["page"]["live_board_rows"][0]["availability_label"]
        == "Both reports"
    )

    classic_dashboard_status, _, classic_dashboard_body = _call_app(
        app,
        "/classic",
        query="window=14",
    )
    assert classic_dashboard_status == "200 OK"
    assert (
        "Best-path review, live recommendations, and season history in one loop"
        in classic_dashboard_body
    )
    assert "Overview" in classic_dashboard_body
    assert "Review recommendations" in classic_dashboard_body
    assert "Availability Shadow only" in classic_dashboard_body
    assert "/picks?season=2026" in classic_dashboard_body

    upcoming_status, _, upcoming_body = _call_app(app, "/upcoming")
    assert upcoming_status == "200 OK"
    assert 'id="react-dashboard-root"' in upcoming_body
    assert 'data-app-path="/upcoming"' in upcoming_body
    assert 'data-upcoming-api="/api/upcoming"' in upcoming_body
    assert 'data-classic-href="/classic/upcoming"' in upcoming_body
    assert "Open the server-rendered recommendations fallback" in upcoming_body

    classic_upcoming_status, _, classic_upcoming_body = _call_app(
        app,
        "/classic/upcoming",
    )
    assert classic_upcoming_status == "200 OK"
    assert "Current recommendations and recent board state" in classic_upcoming_body
    assert "Coverage diagnostics" in classic_upcoming_body
    assert (
        "1 of 1 current upcoming rows have stored official coverage."
        in classic_upcoming_body
    )
    assert "Latest update Mar 11, 2026 04:30 PM EDT" in classic_upcoming_body
    assert (
        "Matching quality: unmatched availability rows appear on 1 covered "
        "upcoming row (team sides 0, opponent sides 1)."
        in classic_upcoming_body
    )
    assert (
        "Status mix: any out on 1 covered upcoming row; any questionable on 1 "
        "covered upcoming row."
        in classic_upcoming_body
    )
    assert "Sources: ncaa." in classic_upcoming_body
    assert "Recent, in-progress, and upcoming board" in classic_upcoming_body
    assert "Availability Both reports" in classic_upcoming_body
    assert "Win 71-64" in classic_upcoming_body

    models_status, _, models_body = _call_app(app, "/models")
    assert models_status == "200 OK"
    assert 'id="react-dashboard-root"' in models_body
    assert 'data-app-path="/models"' in models_body
    assert 'data-models-api="/api/models"' in models_body
    assert 'data-classic-href="/classic/models"' in models_body
    assert "Open the server-rendered model review fallback" in models_body

    classic_models_status, _, classic_models_body = _call_app(app, "/classic/models")
    assert classic_models_status == "200 OK"
    assert "Availability diagnostics" in classic_models_body
    assert "Official availability coverage" in classic_models_body
    assert "The American MBB player availability" in classic_models_body

    performance_status, _, performance_body = _call_app(app, "/performance")
    assert performance_status == "200 OK"
    assert 'id="react-dashboard-root"' in performance_body
    assert 'data-app-path="/performance"' in performance_body
    assert 'data-performance-api="/api/performance"' in performance_body
    assert 'data-classic-href="/classic/performance"' in performance_body
    assert "Open the server-rendered performance fallback" in performance_body

    picks_status, _, picks_body = _call_app(app, "/picks", query="season=2026")
    assert picks_status == "200 OK"
    assert 'id="react-dashboard-root"' in picks_body
    assert 'data-app-path="/picks"' in picks_body
    assert 'data-picks-api="/api/picks"' in picks_body
    assert 'data-classic-href="/classic/picks"' in picks_body
    assert "Open the server-rendered picks fallback" in picks_body

    classic_picks_status, _, classic_picks_body = _call_app(
        app,
        "/classic/picks",
        query="season=2026",
    )
    assert classic_picks_status == "200 OK"
    assert "Start with season, then narrow by date" in classic_picks_body
    assert 'name="season"' in classic_picks_body
    assert "/classic/picks?season=2026" in classic_picks_body

    performance_api_status, _, performance_api_body = _call_app(
        app,
        "/api/performance",
        query="window=14",
    )
    assert performance_api_status == "200 OK"
    performance_payload = json.loads(performance_api_body)
    assert performance_payload["selected_window"] == "14"
    assert (
        performance_payload["page"]["full_history_chart"]["series"][0]["value_label"]
        == "+$108.00"
    )
    assert (
        performance_payload["page"]["full_history_chart"]["series"][0][
            "interactive_points"
        ][0]["label"]
        == "Start"
    )
    assert (
        performance_payload["page"]["season_comparison_chart"]["series"][0]["label"]
        == "2024"
    )

    classic_performance_status, _, classic_performance_body = _call_app(
        app,
        "/classic/performance",
        query="window=14",
    )
    assert classic_performance_status == "200 OK"
    assert "Full report history" in classic_performance_body
    assert "data-interactive-chart" in classic_performance_body
    assert "Each season restarted at zero profit" in classic_performance_body
    assert (
        "Overlaying seasons on the same zero-profit baseline"
        in classic_performance_body
    )
    assert "Stake n/a to n/a" in classic_performance_body
    assert "/picks?season=2026" in classic_performance_body

    team_api_status, _, team_api_body = _call_app(
        app,
        "/api/teams/duke-blue-devils",
    )
    assert team_api_status == "200 OK"
    team_payload = json.loads(team_api_body)
    assert team_payload["page"]["team"]["team_name"] == "Duke Blue Devils"

    teams_status, _, teams_body = _call_app(app, "/teams", query="q=duke")
    assert teams_status == "200 OK"
    assert 'id="react-dashboard-root"' in teams_body
    assert 'data-app-path="/teams"' in teams_body
    assert 'data-teams-api="/api/teams"' in teams_body
    assert 'data-classic-href="/classic/teams"' in teams_body
    assert "Open the server-rendered team-search fallback" in teams_body

    classic_teams_status, _, classic_teams_body = _call_app(
        app,
        "/classic/teams",
        query="q=duke",
    )
    assert classic_teams_status == "200 OK"
    assert 'name="q"' in classic_teams_body
    assert "Matches for" in classic_teams_body
    assert "/teams/duke-blue-devils" in classic_teams_body

    team_status, _, team_body = _call_app(app, "/teams/duke-blue-devils")
    assert team_status == "200 OK"
    assert "Duke Blue Devils" in team_body
    assert "Board involvement" in team_body

    static_status, static_headers, static_body = _call_app(app, "/static/dashboard.css")
    assert static_status == "200 OK"
    assert "text/css" in static_headers["Content-Type"]
    assert ":root" in static_body

    react_status, _, react_body = _call_app(app, "/app", query="window=30")
    assert react_status == "200 OK"
    assert 'id="react-dashboard-root"' in react_body
    assert 'data-app-path="/app"' in react_body
    assert 'data-classic-href="/classic"' in react_body
    assert 'data-window="30"' in react_body
    assert "/static/react/dashboard-react.js" in react_body
    assert "This React route needs JavaScript." in react_body
    assert "Open the server-rendered dashboard fallback" in react_body

    react_upcoming_status, _, react_upcoming_body = _call_app(app, "/app/upcoming")
    assert react_upcoming_status == "200 OK"
    assert 'data-app-path="/app/upcoming"' in react_upcoming_body
    assert 'data-upcoming-api="/api/upcoming"' in react_upcoming_body
    assert 'data-classic-href="/classic/upcoming"' in react_upcoming_body

    react_performance_status, _, react_performance_body = _call_app(
        app,
        "/app/performance",
        query="window=30",
    )
    assert react_performance_status == "200 OK"
    assert 'data-app-path="/app/performance"' in react_performance_body
    assert 'data-performance-api="/api/performance"' in react_performance_body
    assert 'data-classic-href="/classic/performance"' in react_performance_body

    react_models_status, _, react_models_body = _call_app(app, "/app/models")
    assert react_models_status == "200 OK"
    assert 'data-app-path="/app/models"' in react_models_body
    assert 'data-models-api="/api/models"' in react_models_body
    assert 'data-classic-href="/classic/models"' in react_models_body

    react_teams_status, _, react_teams_body = _call_app(app, "/app/teams")
    assert react_teams_status == "200 OK"
    assert 'data-app-path="/app/teams"' in react_teams_body
    assert 'data-teams-api="/api/teams"' in react_teams_body
    assert 'data-classic-href="/classic/teams"' in react_teams_body

    react_picks_status, _, react_picks_body = _call_app(app, "/app/picks")
    assert react_picks_status == "200 OK"
    assert 'data-app-path="/app/picks"' in react_picks_body
    assert 'data-picks-api="/api/picks"' in react_picks_body
    assert 'data-classic-href="/classic/picks"' in react_picks_body

    react_asset_status, react_asset_headers, react_asset_body = _call_app(
        app,
        "/static/react/dashboard-react.js",
    )
    assert react_asset_status == "200 OK"
    assert "javascript" in react_asset_headers["Content-Type"]
    assert "/api/teams" in react_asset_body
    assert "/api/models" in react_asset_body
    assert "/api/performance" in react_asset_body
    assert "/api/upcoming" in react_asset_body
    assert "/api/picks" in react_asset_body
    assert "/classic" in react_asset_body
    assert "/classic/teams" in react_asset_body
    assert "/classic/models" in react_asset_body
    assert "/classic/performance" in react_asset_body
    assert "/classic/upcoming" in react_asset_body
    assert "/classic/picks" in react_asset_body


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
            overview_cards=(_overview_card(), _availability_overview_card()),
            season_cards=(_season_card(),),
            recent_summary=_performance_summary(),
            recent_rows=(_pick_row(),),
            upcoming_rows=(_pick_row(status_label="Bet", profit_label="Pending"),),
            metric_definitions=(_metric_definition(),),
            strategy_note="Current strategy note.",
            board_note="Current board note.",
            availability_usage=_availability_usage(),
        )

    def get_models_page(self) -> ModelsPage:
        return ModelsPage(
            overview_cards=(_overview_card(), _availability_overview_card()),
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
            availability_usage=_availability_usage(),
            availability_diagnostics=_availability_diagnostics(),
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
            season_cards=(_season_card(),),
            season_bars=(_season_bar(),),
            full_history_chart=_full_history_chart(),
            season_comparison_chart=_season_comparison_chart(),
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
            availability_usage=_availability_usage(),
            availability_summary=UpcomingAvailabilitySummary(
                label="1 of 1 current upcoming rows have stored official coverage.",
                detail="Breakdown: both 1, team only 0, opponent only 0.",
                freshness_note=(
                    "Latest update Mar 11, 2026 04:30 PM EDT | "
                    "Closest report 90 min before tip"
                ),
                matching_note=(
                    "Matching quality: unmatched availability rows appear on 1 "
                    "covered upcoming row (team sides 0, opponent sides 1)."
                ),
                status_note=(
                    "Status mix: any out on 1 covered upcoming row; any "
                    "questionable on 1 covered upcoming row."
                ),
                source_note="Sources: ncaa.",
            ),
            live_board_rows=(_live_board_row(),),
        )

    def get_picks_page(self, *, filters: PickHistoryFilters) -> PicksPage:
        return PicksPage(
            filters=filters,
            seasons=("2026", "2025"),
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


def _availability_overview_card() -> OverviewCard:
    return OverviewCard(
        label="Availability usage",
        value="Shadow only",
        detail="2 games, 11 status rows, 2 unmatched, 85 min before tip",
        why_it_matters=(
            "Official availability is stored for diagnostics only. It does not "
            "change the promoted live board, backtest, or betting-policy path."
        ),
    )


def _availability_usage() -> AvailabilityUsageView:
    return AvailabilityUsageView(
        state="shadow_only",
        label="Shadow only",
        note=(
            "Official availability is stored for diagnostics only. It does not "
            "change the promoted live board, backtest, or betting-policy path."
        ),
    )


def _availability_diagnostics() -> AvailabilityDiagnosticsSection:
    return AvailabilityDiagnosticsSection(
        usage=_availability_usage(),
        stats=(
            AvailabilityDiagnosticStat(label="Games covered", value="2"),
            AvailabilityDiagnosticStat(label="Reports loaded", value="3"),
            AvailabilityDiagnosticStat(label="Player rows", value="11"),
            AvailabilityDiagnosticStat(label="Unmatched rows", value="2"),
            AvailabilityDiagnosticStat(label="Timing", value="85 min before tip"),
        ),
        season_labels=("2026",),
        scope_labels=("NCAA Tournament",),
        source_labels=("The American MBB player availability",),
        status_badges=(
            AvailabilityStatusBadge(label="Available", value="6"),
            AvailabilityStatusBadge(label="Questionable", value="3"),
            AvailabilityStatusBadge(label="Out", value="2"),
        ),
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


def _season_bar() -> SeasonChartBar:
    return SeasonChartBar(
        season=2026,
        profit_label="+$143.34",
        roi_label="+10.11%",
        height_pct=100.0,
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


def _full_history_chart() -> PerformanceHistoryChart:
    return PerformanceHistoryChart(
        title="All settled picks across the full report window",
        subtitle="This uses every settled backtest pick in the current report.",
        start_label="Jan 06, 2024 07:00 PM EST",
        end_label="Mar 11, 2026 09:00 PM EDT",
        min_label="-$30.00",
        max_label="+$140.00",
        zero_y=31.0,
        series=(
            PerformanceChartSeries(
                label="Full window",
                style_class="series-a",
                tone="good",
                points=("0.00,24.00", "50.00,18.00", "100.00,8.00"),
                interactive_points=(
                    PerformanceChartPoint(
                        x_pct=0.0,
                        y_pct=24.0,
                        label="Start",
                        value_label="$0.00",
                        detail="Zero baseline",
                    ),
                    PerformanceChartPoint(
                        x_pct=100.0,
                        y_pct=8.0,
                        label="Mar 11, 2026 09:00 PM EDT",
                        value_label="+$108.00",
                        detail="120 settled picks",
                    ),
                ),
                area_points=(
                    "0.00,48.00",
                    "0.00,24.00",
                    "50.00,18.00",
                    "100.00,8.00",
                    "100.00,48.00",
                ),
                value_label="+$108.00",
                detail="120 settled picks",
            ),
        ),
        markers=(
            PerformanceChartMarker(label="2024", offset_pct=0.0),
            PerformanceChartMarker(label="2025", offset_pct=45.0),
            PerformanceChartMarker(label="2026", offset_pct=79.0),
        ),
    )


def _season_comparison_chart() -> PerformanceHistoryChart:
    return PerformanceHistoryChart(
        title="Each season restarted at zero profit",
        subtitle=(
            "Overlaying seasons on the same zero-profit baseline makes "
            "late-season runs easier to compare."
        ),
        start_label="Season start",
        end_label="Season finish",
        min_label="-$40.00",
        max_label="+$150.00",
        zero_y=34.0,
        series=(
            PerformanceChartSeries(
                label="2024",
                style_class="series-a",
                tone="bad",
                points=("0.00,24.00", "100.00,34.00"),
                interactive_points=(
                    PerformanceChartPoint(
                        x_pct=0.0,
                        y_pct=24.0,
                        label="2024 season start",
                        value_label="$0.00",
                        detail="Zero-profit baseline",
                    ),
                    PerformanceChartPoint(
                        x_pct=100.0,
                        y_pct=34.0,
                        label="Season finish",
                        value_label="-$18.00",
                        detail="ROI -3.20%",
                    ),
                ),
                value_label="-$18.00",
                detail="ROI -3.20%",
            ),
            PerformanceChartSeries(
                label="2025",
                style_class="series-b",
                tone="good",
                points=("0.00,24.00", "100.00,10.00"),
                interactive_points=(
                    PerformanceChartPoint(
                        x_pct=0.0,
                        y_pct=24.0,
                        label="2025 season start",
                        value_label="$0.00",
                        detail="Zero-profit baseline",
                    ),
                    PerformanceChartPoint(
                        x_pct=100.0,
                        y_pct=10.0,
                        label="Season finish",
                        value_label="+$44.00",
                        detail="ROI +7.10%",
                    ),
                ),
                value_label="+$44.00",
                detail="ROI +7.10%",
            ),
            PerformanceChartSeries(
                label="2026",
                style_class="series-c",
                tone="good",
                points=("0.00,24.00", "100.00,4.00"),
                interactive_points=(
                    PerformanceChartPoint(
                        x_pct=0.0,
                        y_pct=24.0,
                        label="2026 season start",
                        value_label="$0.00",
                        detail="Zero-profit baseline",
                    ),
                    PerformanceChartPoint(
                        x_pct=100.0,
                        y_pct=4.0,
                        label="Season finish",
                        value_label="+$82.00",
                        detail="ROI +9.80%",
                    ),
                ),
                value_label="+$82.00",
                detail="ROI +9.80%",
            ),
        ),
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


def _live_board_row() -> LiveBoardRow:
    return LiveBoardRow(
        game_id=401,
        commence_label="Mar 11, 2026 07:00 PM EDT",
        matchup_label="Duke Blue Devils vs Virginia Cavaliers",
        game_status_label="Final",
        game_status_tone="flat",
        board_status_label="Bet",
        board_status_tone="good",
        side_label="Duke Blue Devils -4.5",
        result_label="Win 71-64",
        result_tone="good",
        note_label="Tracked live",
        availability_label="Both reports",
        availability_note=(
            "Duke Blue Devils: 1 out, 90m pre-tip; "
            "Virginia Cavaliers: 1 questionable, 1 unmatched, 105m pre-tip"
        ),
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
        available_games=1,
        candidates_considered=2,
        bets_placed=1,
        recommendations=[
            _placed_bet(),
        ],
        deferred_recommendations=[],
        availability_summary=PredictionAvailabilitySummary(
            games_with_context=1,
            games_with_both_reports=1,
            games_with_unmatched_rows=1,
            team_sides_with_unmatched_rows=0,
            opponent_sides_with_unmatched_rows=1,
            games_with_any_out=1,
            games_with_any_questionable=1,
            source_names=("ncaa",),
            latest_report_update_at="2026-03-11T20:30:00+00:00",
            closest_report_minutes_before_tip=90.0,
        ),
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
                availability_context=AvailabilityGameContext(
                    coverage_status="both",
                    team=AvailabilitySideContext(has_report=True, out_count=1),
                    opponent=AvailabilitySideContext(
                        has_report=True,
                        questionable_count=1,
                    ),
                ),
            ),
        ],
        live_board_games=[
            LiveBoardGame(
                game_id=401,
                commence_time=(now + timedelta(hours=2)).isoformat(),
                home_team_name="Duke Blue Devils",
                away_team_name="Virginia Cavaliers",
                game_status="upcoming",
                board_status="bet",
                market="spread",
                team_name="Duke Blue Devils",
                opponent_name="Virginia Cavaliers",
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
                note="qualified",
                availability_context=AvailabilityGameContext(
                    coverage_status="both",
                    team=AvailabilitySideContext(
                        has_report=True,
                        out_count=1,
                        latest_minutes_before_tip=90.0,
                    ),
                    opponent=AvailabilitySideContext(
                        has_report=True,
                        questionable_count=1,
                        unmatched_row_count=1,
                        latest_minutes_before_tip=105.0,
                    ),
                ),
            ),
            LiveBoardGame(
                game_id=402,
                commence_time=(now - timedelta(hours=2)).isoformat(),
                home_team_name="North Carolina Tar Heels",
                away_team_name="Duke Blue Devils",
                game_status="final",
                board_status="pass",
                market="spread",
                team_name="Duke Blue Devils",
                opponent_name="North Carolina Tar Heels",
                side="away",
                sportsbook="betmgm",
                market_price=-110.0,
                line_value=4.5,
                probability_edge=0.015,
                expected_value=0.010,
                note="probability_edge",
                home_score=71,
                away_score=64,
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
        output_path=Path("docs/results/best-model-5y-backtest.md"),
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


def _report_with_window_stakes() -> BestBacktestReport:
    bets = [
        replace(
            _placed_bet(),
            game_id=501,
            commence_time="2026-03-05T19:00:00+00:00",
            team_name="Team A",
            opponent_name="Opponent A",
            stake_amount=50.0,
        ),
        replace(
            _placed_bet(),
            game_id=502,
            commence_time="2026-03-18T19:00:00+00:00",
            team_name="Team B",
            opponent_name="Opponent B",
            stake_amount=40.0,
        ),
        replace(
            _placed_bet(),
            game_id=503,
            commence_time="2026-03-24T19:00:00+00:00",
            team_name="Team C",
            opponent_name="Opponent C",
            stake_amount=35.0,
        ),
        replace(
            _placed_bet(),
            game_id=504,
            commence_time="2026-03-30T19:00:00+00:00",
            team_name="Team D",
            opponent_name="Opponent D",
            stake_amount=10.0,
        ),
    ]
    total_staked = sum(bet.stake_amount for bet in bets)
    total_profit = total_staked
    summary = BacktestSummary(
        market="best",
        start_season=2024,
        end_season=2026,
        evaluation_season=2026,
        blocks=12,
        candidates_considered=48,
        bets_placed=len(bets),
        wins=len(bets),
        losses=0,
        pushes=0,
        total_staked=total_staked,
        profit=total_profit,
        roi=total_profit / total_staked,
        units_won=total_profit / 25.0,
        starting_bankroll=1000.0,
        ending_bankroll=1000.0 + total_profit,
        max_drawdown=0.0,
        sample_bets=[bets[-1]],
        placed_bets=bets,
        clv=ClosingLineValueSummary(
            bets_evaluated=len(bets),
            positive_bets=len(bets),
            spread_bets_evaluated=len(bets),
            total_spread_line_delta=-0.4,
            spread_price_bets_evaluated=len(bets),
            total_spread_price_probability_delta=0.04,
            spread_closing_ev_bets_evaluated=len(bets),
            total_spread_closing_expected_value=0.32,
        ),
    )
    return BestBacktestReport(
        output_path=Path("docs/results/best-model-5y-backtest.md"),
        history_output_path=None,
        selected_seasons=(2026,),
        summaries=(summary,),
        aggregate_bets=len(bets),
        aggregate_profit=total_profit,
        aggregate_roi=total_profit / total_staked,
        aggregate_units=total_profit / 25.0,
        max_drawdown=0.0,
        zero_bet_seasons=(),
        latest_summary=summary,
        markdown="report",
        aggregate_clv=summary.clv,
    )


def _multi_season_best_report() -> BestBacktestReport:
    summary_2024 = _summary_for_season(
        season=2024,
        commence_time="2024-01-06T19:00:00+00:00",
        profit=-12.0,
        roi=-0.12,
        max_drawdown=0.05,
    )
    summary_2025 = _summary_for_season(
        season=2025,
        commence_time="2025-01-10T19:00:00+00:00",
        profit=8.0,
        roi=0.08,
        max_drawdown=0.03,
    )
    summary_2026 = _summary_for_season(
        season=2026,
        commence_time="2026-03-11T19:00:00+00:00",
        profit=28.0,
        roi=0.28,
        max_drawdown=0.02,
    )
    return BestBacktestReport(
        output_path=Path("docs/results/best-model-5y-backtest.md"),
        history_output_path=None,
        selected_seasons=(2024, 2025, 2026),
        summaries=(summary_2024, summary_2025, summary_2026),
        aggregate_bets=3,
        aggregate_profit=24.0,
        aggregate_roi=0.08,
        aggregate_units=0.96,
        max_drawdown=0.05,
        zero_bet_seasons=(),
        latest_summary=summary_2026,
        markdown="report",
        aggregate_clv=summary_2026.clv,
    )


def _summary_for_season(
    *,
    season: int,
    commence_time: str,
    profit: float,
    roi: float,
    max_drawdown: float,
) -> BacktestSummary:
    stake_amount = abs(profit) or 100.0
    if profit > 0:
        settlement = "win"
    elif profit < 0:
        settlement = "loss"
    else:
        settlement = "push"
    bet = PlacedBet(
        game_id=400 + season,
        commence_time=commence_time,
        market="spread",
        team_name=f"Team {season}",
        opponent_name=f"Opponent {season}",
        side="home",
        market_price=100.0,
        line_value=-4.5,
        model_probability=0.542,
        implied_probability=0.500,
        probability_edge=0.042,
        expected_value=0.050,
        stake_fraction=0.02,
        stake_amount=stake_amount,
        settlement=settlement,
        sportsbook="draftkings",
        eligible_books=5,
        positive_ev_books=3,
        coverage_rate=0.8,
    )
    return BacktestSummary(
        market="best",
        start_season=2024,
        end_season=2026,
        evaluation_season=season,
        blocks=1,
        candidates_considered=1,
        bets_placed=1,
        wins=1 if settlement == "win" else 0,
        losses=1 if settlement == "loss" else 0,
        pushes=1 if settlement == "push" else 0,
        total_staked=stake_amount,
        profit=profit,
        roi=roi,
        units_won=profit / 25.0,
        starting_bankroll=1000.0,
        ending_bankroll=1000.0 + profit,
        max_drawdown=max_drawdown,
        sample_bets=[bet],
        placed_bets=[bet],
        clv=ClosingLineValueSummary(
            bets_evaluated=1,
            positive_bets=1 if profit > 0 else 0,
            spread_bets_evaluated=1,
            total_spread_line_delta=-0.1,
            spread_price_bets_evaluated=1,
            total_spread_price_probability_delta=0.01,
            spread_closing_ev_bets_evaluated=1,
            total_spread_closing_expected_value=0.08,
        ),
    )
