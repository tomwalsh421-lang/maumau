# Best Model Backtest Report

Generated: `2026-03-09T19:17:21-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260309_191721.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `disabled`
- Spread model family: `logistic`
- Seasons: `2024`, `2025`, `2026`
- Starting bankroll: `+$1000.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Assessment

The current deployable path is positive across the full window, but season-to-season stability is mixed.

- Aggregate result: `+$78.80` on `149` bets, ROI `+10.12%`
- Latest season `2026`: `+$25.58`, ROI `+72.50%`
- Best season: `2024` with `+$53.83`
- Worst season: `2025` with `-$0.61`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `2024` | 138 | +$53.83 | +7.31% | +2.15u | +3.90% | 73-63-2 | `min_edge=0.027, min_confidence=0.518, min_probability_edge=0.025, min_games_played=4, max_spread_abs_line=10.0` |
| `2025` | 2 | -$0.61 | -8.27% | -0.02u | +0.39% | 1-1-0 | `min_edge=0.027, min_confidence=0.518, min_probability_edge=0.025, min_games_played=4, max_spread_abs_line=10.0` |
| `2026` | 9 | +$25.58 | +72.50% | +1.02u | +0.36% | 8-1-0 | `min_edge=0.027, min_confidence=0.518, min_probability_edge=0.025, min_games_played=4, max_spread_abs_line=10.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 149 | +$78.80 | +10.12% | +3.15u | +3.90% | 2/3 |

## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
