"""Markdown reporting for walk-forward best-model backtests."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import median

from cbb.db import (
    REPO_ROOT,
    AvailabilityGameSideShadow,
    AvailabilityShadowSummary,
    get_availability_game_side_shadows,
    get_availability_shadow_summary,
)
from cbb.modeling.artifacts import ModelFamily
from cbb.modeling.backtest import (
    DEFAULT_BACKTEST_RETRAIN_DAYS,
    DEFAULT_STARTING_BANKROLL,
    DEFAULT_UNIT_SIZE,
    BacktestOptions,
    BacktestSummary,
    ClosingLineValueObservation,
    ClosingLineValueSummary,
    SpreadSegmentAttribution,
    SpreadSegmentSummary,
    backtest_betting_model,
    summarize_closing_line_value,
)
from cbb.modeling.dataset import get_available_seasons
from cbb.modeling.policy import BetPolicy, PlacedBet, settle_bet
from cbb.modeling.train import DEFAULT_SPREAD_MODEL_FAMILY

DEFAULT_BEST_BACKTEST_REPORT_PATH = (
    REPO_ROOT / "docs" / "results" / "best-model-3y-backtest.md"
)
AVAILABILITY_USAGE_STATE = "shadow_only"
AVAILABILITY_USAGE_NOTE = (
    "Official availability is stored for diagnostics only. It does not change "
    "the promoted live board, backtest, or betting-policy path."
)
MIN_AVAILABILITY_SLICE_BETS = 5


@dataclass(frozen=True)
class BestBacktestReportOptions:
    """Options for generating the built-in best-model report."""

    output_path: Path = DEFAULT_BEST_BACKTEST_REPORT_PATH
    seasons: int = 3
    max_season: int | None = None
    database_url: str | None = None
    starting_bankroll: float = DEFAULT_STARTING_BANKROLL
    unit_size: float = DEFAULT_UNIT_SIZE
    retrain_days: int = DEFAULT_BACKTEST_RETRAIN_DAYS
    auto_tune_spread_policy: bool = False
    use_timing_layer: bool = False
    spread_model_family: ModelFamily = DEFAULT_SPREAD_MODEL_FAMILY
    policy: BetPolicy = field(default_factory=BetPolicy)
    write_history_copy: bool = True
    history_dir: Path | None = None


@dataclass(frozen=True)
class BestBacktestReport:
    """Generated best-model report plus its key aggregate metrics."""

    output_path: Path
    history_output_path: Path | None
    selected_seasons: tuple[int, ...]
    summaries: tuple[BacktestSummary, ...]
    aggregate_bets: int
    aggregate_profit: float
    aggregate_roi: float
    aggregate_units: float
    max_drawdown: float
    zero_bet_seasons: tuple[int, ...]
    latest_summary: BacktestSummary
    markdown: str
    generated_at: str = ""
    aggregate_clv: ClosingLineValueSummary = ClosingLineValueSummary()
    availability_shadow_summary: AvailabilityShadowSummary = field(
        default_factory=AvailabilityShadowSummary
    )
    availability_usage_state: str = AVAILABILITY_USAGE_STATE
    availability_usage_note: str = AVAILABILITY_USAGE_NOTE


@dataclass(frozen=True)
class AvailabilityEvaluatedBet:
    """One settled best-path bet joined to the game-side availability shadow model."""

    evaluation_season: int
    bet: PlacedBet
    clv_observation: ClosingLineValueObservation | None
    availability: AvailabilityGameSideShadow | None


@dataclass(frozen=True)
class AvailabilityEvaluationSlice:
    """One shadow-only evaluation slice rendered in the canonical report."""

    label: str
    bets: int
    wins: int
    losses: int
    pushes: int
    profit: float | None
    roi: float | None
    clv: ClosingLineValueSummary = field(default_factory=ClosingLineValueSummary)
    note: str = ""
    insufficient_sample: bool = False


@dataclass(frozen=True)
class AvailabilityEvaluationGroup:
    """One group of shadow-only availability evaluation slices."""

    title: str
    description: str
    slices: tuple[AvailabilityEvaluationSlice, ...]


@dataclass(frozen=True)
class StakeSizeSummary:
    """Observed stake-size distribution for the rendered report window."""

    bets: int = 0
    average_stake: float | None = None
    median_stake: float | None = None
    smallest_stake: float | None = None
    largest_stake: float | None = None


def build_best_backtest_report(
    options: BestBacktestReportOptions,
    *,
    progress: Callable[[str], None] | None = None,
) -> BestBacktestReport:
    """Backtest the current best model without writing output files."""
    if options.seasons < 1:
        raise ValueError("seasons must be at least 1")

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    available_seasons = get_available_seasons(options.database_url)
    if not available_seasons:
        raise ValueError("No completed seasons are available for reporting")

    selected_seasons = _select_report_seasons(
        available_seasons=available_seasons,
        seasons=options.seasons,
        max_season=options.max_season,
    )
    summaries: list[BacktestSummary] = []
    for season in selected_seasons:
        if progress is not None:
            progress(f"Backtesting season {season}...")
        summary = backtest_betting_model(
            BacktestOptions(
                market="best",
                evaluation_season=season,
                starting_bankroll=options.starting_bankroll,
                unit_size=options.unit_size,
                retrain_days=options.retrain_days,
                auto_tune_spread_policy=options.auto_tune_spread_policy,
                use_timing_layer=options.use_timing_layer,
                spread_model_family=options.spread_model_family,
                policy=options.policy,
                database_url=options.database_url,
            )
        )
        summaries.append(summary)
        if progress is not None:
            progress(
                f"Finished season {season}: bets={summary.bets_placed}, "
                f"profit={_format_currency(summary.profit)}, "
                f"roi={_format_pct(summary.roi)}"
            )

    aggregate_profit = sum(summary.profit for summary in summaries)
    aggregate_bets = sum(summary.bets_placed for summary in summaries)
    aggregate_units = sum(summary.units_won for summary in summaries)
    total_staked = sum(summary.total_staked for summary in summaries)
    aggregate_roi = aggregate_profit / total_staked if total_staked > 0 else 0.0
    max_drawdown = max((summary.max_drawdown for summary in summaries), default=0.0)
    zero_bet_seasons = tuple(
        summary.evaluation_season for summary in summaries if summary.bets_placed == 0
    )
    availability_shadow_summary = get_availability_shadow_summary(
        options.database_url
    )
    availability_evaluation_groups = _build_availability_evaluation_groups(
        summaries=tuple(summaries),
        game_side_shadows=(
            get_availability_game_side_shadows(options.database_url)
            if any(summary.placed_bets for summary in summaries)
            else ()
        ),
    )
    output_path = _resolve_output_path(options.output_path)
    history_output_path = (
        _build_history_output_path(
            output_path=output_path,
            history_dir=options.history_dir,
        )
        if options.write_history_copy
        else None
    )
    markdown = render_best_backtest_report(
        generated_at=generated_at,
        selected_seasons=tuple(selected_seasons),
        summaries=tuple(summaries),
        output_path=output_path,
        history_output_path=history_output_path,
        starting_bankroll=options.starting_bankroll,
        unit_size=options.unit_size,
        retrain_days=options.retrain_days,
        auto_tune_spread_policy=options.auto_tune_spread_policy,
        use_timing_layer=options.use_timing_layer,
        spread_model_family=options.spread_model_family,
        availability_shadow_summary=availability_shadow_summary,
        availability_evaluation_groups=availability_evaluation_groups,
    )
    return BestBacktestReport(
        output_path=output_path,
        history_output_path=history_output_path,
        generated_at=generated_at,
        selected_seasons=tuple(selected_seasons),
        summaries=tuple(summaries),
        aggregate_bets=aggregate_bets,
        aggregate_profit=aggregate_profit,
        aggregate_roi=aggregate_roi,
        aggregate_units=aggregate_units,
        max_drawdown=max_drawdown,
        zero_bet_seasons=zero_bet_seasons,
        aggregate_clv=_combine_clv_summaries(summaries),
        latest_summary=summaries[-1],
        markdown=markdown,
        availability_shadow_summary=availability_shadow_summary,
    )


def generate_best_backtest_report(
    options: BestBacktestReportOptions,
    *,
    progress: Callable[[str], None] | None = None,
) -> BestBacktestReport:
    """Backtest the current best model and write a Markdown report."""
    report = build_best_backtest_report(options, progress=progress)
    report.output_path.parent.mkdir(parents=True, exist_ok=True)
    report.output_path.write_text(report.markdown, encoding="utf-8")
    if report.history_output_path is not None:
        report.history_output_path.parent.mkdir(parents=True, exist_ok=True)
        report.history_output_path.write_text(report.markdown, encoding="utf-8")
    return report


def render_best_backtest_report(
    *,
    generated_at: str,
    selected_seasons: tuple[int, ...],
    summaries: tuple[BacktestSummary, ...],
    output_path: Path,
    history_output_path: Path | None,
    starting_bankroll: float,
    unit_size: float,
    retrain_days: int,
    auto_tune_spread_policy: bool,
    use_timing_layer: bool,
    spread_model_family: ModelFamily,
    availability_shadow_summary: AvailabilityShadowSummary,
    availability_evaluation_groups: tuple[AvailabilityEvaluationGroup, ...],
) -> str:
    """Render the best-model report Markdown."""
    total_bets = sum(summary.bets_placed for summary in summaries)
    total_profit = sum(summary.profit for summary in summaries)
    total_staked = sum(summary.total_staked for summary in summaries)
    total_units = sum(summary.units_won for summary in summaries)
    aggregate_roi = total_profit / total_staked if total_staked > 0 else 0.0
    max_drawdown = max((summary.max_drawdown for summary in summaries), default=0.0)
    aggregate_clv = _combine_clv_summaries(summaries)
    aggregate_spread_segments = _combine_spread_segment_attributions(summaries)
    total_spread_bets = sum(
        _count_market_bets(summary, market="spread") for summary in summaries
    )
    total_moneyline_bets = sum(
        _count_market_bets(summary, market="moneyline") for summary in summaries
    )
    close_coverage_summary = _format_close_coverage_summary(
        aggregate_clv,
        total_spread_bets,
        total_moneyline_bets,
    )
    stake_size_summary = build_stake_size_summary(summaries)
    availability_shadow_compact_summary = _format_availability_shadow_compact_summary(
        availability_shadow_summary
    )
    profitable_seasons = [
        summary.evaluation_season
        for summary in summaries
        if summary.bets_placed > 0 and summary.profit > 0
    ]
    active_seasons = [
        summary.evaluation_season for summary in summaries if summary.bets_placed > 0
    ]
    zero_bet_seasons = [
        summary.evaluation_season for summary in summaries if summary.bets_placed == 0
    ]
    latest_summary = summaries[-1]
    best_summary = max(summaries, key=lambda summary: summary.profit)
    worst_summary = min(summaries, key=lambda summary: summary.profit)
    assessment = _build_assessment(
        summaries=summaries,
        aggregate_profit=total_profit,
        latest_summary=latest_summary,
        profitable_seasons=profitable_seasons,
        active_seasons=active_seasons,
    )
    decision_evidence = _build_decision_evidence(
        aggregate_clv=aggregate_clv,
        total_profit=total_profit,
        total_bets=total_bets,
    )
    decision_risk = _build_decision_risk(
        worst_summary=worst_summary,
        profitable_seasons=profitable_seasons,
        active_seasons=active_seasons,
    )
    decision_next_action = _build_decision_next_action(aggregate_profit=total_profit)

    lines = [
        "# Best Model Backtest Report",
        "",
        f"Generated: `{generated_at}`",
        f"Output: `{_display_output_path(output_path)}`",
        (
            f"History Copy: `{_display_output_path(history_output_path)}`"
            if history_output_path is not None
            else "History Copy: `disabled`"
        ),
        "",
        "## Scope",
        "",
        "- Market: `best`",
        (
            "- Auto-tuned spread policy: "
            f"`{'enabled' if auto_tune_spread_policy else 'disabled'}`"
        ),
        f"- Timing layer: `{'enabled' if use_timing_layer else 'disabled'}`",
        f"- Spread model family: `{spread_model_family}`",
        f"- Seasons: {', '.join(f'`{season}`' for season in selected_seasons)}",
        f"- Starting bankroll: `{_format_currency(starting_bankroll)}`",
        f"- Unit size: `{_format_currency(unit_size)}`",
        f"- Retrain cadence: `{retrain_days} days`",
        "",
        "## Decision Snapshot",
        "",
        f"- Verdict: {assessment}",
        f"- Strongest evidence: {decision_evidence}",
        f"- Main risk: {decision_risk}",
        *(
            [f"- Stake profile: {_format_stake_profile_compact(stake_size_summary)}"]
            if stake_size_summary.bets > 0
            else []
        ),
        f"- Close-quality coverage: {close_coverage_summary}",
        f"- Next action: {decision_next_action}",
        "",
        "## Assessment",
        "",
        assessment,
        "",
        (
            f"- Aggregate result: `{_format_currency(total_profit)}` on "
            f"`{total_bets}` bets, ROI `{_format_pct(aggregate_roi)}`"
        ),
        f"- Aggregate CLV: {_format_clv_summary(aggregate_clv)}",
        f"- Close-market coverage: {close_coverage_summary}",
        (
            f"- Latest season `{latest_summary.evaluation_season}`: "
            f"`{_format_currency(latest_summary.profit)}`, "
            f"ROI `{_format_pct(latest_summary.roi)}`"
        ),
        (f"- Latest season CLV: {_format_clv_summary(latest_summary.clv)}"),
        *(
            [f"- Stake sizing: {_format_stake_profile_verbose(stake_size_summary)}"]
            if stake_size_summary.bets > 0
            else []
        ),
        f"- Availability shadow data: {availability_shadow_compact_summary}",
        (
            f"- Best season: `{best_summary.evaluation_season}` with "
            f"`{_format_currency(best_summary.profit)}`"
        ),
        (
            f"- Worst season: `{worst_summary.evaluation_season}` with "
            f"`{_format_currency(worst_summary.profit)}`"
        ),
        (
            "- Zero-bet seasons: "
            + (
                ", ".join(f"`{season}`" for season in zero_bet_seasons)
                if zero_bet_seasons
                else "`none`"
            )
        ),
        "",
        "## Season Results",
        "",
        (
            "| Season | Bets | Profit | ROI | Units | Max Drawdown | "
            "Wins-Losses-Pushes | CLV | Final Policy |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    lines.extend(
        (
            f"| `{summary.evaluation_season}` | {summary.bets_placed} | "
            f"{_format_currency(summary.profit)} | {_format_pct(summary.roi)} | "
            f"{_format_units(summary.units_won)} | "
            f"{_format_pct(summary.max_drawdown)} | "
            f"{summary.wins}-{summary.losses}-{summary.pushes} | "
            f"{_format_clv_summary(summary.clv)} | "
            f"{_format_policy(summary)} |"
        )
        for summary in summaries
    )
    lines.extend(
        [
            "",
            "## Aggregate",
            "",
            (
                "| Seasons | Bets | Profit | ROI | Units | Max Drawdown | "
                "Profitable Seasons |"
            ),
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            (
                f"| {len(selected_seasons)} | {total_bets} | "
                f"{_format_currency(total_profit)} | {_format_pct(aggregate_roi)} | "
                f"{_format_units(total_units)} | {_format_pct(max_drawdown)} | "
                f"{len(profitable_seasons)}/{len(active_seasons)} |"
            ),
            "",
            "## Official Availability Shadow",
            "",
            (
                "Stored official availability data is shadow-only in the current repo. "
                "It is visible for audit and coverage review here, but it is not used "
                "by the live prediction, backtest, or betting-policy paths yet."
            ),
            "",
            "| Metric | Value | Notes |",
            "| --- | --- | --- |",
            *_render_availability_shadow_rows(availability_shadow_summary),
            "",
            *(
                [
                    "## Availability Evaluation Slices",
                    "",
                    (
                        "These shadow diagnostics join settled best-path bets to the "
                        "latest matched official availability report for the bet "
                        "side. They do not change the canonical headline metrics "
                        "and they are not promotion evidence by themselves."
                    ),
                    "",
                    (
                        f"Rows with fewer than `{MIN_AVAILABILITY_SLICE_BETS}` "
                        "settled bets are marked `insufficient sample`."
                    ),
                    "",
                    *_render_availability_evaluation_groups(
                        availability_evaluation_groups
                    ),
                ]
                if availability_evaluation_groups
                else []
            ),
            "## Close-Market Coverage",
            "",
            "| Metric | Tracked | Missing / Unmatched | Notes |",
            "| --- | ---: | ---: | --- |",
            *_render_close_coverage_rows(
                aggregate_clv=aggregate_clv,
                total_spread_bets=total_spread_bets,
                total_moneyline_bets=total_moneyline_bets,
            ),
            "",
            "## Closing-Line Value",
            "",
            (
                "| Season | Bets Tracked | Positive | Neutral | Negative | "
                "Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | "
                "Avg Spread No-Vig Close Delta | Avg Spread Closing EV | "
                "Avg Moneyline CLV |"
            ),
            (
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | "
                "---: | ---: | ---: |"
            ),
        ]
    )
    lines.extend(
        (
            f"| `{summary.evaluation_season}` | {summary.clv.bets_evaluated} | "
            f"{summary.clv.positive_bets} | {summary.clv.neutral_bets} | "
            f"{summary.clv.negative_bets} | "
            f"{_format_pct(summary.clv.positive_rate)} | "
            f"{_format_spread_clv(summary.clv)} | "
            f"{_format_spread_price_clv(summary.clv)} | "
            f"{_format_spread_no_vig_clv(summary.clv)} | "
            f"{_format_spread_closing_ev(summary.clv)} | "
            f"{_format_moneyline_clv(summary.clv)} |"
        )
        for summary in summaries
    )
    lines.extend(
        [
            (
                f"| Aggregate | {aggregate_clv.bets_evaluated} | "
                f"{aggregate_clv.positive_bets} | {aggregate_clv.neutral_bets} | "
                f"{aggregate_clv.negative_bets} | "
                f"{_format_pct(aggregate_clv.positive_rate)} | "
                f"{_format_spread_clv(aggregate_clv)} | "
                f"{_format_spread_price_clv(aggregate_clv)} | "
                f"{_format_spread_no_vig_clv(aggregate_clv)} | "
                f"{_format_spread_closing_ev(aggregate_clv)} | "
                f"{_format_moneyline_clv(aggregate_clv)} |"
            ),
        ]
    )
    if aggregate_spread_segments:
        lines.extend(["", "## Spread Segment Attribution", ""])
        for dimension_summary in aggregate_spread_segments:
            lines.extend(_render_spread_segment_attribution(dimension_summary))
    lines.extend(
        [
            "",
            "## Notes",
            "",
            (
                "- `best` is the current deployable spread-only path when a "
                "spread artifact is available. Moneyline is only used when "
                "spread cannot train or load."
            ),
            (
                "- When the timing layer is enabled, spread bets are evaluated "
                "from a six-hour pre-tip snapshot and only early bets with "
                "favorable predicted closing-line movement are kept."
            ),
            (
                "- CLV is measured against the stored closing consensus. "
                "Spread now tracks line delta, raw price delta, no-vig close "
                "delta, and model EV at the close quote; moneyline tracks "
                "normalized implied-probability delta."
            ),
            (
                "- The positive/neutral/negative CLV counts still use spread "
                "line movement for spread bets and no-vig close delta for "
                "moneyline bets. The added spread price and close-EV columns "
                "are supplemental execution measurements."
            ),
            (
                "- When a backtest scores the closing snapshot itself, spread "
                "line CLV should be near-neutral, but price CLV and closing EV "
                "can still move because the executable quote and the stored "
                "close consensus are not always identical."
            ),
            (
                "- Close-market coverage uses tracked settled bets as the "
                "denominator for each market-specific signal."
            ),
            (
                "- Official availability data can now be stored and surfaced in "
                "shadow form for diagnostics, but it is still excluded from the "
                "promoted live and backtest model paths."
            ),
            (
                "- The spread segment tables are aggregate attribution views "
                "for qualified spread bets only. They are intended for "
                "research diagnostics, not direct causal claims."
            ),
            (
                "- A `0`-bet season means the active policy did not find "
                "qualifying opportunities in that season."
            ),
            "- Refresh this report with `cbb model report`.",
            "",
        ]
    )
    return "\n".join(lines)


def _select_report_seasons(
    *,
    available_seasons: list[int],
    seasons: int,
    max_season: int | None,
) -> list[int]:
    eligible_seasons = [
        season
        for season in available_seasons
        if max_season is None or season <= max_season
    ]
    if not eligible_seasons:
        raise ValueError("No completed seasons match the requested report window")
    return eligible_seasons[-seasons:]


def _resolve_output_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def _build_history_output_path(
    *,
    output_path: Path,
    history_dir: Path | None,
) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    resolved_history_dir = (
        _resolve_output_path(history_dir)
        if history_dir is not None
        else output_path.parent / "history"
    )
    return resolved_history_dir / f"{output_path.stem}_{timestamp}{output_path.suffix}"


def _display_output_path(path: Path) -> Path:
    return path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path


def _build_assessment(
    *,
    summaries: tuple[BacktestSummary, ...],
    aggregate_profit: float,
    latest_summary: BacktestSummary,
    profitable_seasons: list[int],
    active_seasons: list[int],
) -> str:
    _ = summaries
    if active_seasons and len(profitable_seasons) == len(active_seasons):
        return (
            "The current deployable path is positive in every season where it "
            "actually placed bets."
        )
    if latest_summary.profit > 0 and aggregate_profit <= 0:
        return (
            "The current deployable path is positive in the latest season, but "
            "it is still negative across the full window."
        )
    if aggregate_profit > 0:
        return (
            "The current deployable path is positive across the full window, "
            "but season-to-season stability is mixed."
        )
    return "The current deployable path is not yet positive across the full window."


def _format_currency(value: float) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}${abs(value):.2f}"


def _format_pct(value: float) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{abs(value) * 100:.2f}%"


def _format_units(value: float) -> str:
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{abs(value):.2f}u"


def _format_policy(summary: BacktestSummary) -> str:
    if summary.final_policy is None:
        return "`base`"
    max_spread_abs_line = (
        "none"
        if summary.final_policy.max_spread_abs_line is None
        else f"{summary.final_policy.max_spread_abs_line:.1f}"
    )
    parts = [
        "`",
        f"min_edge={summary.final_policy.min_edge:.3f}, ",
        f"min_confidence={summary.final_policy.min_confidence:.3f}, ",
        f"min_probability_edge={summary.final_policy.min_probability_edge:.3f}, ",
        "uncertainty_probability_buffer="
        f"{summary.final_policy.uncertainty_probability_buffer:.4f}, ",
        f"min_games_played={summary.final_policy.min_games_played}, ",
        f"min_positive_ev_books={summary.final_policy.min_positive_ev_books}, ",
        "max_bets_per_day="
        f"{_format_optional_int(summary.final_policy.max_bets_per_day)}, ",
        "min_median_expected_value="
        f"{_format_optional_edge(summary.final_policy.min_median_expected_value)}, ",
        f"max_spread_abs_line={max_spread_abs_line}, ",
        "max_abs_rest_days_diff="
        f"{_format_optional_float(summary.final_policy.max_abs_rest_days_diff)}",
    ]
    parts.append("`")
    return "".join(parts)


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.1f}"


def _format_optional_int(value: int | None) -> str:
    if value is None:
        return "none"
    return str(value)


def _format_optional_edge(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.3f}"


def build_stake_size_summary(
    summaries: tuple[BacktestSummary, ...],
) -> StakeSizeSummary:
    """Return the observed settled-bet stake profile for the report window."""
    stake_amounts = [
        bet.stake_amount
        for summary in summaries
        for bet in summary.placed_bets
        if bet.stake_amount > 0.0
    ]
    if not stake_amounts:
        return StakeSizeSummary()
    return StakeSizeSummary(
        bets=len(stake_amounts),
        average_stake=sum(stake_amounts) / len(stake_amounts),
        median_stake=median(stake_amounts),
        smallest_stake=min(stake_amounts),
        largest_stake=max(stake_amounts),
    )


def _format_stake_profile_compact(summary: StakeSizeSummary) -> str:
    if summary.bets == 0 or summary.median_stake is None:
        return "unavailable"
    return (
        f"typical settled bet `{_format_currency(summary.median_stake)}`; "
        f"smallest `{_format_currency(summary.smallest_stake or 0.0)}`; "
        f"largest `{_format_currency(summary.largest_stake or 0.0)}`"
    )


def _format_stake_profile_verbose(summary: StakeSizeSummary) -> str:
    if summary.bets == 0 or summary.median_stake is None:
        return "unavailable"
    return (
        f"average `{_format_currency(summary.average_stake or 0.0)}`, "
        f"median `{_format_currency(summary.median_stake)}`, "
        f"smallest `{_format_currency(summary.smallest_stake or 0.0)}`, "
        f"largest `{_format_currency(summary.largest_stake or 0.0)}`"
    )


def _build_availability_evaluation_groups(
    *,
    summaries: tuple[BacktestSummary, ...],
    game_side_shadows: tuple[AvailabilityGameSideShadow, ...],
) -> tuple[AvailabilityEvaluationGroup, ...]:
    evaluated_bets = _build_availability_evaluated_bets(
        summaries=summaries,
        game_side_shadows=game_side_shadows,
    )
    if not evaluated_bets:
        return ()

    groups: list[AvailabilityEvaluationGroup] = []
    covered_bets = [
        record for record in evaluated_bets if record.availability is not None
    ]
    fully_covered_bets = [
        record
        for record in covered_bets
        if record.availability is not None
        and record.availability.opponent_has_official_report
    ]
    groups.append(
        AvailabilityEvaluationGroup(
            title="Coverage",
            description=(
                "Coverage compares settled best-path bets against the latest "
                "matched official report for the bet side."
            ),
            slices=tuple(
                slice_summary
                for slice_summary in (
                    _build_availability_evaluation_slice(
                        label="Covered side report",
                        note="Latest matched official report exists for the bet side.",
                        records=covered_bets,
                    ),
                    _build_availability_evaluation_slice(
                        label="Fully covered matchup",
                        note=(
                            "Both team sides had latest matched official reports "
                            "available."
                        ),
                        records=fully_covered_bets,
                    )
                    if covered_bets
                    else None,
                    _build_availability_evaluation_slice(
                        label="Uncovered side report",
                        note="No matched official report exists for the bet side.",
                        records=[
                            record
                            for record in evaluated_bets
                            if record.availability is None
                        ],
                    ),
                )
                if slice_summary is not None
            ),
        )
    )

    status_slices = [
        _build_availability_evaluation_slice(
            label="Side has any out",
            note="Latest matched side report includes at least one `out`.",
            records=[
                record
                for record in covered_bets
                if record.availability is not None and record.availability.team_any_out
            ],
        ),
        _build_availability_evaluation_slice(
            label="Side has any questionable",
            note=(
                "Latest matched side report includes at least one "
                "`questionable`."
            ),
            records=[
                record
                for record in covered_bets
                if (
                    record.availability is not None
                    and record.availability.team_any_questionable
                )
            ],
        ),
        _build_availability_evaluation_slice(
            label="Opponent has any out",
            note="Latest matched opponent report includes at least one `out`.",
            records=[
                record
                for record in fully_covered_bets
                if (
                    record.availability is not None
                    and record.availability.opponent_any_out
                )
            ],
        ),
        _build_availability_evaluation_slice(
            label="Opponent has any questionable",
            note=(
                "Latest matched opponent report includes at least one "
                "`questionable`."
            ),
            records=[
                record
                for record in fully_covered_bets
                if (
                    record.availability is not None
                    and record.availability.opponent_any_questionable
                )
            ],
        ),
    ]
    populated_status_slices = tuple(
        slice_summary for slice_summary in status_slices if slice_summary.bets > 0
    )
    if populated_status_slices:
        groups.append(
            AvailabilityEvaluationGroup(
                title="Status Flags",
                description=(
                    "Status flags use the latest matched official reports only. "
                    "They do not weight player importance or lineup value."
                ),
                slices=populated_status_slices,
            )
        )

    timing_slices = tuple(
        _build_availability_evaluation_slice(
            label=label,
            note=note,
            records=[
                record
                for record in covered_bets
                if (
                    record.availability is not None
                    and _availability_timing_bucket(
                        record.availability.latest_minutes_before_tip
                    )
                    == bucket
                )
            ],
        )
        for bucket, label, note in (
            (
                "0_to_120m",
                "0 to 120 min before tip",
                "Latest matched side update landed within two hours of tip.",
            ),
            (
                "121_to_360m",
                "121 to 360 min before tip",
                (
                    "Latest matched side update landed between two and six "
                    "hours before tip."
                ),
            ),
            (
                "361m_plus",
                "361+ min before tip",
                "Latest matched side update landed more than six hours before tip.",
            ),
            (
                "after_tip",
                "After tip",
                (
                    "Latest matched side update timestamp landed after the "
                    "stored tip time."
                ),
            ),
        )
    )
    populated_timing_slices = tuple(
        slice_summary for slice_summary in timing_slices if slice_summary.bets > 0
    )
    if populated_timing_slices:
        groups.append(
            AvailabilityEvaluationGroup(
                title="Latest Update Timing",
                description=(
                    "Timing buckets use the latest matched side update relative "
                    "to tip when the stored timing fields support it."
                ),
                slices=populated_timing_slices,
            )
        )

    return tuple(groups)


def _build_availability_evaluated_bets(
    *,
    summaries: tuple[BacktestSummary, ...],
    game_side_shadows: tuple[AvailabilityGameSideShadow, ...],
) -> tuple[AvailabilityEvaluatedBet, ...]:
    shadows_by_scope = {
        (shadow.game_id, shadow.side): shadow for shadow in game_side_shadows
    }
    evaluated_bets: list[AvailabilityEvaluatedBet] = []
    for summary in summaries:
        clv_by_scope = {
            (observation.game_id, observation.market, observation.side): observation
            for observation in summary.clv_observations
            if observation.game_id is not None and observation.side is not None
        }
        for bet in summary.placed_bets:
            if bet.settlement not in {"win", "loss", "push"}:
                continue
            evaluated_bets.append(
                AvailabilityEvaluatedBet(
                    evaluation_season=summary.evaluation_season,
                    bet=bet,
                    clv_observation=clv_by_scope.get(
                        (bet.game_id, bet.market, bet.side)
                    ),
                    availability=shadows_by_scope.get((bet.game_id, bet.side)),
                )
            )
    return tuple(evaluated_bets)


def _build_availability_evaluation_slice(
    *,
    label: str,
    note: str,
    records: list[AvailabilityEvaluatedBet],
) -> AvailabilityEvaluationSlice:
    wins = sum(1 for record in records if record.bet.settlement == "win")
    losses = sum(1 for record in records if record.bet.settlement == "loss")
    pushes = sum(1 for record in records if record.bet.settlement == "push")
    clv = summarize_closing_line_value(
        [
            record.clv_observation
            for record in records
            if record.clv_observation is not None
        ]
    )
    if not records:
        return AvailabilityEvaluationSlice(
            label=label,
            bets=0,
            wins=0,
            losses=0,
            pushes=0,
            profit=None,
            roi=None,
            clv=ClosingLineValueSummary(),
            note=f"{note} No settled best-path bets landed in this slice.",
            insufficient_sample=True,
        )

    if len(records) < MIN_AVAILABILITY_SLICE_BETS:
        return AvailabilityEvaluationSlice(
            label=label,
            bets=len(records),
            wins=wins,
            losses=losses,
            pushes=pushes,
            profit=None,
            roi=None,
            clv=ClosingLineValueSummary(),
            note=(
                f"{note} Insufficient sample below "
                f"{MIN_AVAILABILITY_SLICE_BETS} settled bets."
            ),
            insufficient_sample=True,
        )

    total_staked = sum(record.bet.stake_amount for record in records)
    profit = sum(settle_bet(record.bet) for record in records)
    roi = profit / total_staked if total_staked > 0 else None
    return AvailabilityEvaluationSlice(
        label=label,
        bets=len(records),
        wins=wins,
        losses=losses,
        pushes=pushes,
        profit=profit,
        roi=roi,
        clv=clv,
        note=note,
        insufficient_sample=False,
    )


def _render_availability_evaluation_groups(
    groups: tuple[AvailabilityEvaluationGroup, ...],
) -> list[str]:
    lines: list[str] = []
    for group in groups:
        lines.extend(
            [
                f"### {group.title}",
                "",
                group.description,
                "",
                "| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |",
                "| --- | ---: | --- | ---: | ---: | --- | --- |",
            ]
        )
        lines.extend(
            (
                f"| {slice_summary.label} | {slice_summary.bets} | "
                f"{slice_summary.wins}-{slice_summary.losses}-{slice_summary.pushes} | "
                f"{_format_availability_slice_profit(slice_summary)} | "
                f"{_format_availability_slice_roi(slice_summary)} | "
                f"{_format_availability_slice_clv(slice_summary)} | "
                f"{slice_summary.note} |"
            )
            for slice_summary in group.slices
        )
        lines.extend([""])
    return lines


def _availability_timing_bucket(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 0:
        return "after_tip"
    if value <= 120:
        return "0_to_120m"
    if value <= 360:
        return "121_to_360m"
    return "361m_plus"


def _format_availability_slice_profit(
    slice_summary: AvailabilityEvaluationSlice,
) -> str:
    if slice_summary.profit is None:
        return "`insufficient sample`"
    return _format_currency(slice_summary.profit)


def _format_availability_slice_roi(
    slice_summary: AvailabilityEvaluationSlice,
) -> str:
    if slice_summary.roi is None:
        return "`insufficient sample`"
    return _format_pct(slice_summary.roi)


def _format_availability_slice_clv(
    slice_summary: AvailabilityEvaluationSlice,
) -> str:
    if slice_summary.insufficient_sample:
        return "`insufficient sample`"
    return _format_clv_summary(slice_summary.clv)


def _format_availability_shadow_compact_summary(
    summary: AvailabilityShadowSummary,
) -> str:
    if not summary.has_data:
        return (
            "No official availability shadow data is currently loaded. This "
            "diagnostic lane is still separate from live and backtest outputs."
        )
    compact_parts = [
        f"`{summary.games_covered}` games",
        f"`{summary.player_rows_loaded}` status rows",
    ]
    if summary.unmatched_player_rows is not None:
        compact_parts.append(f"`{summary.unmatched_player_rows}` unmatched")
    timing_summary = _format_availability_shadow_timing(summary)
    compact_text = ", ".join(compact_parts)
    if timing_summary is None:
        return (
            f"Shadow-only coverage is stored for {compact_text}. "
            "It is not consumed by the live or backtest model paths yet."
        )
    return (
        f"Shadow-only coverage is stored for {compact_text}; "
        f"{timing_summary}. It is not consumed by the live or backtest model "
        "paths yet."
    )


def _render_availability_shadow_rows(
    summary: AvailabilityShadowSummary,
) -> list[str]:
    if not summary.has_data:
        return [
            (
                "| Shadow data | `not loaded` | "
                "No official availability reports are stored yet. |"
            )
        ]

    rows = [
        (
            f"| Official reports | `{summary.reports_loaded}` | "
            "Stored raw report snapshots from the availability import lane. |"
        ),
        (
            f"| Player status rows | `{summary.player_rows_loaded}` | "
            "Parsed player-level status records stored for shadow analysis. |"
        ),
        (
            f"| Covered games | `{summary.games_covered}` | "
            "Distinct matched games represented in the stored reports. |"
        ),
        (
            f"| Matched rows | "
            f"{_format_optional_shadow_int(summary.matched_player_rows)} | "
            "Rows linked to a repo team/game scope when matching columns exist. |"
        ),
        (
            f"| Unmatched rows | "
            f"{_format_optional_shadow_int(summary.unmatched_player_rows)} | "
            "Imported rows still unmatched after normalization. |"
        ),
        (
            f"| Latest update | `{summary.latest_update_at or 'n/a'}` | "
            f"{_availability_shadow_notes(summary)} |"
        ),
        (
            f"| Seasons | {_format_shadow_label_list(summary.seasons)} | "
            "Distinct seasons represented in stored official reports. |"
        ),
        (
            f"| Scope | {_format_shadow_label_list(summary.scope_labels)} | "
            "Stored season / tournament scope labels when present. |"
        ),
        (
            f"| Source | {_format_shadow_label_list(summary.source_labels)} | "
            "Distinct upstream source labels recorded with the reports. |"
        ),
        (
            f"| Status mix | {_format_shadow_status_counts(summary)} | "
            "Top stored player-status values across imported rows. |"
        ),
    ]
    return rows


def _format_optional_shadow_int(value: int | None) -> str:
    if value is None:
        return "`n/a`"
    return f"`{value}`"


def _format_shadow_label_list(values: Sequence[object]) -> str:
    if not values:
        return "`n/a`"
    return ", ".join(f"`{value}`" for value in values)


def _format_shadow_status_counts(summary: AvailabilityShadowSummary) -> str:
    if not summary.status_counts:
        return "`n/a`"
    return ", ".join(
        f"`{status.status}` {status.row_count}" for status in summary.status_counts
    )


def _format_availability_shadow_timing(
    summary: AvailabilityShadowSummary,
) -> str | None:
    if summary.latest_minutes_before_tip is not None:
        return (
            f"latest stored update was "
            f"`{_format_minutes_before_tip(summary.latest_minutes_before_tip)}`"
        )
    if summary.average_minutes_before_tip is not None:
        return (
            f"average stored update timing was "
            f"`{_format_minutes_before_tip(summary.average_minutes_before_tip)}`"
        )
    return None


def _availability_shadow_notes(summary: AvailabilityShadowSummary) -> str:
    return (
        _format_availability_shadow_timing(summary)
        or "Tip-relative timing is not yet available."
    )


def _format_minutes_before_tip(value: float) -> str:
    if value < 0:
        return f"{abs(value):.0f} min after tip"
    return f"{value:.0f} min before tip"


def _count_market_bets(summary: BacktestSummary, *, market: str) -> int:
    placed_market_bets = sum(1 for bet in summary.placed_bets if bet.market == market)
    if placed_market_bets > 0:
        return placed_market_bets
    if market == "spread":
        return max(
            summary.clv.spread_bets_evaluated,
            summary.clv.spread_price_bets_evaluated,
            summary.clv.spread_no_vig_bets_evaluated,
            summary.clv.spread_closing_ev_bets_evaluated,
        )
    return summary.clv.moneyline_bets_evaluated


def _combine_clv_summaries(
    summaries: tuple[BacktestSummary, ...] | list[BacktestSummary],
) -> ClosingLineValueSummary:
    return _combine_clv_summary_values([summary.clv for summary in summaries])


def _combine_clv_summary_values(
    summaries: Sequence[ClosingLineValueSummary],
) -> ClosingLineValueSummary:
    return ClosingLineValueSummary(
        bets_evaluated=sum(summary.bets_evaluated for summary in summaries),
        positive_bets=sum(summary.positive_bets for summary in summaries),
        negative_bets=sum(summary.negative_bets for summary in summaries),
        neutral_bets=sum(summary.neutral_bets for summary in summaries),
        spread_bets_evaluated=sum(
            summary.spread_bets_evaluated for summary in summaries
        ),
        total_spread_line_delta=sum(
            summary.total_spread_line_delta for summary in summaries
        ),
        spread_price_bets_evaluated=sum(
            summary.spread_price_bets_evaluated for summary in summaries
        ),
        total_spread_price_probability_delta=sum(
            summary.total_spread_price_probability_delta for summary in summaries
        ),
        spread_no_vig_bets_evaluated=sum(
            summary.spread_no_vig_bets_evaluated for summary in summaries
        ),
        total_spread_no_vig_probability_delta=sum(
            summary.total_spread_no_vig_probability_delta for summary in summaries
        ),
        spread_closing_ev_bets_evaluated=sum(
            summary.spread_closing_ev_bets_evaluated for summary in summaries
        ),
        total_spread_closing_expected_value=sum(
            summary.total_spread_closing_expected_value for summary in summaries
        ),
        moneyline_bets_evaluated=sum(
            summary.moneyline_bets_evaluated for summary in summaries
        ),
        total_moneyline_probability_delta=sum(
            summary.total_moneyline_probability_delta for summary in summaries
        ),
    )


def _combine_spread_segment_attributions(
    summaries: tuple[BacktestSummary, ...] | list[BacktestSummary],
) -> tuple[SpreadSegmentAttribution, ...]:
    grouped: dict[str, dict[str, list[SpreadSegmentSummary]]] = {}
    for summary in summaries:
        for dimension_summary in summary.spread_segment_attribution:
            for segment_summary in dimension_summary.segments:
                grouped.setdefault(dimension_summary.dimension, {}).setdefault(
                    segment_summary.value, []
                ).append(segment_summary)

    combined: list[SpreadSegmentAttribution] = []
    for dimension, segment_groups in grouped.items():
        total_dimension_bets = sum(
            segment_summary.bets
            for segment_summaries in segment_groups.values()
            for segment_summary in segment_summaries
        )
        segments: list[SpreadSegmentSummary] = []
        for value, segment_summaries in segment_groups.items():
            bets = sum(segment_summary.bets for segment_summary in segment_summaries)
            total_staked = sum(
                segment_summary.total_staked for segment_summary in segment_summaries
            )
            profit = sum(
                segment_summary.profit for segment_summary in segment_summaries
            )
            segments.append(
                SpreadSegmentSummary(
                    value=value,
                    bets=bets,
                    total_staked=total_staked,
                    profit=profit,
                    roi=profit / total_staked if total_staked > 0 else 0.0,
                    share_of_bets=bets / float(total_dimension_bets)
                    if total_dimension_bets > 0
                    else 0.0,
                    clv=_combine_clv_summary_values(
                        [segment_summary.clv for segment_summary in segment_summaries]
                    ),
                )
            )
        combined.append(
            SpreadSegmentAttribution(
                dimension=dimension,
                segments=tuple(
                    sorted(
                        segments,
                        key=lambda item: (
                            item.clv.average_spread_closing_expected_value
                            if (
                                item.clv.average_spread_closing_expected_value
                                is not None
                            )
                            else float("inf"),
                            item.roi,
                            -item.bets,
                            item.value,
                        ),
                    )
                ),
            )
        )
    return tuple(combined)


def _render_spread_segment_attribution(
    dimension_summary: SpreadSegmentAttribution,
) -> list[str]:
    lines = [
        f"### {_format_segment_dimension(dimension_summary.dimension)}",
        "",
        "| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        (
            f"| `{_format_segment_value(segment_summary.value)}` | "
            f"{segment_summary.bets} | "
            f"{_format_pct(segment_summary.share_of_bets)} | "
            f"{_format_currency(segment_summary.profit)} | "
            f"{_format_pct(segment_summary.roi)} | "
            f"{_format_spread_closing_ev(segment_summary.clv)} |"
        )
        for segment_summary in dimension_summary.segments
    )
    lines.append("")
    return lines


def _format_segment_dimension(value: str) -> str:
    labels = {
        "expected_value_bucket": "Expected Value Bucket",
        "probability_edge_bucket": "Probability Edge Bucket",
        "season_phase": "Season Phase",
        "line_bucket": "Line Bucket",
        "book_depth": "Book Depth",
        "same_conference": "Conference Matchup",
        "conference_group": "Conference Group",
        "tip_window": "Tip Window",
    }
    return labels.get(value, value.replace("_", " ").title())


def _format_segment_value(value: str) -> str:
    labels = {
        "ev_below_4": "Below 4%",
        "ev_4_to_6": "4% to 6%",
        "ev_6_to_8": "6% to 8%",
        "ev_8_to_10": "8% to 10%",
        "ev_10_plus": "10%+",
        "edge_below_4": "Below 4%",
        "edge_4_to_6": "4% to 6%",
        "edge_6_to_8": "6% to 8%",
        "edge_8_to_10": "8% to 10%",
        "edge_10_plus": "10%+",
        "same_conference": "Same Conference",
        "nonconference": "Non-Conference",
        "priced_range": "Priced Range",
        "long_line": "Long Line",
        "low_depth": "Low Depth",
        "mid_depth": "Mid Depth",
        "high_depth": "High Depth",
        "mid_major": "Mid-Major",
        "0_to_6h": "0 to 6h",
        "6_to_12h": "6 to 12h",
        "12_to_24h": "12 to 24h",
        "24_to_48h": "24 to 48h",
        "48h_plus": "48h+",
    }
    return labels.get(value, value.replace("_", " ").title())


def _format_clv_summary(summary: ClosingLineValueSummary) -> str:
    if summary.bets_evaluated == 0:
        return "`none tracked`"
    parts = [
        f"`{summary.positive_bets}/{summary.bets_evaluated}` positive",
        f"`{_format_pct(summary.positive_rate)}`",
    ]
    if summary.average_spread_line_delta is not None:
        parts.append(f"`{_format_spread_clv(summary)}` spread line")
    if summary.average_spread_price_probability_delta is not None:
        parts.append(f"`{_format_spread_price_clv(summary)}` spread price")
    if summary.average_spread_no_vig_probability_delta is not None:
        parts.append(f"`{_format_spread_no_vig_clv(summary)}` spread no-vig")
    if summary.average_spread_closing_expected_value is not None:
        parts.append(f"`{_format_spread_closing_ev(summary)}` spread close EV")
    if summary.average_moneyline_probability_delta is not None:
        parts.append(f"`{_format_moneyline_clv(summary)}` moneyline")
    return ", ".join(parts)


def _build_decision_evidence(
    *,
    aggregate_clv: ClosingLineValueSummary,
    total_profit: float,
    total_bets: int,
) -> str:
    if (
        aggregate_clv.average_spread_price_probability_delta is not None
        and aggregate_clv.average_spread_closing_expected_value is not None
    ):
        return (
            "aggregate spread price CLV "
            f"`{_format_spread_price_clv(aggregate_clv)}` and spread close EV "
            f"`{_format_spread_closing_ev(aggregate_clv)}` remain positive."
        )
    if total_bets > 0:
        return (
            f"the report window is `{_format_currency(total_profit)}` on "
            f"`{total_bets}` placed bets."
        )
    return "the report still has no settled bets to evaluate."


def _build_decision_risk(
    *,
    worst_summary: BacktestSummary,
    profitable_seasons: list[int],
    active_seasons: list[int],
) -> str:
    if not active_seasons:
        return "no active seasons placed bets in the selected window."
    if len(profitable_seasons) == len(active_seasons):
        return "there are no losing active seasons in the current window."
    return (
        f"season stability is mixed; `{worst_summary.evaluation_season}` is the "
        f"weakest season at `{_format_currency(worst_summary.profit)}`."
    )


def _build_decision_next_action(*, aggregate_profit: float) -> str:
    if aggregate_profit > 0:
        return (
            "verify the close-market coverage table before promoting new "
            "structural model changes."
        )
    return (
        "do not promote new defaults until the weakest season and close-market "
        "coverage are understood."
    )


def _format_close_coverage_summary(
    summary: ClosingLineValueSummary,
    total_spread_bets: int,
    total_moneyline_bets: int,
) -> str:
    parts: list[str] = []
    if total_spread_bets > 0:
        parts.append(
            "spread close EV "
            f"`{summary.spread_closing_ev_bets_evaluated}/{total_spread_bets}`"
        )
    if total_moneyline_bets > 0:
        parts.append(
            "moneyline close probability "
            f"`{summary.moneyline_bets_evaluated}/{total_moneyline_bets}`"
        )
    if not parts:
        return "`none tracked`"
    return ", ".join(parts)


def _render_close_coverage_rows(
    *,
    aggregate_clv: ClosingLineValueSummary,
    total_spread_bets: int,
    total_moneyline_bets: int,
) -> list[str]:
    rows: list[tuple[str, int, int, str]] = []
    if total_spread_bets > 0:
        rows.extend(
            [
                (
                    "Spread line CLV",
                    aggregate_clv.spread_bets_evaluated,
                    max(total_spread_bets - aggregate_clv.spread_bets_evaluated, 0),
                    "Missing when no closing spread line can be matched.",
                ),
                (
                    "Spread price CLV",
                    aggregate_clv.spread_price_bets_evaluated,
                    max(
                        total_spread_bets - aggregate_clv.spread_price_bets_evaluated,
                        0,
                    ),
                    "Tracks executable price movement against the stored close.",
                ),
                (
                    "Spread no-vig close delta",
                    aggregate_clv.spread_no_vig_bets_evaluated,
                    max(
                        total_spread_bets - aggregate_clv.spread_no_vig_bets_evaluated,
                        0,
                    ),
                    "Uses the stored closing consensus after removing vig.",
                ),
                (
                    "Spread closing EV",
                    aggregate_clv.spread_closing_ev_bets_evaluated,
                    max(
                        total_spread_bets
                        - aggregate_clv.spread_closing_ev_bets_evaluated,
                        0,
                    ),
                    "Most direct execution-quality check for qualified spread bets.",
                ),
            ]
        )
    if total_moneyline_bets > 0:
        rows.append(
            (
                "Moneyline close probability",
                aggregate_clv.moneyline_bets_evaluated,
                max(total_moneyline_bets - aggregate_clv.moneyline_bets_evaluated, 0),
                "Uses normalized implied probability at the stored moneyline close.",
            )
        )
    if not rows:
        return ["| `none` | 0/0 | 0 | No close-market observations were tracked. |"]
    return [
        (
            f"| {label} | {_format_tracked_coverage(tracked, tracked + missing)} | "
            f"{_format_missing_coverage(missing, tracked + missing)} | {note} |"
        )
        for label, tracked, missing, note in rows
    ]


def _format_tracked_coverage(tracked: int, total: int) -> str:
    if total <= 0:
        return "0/0"
    return f"{tracked}/{total} ({_format_pct(tracked / total)})"


def _format_missing_coverage(missing: int, total: int) -> str:
    if total <= 0:
        return "0/0"
    return f"{missing}/{total} ({_format_pct(missing / total)})"


def _format_spread_clv(summary: ClosingLineValueSummary) -> str:
    if summary.average_spread_line_delta is None:
        return "none"
    value = summary.average_spread_line_delta
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{abs(value):.2f} pts"


def _format_moneyline_clv(summary: ClosingLineValueSummary) -> str:
    if summary.average_moneyline_probability_delta is None:
        return "none"
    value = summary.average_moneyline_probability_delta * 100.0
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{abs(value):.2f} pp"


def _format_spread_price_clv(summary: ClosingLineValueSummary) -> str:
    if summary.average_spread_price_probability_delta is None:
        return "none"
    value = summary.average_spread_price_probability_delta * 100.0
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{abs(value):.2f} pp"


def _format_spread_no_vig_clv(summary: ClosingLineValueSummary) -> str:
    if summary.average_spread_no_vig_probability_delta is None:
        return "none"
    value = summary.average_spread_no_vig_probability_delta * 100.0
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{abs(value):.2f} pp"


def _format_spread_closing_ev(summary: ClosingLineValueSummary) -> str:
    if summary.average_spread_closing_expected_value is None:
        return "none"
    value = summary.average_spread_closing_expected_value
    sign = "+" if value > 0 else "-" if value < 0 else ""
    return f"{sign}{abs(value):.3f}"
