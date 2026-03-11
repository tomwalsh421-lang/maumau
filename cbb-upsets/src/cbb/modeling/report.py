"""Markdown reporting for walk-forward best-model backtests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cbb.db import REPO_ROOT
from cbb.modeling.artifacts import ModelFamily
from cbb.modeling.backtest import (
    DEFAULT_BACKTEST_RETRAIN_DAYS,
    DEFAULT_STARTING_BANKROLL,
    DEFAULT_UNIT_SIZE,
    BacktestOptions,
    BacktestSummary,
    ClosingLineValueSummary,
    backtest_betting_model,
)
from cbb.modeling.dataset import get_available_seasons
from cbb.modeling.policy import BetPolicy
from cbb.modeling.train import DEFAULT_SPREAD_MODEL_FAMILY

DEFAULT_BEST_BACKTEST_REPORT_PATH = (
    REPO_ROOT / "docs" / "results" / "best-model-3y-backtest.md"
)


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
    aggregate_clv: ClosingLineValueSummary = ClosingLineValueSummary()


def generate_best_backtest_report(
    options: BestBacktestReportOptions,
    *,
    progress: Callable[[str], None] | None = None,
) -> BestBacktestReport:
    """Backtest the current best model and write a Markdown report."""
    if options.seasons < 1:
        raise ValueError("seasons must be at least 1")

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
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    if history_output_path is not None:
        history_output_path.parent.mkdir(parents=True, exist_ok=True)
        history_output_path.write_text(markdown, encoding="utf-8")
    return BestBacktestReport(
        output_path=output_path,
        history_output_path=history_output_path,
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
    )


def render_best_backtest_report(
    *,
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
) -> str:
    """Render the best-model report Markdown."""
    total_bets = sum(summary.bets_placed for summary in summaries)
    total_profit = sum(summary.profit for summary in summaries)
    total_staked = sum(summary.total_staked for summary in summaries)
    total_units = sum(summary.units_won for summary in summaries)
    aggregate_roi = total_profit / total_staked if total_staked > 0 else 0.0
    max_drawdown = max((summary.max_drawdown for summary in summaries), default=0.0)
    aggregate_clv = _combine_clv_summaries(summaries)
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

    lines = [
        "# Best Model Backtest Report",
        "",
        f"Generated: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
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
        "## Assessment",
        "",
        _build_assessment(
            summaries=summaries,
            aggregate_profit=total_profit,
            latest_summary=latest_summary,
            profitable_seasons=profitable_seasons,
            active_seasons=active_seasons,
        ),
        "",
        (
            f"- Aggregate result: `{_format_currency(total_profit)}` on "
            f"`{total_bets}` bets, ROI `{_format_pct(aggregate_roi)}`"
        ),
        f"- Aggregate CLV: {_format_clv_summary(aggregate_clv)}",
        (
            f"- Latest season `{latest_summary.evaluation_season}`: "
            f"`{_format_currency(latest_summary.profit)}`, "
            f"ROI `{_format_pct(latest_summary.roi)}`"
        ),
        (
            f"- Latest season CLV: "
            f"{_format_clv_summary(latest_summary.clv)}"
        ),
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
    return (
        "`"
        f"min_edge={summary.final_policy.min_edge:.3f}, "
        f"min_confidence={summary.final_policy.min_confidence:.3f}, "
        f"min_probability_edge={summary.final_policy.min_probability_edge:.3f}, "
        f"min_games_played={summary.final_policy.min_games_played}, "
        f"min_positive_ev_books={summary.final_policy.min_positive_ev_books}, "
        "min_median_expected_value="
        f"{_format_optional_edge(summary.final_policy.min_median_expected_value)}, "
        f"max_spread_abs_line={max_spread_abs_line}, "
        "max_abs_rest_days_diff="
        f"{_format_optional_float(summary.final_policy.max_abs_rest_days_diff)}"
        "`"
    )


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.1f}"


def _format_optional_edge(value: float | None) -> str:
    if value is None:
        return "none"
    return f"{value:.3f}"


def _combine_clv_summaries(
    summaries: tuple[BacktestSummary, ...] | list[BacktestSummary],
) -> ClosingLineValueSummary:
    return ClosingLineValueSummary(
        bets_evaluated=sum(summary.clv.bets_evaluated for summary in summaries),
        positive_bets=sum(summary.clv.positive_bets for summary in summaries),
        negative_bets=sum(summary.clv.negative_bets for summary in summaries),
        neutral_bets=sum(summary.clv.neutral_bets for summary in summaries),
        spread_bets_evaluated=sum(
            summary.clv.spread_bets_evaluated for summary in summaries
        ),
        total_spread_line_delta=sum(
            summary.clv.total_spread_line_delta for summary in summaries
        ),
        spread_price_bets_evaluated=sum(
            summary.clv.spread_price_bets_evaluated for summary in summaries
        ),
        total_spread_price_probability_delta=sum(
            summary.clv.total_spread_price_probability_delta
            for summary in summaries
        ),
        spread_no_vig_bets_evaluated=sum(
            summary.clv.spread_no_vig_bets_evaluated for summary in summaries
        ),
        total_spread_no_vig_probability_delta=sum(
            summary.clv.total_spread_no_vig_probability_delta
            for summary in summaries
        ),
        spread_closing_ev_bets_evaluated=sum(
            summary.clv.spread_closing_ev_bets_evaluated
            for summary in summaries
        ),
        total_spread_closing_expected_value=sum(
            summary.clv.total_spread_closing_expected_value
            for summary in summaries
        ),
        moneyline_bets_evaluated=sum(
            summary.clv.moneyline_bets_evaluated for summary in summaries
        ),
        total_moneyline_probability_delta=sum(
            summary.clv.total_moneyline_probability_delta for summary in summaries
        ),
    )


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
