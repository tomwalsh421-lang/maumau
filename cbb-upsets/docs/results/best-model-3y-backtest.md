# Best Model Backtest Report

Generated: `2026-03-08T20:09:57-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260308_200957.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `enabled`
- Spread model family: `logistic`
- Seasons: `2024`, `2025`, `2026`
- Starting bankroll: `+$1000.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Assessment

The current deployable path is not yet positive across the full window.

- Aggregate result: `-$73.39` on `312` bets, ROI `-5.07%`
- Latest season `2026`: `-$12.92`, ROI `-3.92%`
- Best season: `2026` with `-$12.92`
- Worst season: `2025` with `-$34.23`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `2024` | 89 | -$26.24 | -8.52% | -1.05u | +3.48% | 41-45-3 | `min_edge=0.030, min_probability_edge=0.025, min_games_played=4, max_spread_abs_line=10.0` |
| `2025` | 119 | -$34.23 | -4.22% | -1.37u | +6.95% | 74-45-0 | `min_edge=0.030, min_probability_edge=0.025, min_games_played=4, max_spread_abs_line=10.0` |
| `2026` | 104 | -$12.92 | -3.92% | -0.52u | +3.80% | 56-48-0 | `min_edge=0.020, min_probability_edge=0.025, min_games_played=8, max_spread_abs_line=25.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 312 | -$73.39 | -5.07% | -2.94u | +6.95% | 0/3 |

## Notes

- `best` is the current deployable spread-first path. When spread can train, it is preferred over moneyline.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
