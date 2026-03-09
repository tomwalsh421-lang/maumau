# Best Model Backtest Report

Generated: `2026-03-08T21:02:32-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260308_210232.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `enabled`
- Spread model family: `logistic`
- Seasons: `2024`, `2025`, `2026`
- Starting bankroll: `+$1000.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Assessment

The current deployable path is positive in the latest season, but it is still negative across the full window.

- Aggregate result: `-$45.28` on `302` bets, ROI `-3.14%`
- Latest season `2026`: `+$15.19`, ROI `+4.68%`
- Best season: `2026` with `+$15.19`
- Worst season: `2025` with `-$34.23`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `2024` | 89 | -$26.24 | -8.52% | -1.05u | +3.48% | 41-45-3 | `min_edge=0.030, min_probability_edge=0.025, min_games_played=4, max_spread_abs_line=10.0` |
| `2025` | 119 | -$34.23 | -4.22% | -1.37u | +6.95% | 74-45-0 | `min_edge=0.030, min_probability_edge=0.025, min_games_played=4, max_spread_abs_line=10.0` |
| `2026` | 94 | +$15.19 | +4.68% | +0.61u | +4.29% | 54-40-0 | `base` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 302 | -$45.28 | -3.14% | -1.81u | +6.95% | 1/3 |

## Notes

- `best` is the current deployable spread-first path. When spread can train, it is preferred over moneyline.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
