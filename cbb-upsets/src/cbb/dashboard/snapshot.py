"""Structured dashboard snapshot generation and freshness helpers."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast

import orjson

from cbb.db import (
    REPO_ROOT,
    AvailabilityShadowStatusCount,
    AvailabilityShadowSummary,
)
from cbb.modeling.artifacts import (
    ARTIFACTS_DIR,
    DEFAULT_ARTIFACT_NAME,
    ModelMarket,
    artifact_path,
    load_artifact,
)
from cbb.modeling.backtest import (
    DEFAULT_BACKTEST_RETRAIN_DAYS,
    DEFAULT_STARTING_BANKROLL,
    DEFAULT_UNIT_SIZE,
    BacktestSummary,
    ClosingLineValueObservation,
    ClosingLineValueSummary,
)
from cbb.modeling.policy import (
    DEFAULT_DEPLOYABLE_SPREAD_POLICY,
    BetPolicy,
    PlacedBet,
    settle_bet,
)
from cbb.modeling.report import (
    DEFAULT_BEST_BACKTEST_REPORT_PATH,
    BestBacktestReport,
    BestBacktestReportOptions,
    generate_best_backtest_report,
)
from cbb.modeling.train import DEFAULT_MODEL_SEASONS_BACK, DEFAULT_SPREAD_MODEL_FAMILY

DASHBOARD_SNAPSHOT_SCHEMA_VERSION = "dashboard_snapshot.v1"
DEFAULT_DASHBOARD_SNAPSHOT_PATH = (
    REPO_ROOT / "docs" / "results" / "best-model-dashboard-snapshot.json"
)
RECENT_WINDOW_KEYS = ("7", "14", "30", "90", "season")
RECENT_WINDOW_DAYS = {
    "7": 7,
    "14": 14,
    "30": 30,
    "90": 90,
}
AvailabilityUsageState = Literal["shadow_only", "research_only", "live"]
DEFAULT_AVAILABILITY_USAGE_STATE: AvailabilityUsageState = "shadow_only"
_AVAILABILITY_USAGE_ALIASES = {
    "shadow_only": "shadow_only",
    "research_only": "research_only",
    "live": "live",
    "live_path": "live",
    "not_loaded": "shadow_only",
}
_AVAILABILITY_USAGE_NOTES: dict[AvailabilityUsageState, str] = {
    "shadow_only": (
        "Official availability is stored for diagnostics only. It does not "
        "change the promoted live board, backtest, or betting-policy path."
    ),
    "research_only": (
        "Official availability is active in bounded research analysis, but it "
        "is not part of the promoted live board or betting-policy path."
    ),
    "live": (
        "Official availability now affects the promoted live board and should "
        "be treated as a live decision input."
    ),
}


@dataclass(frozen=True)
class DashboardSnapshotArtifact:
    """One active artifact identity tracked by the dashboard snapshot."""

    market: str
    artifact_name: str
    path: str
    sha256: str
    model_family: str
    trained_at: str
    start_season: int
    end_season: int


@dataclass(frozen=True)
class DashboardSnapshotArtifactSource:
    """Current best-path artifact state used for freshness validation."""

    active_best_market: str | None
    entries: tuple[DashboardSnapshotArtifact, ...]
    signature: str


@dataclass(frozen=True)
class DashboardSnapshotPolicy:
    """Policy fields that define the canonical report window."""

    min_edge: float
    min_confidence: float
    min_probability_edge: float
    uncertainty_probability_buffer: float
    min_games_played: int
    kelly_fraction: float
    max_bet_fraction: float
    max_daily_exposure_fraction: float
    max_bets_per_day: int | None
    min_moneyline_price: float
    max_moneyline_price: float
    max_spread_abs_line: float | None
    max_abs_rest_days_diff: float | None
    min_positive_ev_books: int
    min_median_expected_value: float | None


@dataclass(frozen=True)
class DashboardSnapshotReportIdentity:
    """Canonical report identity stored inside the dashboard snapshot."""

    output_path: str
    history_output_path: str | None
    generated_at: str
    selected_seasons: tuple[int, ...]
    seasons: int
    max_season: int | None
    starting_bankroll: float
    unit_size: float
    retrain_days: int
    auto_tune_spread_policy: bool
    use_timing_layer: bool
    spread_model_family: str
    policy: DashboardSnapshotPolicy
    signature: str


@dataclass(frozen=True)
class DashboardSnapshotAvailabilityUsage:
    """Explicit contract for how official availability is currently used."""

    state: AvailabilityUsageState = DEFAULT_AVAILABILITY_USAGE_STATE
    note: str = _AVAILABILITY_USAGE_NOTES[DEFAULT_AVAILABILITY_USAGE_STATE]


@dataclass(frozen=True)
class DashboardSnapshotClv:
    """Aggregate closing-line-value fields exposed to the dashboard."""

    bets_evaluated: int
    positive_bets: int
    negative_bets: int
    neutral_bets: int
    positive_rate: float
    average_spread_line_delta: float | None
    average_spread_price_probability_delta: float | None
    average_spread_no_vig_probability_delta: float | None
    average_spread_closing_expected_value: float | None
    average_moneyline_probability_delta: float | None


@dataclass(frozen=True)
class DashboardSnapshotAggregateSummary:
    """Aggregate bankroll summary stored in the snapshot."""

    bets: int
    profit: float
    roi: float
    units: float
    max_drawdown: float
    profitable_seasons: int
    active_seasons: int


@dataclass(frozen=True)
class DashboardSnapshotSeasonSummary:
    """One season summary for the dashboard snapshot."""

    season: int
    bets: int
    wins: int
    losses: int
    pushes: int
    profit: float
    roi: float
    units: float
    max_drawdown: float
    clv: DashboardSnapshotClv


@dataclass(frozen=True)
class DashboardSnapshotBetClv:
    """One bet-level CLV observation stored in the snapshot."""

    market: str
    reference_delta: float
    spread_line_delta: float | None
    spread_price_probability_delta: float | None
    spread_no_vig_probability_delta: float | None
    spread_closing_expected_value: float | None
    moneyline_probability_delta: float | None
    game_id: int | None
    side: str | None


@dataclass(frozen=True)
class DashboardSnapshotHistoricalBet:
    """One settled backtest bet stored for dashboard history views."""

    season: int
    game_id: int
    commence_time: str
    market: str
    team_name: str
    opponent_name: str
    side: str
    sportsbook: str
    market_price: float
    line_value: float | None
    model_probability: float
    implied_probability: float
    probability_edge: float
    expected_value: float
    stake_fraction: float
    stake_amount: float
    settlement: str
    profit: float
    minimum_games_played: int
    eligible_books: int
    positive_ev_books: int
    coverage_rate: float
    clv: DashboardSnapshotBetClv | None = None


@dataclass(frozen=True)
class DashboardSnapshotRecentWindow:
    """One precomputed recent-performance window inside the snapshot."""

    key: str
    anchor_time: str | None
    bets: int
    wins: int
    losses: int
    pushes: int
    profit: float
    roi: float
    total_staked: float
    max_drawdown: float
    bankroll_exposure: float
    average_edge: float
    average_ev: float
    clv: DashboardSnapshotClv
    bankroll_series: tuple[float, ...]
    rows: tuple[DashboardSnapshotHistoricalBet, ...]


@dataclass(frozen=True)
class DashboardSnapshot:
    """Durable dashboard snapshot for the canonical best-model workflow."""

    schema_version: str
    generated_at: str
    source_artifacts: DashboardSnapshotArtifactSource
    canonical_report: DashboardSnapshotReportIdentity
    aggregate_summary: DashboardSnapshotAggregateSummary
    aggregate_clv: DashboardSnapshotClv
    season_summaries: tuple[DashboardSnapshotSeasonSummary, ...]
    historical_bets: tuple[DashboardSnapshotHistoricalBet, ...]
    recent_windows: tuple[DashboardSnapshotRecentWindow, ...]
    availability_usage: DashboardSnapshotAvailabilityUsage = field(
        default_factory=DashboardSnapshotAvailabilityUsage
    )
    availability_shadow_summary: AvailabilityShadowSummary = field(
        default_factory=AvailabilityShadowSummary
    )

    def to_report(self) -> BestBacktestReport:
        """Rehydrate the best-report object used by the current UI helpers."""
        summaries: list[BacktestSummary] = []
        bets_by_season: dict[int, list[DashboardSnapshotHistoricalBet]] = defaultdict(
            list
        )
        for record in self.historical_bets:
            bets_by_season[record.season].append(record)
        for season_summary in self.season_summaries:
            history_rows = sorted(
                bets_by_season.get(season_summary.season, []),
                key=lambda row: row.commence_time,
            )
            placed_bets = [_placed_bet_from_snapshot(row) for row in history_rows]
            clv_observations = [
                _clv_observation_from_snapshot(row.clv)
                for row in history_rows
                if row.clv is not None
            ]
            summaries.append(
                BacktestSummary(
                    market="best",
                    start_season=min(self.canonical_report.selected_seasons),
                    end_season=season_summary.season,
                    evaluation_season=season_summary.season,
                    blocks=0,
                    candidates_considered=0,
                    bets_placed=season_summary.bets,
                    wins=season_summary.wins,
                    losses=season_summary.losses,
                    pushes=season_summary.pushes,
                    total_staked=sum(row.stake_amount for row in history_rows),
                    profit=season_summary.profit,
                    roi=season_summary.roi,
                    units_won=season_summary.units,
                    starting_bankroll=self.canonical_report.starting_bankroll,
                    ending_bankroll=(
                        self.canonical_report.starting_bankroll + season_summary.profit
                    ),
                    max_drawdown=season_summary.max_drawdown,
                    sample_bets=placed_bets[:5],
                    placed_bets=placed_bets,
                    clv_observations=clv_observations,
                    clv=_closing_line_value_summary_from_snapshot(season_summary.clv),
                    final_policy=_policy_to_model(self.canonical_report.policy),
                )
            )
        output_path = REPO_ROOT / self.canonical_report.output_path
        history_output_path = (
            REPO_ROOT / self.canonical_report.history_output_path
            if self.canonical_report.history_output_path is not None
            else None
        )
        return BestBacktestReport(
            output_path=output_path,
            history_output_path=history_output_path,
            selected_seasons=self.canonical_report.selected_seasons,
            summaries=tuple(summaries),
            aggregate_bets=self.aggregate_summary.bets,
            aggregate_profit=self.aggregate_summary.profit,
            aggregate_roi=self.aggregate_summary.roi,
            aggregate_units=self.aggregate_summary.units,
            max_drawdown=self.aggregate_summary.max_drawdown,
            zero_bet_seasons=tuple(
                summary.season for summary in self.season_summaries if summary.bets == 0
            ),
            latest_summary=summaries[-1],
            markdown=output_path.read_text(encoding="utf-8")
            if output_path.exists()
            else "",
            generated_at=self.canonical_report.generated_at,
            aggregate_clv=_closing_line_value_summary_from_snapshot(self.aggregate_clv),
            availability_shadow_summary=self.availability_shadow_summary,
            availability_usage_state=self.availability_usage.state,
            availability_usage_note=self.availability_usage.note,
        )


def canonical_dashboard_report_options(
    *,
    database_url: str | None = None,
) -> BestBacktestReportOptions:
    """Return the canonical report configuration that feeds the dashboard."""
    return BestBacktestReportOptions(
        output_path=DEFAULT_BEST_BACKTEST_REPORT_PATH,
        seasons=DEFAULT_MODEL_SEASONS_BACK,
        max_season=None,
        database_url=database_url,
        starting_bankroll=DEFAULT_STARTING_BANKROLL,
        unit_size=DEFAULT_UNIT_SIZE,
        retrain_days=DEFAULT_BACKTEST_RETRAIN_DAYS,
        auto_tune_spread_policy=False,
        use_timing_layer=False,
        spread_model_family=DEFAULT_SPREAD_MODEL_FAMILY,
        policy=DEFAULT_DEPLOYABLE_SPREAD_POLICY,
    )


def is_canonical_dashboard_report_options(options: BestBacktestReportOptions) -> bool:
    """Return whether report options match the canonical dashboard workflow."""
    canonical_options = canonical_dashboard_report_options(
        database_url=options.database_url,
    )
    return _report_settings_payload(options) == _report_settings_payload(
        canonical_options
    )


def build_dashboard_snapshot(
    report: BestBacktestReport,
    *,
    report_options: BestBacktestReportOptions,
    artifacts_dir: Path | None = None,
    generated_at: str | None = None,
) -> DashboardSnapshot:
    """Build the minimal durable dashboard snapshot from one report."""
    historical_bets = _historical_bets_from_report(report)
    aggregate_summary = DashboardSnapshotAggregateSummary(
        bets=report.aggregate_bets,
        profit=report.aggregate_profit,
        roi=report.aggregate_roi,
        units=report.aggregate_units,
        max_drawdown=report.max_drawdown,
        profitable_seasons=sum(
            1
            for summary in report.summaries
            if summary.bets_placed > 0 and summary.profit > 0
        ),
        active_seasons=sum(
            1 for summary in report.summaries if summary.bets_placed > 0
        ),
    )
    season_summaries = tuple(
        DashboardSnapshotSeasonSummary(
            season=summary.evaluation_season,
            bets=summary.bets_placed,
            wins=summary.wins,
            losses=summary.losses,
            pushes=summary.pushes,
            profit=summary.profit,
            roi=summary.roi,
            units=summary.units_won,
            max_drawdown=summary.max_drawdown,
            clv=_clv_summary_from_model(summary.clv),
        )
        for summary in report.summaries
    )
    return DashboardSnapshot(
        schema_version=DASHBOARD_SNAPSHOT_SCHEMA_VERSION,
        generated_at=generated_at or report.generated_at,
        source_artifacts=current_dashboard_artifact_source(artifacts_dir=artifacts_dir),
        canonical_report=_dashboard_report_identity(
            report=report,
            options=report_options,
        ),
        aggregate_summary=aggregate_summary,
        aggregate_clv=_clv_summary_from_model(report.aggregate_clv),
        season_summaries=season_summaries,
        historical_bets=historical_bets,
        recent_windows=tuple(
            _recent_window_from_history(
                key=window_key,
                report=report,
                historical_bets=historical_bets,
            )
            for window_key in RECENT_WINDOW_KEYS
        ),
        availability_usage=_availability_usage_from_report(report),
        availability_shadow_summary=report.availability_shadow_summary,
    )


def write_dashboard_snapshot(
    report: BestBacktestReport,
    *,
    report_options: BestBacktestReportOptions,
    snapshot_path: Path = DEFAULT_DASHBOARD_SNAPSHOT_PATH,
    artifacts_dir: Path | None = None,
) -> Path:
    """Persist the dashboard snapshot for one canonical report."""
    snapshot = build_dashboard_snapshot(
        report,
        report_options=report_options,
        artifacts_dir=artifacts_dir,
    )
    payload = _snapshot_to_payload(snapshot)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_bytes(
        orjson.dumps(payload, option=orjson.OPT_INDENT_2 | orjson.OPT_SORT_KEYS)
    )
    return snapshot_path


def load_dashboard_snapshot(
    snapshot_path: Path = DEFAULT_DASHBOARD_SNAPSHOT_PATH,
) -> DashboardSnapshot:
    """Load a stored dashboard snapshot from disk."""
    payload = orjson.loads(snapshot_path.read_bytes())
    if payload.get("schema_version") != DASHBOARD_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError(
            "Unsupported dashboard snapshot schema version: "
            f"{payload.get('schema_version')!r}"
        )
    return _snapshot_from_payload(payload)


def dashboard_snapshot_staleness_reason(
    *,
    snapshot_path: Path = DEFAULT_DASHBOARD_SNAPSHOT_PATH,
    report_options: BestBacktestReportOptions | None = None,
    artifacts_dir: Path | None = None,
) -> str | None:
    """Return a staleness reason when the dashboard snapshot needs refresh."""
    if not snapshot_path.exists():
        return "Dashboard snapshot is missing."
    try:
        snapshot = load_dashboard_snapshot(snapshot_path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"Dashboard snapshot is unreadable: {exc}"

    expected_options = report_options or canonical_dashboard_report_options()
    expected_report_signature = _signature(_report_settings_payload(expected_options))
    if snapshot.canonical_report.signature != expected_report_signature:
        return "Dashboard snapshot does not match the canonical best report settings."

    current_artifacts = current_dashboard_artifact_source(artifacts_dir=artifacts_dir)
    if snapshot.source_artifacts.signature != current_artifacts.signature:
        return "Dashboard snapshot no longer matches the current best-path artifacts."

    return None


def ensure_dashboard_snapshot_fresh(
    *,
    database_url: str | None = None,
    artifacts_dir: Path | None = None,
    snapshot_path: Path = DEFAULT_DASHBOARD_SNAPSHOT_PATH,
    progress: Callable[[str], None] | None = None,
) -> DashboardSnapshot:
    """Refresh the canonical report and snapshot when the dashboard needs it."""
    report_options = canonical_dashboard_report_options(database_url=database_url)
    stale_reason = dashboard_snapshot_staleness_reason(
        snapshot_path=snapshot_path,
        report_options=report_options,
        artifacts_dir=artifacts_dir,
    )
    if stale_reason is None:
        return load_dashboard_snapshot(snapshot_path)

    if progress is not None:
        progress(
            f"{stale_reason} Refreshing the canonical report and dashboard snapshot."
        )
    report = generate_best_backtest_report(report_options, progress=progress)
    write_dashboard_snapshot(
        report,
        report_options=report_options,
        snapshot_path=snapshot_path,
        artifacts_dir=artifacts_dir,
    )
    if progress is not None:
        progress(f"Dashboard snapshot ready: {_relative_repo_path(snapshot_path)}")
    return load_dashboard_snapshot(snapshot_path)


def current_dashboard_artifact_source(
    *,
    artifacts_dir: Path | None = None,
) -> DashboardSnapshotArtifactSource:
    """Return the current best-path artifact identity used for freshness checks."""
    resolved_dir = (artifacts_dir or ARTIFACTS_DIR).resolve()
    entries: list[DashboardSnapshotArtifact] = []
    for market in ("spread", "moneyline"):
        path = artifact_path(
            market=market,
            artifact_name=DEFAULT_ARTIFACT_NAME,
            artifacts_dir=resolved_dir,
        )
        if not path.exists():
            continue
        try:
            artifact = load_artifact(
                market=market,
                artifact_name=DEFAULT_ARTIFACT_NAME,
                artifacts_dir=resolved_dir,
            )
        except (FileNotFoundError, KeyError, OSError, ValueError) as exc:
            raise ValueError(
                f"Unable to load best-path artifact '{path.name}': {exc}"
            ) from exc
        entries.append(
            DashboardSnapshotArtifact(
                market=market,
                artifact_name=DEFAULT_ARTIFACT_NAME,
                path=_relative_repo_path(path),
                sha256=sha256(path.read_bytes()).hexdigest(),
                model_family=artifact.model_family,
                trained_at=artifact.metrics.trained_at,
                start_season=artifact.metrics.start_season,
                end_season=artifact.metrics.end_season,
            )
        )
    active_best_market = None
    if any(entry.market == "spread" for entry in entries):
        active_best_market = "spread"
    elif any(entry.market == "moneyline" for entry in entries):
        active_best_market = "moneyline"
    payload: dict[str, object] = {
        "active_best_market": active_best_market,
        "entries": cast(list[object], [asdict(entry) for entry in entries]),
    }
    return DashboardSnapshotArtifactSource(
        active_best_market=active_best_market,
        entries=tuple(entries),
        signature=_signature(payload),
    )


def _dashboard_report_identity(
    *,
    report: BestBacktestReport,
    options: BestBacktestReportOptions,
) -> DashboardSnapshotReportIdentity:
    payload = _report_settings_payload(options)
    return DashboardSnapshotReportIdentity(
        output_path=_relative_repo_path(report.output_path),
        history_output_path=(
            _relative_repo_path(report.history_output_path)
            if report.history_output_path is not None
            else None
        ),
        generated_at=report.generated_at,
        selected_seasons=report.selected_seasons,
        seasons=options.seasons,
        max_season=options.max_season,
        starting_bankroll=options.starting_bankroll,
        unit_size=options.unit_size,
        retrain_days=options.retrain_days,
        auto_tune_spread_policy=options.auto_tune_spread_policy,
        use_timing_layer=options.use_timing_layer,
        spread_model_family=options.spread_model_family,
        policy=_policy_from_model(options.policy),
        signature=_signature(payload),
    )


def _policy_from_model(policy: BetPolicy) -> DashboardSnapshotPolicy:
    return DashboardSnapshotPolicy(
        min_edge=policy.min_edge,
        min_confidence=policy.min_confidence,
        min_probability_edge=policy.min_probability_edge,
        uncertainty_probability_buffer=policy.uncertainty_probability_buffer,
        min_games_played=policy.min_games_played,
        kelly_fraction=policy.kelly_fraction,
        max_bet_fraction=policy.max_bet_fraction,
        max_daily_exposure_fraction=policy.max_daily_exposure_fraction,
        max_bets_per_day=policy.max_bets_per_day,
        min_moneyline_price=policy.min_moneyline_price,
        max_moneyline_price=policy.max_moneyline_price,
        max_spread_abs_line=policy.max_spread_abs_line,
        max_abs_rest_days_diff=policy.max_abs_rest_days_diff,
        min_positive_ev_books=policy.min_positive_ev_books,
        min_median_expected_value=policy.min_median_expected_value,
    )


def _policy_to_model(policy: DashboardSnapshotPolicy) -> BetPolicy:
    return BetPolicy(
        min_edge=policy.min_edge,
        min_confidence=policy.min_confidence,
        min_probability_edge=policy.min_probability_edge,
        uncertainty_probability_buffer=policy.uncertainty_probability_buffer,
        min_games_played=policy.min_games_played,
        kelly_fraction=policy.kelly_fraction,
        max_bet_fraction=policy.max_bet_fraction,
        max_daily_exposure_fraction=policy.max_daily_exposure_fraction,
        max_bets_per_day=policy.max_bets_per_day,
        min_moneyline_price=policy.min_moneyline_price,
        max_moneyline_price=policy.max_moneyline_price,
        max_spread_abs_line=policy.max_spread_abs_line,
        max_abs_rest_days_diff=policy.max_abs_rest_days_diff,
        min_positive_ev_books=policy.min_positive_ev_books,
        min_median_expected_value=policy.min_median_expected_value,
    )


def _report_settings_payload(options: BestBacktestReportOptions) -> dict[str, object]:
    return {
        "output_path": _relative_repo_path(options.output_path),
        "seasons": options.seasons,
        "max_season": options.max_season,
        "starting_bankroll": options.starting_bankroll,
        "unit_size": options.unit_size,
        "retrain_days": options.retrain_days,
        "auto_tune_spread_policy": options.auto_tune_spread_policy,
        "use_timing_layer": options.use_timing_layer,
        "spread_model_family": options.spread_model_family,
        "policy": asdict(_policy_from_model(options.policy)),
    }


def _clv_summary_from_model(summary: ClosingLineValueSummary) -> DashboardSnapshotClv:
    return DashboardSnapshotClv(
        bets_evaluated=summary.bets_evaluated,
        positive_bets=summary.positive_bets,
        negative_bets=summary.negative_bets,
        neutral_bets=summary.neutral_bets,
        positive_rate=summary.positive_rate,
        average_spread_line_delta=summary.average_spread_line_delta,
        average_spread_price_probability_delta=(
            summary.average_spread_price_probability_delta
        ),
        average_spread_no_vig_probability_delta=(
            summary.average_spread_no_vig_probability_delta
        ),
        average_spread_closing_expected_value=(
            summary.average_spread_closing_expected_value
        ),
        average_moneyline_probability_delta=(
            summary.average_moneyline_probability_delta
        ),
    )


def _closing_line_value_summary_from_snapshot(
    summary: DashboardSnapshotClv,
) -> ClosingLineValueSummary:
    spread_bets_evaluated = (
        summary.bets_evaluated if summary.average_spread_line_delta is not None else 0
    )
    spread_price_bets_evaluated = (
        summary.bets_evaluated
        if summary.average_spread_price_probability_delta is not None
        else 0
    )
    spread_no_vig_bets_evaluated = (
        summary.bets_evaluated
        if summary.average_spread_no_vig_probability_delta is not None
        else 0
    )
    spread_closing_ev_bets_evaluated = (
        summary.bets_evaluated
        if summary.average_spread_closing_expected_value is not None
        else 0
    )
    moneyline_bets_evaluated = (
        summary.bets_evaluated
        if summary.average_moneyline_probability_delta is not None
        else 0
    )
    return ClosingLineValueSummary(
        bets_evaluated=summary.bets_evaluated,
        positive_bets=summary.positive_bets,
        negative_bets=summary.negative_bets,
        neutral_bets=summary.neutral_bets,
        spread_bets_evaluated=spread_bets_evaluated,
        total_spread_line_delta=(
            (summary.average_spread_line_delta or 0.0) * spread_bets_evaluated
        ),
        spread_price_bets_evaluated=spread_price_bets_evaluated,
        total_spread_price_probability_delta=(
            (summary.average_spread_price_probability_delta or 0.0)
            * spread_price_bets_evaluated
        ),
        spread_no_vig_bets_evaluated=spread_no_vig_bets_evaluated,
        total_spread_no_vig_probability_delta=(
            (summary.average_spread_no_vig_probability_delta or 0.0)
            * spread_no_vig_bets_evaluated
        ),
        spread_closing_ev_bets_evaluated=spread_closing_ev_bets_evaluated,
        total_spread_closing_expected_value=(
            (summary.average_spread_closing_expected_value or 0.0)
            * spread_closing_ev_bets_evaluated
        ),
        moneyline_bets_evaluated=moneyline_bets_evaluated,
        total_moneyline_probability_delta=(
            (summary.average_moneyline_probability_delta or 0.0)
            * moneyline_bets_evaluated
        ),
    )


def _historical_bets_from_report(
    report: BestBacktestReport,
) -> tuple[DashboardSnapshotHistoricalBet, ...]:
    rows: list[DashboardSnapshotHistoricalBet] = []
    for summary in report.summaries:
        observation_by_scope = {
            (observation.game_id, observation.market, observation.side): observation
            for observation in summary.clv_observations
            if observation.game_id is not None and observation.side is not None
        }
        for bet in summary.placed_bets:
            clv = observation_by_scope.get((bet.game_id, bet.market, bet.side))
            rows.append(
                DashboardSnapshotHistoricalBet(
                    season=summary.evaluation_season,
                    game_id=bet.game_id,
                    commence_time=bet.commence_time,
                    market=bet.market,
                    team_name=bet.team_name,
                    opponent_name=bet.opponent_name,
                    side=bet.side,
                    sportsbook=bet.sportsbook,
                    market_price=bet.market_price,
                    line_value=bet.line_value,
                    model_probability=bet.model_probability,
                    implied_probability=bet.implied_probability,
                    probability_edge=bet.probability_edge,
                    expected_value=bet.expected_value,
                    stake_fraction=bet.stake_fraction,
                    stake_amount=bet.stake_amount,
                    settlement=bet.settlement,
                    profit=settle_bet(bet),
                    minimum_games_played=bet.minimum_games_played,
                    eligible_books=bet.eligible_books,
                    positive_ev_books=bet.positive_ev_books,
                    coverage_rate=bet.coverage_rate,
                    clv=(
                        DashboardSnapshotBetClv(
                            market=clv.market,
                            reference_delta=clv.reference_delta,
                            spread_line_delta=clv.spread_line_delta,
                            spread_price_probability_delta=(
                                clv.spread_price_probability_delta
                            ),
                            spread_no_vig_probability_delta=(
                                clv.spread_no_vig_probability_delta
                            ),
                            spread_closing_expected_value=(
                                clv.spread_closing_expected_value
                            ),
                            moneyline_probability_delta=(
                                clv.moneyline_probability_delta
                            ),
                            game_id=clv.game_id,
                            side=clv.side,
                        )
                        if clv is not None
                        else None
                    ),
                )
            )
    return tuple(sorted(rows, key=lambda row: row.commence_time))


def _recent_window_from_history(
    *,
    key: str,
    report: BestBacktestReport,
    historical_bets: Sequence[DashboardSnapshotHistoricalBet],
) -> DashboardSnapshotRecentWindow:
    selected_rows = _rows_for_window(
        key=key,
        report=report,
        historical_bets=historical_bets,
    )
    if not historical_bets:
        anchor_time = None
    elif selected_rows:
        anchor_time = selected_rows[-1].commence_time
    else:
        anchor_time = historical_bets[-1].commence_time
    if not selected_rows:
        return DashboardSnapshotRecentWindow(
            key=key,
            anchor_time=anchor_time,
            bets=0,
            wins=0,
            losses=0,
            pushes=0,
            profit=0.0,
            roi=0.0,
            total_staked=0.0,
            max_drawdown=0.0,
            bankroll_exposure=0.0,
            average_edge=0.0,
            average_ev=0.0,
            clv=_clv_summary_from_model(ClosingLineValueSummary()),
            bankroll_series=(report.latest_summary.starting_bankroll,),
            rows=(),
        )

    total_staked = sum(row.stake_amount for row in selected_rows)
    profit = sum(row.profit for row in selected_rows)
    wins = sum(1 for row in selected_rows if row.settlement == "win")
    losses = sum(1 for row in selected_rows if row.settlement == "loss")
    pushes = sum(1 for row in selected_rows if row.settlement == "push")
    bankroll = report.latest_summary.starting_bankroll
    peak_bankroll = bankroll
    max_drawdown = 0.0
    bankroll_series = [bankroll]
    for row in selected_rows:
        bankroll += row.profit
        bankroll_series.append(bankroll)
        peak_bankroll = max(peak_bankroll, bankroll)
        if peak_bankroll > 0:
            max_drawdown = max(max_drawdown, (peak_bankroll - bankroll) / peak_bankroll)
    clv_summary = _summarize_snapshot_clv(selected_rows)
    return DashboardSnapshotRecentWindow(
        key=key,
        anchor_time=anchor_time,
        bets=len(selected_rows),
        wins=wins,
        losses=losses,
        pushes=pushes,
        profit=profit,
        roi=profit / total_staked if total_staked > 0 else 0.0,
        total_staked=total_staked,
        max_drawdown=max_drawdown,
        bankroll_exposure=(
            total_staked / report.latest_summary.starting_bankroll
            if report.latest_summary.starting_bankroll > 0
            else 0.0
        ),
        average_edge=_average(row.probability_edge for row in selected_rows),
        average_ev=_average(row.expected_value for row in selected_rows),
        clv=clv_summary,
        bankroll_series=tuple(bankroll_series),
        rows=tuple(selected_rows[-30:][::-1]),
    )


def _rows_for_window(
    *,
    key: str,
    report: BestBacktestReport,
    historical_bets: Sequence[DashboardSnapshotHistoricalBet],
) -> list[DashboardSnapshotHistoricalBet]:
    if not historical_bets:
        return []
    if key == "season":
        latest_season = report.latest_summary.evaluation_season
        return [row for row in historical_bets if row.season == latest_season]
    latest_time = _parse_timestamp(historical_bets[-1].commence_time)
    window_start = latest_time - timedelta(days=RECENT_WINDOW_DAYS[key] - 1)
    return [
        row
        for row in historical_bets
        if _parse_timestamp(row.commence_time) >= window_start
    ]


def _summarize_snapshot_clv(
    rows: Sequence[DashboardSnapshotHistoricalBet],
) -> DashboardSnapshotClv:
    observations = [
        _clv_observation_from_snapshot(row.clv) for row in rows if row.clv is not None
    ]
    summary = ClosingLineValueSummary()
    if observations:
        from cbb.modeling.backtest import summarize_closing_line_value

        summary = summarize_closing_line_value(observations)
    return _clv_summary_from_model(summary)


def _snapshot_to_payload(snapshot: DashboardSnapshot) -> dict[str, object]:
    return asdict(snapshot)


def _snapshot_from_payload(payload: dict[str, object]) -> DashboardSnapshot:
    source_payload = _require_mapping(payload["source_artifacts"])
    report_payload = _require_mapping(payload["canonical_report"])
    return DashboardSnapshot(
        schema_version=_string_value(payload["schema_version"]),
        generated_at=_string_value(payload["generated_at"]),
        source_artifacts=DashboardSnapshotArtifactSource(
            active_best_market=_optional_str(source_payload.get("active_best_market")),
            entries=tuple(
                _artifact_from_payload(_require_mapping(item))
                for item in _require_sequence(source_payload["entries"])
            ),
            signature=_string_value(source_payload["signature"]),
        ),
        canonical_report=DashboardSnapshotReportIdentity(
            output_path=_string_value(report_payload["output_path"]),
            history_output_path=_optional_str(
                report_payload.get("history_output_path")
            ),
            generated_at=_string_value(report_payload["generated_at"]),
            selected_seasons=tuple(
                _int_value(season)
                for season in _require_sequence(report_payload["selected_seasons"])
            ),
            seasons=_int_value(report_payload["seasons"]),
            max_season=_optional_int(report_payload.get("max_season")),
            starting_bankroll=_float_value(report_payload["starting_bankroll"]),
            unit_size=_float_value(report_payload["unit_size"]),
            retrain_days=_int_value(report_payload["retrain_days"]),
            auto_tune_spread_policy=_bool_value(
                report_payload["auto_tune_spread_policy"]
            ),
            use_timing_layer=_bool_value(report_payload["use_timing_layer"]),
            spread_model_family=_string_value(report_payload["spread_model_family"]),
            policy=_policy_from_payload(_require_mapping(report_payload["policy"])),
            signature=_string_value(report_payload["signature"]),
        ),
        aggregate_summary=_aggregate_from_payload(
            _require_mapping(payload["aggregate_summary"])
        ),
        aggregate_clv=_clv_from_payload(_require_mapping(payload["aggregate_clv"])),
        season_summaries=tuple(
            _season_summary_from_payload(_require_mapping(item))
            for item in _require_sequence(payload["season_summaries"])
        ),
        historical_bets=tuple(
            _historical_bet_from_payload(_require_mapping(item))
            for item in _require_sequence(payload["historical_bets"])
        ),
        recent_windows=tuple(
            _recent_window_from_payload(_require_mapping(item))
            for item in _require_sequence(payload["recent_windows"])
        ),
        availability_usage=_availability_usage_from_payload(
            payload.get("availability_usage")
        ),
        availability_shadow_summary=_availability_shadow_summary_from_payload(
            payload.get("availability_shadow_summary")
        ),
    )


def _policy_from_payload(payload: dict[str, object]) -> DashboardSnapshotPolicy:
    return DashboardSnapshotPolicy(
        min_edge=_float_value(payload["min_edge"]),
        min_confidence=_float_value(payload["min_confidence"]),
        min_probability_edge=_float_value(payload["min_probability_edge"]),
        uncertainty_probability_buffer=_float_value(
            payload["uncertainty_probability_buffer"]
        ),
        min_games_played=_int_value(payload["min_games_played"]),
        kelly_fraction=_float_value(payload["kelly_fraction"]),
        max_bet_fraction=_float_value(payload["max_bet_fraction"]),
        max_daily_exposure_fraction=_float_value(
            payload["max_daily_exposure_fraction"]
        ),
        max_bets_per_day=_optional_int(payload.get("max_bets_per_day")),
        min_moneyline_price=_float_value(payload["min_moneyline_price"]),
        max_moneyline_price=_float_value(payload["max_moneyline_price"]),
        max_spread_abs_line=_optional_float(payload.get("max_spread_abs_line")),
        max_abs_rest_days_diff=_optional_float(payload.get("max_abs_rest_days_diff")),
        min_positive_ev_books=_int_value(payload["min_positive_ev_books"]),
        min_median_expected_value=_optional_float(
            payload.get("min_median_expected_value")
        ),
    )


def _aggregate_from_payload(
    payload: dict[str, object],
) -> DashboardSnapshotAggregateSummary:
    return DashboardSnapshotAggregateSummary(
        bets=_int_value(payload["bets"]),
        profit=_float_value(payload["profit"]),
        roi=_float_value(payload["roi"]),
        units=_float_value(payload["units"]),
        max_drawdown=_float_value(payload["max_drawdown"]),
        profitable_seasons=_int_value(payload["profitable_seasons"]),
        active_seasons=_int_value(payload["active_seasons"]),
    )


def _clv_from_payload(payload: dict[str, object]) -> DashboardSnapshotClv:
    return DashboardSnapshotClv(
        bets_evaluated=_int_value(payload["bets_evaluated"]),
        positive_bets=_int_value(payload["positive_bets"]),
        negative_bets=_int_value(payload["negative_bets"]),
        neutral_bets=_int_value(payload["neutral_bets"]),
        positive_rate=_float_value(payload["positive_rate"]),
        average_spread_line_delta=_optional_float(
            payload.get("average_spread_line_delta")
        ),
        average_spread_price_probability_delta=_optional_float(
            payload.get("average_spread_price_probability_delta")
        ),
        average_spread_no_vig_probability_delta=_optional_float(
            payload.get("average_spread_no_vig_probability_delta")
        ),
        average_spread_closing_expected_value=_optional_float(
            payload.get("average_spread_closing_expected_value")
        ),
        average_moneyline_probability_delta=_optional_float(
            payload.get("average_moneyline_probability_delta")
        ),
    )


def _season_summary_from_payload(
    payload: dict[str, object],
) -> DashboardSnapshotSeasonSummary:
    return DashboardSnapshotSeasonSummary(
        season=_int_value(payload["season"]),
        bets=_int_value(payload["bets"]),
        wins=_int_value(payload["wins"]),
        losses=_int_value(payload["losses"]),
        pushes=_int_value(payload["pushes"]),
        profit=_float_value(payload["profit"]),
        roi=_float_value(payload["roi"]),
        units=_float_value(payload["units"]),
        max_drawdown=_float_value(payload["max_drawdown"]),
        clv=_clv_from_payload(_require_mapping(payload["clv"])),
    )


def _historical_bet_from_payload(
    payload: dict[str, object],
) -> DashboardSnapshotHistoricalBet:
    clv_payload = payload.get("clv")
    clv_mapping = _require_mapping(clv_payload) if clv_payload is not None else None
    return DashboardSnapshotHistoricalBet(
        season=_int_value(payload["season"]),
        game_id=_int_value(payload["game_id"]),
        commence_time=_string_value(payload["commence_time"]),
        market=_string_value(payload["market"]),
        team_name=_string_value(payload["team_name"]),
        opponent_name=_string_value(payload["opponent_name"]),
        side=_string_value(payload["side"]),
        sportsbook=_string_value(payload["sportsbook"]),
        market_price=_float_value(payload["market_price"]),
        line_value=_optional_float(payload.get("line_value")),
        model_probability=_float_value(payload["model_probability"]),
        implied_probability=_float_value(payload["implied_probability"]),
        probability_edge=_float_value(payload["probability_edge"]),
        expected_value=_float_value(payload["expected_value"]),
        stake_fraction=_float_value(payload["stake_fraction"]),
        stake_amount=_float_value(payload["stake_amount"]),
        settlement=_string_value(payload["settlement"]),
        profit=_float_value(payload["profit"]),
        minimum_games_played=_int_value(payload["minimum_games_played"]),
        eligible_books=_int_value(payload["eligible_books"]),
        positive_ev_books=_int_value(payload["positive_ev_books"]),
        coverage_rate=_float_value(payload["coverage_rate"]),
        clv=(
            DashboardSnapshotBetClv(
                market=_string_value(clv_mapping["market"]),
                reference_delta=_float_value(clv_mapping["reference_delta"]),
                spread_line_delta=_optional_float(clv_mapping.get("spread_line_delta")),
                spread_price_probability_delta=_optional_float(
                    clv_mapping.get("spread_price_probability_delta")
                ),
                spread_no_vig_probability_delta=_optional_float(
                    clv_mapping.get("spread_no_vig_probability_delta")
                ),
                spread_closing_expected_value=_optional_float(
                    clv_mapping.get("spread_closing_expected_value")
                ),
                moneyline_probability_delta=_optional_float(
                    clv_mapping.get("moneyline_probability_delta")
                ),
                game_id=_optional_int(clv_mapping.get("game_id")),
                side=_optional_str(clv_mapping.get("side")),
            )
            if clv_mapping is not None
            else None
        ),
    )


def _recent_window_from_payload(
    payload: dict[str, object],
) -> DashboardSnapshotRecentWindow:
    return DashboardSnapshotRecentWindow(
        key=_string_value(payload["key"]),
        anchor_time=_optional_str(payload.get("anchor_time")),
        bets=_int_value(payload["bets"]),
        wins=_int_value(payload["wins"]),
        losses=_int_value(payload["losses"]),
        pushes=_int_value(payload["pushes"]),
        profit=_float_value(payload["profit"]),
        roi=_float_value(payload["roi"]),
        total_staked=_float_value(payload["total_staked"]),
        max_drawdown=_float_value(payload["max_drawdown"]),
        bankroll_exposure=_float_value(payload["bankroll_exposure"]),
        average_edge=_float_value(payload["average_edge"]),
        average_ev=_float_value(payload["average_ev"]),
        clv=_clv_from_payload(_require_mapping(payload["clv"])),
        bankroll_series=tuple(
            _float_value(value)
            for value in _require_sequence(payload["bankroll_series"])
        ),
        rows=tuple(
            _historical_bet_from_payload(_require_mapping(item))
            for item in _require_sequence(payload["rows"])
        ),
    )


def _availability_shadow_summary_from_payload(
    payload: object,
) -> AvailabilityShadowSummary:
    if payload is None:
        return AvailabilityShadowSummary()
    mapping = _require_mapping(payload)
    return AvailabilityShadowSummary(
        reports_loaded=_int_value(mapping.get("reports_loaded", 0)),
        player_rows_loaded=_int_value(mapping.get("player_rows_loaded", 0)),
        games_covered=_int_value(mapping.get("games_covered", 0)),
        matched_player_rows=_optional_int(mapping.get("matched_player_rows")),
        unmatched_player_rows=_optional_int(mapping.get("unmatched_player_rows")),
        latest_update_at=_optional_str(mapping.get("latest_update_at")),
        average_minutes_before_tip=_optional_float(
            mapping.get("average_minutes_before_tip")
        ),
        latest_minutes_before_tip=_optional_float(
            mapping.get("latest_minutes_before_tip")
        ),
        seasons=tuple(
            _int_value(value) for value in _require_sequence(mapping.get("seasons", []))
        ),
        scope_labels=tuple(
            _string_value(value)
            for value in _require_sequence(mapping.get("scope_labels", []))
        ),
        source_labels=tuple(
            _string_value(value)
            for value in _require_sequence(mapping.get("source_labels", []))
        ),
        status_counts=tuple(
            AvailabilityShadowStatusCount(
                status=_string_value(status_payload["status"]),
                row_count=_int_value(status_payload["row_count"]),
            )
            for item in _require_sequence(mapping.get("status_counts", []))
            for status_payload in (_require_mapping(item),)
        ),
    )


def _availability_usage_from_payload(
    payload: object,
) -> DashboardSnapshotAvailabilityUsage:
    if payload is None:
        return DashboardSnapshotAvailabilityUsage()
    mapping = _require_mapping(payload)
    state = _normalize_availability_usage_state(_optional_str(mapping.get("state")))
    note = _optional_str(mapping.get("note")) or _default_availability_usage_note(state)
    return DashboardSnapshotAvailabilityUsage(state=state, note=note)


def _availability_usage_from_report(
    report: BestBacktestReport,
) -> DashboardSnapshotAvailabilityUsage:
    state = _normalize_availability_usage_state(
        cast(str | None, getattr(report, "availability_usage_state", None))
    )
    note = cast(str | None, getattr(report, "availability_usage_note", None))
    return DashboardSnapshotAvailabilityUsage(
        state=state,
        note=note or _default_availability_usage_note(state),
    )


def _normalize_availability_usage_state(value: str | None) -> AvailabilityUsageState:
    if value is None:
        return DEFAULT_AVAILABILITY_USAGE_STATE
    normalized = _AVAILABILITY_USAGE_ALIASES.get(value.strip().lower())
    if normalized is None:
        return DEFAULT_AVAILABILITY_USAGE_STATE
    return cast(AvailabilityUsageState, normalized)


def _default_availability_usage_note(state: AvailabilityUsageState) -> str:
    return _AVAILABILITY_USAGE_NOTES[state]


def _artifact_from_payload(payload: dict[str, object]) -> DashboardSnapshotArtifact:
    return DashboardSnapshotArtifact(
        market=_string_value(payload["market"]),
        artifact_name=_string_value(payload["artifact_name"]),
        path=_string_value(payload["path"]),
        sha256=_string_value(payload["sha256"]),
        model_family=_string_value(payload["model_family"]),
        trained_at=_string_value(payload["trained_at"]),
        start_season=_int_value(payload["start_season"]),
        end_season=_int_value(payload["end_season"]),
    )


def _placed_bet_from_snapshot(row: DashboardSnapshotHistoricalBet) -> PlacedBet:
    return PlacedBet(
        game_id=row.game_id,
        commence_time=row.commence_time,
        market=cast(ModelMarket, row.market),
        team_name=row.team_name,
        opponent_name=row.opponent_name,
        side=row.side,
        sportsbook=row.sportsbook,
        market_price=row.market_price,
        line_value=row.line_value,
        model_probability=row.model_probability,
        implied_probability=row.implied_probability,
        probability_edge=row.probability_edge,
        expected_value=row.expected_value,
        stake_fraction=row.stake_fraction,
        stake_amount=row.stake_amount,
        settlement=row.settlement,
        minimum_games_played=row.minimum_games_played,
        eligible_books=row.eligible_books,
        positive_ev_books=row.positive_ev_books,
        coverage_rate=row.coverage_rate,
    )


def _clv_observation_from_snapshot(
    clv: DashboardSnapshotBetClv,
) -> ClosingLineValueObservation:
    return ClosingLineValueObservation(
        market=cast(ModelMarket, clv.market),
        reference_delta=clv.reference_delta,
        spread_line_delta=clv.spread_line_delta,
        spread_price_probability_delta=clv.spread_price_probability_delta,
        spread_no_vig_probability_delta=clv.spread_no_vig_probability_delta,
        spread_closing_expected_value=clv.spread_closing_expected_value,
        moneyline_probability_delta=clv.moneyline_probability_delta,
        game_id=clv.game_id,
        side=clv.side,
    )


def _average(values: Iterable[float]) -> float:
    collected = list(values)
    if not collected:
        return 0.0
    return sum(collected) / len(collected)


def _parse_timestamp(value: str) -> datetime:
    normalized_value = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed_value = datetime.fromisoformat(normalized_value)
    if parsed_value.tzinfo is None:
        return parsed_value.replace(tzinfo=UTC)
    return parsed_value


def _relative_repo_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path.resolve())


def _signature(payload: object) -> str:
    return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _require_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"Expected mapping payload, got {type(value).__name__}")
    return value


def _require_sequence(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"Expected list payload, got {type(value).__name__}")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return _float_value(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _int_value(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _string_value(value: object) -> str:
    return str(value)


def _float_value(value: object) -> float:
    if not isinstance(value, (float, int, str)):
        raise TypeError(f"Expected numeric payload, got {type(value).__name__}")
    return float(value)


def _int_value(value: object) -> int:
    if not isinstance(value, (int, str)):
        raise TypeError(f"Expected integer payload, got {type(value).__name__}")
    return int(value)


def _bool_value(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    raise TypeError(f"Expected bool payload, got {type(value).__name__}")
