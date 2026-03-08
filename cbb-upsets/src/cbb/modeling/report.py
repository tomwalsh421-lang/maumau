"""Markdown reporting for walk-forward best-model backtests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
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
    backtest_betting_model,
)
from cbb.modeling.dataset import get_available_seasons
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
    auto_tune_spread_policy: bool = True
    spread_model_family: ModelFamily = DEFAULT_SPREAD_MODEL_FAMILY
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
                spread_model_family=options.spread_model_family,
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
    spread_model_family: ModelFamily,
) -> str:
    """Render the best-model report Markdown."""
    total_bets = sum(summary.bets_placed for summary in summaries)
    total_profit = sum(summary.profit for summary in summaries)
    total_staked = sum(summary.total_staked for summary in summaries)
    total_units = sum(summary.units_won for summary in summaries)
    aggregate_roi = total_profit / total_staked if total_staked > 0 else 0.0
    max_drawdown = max((summary.max_drawdown for summary in summaries), default=0.0)
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
        (
            f"- Latest season `{latest_summary.evaluation_season}`: "
            f"`{_format_currency(latest_summary.profit)}`, "
            f"ROI `{_format_pct(latest_summary.roi)}`"
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
            "Wins-Losses-Pushes | Final Policy |"
        ),
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    lines.extend(
        (
            f"| `{summary.evaluation_season}` | {summary.bets_placed} | "
            f"{_format_currency(summary.profit)} | {_format_pct(summary.roi)} | "
            f"{_format_units(summary.units_won)} | "
            f"{_format_pct(summary.max_drawdown)} | "
            f"{summary.wins}-{summary.losses}-{summary.pushes} | "
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
            "## Notes",
            "",
            (
                "- `best` is the current deployable spread-first path. "
                "When spread can train, it is preferred over moneyline."
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
        f"min_probability_edge={summary.final_policy.min_probability_edge:.3f}, "
        f"min_games_played={summary.final_policy.min_games_played}, "
        f"max_spread_abs_line={max_spread_abs_line}"
        "`"
    )
