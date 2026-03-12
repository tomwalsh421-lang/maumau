# Best Model Backtest Report

Generated: `2026-03-12T12:39:07-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260312_124725.md`

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
- Strongest evidence: aggregate spread price CLV `+1.87 pp` and spread close EV `+0.083` remain positive.
- Main risk: season stability is mixed; `2024` is the weakest season at `-$84.90`.
- Close-quality coverage: spread close EV `570/570`
- Next action: verify the close-market coverage table before promoting new structural model changes.

## Assessment

The current deployable path is positive across the full window, but season-to-season stability is mixed.

- Aggregate result: `+$277.21` on `570` bets, ROI `+7.18%`
- Aggregate CLV: `64/570` positive, `+11.23%`, `-0.45 pts` spread line, `+1.87 pp` spread price, `+1.59 pp` spread no-vig, `+0.083` spread close EV
- Close-market coverage: spread close EV `570/570`
- Latest season `2026`: `+$137.86`, ROI `+9.68%`
- Latest season CLV: `14/207` positive, `+6.76%`, `-0.55 pts` spread line, `+2.01 pp` spread price, `+1.68 pp` spread no-vig, `+0.093` spread close EV
- Best season: `2025` with `+$224.26`
- Worst season: `2024` with `-$84.90`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 161 | -$84.90 | -8.76% | -3.40u | +10.49% | 74-86-1 | `28/161` positive, `+17.39%`, `-0.40 pts` spread line, `+1.74 pp` spread price, `+1.55 pp` spread no-vig, `+0.055` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 202 | +$224.26 | +15.29% | +8.97u | +9.05% | 118-83-1 | `22/202` positive, `+10.89%`, `-0.41 pts` spread line, `+1.85 pp` spread price, `+1.53 pp` spread no-vig, `+0.094` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 207 | +$137.86 | +9.68% | +5.51u | +6.79% | 115-92-0 | `14/207` positive, `+6.76%`, `-0.55 pts` spread line, `+2.01 pp` spread price, `+1.68 pp` spread no-vig, `+0.093` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 570 | +$277.21 | +7.18% | +11.09u | +10.49% | 2/3 |

## Close-Market Coverage

| Metric | Tracked | Missing / Unmatched | Notes |
| --- | ---: | ---: | --- |
| Spread line CLV | 570/570 (+100.00%) | 0/570 (0.00%) | Missing when no closing spread line can be matched. |
| Spread price CLV | 570/570 (+100.00%) | 0/570 (0.00%) | Tracks executable price movement against the stored close. |
| Spread no-vig close delta | 570/570 (+100.00%) | 0/570 (0.00%) | Uses the stored closing consensus after removing vig. |
| Spread closing EV | 570/570 (+100.00%) | 0/570 (0.00%) | Most direct execution-quality check for qualified spread bets. |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 161 | 28 | 11 | 122 | +17.39% | -0.40 pts | +1.74 pp | +1.55 pp | +0.055 | none |
| `2025` | 202 | 22 | 14 | 166 | +10.89% | -0.41 pts | +1.85 pp | +1.53 pp | +0.094 | none |
| `2026` | 207 | 14 | 12 | 181 | +6.76% | -0.55 pts | +2.01 pp | +1.68 pp | +0.093 | none |
| Aggregate | 570 | 64 | 37 | 469 | +11.23% | -0.45 pts | +1.87 pp | +1.59 pp | +0.083 | none |

## Spread Segment Attribution

### Expected Value Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 257 | +45.09% | +$127.89 | +9.66% | +0.037 |
| `6% to 8%` | 189 | +33.16% | +$101.28 | +7.81% | +0.095 |
| `8% to 10%` | 81 | +14.21% | -$3.51 | -0.48% | +0.142 |
| `10%+` | 43 | +7.54% | +$51.55 | +10.16% | +0.193 |

### Probability Edge Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 444 | +77.89% | +$194.59 | +7.33% | +0.067 |
| `6% to 8%` | 112 | +19.65% | +$28.29 | +2.79% | +0.131 |
| `10%+` | 1 | +0.18% | +$22.70 | +130.00% | +0.155 |
| `8% to 10%` | 13 | +2.28% | +$31.63 | +18.26% | +0.200 |

### Season Phase

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Established` | 570 | +100.00% | +$277.21 | +7.18% | +0.083 |

### Line Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Priced Range` | 181 | +31.75% | +$181.74 | +15.32% | +0.060 |
| `Tight` | 389 | +68.25% | +$95.47 | +3.57% | +0.093 |

### Book Depth

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `High Depth` | 554 | +97.19% | +$290.44 | +7.74% | +0.083 |
| `Mid Depth` | 16 | +2.81% | -$13.23 | -12.15% | +0.091 |

### Conference Matchup

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Non-Conference` | 50 | +8.98% | -$2.56 | -0.76% | +0.064 |
| `Same Conference` | 507 | +91.02% | +$264.30 | +7.67% | +0.085 |

### Conference Group

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Unknown` | 8 | +1.40% | -$8.69 | -21.22% | +0.043 |
| `Other` | 562 | +98.60% | +$285.91 | +7.49% | +0.083 |

### Tip Window

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0 to 6h` | 570 | +100.00% | +$277.21 | +7.18% | +0.083 |


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
