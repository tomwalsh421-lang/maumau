# Best Model Backtest Report

Generated: `2026-03-11T09:36:57-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260311_093657.md`

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

- Aggregate result: `+$175.49` on `689` bets, ROI `+3.66%`
- Aggregate CLV: `95/689` positive, `+13.79%`, `-0.41 pts` spread line, `+1.79 pp` spread price, `+1.49 pp` spread no-vig, `+0.073` spread close EV
- Latest season `2026`: `+$134.21`, ROI `+7.90%`
- Latest season CLV: `18/237` positive, `+7.59%`, `-0.49 pts` spread line, `+1.87 pp` spread price, `+1.53 pp` spread no-vig, `+0.078` spread close EV
- Best season: `2025` with `+$147.14`
- Worst season: `2024` with `-$105.86`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 215 | -$105.86 | -8.26% | -4.23u | +14.22% | 100-114-1 | `41/215` positive, `+19.07%`, `-0.38 pts` spread line, `+1.69 pp` spread price, `+1.44 pp` spread no-vig, `+0.050` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 237 | +$147.14 | +8.10% | +5.89u | +8.52% | 130-105-2 | `36/237` positive, `+15.19%`, `-0.36 pts` spread line, `+1.80 pp` spread price, `+1.49 pp` spread no-vig, `+0.088` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 237 | +$134.21 | +7.90% | +5.37u | +8.56% | 129-108-0 | `18/237` positive, `+7.59%`, `-0.49 pts` spread line, `+1.87 pp` spread price, `+1.53 pp` spread no-vig, `+0.078` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 689 | +$175.49 | +3.66% | +7.02u | +14.22% | 2/3 |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 215 | 41 | 14 | 160 | +19.07% | -0.38 pts | +1.69 pp | +1.44 pp | +0.050 | none |
| `2025` | 237 | 36 | 18 | 183 | +15.19% | -0.36 pts | +1.80 pp | +1.49 pp | +0.088 | none |
| `2026` | 237 | 18 | 15 | 204 | +7.59% | -0.49 pts | +1.87 pp | +1.53 pp | +0.078 | none |
| Aggregate | 689 | 95 | 47 | 547 | +13.79% | -0.41 pts | +1.79 pp | +1.49 pp | +0.073 | none |

## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- When the timing layer is enabled, spread bets are evaluated from a six-hour pre-tip snapshot and only early bets with favorable predicted closing-line movement are kept.
- CLV is measured against the stored closing consensus. Spread now tracks line delta, raw price delta, no-vig close delta, and model EV at the close quote; moneyline tracks normalized implied-probability delta.
- The positive/neutral/negative CLV counts still use spread line movement for spread bets and no-vig close delta for moneyline bets. The added spread price and close-EV columns are supplemental execution measurements.
- When a backtest scores the closing snapshot itself, spread line CLV should be near-neutral, but price CLV and closing EV can still move because the executable quote and the stored close consensus are not always identical.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
