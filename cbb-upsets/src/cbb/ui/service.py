"""View-model builders for the local server-rendered dashboard."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from math import ceil
from pathlib import Path
from threading import Lock, Thread
from typing import Literal

from sqlalchemy import text

from cbb.db import (
    TeamRecentResult,
    UpcomingGameView,
    get_engine,
    get_team_view,
)
from cbb.modeling.artifacts import ARTIFACTS_DIR, DEFAULT_ARTIFACT_NAME, load_artifact
from cbb.modeling.backtest import (
    ClosingLineValueObservation,
    summarize_closing_line_value,
)
from cbb.modeling.infer import (
    DeferredRecommendation,
    PredictionOptions,
    PredictionSummary,
    UpcomingGamePrediction,
    predict_best_bets,
)
from cbb.modeling.policy import CandidateBet, PlacedBet, settle_bet
from cbb.modeling.report import BestBacktestReport
from cbb.ui.cache import TtlCache
from cbb.ui.snapshot import (
    DEFAULT_DASHBOARD_SNAPSHOT_PATH,
    load_dashboard_snapshot,
)

PerformanceWindowKey = Literal["7", "14", "30", "90", "season"]

SEARCH_TEAMS_SQL = text(
    """
    SELECT
        teams.team_key,
        teams.name,
        teams.name AS match_name,
        FALSE AS is_alias
    FROM teams
    UNION ALL
    SELECT
        teams.team_key,
        teams.name,
        team_aliases.alias_name AS match_name,
        TRUE AS is_alias
    FROM team_aliases
    JOIN teams ON teams.team_id = team_aliases.team_id
    ORDER BY name
    """
)
PERFORMANCE_WINDOW_LABELS: dict[PerformanceWindowKey, str] = {
    "7": "7 days",
    "14": "14 days",
    "30": "30 days",
    "90": "90 days",
    "season": "Season to date",
}
PERFORMANCE_WINDOW_DAYS: dict[str, int] = {
    "7": 7,
    "14": 14,
    "30": 30,
    "90": 90,
}


@dataclass(frozen=True)
class DashboardConfig:
    """Runtime configuration for the local dashboard service."""

    default_window_key: PerformanceWindowKey = "14"
    database_url: str | None = None
    artifacts_dir: Path | None = None
    snapshot_path: Path | None = None
    report_ttl_seconds: int = 300
    prediction_ttl_seconds: int = 90
    team_ttl_seconds: int = 600
    now: datetime | None = None
    local_timezone: tzinfo | None = None


@dataclass(frozen=True)
class MetricDefinition:
    """Plain-English metric explanation shown across the UI."""

    slug: str
    label: str
    summary: str
    repo_meaning: str


@dataclass(frozen=True)
class ModelArtifactCard:
    """One stored model artifact summarized for the UI."""

    market: str
    artifact_name: str
    model_family: str
    role_label: str
    trained_range: str
    trained_at_label: str
    feature_count: int
    market_blend_weight_label: str
    max_market_delta_label: str


@dataclass(frozen=True)
class OverviewCard:
    """One headline KPI card."""

    label: str
    value: str
    detail: str
    why_it_matters: str


@dataclass(frozen=True)
class SeasonSummaryCard:
    """Season-level summary card used on the dashboard and models pages."""

    season: int
    bets: int
    profit_label: str
    roi_label: str
    drawdown_label: str
    close_ev_label: str
    tone: str


@dataclass(frozen=True)
class SeasonChartBar:
    """Simple season comparison bar used by the dashboard charts."""

    season: int
    profit_label: str
    roi_label: str
    height_pct: float
    tone: str


@dataclass(frozen=True)
class WindowOption:
    """One selectable performance window."""

    key: PerformanceWindowKey
    label: str
    selected: bool


@dataclass(frozen=True)
class PerformanceWindowSummary:
    """Aggregated recent settled performance for one time window."""

    key: PerformanceWindowKey
    label: str
    anchor_label: str
    bets: int
    wins: int
    losses: int
    pushes: int
    profit_label: str
    roi_label: str
    total_staked_label: str
    drawdown_label: str
    bankroll_exposure_label: str
    average_edge_label: str
    average_ev_label: str
    close_ev_label: str
    price_clv_label: str
    line_clv_label: str
    positive_clv_rate_label: str
    sparkline_points: tuple[str, ...]
    sparkline_min_label: str
    sparkline_max_label: str
    explanation: str
    sparkline_area_points: tuple[str, ...] = ()


@dataclass(frozen=True)
class PickTableRow:
    """Table row for historical or upcoming picks."""

    game_id: int
    season_label: str
    commence_label: str
    matchup_label: str
    market_label: str
    side_label: str
    sportsbook_label: str
    line_label: str
    price_label: str
    edge_label: str
    expected_value_label: str
    stake_label: str
    status_label: str
    status_tone: str
    profit_label: str
    coverage_label: str
    books_label: str


@dataclass(frozen=True)
class TeamSearchResult:
    """One team search result."""

    team_key: str
    team_name: str
    match_hint: str | None = None


@dataclass(frozen=True)
class TeamResultRow:
    """Recent completed game row for one team."""

    commence_label: str
    opponent_name: str
    venue_label: str
    score_label: str
    result_label: str
    result_tone: str


@dataclass(frozen=True)
class ScheduleRow:
    """Upcoming or in-progress game row for one team."""

    commence_label: str
    matchup_label: str
    status_label: str
    status_tone: str
    score_label: str
    price_label: str


@dataclass(frozen=True)
class DashboardPage:
    """Combined landing page payload."""

    overview_cards: tuple[OverviewCard, ...]
    season_cards: tuple[SeasonSummaryCard, ...]
    recent_summary: PerformanceWindowSummary
    recent_rows: tuple[PickTableRow, ...]
    upcoming_rows: tuple[PickTableRow, ...]
    metric_definitions: tuple[MetricDefinition, ...]
    strategy_note: str
    board_note: str
    season_bars: tuple[SeasonChartBar, ...] = ()
    report_pending: bool = False
    report_message: str | None = None


@dataclass(frozen=True)
class ModelsPage:
    """Model and artifact overview page payload."""

    overview_cards: tuple[OverviewCard, ...]
    season_cards: tuple[SeasonSummaryCard, ...]
    artifacts: tuple[ModelArtifactCard, ...]
    metric_definitions: tuple[MetricDefinition, ...]
    strategy_note: str
    season_bars: tuple[SeasonChartBar, ...] = ()


@dataclass(frozen=True)
class PerformancePage:
    """Recent performance page payload."""

    windows: tuple[WindowOption, ...]
    summary: PerformanceWindowSummary
    rows: tuple[PickTableRow, ...]


@dataclass(frozen=True)
class UpcomingPage:
    """Upcoming picks page payload."""

    generated_at_label: str
    expires_at_label: str
    policy_note: str
    recommendation_rows: tuple[PickTableRow, ...]
    watch_rows: tuple[PickTableRow, ...]
    board_rows: tuple[PickTableRow, ...]


@dataclass(frozen=True)
class PickHistoryFilters:
    """Normalized query filters for the pick history page."""

    start: str
    end: str
    team: str
    result: str
    market: str
    sportsbook: str


@dataclass(frozen=True)
class PicksPage:
    """Pick history page payload."""

    filters: PickHistoryFilters
    sportsbooks: tuple[str, ...]
    rows: tuple[PickTableRow, ...]
    total_rows: int
    truncated: bool


@dataclass(frozen=True)
class TeamsPage:
    """Team search landing page payload."""

    query: str
    results: tuple[TeamSearchResult, ...]
    featured: tuple[TeamSearchResult, ...]


@dataclass(frozen=True)
class TeamDetailPage:
    """Team detail page payload."""

    team: TeamSearchResult
    recent_results: tuple[TeamResultRow, ...]
    scheduled_games: tuple[ScheduleRow, ...]
    history_rows: tuple[PickTableRow, ...]
    upcoming_rows: tuple[PickTableRow, ...]
    pick_summary: str


@dataclass(frozen=True)
class _HistoricalBetRecord:
    season: int
    bet: PlacedBet
    profit: float
    commence_at: datetime
    clv_observation: ClosingLineValueObservation | None


@dataclass(frozen=True)
class _TeamSearchEntry:
    team_key: str
    team_name: str
    match_name: str
    is_alias: bool


@dataclass(frozen=True)
class _RecentWindowSnapshot:
    """Cached recent-bets payload derived from one report window."""

    summary: PerformanceWindowSummary
    table_rows: tuple[PickTableRow, ...]


@dataclass(frozen=True)
class _UpcomingSnapshot:
    """Cached upcoming-bets payload derived from one prediction snapshot."""

    generated_at_label: str
    expires_at_label: str
    recommendation_rows: tuple[PickTableRow, ...]
    watch_rows: tuple[PickTableRow, ...]
    board_rows: tuple[PickTableRow, ...]


METRIC_DEFINITIONS: tuple[MetricDefinition, ...] = (
    MetricDefinition(
        slug="roi",
        label="ROI",
        summary="Profit divided by dollars risked.",
        repo_meaning=(
            "This is the cleanest summary of whether the deployable spread path "
            "is actually compounding bankroll rather than just winning often."
        ),
    ),
    MetricDefinition(
        slug="drawdown",
        label="Drawdown",
        summary="The worst percentage slide from a prior bankroll peak.",
        repo_meaning=(
            "A higher edge is not useful here if it comes with a meaningfully "
            "deeper bankroll crater. The roadmap treats drawdown as a hard guardrail."
        ),
    ),
    MetricDefinition(
        slug="close-ev",
        label="Close EV",
        summary=(
            "Expected value if the pick were graded against the stored "
            "closing spread market."
        ),
        repo_meaning=(
            "This matters more than raw spread line CLV in the current repo because "
            "the remaining edge appears to be execution-aware pricing rather "
            "than line prediction alone."
        ),
    ),
    MetricDefinition(
        slug="line-clv",
        label="Line CLV",
        summary="How much the taken spread line beat or lagged the stored close.",
        repo_meaning=(
            "Useful context, but the current research view treats it as secondary. "
            "Negative spread line CLV can still coexist with positive price "
            "and close-EV signal."
        ),
    ),
    MetricDefinition(
        slug="price-clv",
        label="Price CLV",
        summary="How much the taken price beat the closing price-implied probability.",
        repo_meaning=(
            "This is a better fit for the current strategy because it captures "
            "book selection "
            "and quote timing, not just whether the spread number moved."
        ),
    ),
    MetricDefinition(
        slug="probability-edge",
        label="Probability edge",
        summary="Model win probability minus market-implied probability.",
        repo_meaning=(
            "This is the direct calibration check on whether the model thinks "
            "the market is underpricing the side."
        ),
    ),
    MetricDefinition(
        slug="expected-value",
        label="Expected value",
        summary="Expected profit per staked dollar at the quoted price.",
        repo_meaning=(
            "The deployable policy is built around EV and edge together. "
            "A pick with no EV does not belong on the board."
        ),
    ),
    MetricDefinition(
        slug="bankroll-exposure",
        label="Bankroll exposure",
        summary="Total dollars risked as a share of the notional bankroll.",
        repo_meaning=(
            "This is the activity reality check. The model should stay active "
            "enough to matter without forcing oversized risk."
        ),
    ),
)


class DashboardService:
    """Read-only service layer for the local dashboard UI."""

    def __init__(self, config: DashboardConfig | None = None) -> None:
        self.config = config or DashboardConfig()
        self._cache = TtlCache()
        self._report_warmup_lock = Lock()
        self._report_warmup_started = False
        self._report_warmup_error: str | None = None
        self._prediction_refresh_lock = Lock()
        self._prediction_refresh_started = False

    def prime_historical_report(self) -> BestBacktestReport:
        """Load the snapshot-backed historical report into cache."""
        return self._refresh_report()

    def get_dashboard_page(
        self,
        *,
        window_key: PerformanceWindowKey | None = None,
    ) -> DashboardPage:
        selected_window = window_key or self.config.default_window_key
        upcoming_snapshot = self._get_upcoming_snapshot()
        upcoming_rows = upcoming_snapshot.recommendation_rows[:6]
        report = self._get_ready_report()
        if report is None:
            return DashboardPage(
                overview_cards=self._pending_overview_cards(),
                season_cards=(),
                recent_summary=self._pending_recent_summary(selected_window),
                recent_rows=(),
                upcoming_rows=upcoming_rows,
                metric_definitions=METRIC_DEFINITIONS[:4],
                strategy_note=(
                    "The current deployable path is market-relative and "
                    "execution-aware. Positive price/no-vig/close-EV signal "
                    "matters more than raw line-beating."
                ),
                board_note=(
                    "Upcoming picks are already live. The heavier canonical "
                    "report is warming in the background."
                ),
                report_pending=True,
                report_message=(
                    self._report_warmup_error
                    or "Canonical report warmup is still in progress."
                ),
            )

        recent_snapshot = self._get_recent_window_snapshot(
            report=report,
            window_key=selected_window,
        )
        return DashboardPage(
            overview_cards=self._build_overview_cards(report),
            season_cards=self._build_season_cards(report),
            season_bars=self._build_season_bars(report),
            recent_summary=recent_snapshot.summary,
            recent_rows=self._get_dashboard_recent_rows(report),
            upcoming_rows=upcoming_rows,
            metric_definitions=METRIC_DEFINITIONS[:4],
            strategy_note=(
                "The current deployable path is market-relative and execution-aware. "
                "Positive price/no-vig/close-EV signal matters more than raw "
                "line-beating."
            ),
            board_note=(
                "Upcoming picks are generated from the current prediction "
                "path, not from scraped CLI text."
            ),
        )

    def get_models_page(self) -> ModelsPage:
        report = self._get_report()
        return ModelsPage(
            overview_cards=self._build_overview_cards(report),
            season_cards=self._build_season_cards(report),
            artifacts=self._discover_artifacts(),
            metric_definitions=METRIC_DEFINITIONS,
            strategy_note=(
                "Best-market deployment is spread-first whenever a spread "
                "artifact is available. "
                "Moneyline only fills the gap when spread cannot train or load."
            ),
            season_bars=self._build_season_bars(report),
        )

    def get_performance_page(
        self,
        *,
        window_key: PerformanceWindowKey | None = None,
    ) -> PerformancePage:
        report = self._get_report()
        selected_key = window_key or self.config.default_window_key
        recent_snapshot = self._get_recent_window_snapshot(
            report=report,
            window_key=selected_key,
        )
        return PerformancePage(
            windows=tuple(
                WindowOption(
                    key=key,
                    label=label,
                    selected=(key == selected_key),
                )
                for key, label in PERFORMANCE_WINDOW_LABELS.items()
            ),
            summary=recent_snapshot.summary,
            rows=recent_snapshot.table_rows,
        )

    def get_upcoming_page(self) -> UpcomingPage:
        snapshot = self._get_upcoming_snapshot()
        return UpcomingPage(
            generated_at_label=snapshot.generated_at_label,
            expires_at_label=snapshot.expires_at_label,
            policy_note=(
                "These are execution-aware recommendations. Books, price, "
                "line, and support depth all matter more here than pretending "
                "every spread number is interchangeable."
            ),
            recommendation_rows=snapshot.recommendation_rows,
            watch_rows=snapshot.watch_rows,
            board_rows=snapshot.board_rows,
        )

    def get_picks_page(self, *, filters: PickHistoryFilters) -> PicksPage:
        report = self._get_report()
        records = self._apply_pick_filters(
            self._historical_bets(report),
            filters=filters,
        )
        sportsbooks = tuple(
            sorted(
                {
                    record.bet.sportsbook
                    for record in self._historical_bets(report)
                    if record.bet.sportsbook
                }
            )
        )
        total_rows = len(records)
        rows = tuple(
            self._historical_pick_row(record)
            for record in records[:250]
        )
        return PicksPage(
            filters=filters,
            sportsbooks=sportsbooks,
            rows=rows,
            total_rows=total_rows,
            truncated=total_rows > 250,
        )

    def get_teams_page(self, *, query: str) -> TeamsPage:
        results = tuple(self.search_teams(query, limit=12))
        featured = tuple(self._featured_teams())
        return TeamsPage(query=query, results=results, featured=featured)

    def get_team_detail_page(self, team_key: str) -> TeamDetailPage:
        team = self._resolve_team(team_key)
        team_view = get_team_view(
            team.team_name,
            database_url=self.config.database_url,
            limit=8,
            now=self.config.now,
        )
        history_rows = tuple(
            self._historical_pick_row(record)
            for record in self._team_history_rows(team.team_name)[:20]
        )
        upcoming_rows = tuple(
            self._upcoming_pick_row(recommendation, "upcoming")
            for recommendation in self._team_upcoming_rows(team.team_name)
        )
        wins = sum(1 for row in history_rows if row.status_label == "Win")
        losses = sum(1 for row in history_rows if row.status_label == "Loss")
        return TeamDetailPage(
            team=team,
            recent_results=tuple(
                self._team_result_row(result) for result in team_view.recent_results
            ),
            scheduled_games=tuple(
                self._schedule_row(game) for game in team_view.scheduled_games
            ),
            history_rows=history_rows,
            upcoming_rows=upcoming_rows,
            pick_summary=(
                f"The current three-season backtest logged "
                f"{len(history_rows)} picks involving "
                f"{team.team_name} in this view ({wins}-{losses} on settled results)."
            ),
        )

    def search_teams(self, query: str, *, limit: int = 8) -> list[TeamSearchResult]:
        query = query.strip()
        if not query:
            return []
        normalized_query = _normalize_search_text(query)
        best_by_team: dict[
            str, tuple[tuple[int, int, int, int], TeamSearchResult]
        ] = {}
        for entry in self._all_team_entries():
            normalized_match = _normalize_search_text(entry.match_name)
            normalized_key = _normalize_search_text(entry.team_key)
            if (
                normalized_query not in normalized_match
                and normalized_query not in normalized_key
            ):
                continue
            result = TeamSearchResult(
                team_key=entry.team_key,
                team_name=entry.team_name,
                match_hint=(
                    f"Alias: {entry.match_name}"
                    if entry.is_alias and entry.match_name != entry.team_name
                    else None
                ),
            )
            sort_key = self._team_match_score(entry, normalized_query)
            current_best = best_by_team.get(entry.team_key)
            if current_best is None or sort_key < current_best[0]:
                best_by_team[entry.team_key] = (sort_key, result)
        ranked = sorted(
            best_by_team.values(),
            key=lambda item: (item[0], item[1].team_name),
        )
        return [result for _, result in ranked[:limit]]

    def default_window_key(self) -> PerformanceWindowKey:
        """Return the configured default performance window."""
        return self.config.default_window_key

    def _get_report(self) -> BestBacktestReport:
        cached_report = self._cache.peek("report")
        if isinstance(cached_report, BestBacktestReport):
            return cached_report
        stale_report = self._cache.peek_stale("report")
        if isinstance(stale_report, BestBacktestReport):
            self._start_report_warmup()
            return stale_report
        return self._refresh_report()

    def _get_ready_report(self) -> BestBacktestReport | None:
        cached_report = self._cache.peek("report")
        if isinstance(cached_report, BestBacktestReport):
            return cached_report
        stale_report = self._cache.peek_stale("report")
        if isinstance(stale_report, BestBacktestReport):
            self._start_report_warmup()
            return stale_report
        self._start_report_warmup()
        return None

    def _refresh_report(self) -> BestBacktestReport:
        report = load_dashboard_snapshot(self._snapshot_path()).to_report()
        return self._cache.set(
            "report",
            ttl_seconds=self.config.report_ttl_seconds,
            stale_ttl_seconds=self._report_stale_ttl_seconds(),
            value=report,
        )

    def _snapshot_path(self) -> Path:
        return self.config.snapshot_path or DEFAULT_DASHBOARD_SNAPSHOT_PATH

    def _report_stale_ttl_seconds(self) -> int:
        if self.config.report_ttl_seconds <= 0:
            return 0
        return min(self.config.report_ttl_seconds, 300)

    def _start_report_warmup(self) -> None:
        cached_report = self._cache.peek("report")
        if isinstance(cached_report, BestBacktestReport):
            return
        with self._report_warmup_lock:
            if self._report_warmup_started:
                return
            self._report_warmup_started = True
        Thread(target=self._warm_report_in_background, daemon=True).start()

    def _warm_report_in_background(self) -> None:
        try:
            self._report_warmup_error = None
            self._refresh_report()
        except Exception as exc:  # pragma: no cover - defensive runtime safety
            self._report_warmup_error = str(exc)
        finally:
            with self._report_warmup_lock:
                self._report_warmup_started = False

    def _get_prediction_summary(self) -> PredictionSummary:
        cached_prediction = self._cache.peek("prediction")
        if isinstance(cached_prediction, PredictionSummary):
            return cached_prediction
        stale_prediction = self._cache.peek_stale("prediction")
        if isinstance(stale_prediction, PredictionSummary):
            self._start_prediction_refresh()
            return stale_prediction
        return self._refresh_prediction_summary()

    def _refresh_prediction_summary(self) -> PredictionSummary:
        prediction = predict_best_bets(
            PredictionOptions(
                market="best",
                limit=24,
                database_url=self.config.database_url,
                artifacts_dir=self.config.artifacts_dir,
                now=self.config.now,
            )
        )
        fresh_ttl_seconds, stale_ttl_seconds = self._prediction_cache_ttls(prediction)
        return self._cache.set(
            "prediction",
            ttl_seconds=fresh_ttl_seconds,
            stale_ttl_seconds=stale_ttl_seconds,
            value=prediction,
        )

    def _prediction_cache_ttls(self, prediction: PredictionSummary) -> tuple[int, int]:
        fresh_ttl_seconds = max(self.config.prediction_ttl_seconds, 0)
        current_time = self.config.now or datetime.now(UTC)
        if prediction.expires_at is not None:
            seconds_until_expiry = max(
                0,
                ceil((prediction.expires_at - current_time).total_seconds()),
            )
            fresh_ttl_seconds = min(fresh_ttl_seconds, seconds_until_expiry)
        stale_ttl_seconds = (
            min(self._prediction_stale_ttl_seconds(), fresh_ttl_seconds)
            if fresh_ttl_seconds > 0
            else 0
        )
        return fresh_ttl_seconds, stale_ttl_seconds

    def _prediction_stale_ttl_seconds(self) -> int:
        if self.config.prediction_ttl_seconds <= 0:
            return 0
        return min(self.config.prediction_ttl_seconds, 15)

    def _start_prediction_refresh(self) -> None:
        cached_prediction = self._cache.peek("prediction")
        if isinstance(cached_prediction, PredictionSummary):
            return
        with self._prediction_refresh_lock:
            if self._prediction_refresh_started:
                return
            self._prediction_refresh_started = True
        Thread(target=self._refresh_prediction_in_background, daemon=True).start()

    def _refresh_prediction_in_background(self) -> None:
        try:
            self._refresh_prediction_summary()
        finally:
            with self._prediction_refresh_lock:
                self._prediction_refresh_started = False

    def _get_upcoming_snapshot(self) -> _UpcomingSnapshot:
        prediction = self._get_prediction_summary()
        cache_key = f"upcoming-snapshot:{self._prediction_cache_token(prediction)}"
        fresh_ttl_seconds, stale_ttl_seconds = self._prediction_cache_ttls(prediction)
        return self._cache.get_or_set(
            cache_key,
            ttl_seconds=fresh_ttl_seconds + stale_ttl_seconds,
            loader=lambda: self._build_upcoming_snapshot(prediction),
        )

    def _build_upcoming_snapshot(
        self,
        prediction: PredictionSummary,
    ) -> _UpcomingSnapshot:
        return _UpcomingSnapshot(
            generated_at_label=_format_optional_timestamp(
                prediction.generated_at,
                local_timezone=self._local_timezone(),
            ),
            expires_at_label=_format_optional_timestamp(
                prediction.expires_at,
                local_timezone=self._local_timezone(),
            ),
            recommendation_rows=tuple(
                self._upcoming_pick_row(recommendation, "live pick")
                for recommendation in prediction.recommendations
            ),
            watch_rows=tuple(
                self._deferred_pick_row(recommendation)
                for recommendation in prediction.deferred_recommendations
            ),
            board_rows=tuple(
                self._upcoming_board_row(game)
                for game in prediction.upcoming_games
                if game.status != "pass"
            ),
        )

    def _all_teams(self) -> tuple[TeamSearchResult, ...]:
        teams_by_key: dict[str, TeamSearchResult] = {}
        for entry in self._all_team_entries():
            teams_by_key.setdefault(
                entry.team_key,
                TeamSearchResult(
                    team_key=entry.team_key,
                    team_name=entry.team_name,
                ),
            )
        return tuple(sorted(teams_by_key.values(), key=lambda team: team.team_name))

    def _all_team_entries(self) -> tuple[_TeamSearchEntry, ...]:
        return self._cache.get_or_set(
            "teams",
            ttl_seconds=self.config.team_ttl_seconds,
            loader=self._load_all_team_entries,
        )

    def _load_all_team_entries(self) -> tuple[_TeamSearchEntry, ...]:
        engine = get_engine(self.config.database_url)
        with engine.connect() as connection:
            rows = connection.execute(SEARCH_TEAMS_SQL).mappings()
            return tuple(
                _TeamSearchEntry(
                    team_key=str(row["team_key"]),
                    team_name=str(row["name"]),
                    match_name=str(row["match_name"]),
                    is_alias=bool(row["is_alias"]),
                )
                for row in rows
            )

    def _resolve_team(self, team_key: str) -> TeamSearchResult:
        for team in self._all_teams():
            if team.team_key == team_key:
                return team
        raise KeyError(team_key)

    def _featured_teams(self) -> list[TeamSearchResult]:
        prediction = self._get_prediction_summary()
        featured: list[TeamSearchResult] = []
        seen: set[str] = set()
        name_to_team = {
            _normalize_search_text(team.team_name): team
            for team in self._all_teams()
        }
        for game in prediction.upcoming_games:
            for team_name in (game.team_name, game.opponent_name):
                team = name_to_team.get(_normalize_search_text(team_name))
                if team is None or team.team_key in seen:
                    continue
                featured.append(team)
                seen.add(team.team_key)
                if len(featured) >= 12:
                    return featured
        return featured[:12]

    def _pending_overview_cards(self) -> tuple[OverviewCard, ...]:
        return (
            OverviewCard(
                label="Canonical report",
                value="Warming",
                detail="The tracked three-season report is loading in the background.",
                why_it_matters=(
                    "This keeps the first dashboard render responsive instead "
                    "of blocking on a full walk-forward rebuild."
                ),
            ),
            OverviewCard(
                label="Upcoming board",
                value="Live",
                detail="Prediction data stays available while the report cache warms.",
                why_it_matters=(
                    "You can still inspect current picks and team views while "
                    "historical metrics finish loading."
                ),
            ),
        )

    def _pending_recent_summary(
        self,
        window_key: PerformanceWindowKey,
    ) -> PerformanceWindowSummary:
        return PerformanceWindowSummary(
            key=window_key,
            label=PERFORMANCE_WINDOW_LABELS[window_key],
            anchor_label="-",
            bets=0,
            wins=0,
            losses=0,
            pushes=0,
            profit_label=_format_money(0.0),
            roi_label=_format_pct(0.0),
            total_staked_label=_format_money(0.0),
            drawdown_label=_format_pct(0.0),
            bankroll_exposure_label=_format_pct(0.0),
            average_edge_label=_format_pct(0.0),
            average_ev_label=_format_pct(0.0),
            close_ev_label="n/a",
            price_clv_label="n/a",
            line_clv_label="n/a",
            positive_clv_rate_label="n/a",
            sparkline_points=(),
            sparkline_min_label=_format_money(0.0),
            sparkline_max_label=_format_money(0.0),
            explanation=(
                "The canonical report is still warming. Refresh shortly to "
                "populate the historical cards and charts."
            ),
        )

    def _build_overview_cards(
        self,
        report: BestBacktestReport,
    ) -> tuple[OverviewCard, ...]:
        profitable_seasons = sum(
            1
            for summary in report.summaries
            if summary.bets_placed > 0 and summary.profit > 0
        )
        active_seasons = sum(
            1 for summary in report.summaries if summary.bets_placed > 0
        )
        return (
            OverviewCard(
                label="Three-season ROI",
                value=_format_pct(report.aggregate_roi),
                detail=(
                    f"{_format_money(report.aggregate_profit)} across "
                    f"{report.aggregate_bets} bets"
                ),
                why_it_matters=(
                    "This is the headline deployable edge check for the "
                    "current baseline."
                ),
            ),
            OverviewCard(
                label="Max drawdown",
                value=_format_pct(report.max_drawdown),
                detail="Worst peak-to-trough bankroll slide in the report window.",
                why_it_matters=(
                    "The roadmap only promotes changes that do not materially "
                    "worsen this."
                ),
            ),
            OverviewCard(
                label="Profitable seasons",
                value=f"{profitable_seasons}/{active_seasons}",
                detail="Seasons with bets and positive profit.",
                why_it_matters=(
                    "This is the stability canary. A single hot season is not "
                    "enough here."
                ),
            ),
            OverviewCard(
                label="Average close EV",
                value=_format_optional_decimal(
                    report.aggregate_clv.average_spread_closing_expected_value
                ),
                detail=(
                    "Average expected value against the stored closing spread "
                    "market."
                ),
                why_it_matters=(
                    "This is the repo's strongest read on whether the edge is "
                    "surviving "
                    "against the market after price and execution effects."
                ),
            ),
            OverviewCard(
                label="Average price CLV",
                value=_format_optional_pp(
                    report.aggregate_clv.average_spread_price_probability_delta
                ),
                detail="Average taken-price delta versus close.",
                why_it_matters=(
                    "This fits the current strategy better than raw spread "
                    "line movement because it captures quote quality."
                ),
            ),
            OverviewCard(
                label="Average line CLV",
                value=_format_optional_line_delta(
                    report.aggregate_clv.average_spread_line_delta
                ),
                detail="Average spread-number movement versus close.",
                why_it_matters=(
                    "Helpful context, but it is not the main decision metric "
                    "for this repo anymore."
                ),
            ),
        )

    def _build_season_cards(
        self,
        report: BestBacktestReport,
    ) -> tuple[SeasonSummaryCard, ...]:
        cards: list[SeasonSummaryCard] = []
        for summary in report.summaries:
            tone = (
                "good"
                if summary.profit > 0
                else "bad" if summary.profit < 0 else "flat"
            )
            cards.append(
                SeasonSummaryCard(
                    season=summary.evaluation_season,
                    bets=summary.bets_placed,
                    profit_label=_format_money(summary.profit),
                    roi_label=_format_pct(summary.roi),
                    drawdown_label=_format_pct(summary.max_drawdown),
                    close_ev_label=_format_optional_decimal(
                        summary.clv.average_spread_closing_expected_value
                    ),
                    tone=tone,
                )
            )
        return tuple(cards)

    def _build_season_bars(
        self,
        report: BestBacktestReport,
    ) -> tuple[SeasonChartBar, ...]:
        if not report.summaries:
            return ()
        max_profit = max(abs(summary.profit) for summary in report.summaries) or 1.0
        bars: list[SeasonChartBar] = []
        for summary in report.summaries:
            bars.append(
                SeasonChartBar(
                    season=summary.evaluation_season,
                    profit_label=_format_money(summary.profit),
                    roi_label=_format_pct(summary.roi),
                    height_pct=max(18.0, (abs(summary.profit) / max_profit) * 100.0)
                    if summary.bets_placed > 0
                    else 12.0,
                    tone=(
                        "good"
                        if summary.profit > 0
                        else "bad" if summary.profit < 0 else "flat"
                    ),
                )
            )
        return tuple(bars)

    def _historical_bets(
        self,
        report: BestBacktestReport,
    ) -> list[_HistoricalBetRecord]:
        cache_key = f"history:{self._report_cache_token(report)}"
        return self._cache.get_or_set(
            cache_key,
            ttl_seconds=self.config.report_ttl_seconds
            + self._report_stale_ttl_seconds(),
            loader=lambda: self._build_historical_bet_records(report),
        )

    def _build_historical_bet_records(
        self,
        report: BestBacktestReport,
    ) -> list[_HistoricalBetRecord]:
        records: list[_HistoricalBetRecord] = []
        for summary in report.summaries:
            observation_by_scope = {
                (observation.game_id, observation.market, observation.side): observation
                for observation in summary.clv_observations
                if observation.game_id is not None and observation.side is not None
            }
            for bet in summary.placed_bets:
                records.append(
                    _HistoricalBetRecord(
                        season=summary.evaluation_season,
                        bet=bet,
                        profit=settle_bet(bet),
                        commence_at=_parse_timestamp(bet.commence_time),
                        clv_observation=observation_by_scope.get(
                            (bet.game_id, bet.market, bet.side)
                        ),
                    )
                )
        return sorted(records, key=lambda record: record.commence_at)

    def _report_cache_token(self, report: BestBacktestReport) -> str:
        return report.generated_at or str(id(report))

    def _prediction_cache_token(self, prediction: PredictionSummary) -> str:
        if prediction.generated_at is not None:
            return prediction.generated_at.isoformat()
        return str(id(prediction))

    def _get_dashboard_recent_rows(
        self,
        report: BestBacktestReport,
    ) -> tuple[PickTableRow, ...]:
        cache_key = f"recent-dashboard:{self._report_cache_token(report)}"
        return self._cache.get_or_set(
            cache_key,
            ttl_seconds=self.config.report_ttl_seconds
            + self._report_stale_ttl_seconds(),
            loader=lambda: tuple(
                self._historical_pick_row(record)
                for record in self._historical_bets(report)[-8:][::-1]
            ),
        )

    def _get_recent_window_snapshot(
        self,
        *,
        report: BestBacktestReport,
        window_key: PerformanceWindowKey,
    ) -> _RecentWindowSnapshot:
        cache_key = f"recent-window:{self._report_cache_token(report)}:{window_key}"
        return self._cache.get_or_set(
            cache_key,
            ttl_seconds=self.config.report_ttl_seconds
            + self._report_stale_ttl_seconds(),
            loader=lambda: self._build_recent_window_snapshot(
                report=report,
                window_key=window_key,
            ),
        )

    def _build_recent_window_snapshot(
        self,
        *,
        report: BestBacktestReport,
        window_key: PerformanceWindowKey,
    ) -> _RecentWindowSnapshot:
        records = self._filter_historical_bets(report=report, window_key=window_key)
        return _RecentWindowSnapshot(
            summary=self._build_recent_performance_summary(
                report=report,
                window_key=window_key,
                records=records,
            ),
            table_rows=tuple(
                self._historical_pick_row(record) for record in records[-30:][::-1]
            ),
        )

    def _filter_historical_bets(
        self,
        *,
        report: BestBacktestReport,
        window_key: PerformanceWindowKey,
    ) -> list[_HistoricalBetRecord]:
        records = self._historical_bets(report)
        if not records:
            return []
        if window_key == "season":
            latest_season = report.latest_summary.evaluation_season
            return [record for record in records if record.season == latest_season]

        latest_settled_at = records[-1].commence_at
        days = PERFORMANCE_WINDOW_DAYS[window_key]
        window_start = latest_settled_at - timedelta(days=days - 1)
        return [record for record in records if record.commence_at >= window_start]

    def _build_recent_performance_summary(
        self,
        *,
        report: BestBacktestReport,
        window_key: PerformanceWindowKey,
        records: Sequence[_HistoricalBetRecord] | None = None,
    ) -> PerformanceWindowSummary:
        selected_records = list(
            records
            if records is not None
            else self._filter_historical_bets(report=report, window_key=window_key)
        )
        historical_bets = self._historical_bets(report)
        latest_anchor = historical_bets[-1].commence_at if historical_bets else None
        if not selected_records:
            return PerformanceWindowSummary(
                key=window_key,
                label=PERFORMANCE_WINDOW_LABELS[window_key],
                anchor_label=_format_optional_timestamp(
                    latest_anchor,
                    local_timezone=self._local_timezone(),
                ),
                bets=0,
                wins=0,
                losses=0,
                pushes=0,
                profit_label=_format_money(0.0),
                roi_label=_format_pct(0.0),
                total_staked_label=_format_money(0.0),
                drawdown_label=_format_pct(0.0),
                bankroll_exposure_label=_format_pct(0.0),
                average_edge_label=_format_pct(0.0),
                average_ev_label=_format_pct(0.0),
                close_ev_label="n/a",
                price_clv_label="n/a",
                line_clv_label="n/a",
                positive_clv_rate_label="n/a",
                sparkline_points=(),
                sparkline_min_label=_format_money(0.0),
                sparkline_max_label=_format_money(0.0),
                explanation="No settled bets land in this window yet.",
                sparkline_area_points=(),
            )

        total_staked = sum(record.bet.stake_amount for record in selected_records)
        profit = sum(record.profit for record in selected_records)
        wins = sum(
            1 for record in selected_records if record.bet.settlement == "win"
        )
        losses = sum(
            1 for record in selected_records if record.bet.settlement == "loss"
        )
        pushes = sum(
            1 for record in selected_records if record.bet.settlement == "push"
        )
        bankroll = report.latest_summary.starting_bankroll
        peak_bankroll = bankroll
        max_drawdown = 0.0
        bankroll_points = [bankroll]
        for record in selected_records:
            bankroll += record.profit
            bankroll_points.append(bankroll)
            peak_bankroll = max(peak_bankroll, bankroll)
            if peak_bankroll > 0:
                max_drawdown = max(
                    max_drawdown,
                    (peak_bankroll - bankroll) / peak_bankroll,
                )
        clv_summary = summarize_closing_line_value(
            [
                record.clv_observation
                for record in selected_records
                if record.clv_observation is not None
            ]
        )
        avg_probability_edge = _average(
            record.bet.probability_edge for record in selected_records
        )
        avg_expected_value = _average(
            record.bet.expected_value for record in selected_records
        )
        latest_record = selected_records[-1].commence_at
        explanation = (
            "Recent windows are anchored to the latest settled backtest pick "
            "in the current report window, "
            "so the view stays stable during off-days."
        )
        return PerformanceWindowSummary(
            key=window_key,
            label=PERFORMANCE_WINDOW_LABELS[window_key],
            anchor_label=_format_optional_timestamp(
                latest_record,
                local_timezone=self._local_timezone(),
            ),
            bets=len(selected_records),
            wins=wins,
            losses=losses,
            pushes=pushes,
            profit_label=_format_money(profit),
            roi_label=_format_pct(profit / total_staked if total_staked > 0 else 0.0),
            total_staked_label=_format_money(total_staked),
            drawdown_label=_format_pct(max_drawdown),
            bankroll_exposure_label=_format_pct(
                total_staked / report.latest_summary.starting_bankroll
                if report.latest_summary.starting_bankroll > 0
                else 0.0
            ),
            average_edge_label=_format_pct(avg_probability_edge),
            average_ev_label=_format_pct(avg_expected_value),
            close_ev_label=_format_optional_decimal(
                clv_summary.average_spread_closing_expected_value
            ),
            price_clv_label=_format_optional_pp(
                clv_summary.average_spread_price_probability_delta
            ),
            line_clv_label=_format_optional_line_delta(
                clv_summary.average_spread_line_delta
            ),
            positive_clv_rate_label=(
                _format_pct(clv_summary.positive_rate)
                if clv_summary.bets_evaluated > 0
                else "n/a"
            ),
            sparkline_points=tuple(_sparkline_points(bankroll_points)),
            sparkline_min_label=_format_money(min(bankroll_points)),
            sparkline_max_label=_format_money(max(bankroll_points)),
            explanation=explanation,
            sparkline_area_points=tuple(_sparkline_area_points(bankroll_points)),
        )

    def _apply_pick_filters(
        self,
        records: Sequence[_HistoricalBetRecord],
        *,
        filters: PickHistoryFilters,
    ) -> list[_HistoricalBetRecord]:
        filtered = list(records)
        if filters.start:
            start_date = date.fromisoformat(filters.start)
            filtered = [
                record
                for record in filtered
                if record.commence_at.date() >= start_date
            ]
        if filters.end:
            end_date = date.fromisoformat(filters.end)
            filtered = [
                record
                for record in filtered
                if record.commence_at.date() <= end_date
            ]
        if filters.team:
            team_query = _normalize_search_text(filters.team)
            filtered = [
                record
                for record in filtered
                if team_query in _normalize_search_text(record.bet.team_name)
                or team_query in _normalize_search_text(record.bet.opponent_name)
            ]
        if filters.result and filters.result != "all":
            filtered = [
                record
                for record in filtered
                if record.bet.settlement == filters.result
            ]
        if filters.market and filters.market != "all":
            filtered = [
                record for record in filtered if record.bet.market == filters.market
            ]
        if filters.sportsbook and filters.sportsbook != "all":
            filtered = [
                record
                for record in filtered
                if (record.bet.sportsbook or "") == filters.sportsbook
            ]
        return sorted(filtered, key=lambda record: record.commence_at, reverse=True)

    def _team_history_rows(self, team_name: str) -> list[_HistoricalBetRecord]:
        report = self._get_report()
        normalized_team = _normalize_search_text(team_name)
        return [
            record
            for record in reversed(self._historical_bets(report))
            if normalized_team in _normalize_search_text(record.bet.team_name)
            or normalized_team in _normalize_search_text(record.bet.opponent_name)
        ]

    def _team_upcoming_rows(self, team_name: str) -> list[PlacedBet]:
        prediction = self._get_prediction_summary()
        normalized_team = _normalize_search_text(team_name)
        return [
            recommendation
            for recommendation in prediction.recommendations
            if normalized_team in _normalize_search_text(recommendation.team_name)
            or normalized_team in _normalize_search_text(recommendation.opponent_name)
        ]

    def _historical_pick_row(self, record: _HistoricalBetRecord) -> PickTableRow:
        return PickTableRow(
            game_id=record.bet.game_id,
            season_label=str(record.season),
            commence_label=_format_optional_timestamp(
                record.commence_at,
                local_timezone=self._local_timezone(),
            ),
            matchup_label=f"{record.bet.team_name} vs {record.bet.opponent_name}",
            market_label=record.bet.market.title(),
            side_label=f"{record.bet.team_name} {self._line_or_moneyline(record.bet)}",
            sportsbook_label=record.bet.sportsbook or "model quote",
            line_label=_format_line(record.bet.line_value),
            price_label=_format_price(record.bet.market_price),
            edge_label=_format_pct(record.bet.probability_edge),
            expected_value_label=_format_pct(record.bet.expected_value),
            stake_label=_format_money(record.bet.stake_amount),
            status_label=record.bet.settlement.title(),
            status_tone=_status_tone(record.bet.settlement),
            profit_label=_format_money(record.profit),
            coverage_label=_format_pct(record.bet.coverage_rate),
            books_label=f"{record.bet.positive_ev_books}/{record.bet.eligible_books}",
        )

    def _upcoming_pick_row(
        self,
        recommendation: PlacedBet,
        season_label: str,
    ) -> PickTableRow:
        return PickTableRow(
            game_id=recommendation.game_id,
            season_label=season_label,
            commence_label=_format_optional_timestamp(
                _parse_timestamp(recommendation.commence_time),
                local_timezone=self._local_timezone(),
            ),
            matchup_label=(
                f"{recommendation.team_name} vs "
                f"{recommendation.opponent_name}"
            ),
            market_label=recommendation.market.title(),
            side_label=(
                f"{recommendation.team_name} "
                f"{self._line_or_moneyline(recommendation)}"
            ),
            sportsbook_label=recommendation.sportsbook or "best quote",
            line_label=_format_line(recommendation.line_value),
            price_label=_format_price(recommendation.market_price),
            edge_label=_format_pct(recommendation.probability_edge),
            expected_value_label=_format_pct(recommendation.expected_value),
            stake_label=_format_money(recommendation.stake_amount),
            status_label="Bet",
            status_tone="good",
            profit_label="Pending",
            coverage_label=_format_pct(recommendation.coverage_rate),
            books_label=f"{recommendation.positive_ev_books}/{recommendation.eligible_books}",
        )

    def _deferred_pick_row(
        self,
        recommendation: DeferredRecommendation,
    ) -> PickTableRow:
        candidate = recommendation.candidate
        return PickTableRow(
            game_id=candidate.game_id,
            season_label="watch",
            commence_label=_format_optional_timestamp(
                _parse_timestamp(candidate.commence_time),
                local_timezone=self._local_timezone(),
            ),
            matchup_label=f"{candidate.team_name} vs {candidate.opponent_name}",
            market_label=candidate.market.title(),
            side_label=f"{candidate.team_name} {self._line_or_moneyline(candidate)}",
            sportsbook_label=candidate.sportsbook or "best quote",
            line_label=_format_line(candidate.line_value),
            price_label=_format_price(candidate.market_price),
            edge_label=_format_pct(candidate.probability_edge),
            expected_value_label=_format_pct(candidate.expected_value),
            stake_label="Wait",
            status_label="Watch",
            status_tone="warn",
            profit_label=_format_pct(recommendation.favorable_close_probability),
            coverage_label=_format_pct(candidate.coverage_rate),
            books_label=f"{candidate.positive_ev_books}/{candidate.eligible_books}",
        )

    def _upcoming_board_row(self, game: UpcomingGamePrediction) -> PickTableRow:
        side_label = (
            f"{game.team_name} {_format_line(game.line_value)}"
            if game.line_value is not None
            else game.team_name
        )
        return PickTableRow(
            game_id=game.game_id,
            season_label=game.status,
            commence_label=_format_optional_timestamp(
                _parse_timestamp(game.commence_time),
                local_timezone=self._local_timezone(),
            ),
            matchup_label=f"{game.team_name} vs {game.opponent_name}",
            market_label=game.market.title() if game.market is not None else "Best",
            side_label=side_label,
            sportsbook_label=game.sportsbook or "board",
            line_label=_format_line(game.line_value),
            price_label=_format_optional_price(game.market_price),
            edge_label=_format_optional_pct(game.probability_edge),
            expected_value_label=_format_optional_pct(game.expected_value),
            stake_label=_format_optional_money(game.stake_amount),
            status_label=game.status.title(),
            status_tone=_status_tone(game.status),
            profit_label=game.note or "-",
            coverage_label=_format_pct(game.coverage_rate),
            books_label=f"{game.positive_ev_books}/{game.eligible_books}",
        )

    def _team_result_row(self, result: TeamRecentResult) -> TeamResultRow:
        score_label = (
            f"{result.team_score}-{result.opponent_score}"
            if result.team_score is not None and result.opponent_score is not None
            else "-"
        )
        result_label = result.result or "-"
        return TeamResultRow(
            commence_label=_format_optional_timestamp(
                _parse_timestamp(result.commence_time)
                if result.commence_time is not None
                else None,
                local_timezone=self._local_timezone(),
            ),
            opponent_name=result.opponent_name,
            venue_label=result.venue_label,
            score_label=score_label,
            result_label=result_label,
            result_tone=_status_tone(result_label.lower()),
        )

    def _schedule_row(self, game: UpcomingGameView) -> ScheduleRow:
        score_label = (
            f"{game.home_score}-{game.away_score}"
            if game.home_score is not None and game.away_score is not None
            else "-"
        )
        price_label = (
            f"{game.home_team} {_format_optional_price(game.home_pregame_moneyline)} / "
            f"{game.away_team} {_format_optional_price(game.away_pregame_moneyline)}"
        )
        return ScheduleRow(
            commence_label=_format_optional_timestamp(
                _parse_timestamp(game.commence_time)
                if game.commence_time is not None
                else None,
                local_timezone=self._local_timezone(),
            ),
            matchup_label=f"{game.home_team} vs {game.away_team}",
            status_label=game.status.replace("_", " ").title(),
            status_tone=_status_tone(game.status),
            score_label=score_label,
            price_label=price_label,
        )

    def _discover_artifacts(self) -> tuple[ModelArtifactCard, ...]:
        artifacts_dir = (self.config.artifacts_dir or ARTIFACTS_DIR).resolve()
        if not artifacts_dir.exists():
            return ()
        cards: list[ModelArtifactCard] = []
        spread_available = False
        moneyline_available = False
        for path in sorted(artifacts_dir.glob("*.json")):
            name_parts = path.stem.split("_", maxsplit=1)
            if len(name_parts) != 2:
                continue
            market, artifact_name = name_parts
            try:
                artifact = load_artifact(
                    market=market,  # type: ignore[arg-type]
                    artifact_name=artifact_name,
                    artifacts_dir=artifacts_dir,
                )
            except (FileNotFoundError, KeyError, ValueError, OSError):
                continue
            if market == "spread":
                spread_available = True
            if market == "moneyline":
                moneyline_available = True
            cards.append(
                ModelArtifactCard(
                    market=artifact.market,
                    artifact_name=artifact_name,
                    model_family=artifact.model_family,
                    role_label=self._artifact_role_label(
                        market=artifact.market,
                        artifact_name=artifact_name,
                    ),
                    trained_range=(
                        f"{artifact.metrics.start_season}-{artifact.metrics.end_season}"
                    ),
                    trained_at_label=_format_trained_at(artifact.metrics.trained_at),
                    feature_count=len(artifact.feature_names),
                    market_blend_weight_label=_format_pct(artifact.market_blend_weight),
                    max_market_delta_label=_format_pct(
                        artifact.max_market_probability_delta
                    ),
                )
            )
        if not cards and (spread_available or moneyline_available):
            return ()
        return tuple(cards)

    def _artifact_role_label(self, *, market: str, artifact_name: str) -> str:
        if artifact_name != DEFAULT_ARTIFACT_NAME:
            return "stored variant"
        if market == "spread":
            return "active best-path artifact"
        if market == "moneyline":
            return "fallback when spread is unavailable"
        return "stored artifact"

    def _team_match_score(
        self,
        team: _TeamSearchEntry,
        normalized_query: str,
    ) -> tuple[int, int, int, int]:
        normalized_name = _normalize_search_text(team.team_name)
        normalized_match = _normalize_search_text(team.match_name)
        normalized_key = _normalize_search_text(team.team_key)
        return (
            0 if normalized_match.startswith(normalized_query) else 1,
            0 if normalized_name.startswith(normalized_query) else 1,
            0 if normalized_key.startswith(normalized_query) else 1,
            1 if team.is_alias else 0,
        )

    def _line_or_moneyline(self, bet: CandidateBet | PlacedBet) -> str:
        if bet.market == "spread":
            return _format_line(bet.line_value)
        return _format_price(bet.market_price)

    def _local_timezone(self) -> tzinfo:
        if self.config.local_timezone is not None:
            return self.config.local_timezone
        tz = datetime.now().astimezone().tzinfo
        return tz or UTC


def parse_pick_history_filters(query: dict[str, str]) -> PickHistoryFilters:
    """Normalize pick-history query params for the UI."""
    return PickHistoryFilters(
        start=_normalize_date_value(query.get("start", "")),
        end=_normalize_date_value(query.get("end", "")),
        team=query.get("team", "").strip(),
        result=_normalize_enum_value(
            query.get("result", "all"),
            allowed={"all", "win", "loss", "push"},
            fallback="all",
        ),
        market=_normalize_enum_value(
            query.get("market", "all"),
            allowed={"all", "spread", "moneyline"},
            fallback="all",
        ),
        sportsbook=query.get("sportsbook", "all").strip() or "all",
    )


def resolve_window_key(
    value: str | None,
    *,
    fallback: PerformanceWindowKey = "14",
) -> PerformanceWindowKey:
    """Resolve a query-string or CLI window selection into a supported key."""
    if value in PERFORMANCE_WINDOW_LABELS:
        return value  # type: ignore[return-value]
    return fallback


def _normalize_search_text(value: str) -> str:
    return "".join(
        character
        for character in value.lower()
        if character.isalnum()
    )


def _normalize_date_value(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ""


def _normalize_enum_value(
    value: str,
    *,
    allowed: set[str],
    fallback: str,
) -> str:
    normalized = value.strip().lower()
    if normalized in allowed:
        return normalized
    return fallback


def _parse_timestamp(value: str) -> datetime:
    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value


def _format_optional_timestamp(
    value: datetime | None,
    *,
    local_timezone: tzinfo,
) -> str:
    if value is None:
        return "-"
    return value.astimezone(local_timezone).strftime("%b %d, %Y %I:%M %p %Z")


def _format_trained_at(value: str) -> str:
    try:
        return _format_optional_timestamp(
            _parse_timestamp(value),
            local_timezone=datetime.now().astimezone().tzinfo or UTC,
        )
    except ValueError:
        return value


def _format_money(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}${value:,.2f}"


def _format_optional_money(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_money(value)


def _format_pct(value: float) -> str:
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.2f}%"


def _format_optional_pct(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_pct(value)


def _format_optional_pp(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.2f} pp"


def _format_optional_decimal(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.3f}"


def _format_optional_line_delta(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}"


def _format_line(value: float | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{value:.1f}"
    return f"{value:.1f}"


def _format_price(value: float) -> str:
    if value > 0:
        return f"+{value:.0f}"
    return f"{value:.0f}"


def _format_optional_price(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_price(value)


def _average(values: Iterable[float]) -> float:
    collected = list(values)
    if not collected:
        return 0.0
    return sum(collected) / len(collected)


def _status_tone(value: str) -> str:
    normalized = value.lower()
    if normalized in {"win", "bet", "qualified", "upcoming"}:
        return "good"
    if normalized in {"loss", "pass"}:
        return "bad"
    if normalized in {"watch", "wait", "in_progress"}:
        return "warn"
    return "flat"


def _sparkline_points(values: Sequence[float]) -> list[str]:
    if not values:
        return []
    min_value = min(values)
    max_value = max(values)
    span = max(max_value - min_value, 1.0)
    width = 100.0
    height = 40.0
    if len(values) == 1:
        return ["0.0,20.0"]
    return [
        (
            f"{(index / (len(values) - 1)) * width:.2f},"
            f"{height - (((value - min_value) / span) * height):.2f}"
        )
        for index, value in enumerate(values)
    ]


def _sparkline_area_points(values: Sequence[float]) -> list[str]:
    line_points = _sparkline_points(values)
    if not line_points:
        return []
    return ["0.00,40.00", *line_points, "100.00,40.00"]
