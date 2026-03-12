# Best Model Backtest Report

Generated: `2026-03-11T22:21:27-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260311_222127.md`

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

- Aggregate result: `+$282.70` on `569` bets, ROI `+7.34%`
- Aggregate CLV: `64/569` positive, `+11.25%`, `-0.46 pts` spread line, `+1.87 pp` spread price, `+1.59 pp` spread no-vig, `+0.083` spread close EV
- Latest season `2026`: `+$143.34`, ROI `+10.11%`
- Latest season CLV: `14/206` positive, `+6.80%`, `-0.55 pts` spread line, `+2.01 pp` spread price, `+1.68 pp` spread no-vig, `+0.094` spread close EV
- Best season: `2025` with `+$224.26`
- Worst season: `2024` with `-$84.90`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 161 | -$84.90 | -8.76% | -3.40u | +10.49% | 74-86-1 | `28/161` positive, `+17.39%`, `-0.40 pts` spread line, `+1.74 pp` spread price, `+1.55 pp` spread no-vig, `+0.055` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 202 | +$224.26 | +15.29% | +8.97u | +9.05% | 118-83-1 | `22/202` positive, `+10.89%`, `-0.41 pts` spread line, `+1.85 pp` spread price, `+1.53 pp` spread no-vig, `+0.094` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 206 | +$143.34 | +10.11% | +5.73u | +6.79% | 115-91-0 | `14/206` positive, `+6.80%`, `-0.55 pts` spread line, `+2.01 pp` spread price, `+1.68 pp` spread no-vig, `+0.094` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 569 | +$282.70 | +7.34% | +11.31u | +10.49% | 2/3 |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 161 | 28 | 11 | 122 | +17.39% | -0.40 pts | +1.74 pp | +1.55 pp | +0.055 | none |
| `2025` | 202 | 22 | 14 | 166 | +10.89% | -0.41 pts | +1.85 pp | +1.53 pp | +0.094 | none |
| `2026` | 206 | 14 | 11 | 181 | +6.80% | -0.55 pts | +2.01 pp | +1.68 pp | +0.094 | none |
| Aggregate | 569 | 64 | 36 | 469 | +11.25% | -0.46 pts | +1.87 pp | +1.59 pp | +0.083 | none |

## Spread Segment Attribution

### Expected Value Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 256 | +44.99% | +$133.38 | +10.11% | +0.037 |
| `6% to 8%` | 189 | +33.22% | +$101.28 | +7.81% | +0.095 |
| `8% to 10%` | 81 | +14.24% | -$3.51 | -0.48% | +0.142 |
| `10%+` | 43 | +7.56% | +$51.55 | +10.16% | +0.193 |

### Probability Edge Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 443 | +77.86% | +$200.07 | +7.55% | +0.067 |
| `6% to 8%` | 112 | +19.68% | +$28.29 | +2.79% | +0.131 |
| `10%+` | 1 | +0.18% | +$22.70 | +130.00% | +0.155 |
| `8% to 10%` | 13 | +2.28% | +$31.63 | +18.26% | +0.200 |

### Season Phase

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Established` | 569 | +100.00% | +$282.70 | +7.34% | +0.083 |

### Line Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Priced Range` | 180 | +31.63% | +$187.23 | +15.86% | +0.060 |
| `Tight` | 389 | +68.37% | +$95.47 | +3.57% | +0.093 |

### Book Depth

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `High Depth` | 553 | +97.19% | +$295.93 | +7.90% | +0.083 |
| `Mid Depth` | 16 | +2.81% | -$13.23 | -12.15% | +0.091 |

### Conference Matchup

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Non-Conference` | 50 | +8.99% | -$2.56 | -0.76% | +0.064 |
| `Same Conference` | 506 | +91.01% | +$269.79 | +7.85% | +0.085 |

### Conference Group

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Unknown` | 8 | +1.41% | -$8.69 | -21.22% | +0.043 |
| `Other` | 561 | +98.59% | +$291.39 | +7.64% | +0.083 |

### Tip Window

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0 to 6h` | 569 | +100.00% | +$282.70 | +7.34% | +0.083 |


## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- When the timing layer is enabled, spread bets are evaluated from a six-hour pre-tip snapshot and only early bets with favorable predicted closing-line movement are kept.
- CLV is measured against the stored closing consensus. Spread now tracks line delta, raw price delta, no-vig close delta, and model EV at the close quote; moneyline tracks normalized implied-probability delta.
- The positive/neutral/negative CLV counts still use spread line movement for spread bets and no-vig close delta for moneyline bets. The added spread price and close-EV columns are supplemental execution measurements.
- When a backtest scores the closing snapshot itself, spread line CLV should be near-neutral, but price CLV and closing EV can still move because the executable quote and the stored close consensus are not always identical.
- The spread segment tables are aggregate attribution views for qualified spread bets only. They are intended for research diagnostics, not direct causal claims.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
