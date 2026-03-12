# Best Model Backtest Report

Generated: `2026-03-12T15:21:08-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260312_152928.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `disabled`
- Timing layer: `disabled`
- Spread model family: `logistic`
- Seasons: `2024`, `2025`, `2026`
- Starting bankroll: `+$1000.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Decision Snapshot

- Verdict: The current deployable path is positive across the full window, but season-to-season stability is mixed.
- Strongest evidence: aggregate spread price CLV `+1.91 pp` and spread close EV `+0.086` remain positive.
- Main risk: season stability is mixed; `2024` is the weakest season at `-$61.81`.
- Close-quality coverage: spread close EV `536/536`
- Next action: verify the close-market coverage table before promoting new structural model changes.

## Assessment

The current deployable path is positive across the full window, but season-to-season stability is mixed.

- Aggregate result: `+$268.02` on `536` bets, ROI `+7.20%`
- Aggregate CLV: `60/536` positive, `+11.19%`, `-0.47 pts` spread line, `+1.91 pp` spread price, `+1.61 pp` spread no-vig, `+0.086` spread close EV
- Close-market coverage: spread close EV `536/536`
- Latest season `2026`: `+$138.57`, ROI `+10.06%`
- Latest season CLV: `14/196` positive, `+7.14%`, `-0.55 pts` spread line, `+2.03 pp` spread price, `+1.70 pp` spread no-vig, `+0.097` spread close EV
- Best season: `2025` with `+$191.25`
- Worst season: `2024` with `-$61.81`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 148 | -$61.81 | -6.66% | -2.47u | +8.23% | 71-77-0 | `24/148` positive, `+16.22%`, `-0.42 pts` spread line, `+1.78 pp` spread price, `+1.57 pp` spread no-vig, `+0.058` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, max_bets_per_day=6, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 192 | +$191.25 | +13.49% | +7.65u | +8.78% | 109-82-1 | `22/192` positive, `+11.46%`, `-0.41 pts` spread line, `+1.88 pp` spread price, `+1.54 pp` spread no-vig, `+0.097` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, max_bets_per_day=6, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 196 | +$138.57 | +10.06% | +5.54u | +7.01% | 110-86-0 | `14/196` positive, `+7.14%`, `-0.55 pts` spread line, `+2.03 pp` spread price, `+1.70 pp` spread no-vig, `+0.097` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, max_bets_per_day=6, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 536 | +$268.02 | +7.20% | +10.72u | +8.78% | 2/3 |

## Close-Market Coverage

| Metric | Tracked | Missing / Unmatched | Notes |
| --- | ---: | ---: | --- |
| Spread line CLV | 536/536 (+100.00%) | 0/536 (0.00%) | Missing when no closing spread line can be matched. |
| Spread price CLV | 536/536 (+100.00%) | 0/536 (0.00%) | Tracks executable price movement against the stored close. |
| Spread no-vig close delta | 536/536 (+100.00%) | 0/536 (0.00%) | Uses the stored closing consensus after removing vig. |
| Spread closing EV | 536/536 (+100.00%) | 0/536 (0.00%) | Most direct execution-quality check for qualified spread bets. |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 148 | 24 | 10 | 114 | +16.22% | -0.42 pts | +1.78 pp | +1.57 pp | +0.058 | none |
| `2025` | 192 | 22 | 11 | 159 | +11.46% | -0.41 pts | +1.88 pp | +1.54 pp | +0.097 | none |
| `2026` | 196 | 14 | 10 | 172 | +7.14% | -0.55 pts | +2.03 pp | +1.70 pp | +0.097 | none |
| Aggregate | 536 | 60 | 31 | 445 | +11.19% | -0.47 pts | +1.91 pp | +1.61 pp | +0.086 | none |

## Spread Segment Attribution

### Expected Value Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 227 | +42.35% | +$113.42 | +9.46% | +0.039 |
| `6% to 8%` | 185 | +34.51% | +$108.95 | +8.46% | +0.096 |
| `8% to 10%` | 81 | +15.11% | -$4.37 | -0.60% | +0.142 |
| `10%+` | 43 | +8.02% | +$50.01 | +9.89% | +0.193 |

### Probability Edge Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 411 | +76.68% | +$187.40 | +7.44% | +0.070 |
| `6% to 8%` | 111 | +20.71% | +$26.82 | +2.65% | +0.132 |
| `10%+` | 1 | +0.19% | +$22.09 | +130.00% | +0.155 |
| `8% to 10%` | 13 | +2.43% | +$31.70 | +18.37% | +0.200 |

### Season Phase

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Established` | 536 | +100.00% | +$268.02 | +7.20% | +0.086 |

### Line Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Priced Range` | 172 | +32.09% | +$164.99 | +14.35% | +0.062 |
| `Tight` | 364 | +67.91% | +$103.02 | +4.01% | +0.098 |

### Book Depth

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `High Depth` | 520 | +97.01% | +$281.09 | +7.78% | +0.086 |
| `Mid Depth` | 16 | +2.99% | -$13.07 | -12.05% | +0.091 |

### Conference Matchup

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Non-Conference` | 49 | +9.35% | -$6.79 | -2.04% | +0.065 |
| `Same Conference` | 475 | +90.65% | +$259.87 | +7.85% | +0.089 |

### Conference Group

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Unknown` | 7 | +1.31% | -$9.21 | -22.51% | +0.041 |
| `Other` | 529 | +98.69% | +$277.23 | +7.53% | +0.087 |

### Tip Window

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0 to 6h` | 536 | +100.00% | +$268.02 | +7.20% | +0.086 |


## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- When the timing layer is enabled, spread bets are evaluated from a six-hour pre-tip snapshot and only early bets with favorable predicted closing-line movement are kept.
- CLV is measured against the stored closing consensus. Spread now tracks line delta, raw price delta, no-vig close delta, and model EV at the close quote; moneyline tracks normalized implied-probability delta.
- The positive/neutral/negative CLV counts still use spread line movement for spread bets and no-vig close delta for moneyline bets. The added spread price and close-EV columns are supplemental execution measurements.
- When a backtest scores the closing snapshot itself, spread line CLV should be near-neutral, but price CLV and closing EV can still move because the executable quote and the stored close consensus are not always identical.
- Close-market coverage uses tracked settled bets as the denominator for each market-specific signal.
- The spread segment tables are aggregate attribution views for qualified spread bets only. They are intended for research diagnostics, not direct causal claims.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
