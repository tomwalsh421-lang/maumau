# Best Model Backtest Report

Generated: `2026-03-11T10:14:00-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260311_101400.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `disabled`
- Timing layer: `disabled`
- Spread model family: `logistic`
- Seasons: `2024`, `2025`, `2026`
- Starting bankroll: `+$1000.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Assessment

The current deployable path is positive across the full window, but season-to-season stability is mixed.

- Aggregate result: `+$247.12` on `633` bets, ROI `+5.80%`
- Aggregate CLV: `80/633` positive, `+12.64%`, `-0.45 pts` spread line, `+1.87 pp` spread price, `+1.57 pp` spread no-vig, `+0.080` spread close EV
- Latest season `2026`: `+$124.91`, ROI `+8.27%`
- Latest season CLV: `14/219` positive, `+6.39%`, `-0.55 pts` spread line, `+2.01 pp` spread price, `+1.68 pp` spread no-vig, `+0.092` spread close EV
- Best season: `2025` with `+$234.58`
- Worst season: `2024` with `-$112.38`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 195 | -$112.38 | -9.85% | -4.50u | +13.38% | 87-107-1 | `37/195` positive, `+18.97%`, `-0.38 pts` spread line, `+1.74 pp` spread price, `+1.49 pp` spread no-vig, `+0.052` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 219 | +$234.58 | +14.56% | +9.38u | +9.51% | 126-92-1 | `29/219` positive, `+13.24%`, `-0.40 pts` spread line, `+1.84 pp` spread price, `+1.52 pp` spread no-vig, `+0.092` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 219 | +$124.91 | +8.27% | +5.00u | +8.56% | 121-98-0 | `14/219` positive, `+6.39%`, `-0.55 pts` spread line, `+2.01 pp` spread price, `+1.68 pp` spread no-vig, `+0.092` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 633 | +$247.12 | +5.80% | +9.88u | +13.38% | 2/3 |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 195 | 37 | 13 | 145 | +18.97% | -0.38 pts | +1.74 pp | +1.49 pp | +0.052 | none |
| `2025` | 219 | 29 | 15 | 175 | +13.24% | -0.40 pts | +1.84 pp | +1.52 pp | +0.092 | none |
| `2026` | 219 | 14 | 11 | 194 | +6.39% | -0.55 pts | +2.01 pp | +1.68 pp | +0.092 | none |
| Aggregate | 633 | 80 | 39 | 514 | +12.64% | -0.45 pts | +1.87 pp | +1.57 pp | +0.080 | none |

## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- When the timing layer is enabled, spread bets are evaluated from a six-hour pre-tip snapshot and only early bets with favorable predicted closing-line movement are kept.
- CLV is measured against the stored closing consensus. Spread now tracks line delta, raw price delta, no-vig close delta, and model EV at the close quote; moneyline tracks normalized implied-probability delta.
- The positive/neutral/negative CLV counts still use spread line movement for spread bets and no-vig close delta for moneyline bets. The added spread price and close-EV columns are supplemental execution measurements.
- When a backtest scores the closing snapshot itself, spread line CLV should be near-neutral, but price CLV and closing EV can still move because the executable quote and the stored close consensus are not always identical.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
