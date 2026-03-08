# Best Model Backtest Report

Generated: `2026-03-08T17:14:53-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260308_171453.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `enabled`
- Seasons: `2024`, `2025`, `2026`
- Starting bankroll: `+$1000.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Assessment

The current deployable path is positive in the latest season, but it is still negative across the full window.

- Aggregate result: `-$35.19` on `136` bets, ROI `-4.44%`
- Latest season `2026`: `+$10.67`, ROI `+17.75%`
- Best season: `2026` with `+$10.67`
- Worst season: `2024` with `-$45.85`
- Zero-bet seasons: `2025`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `2024` | 115 | -$45.85 | -6.26% | -1.83u | +7.46% | 54-60-1 | `min_edge=0.020, min_probability_edge=0.025, min_games_played=12, max_spread_abs_line=none` |
| `2025` | 0 | $0.00 | 0.00% | 0.00u | 0.00% | 0-0-0 | `min_edge=0.020, min_probability_edge=0.025, min_games_played=12, max_spread_abs_line=none` |
| `2026` | 21 | +$10.67 | +17.75% | +0.43u | +1.39% | 13-8-0 | `min_edge=0.020, min_probability_edge=0.015, min_games_played=8, max_spread_abs_line=10.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 136 | -$35.19 | -4.44% | -1.41u | +7.46% | 1/2 |

## Notes

- `best` is the current deployable spread-first path. When spread can train, it is preferred over moneyline.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
