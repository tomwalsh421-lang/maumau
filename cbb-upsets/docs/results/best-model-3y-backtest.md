# Best Model Backtest Report

Generated: `2026-03-13T14:25:46-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260313_143415.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `disabled`
- Timing layer: `disabled`
- Spread model family: `logistic`
- Seasons: `2024`, `2025`, `2026`
- Starting bankroll: `+$3750.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Decision Snapshot

- Verdict: The current deployable path is positive in every season where it actually placed bets.
- Strongest evidence: aggregate spread price CLV `+2.03 pp` and spread close EV `+0.087` remain positive.
- Main risk: there are no losing active seasons in the current window.
- Stake profile: typical settled bet `+$25.99`; smallest `+$15.22`; largest `+$79.06`
- Close-quality coverage: spread close EV `470/470`
- Next action: verify the close-market coverage table before promoting new structural model changes.

## Assessment

The current deployable path is positive in every season where it actually placed bets.

- Aggregate result: `+$1428.11` on `470` bets, ROI `+10.80%`
- Aggregate CLV: `54/470` positive, `+11.49%`, `-0.52 pts` spread line, `+2.03 pp` spread price, `+1.73 pp` spread no-vig, `+0.087` spread close EV
- Close-market coverage: spread close EV `470/470`
- Latest season `2026`: `+$309.07`, ROI `+7.87%`
- Latest season CLV: `11/148` positive, `+7.43%`, `-0.65 pts` spread line, `+2.30 pp` spread price, `+2.00 pp` spread no-vig, `+0.093` spread close EV
- Stake sizing: average `+$28.14`, median `+$25.99`, smallest `+$15.22`, largest `+$79.06`
- Availability shadow data: Shadow-only coverage is stored for `468` games, `7328` status rows, `4409` unmatched. It is not consumed by the live or backtest model paths yet.
- Best season: `2025` with `+$1089.85`
- Worst season: `2024` with `+$29.18`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 132 | +$29.18 | +0.89% | +1.17u | +4.33% | 68-64-0 | `19/132` positive, `+14.39%`, `-0.46 pts` spread line, `+1.83 pp` spread price, `+1.64 pp` spread no-vig, `+0.063` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 190 | +$1089.85 | +18.09% | +43.59u | +8.17% | 109-79-2 | `24/190` positive, `+12.63%`, `-0.45 pts` spread line, `+1.96 pp` spread price, `+1.59 pp` spread no-vig, `+0.099` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 148 | +$309.07 | +7.87% | +12.36u | +6.04% | 81-67-0 | `11/148` positive, `+7.43%`, `-0.65 pts` spread line, `+2.30 pp` spread price, `+2.00 pp` spread no-vig, `+0.093` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 470 | +$1428.11 | +10.80% | +57.12u | +8.17% | 3/3 |

## Official Availability Shadow

Stored official availability data is shadow-only in the current repo. It is visible for audit and coverage review here, but it is not used by the live prediction, backtest, or betting-policy paths yet.

| Metric | Value | Notes |
| --- | --- | --- |
| Official reports | `2840` | Stored raw report snapshots from the availability import lane. |
| Player status rows | `7328` | Parsed player-level status records stored for shadow analysis. |
| Covered games | `468` | Distinct matched games represented in the stored reports. |
| Matched rows | `2919` | Rows linked to a repo team/game scope when matching columns exist. |
| Unmatched rows | `4409` | Imported rows still unmatched after normalization. |
| Latest update | `n/a` | Tip-relative timing is not yet available. |
| Seasons | `2026` | Distinct seasons represented in stored official reports. |
| Scope | `regular-season` | Stored season / tournament scope labels when present. |
| Source | `acc_mbb_availability_archive`, `atlantic10_mbb_availability_archive`, `big12_mbb_availability_archive`, `big_east_mbb_availability_archive`, `big_ten_mbb_availability_archive`, `mvc_mbb_availability_archive`, `sec_mbb_availability_archive`, `the_american_mbb_player_availability` | Distinct upstream source labels recorded with the reports. |
| Status mix | `out` 5911, `questionable` 949, `available` 293, `probable` 175 | Top stored player-status values across imported rows. |

## Availability Evaluation Slices

These shadow diagnostics join settled best-path bets to the latest matched official availability report for the bet side. They do not change the canonical headline metrics and they are not promotion evidence by themselves.

Rows with fewer than `5` settled bets are marked `insufficient sample`.

### Coverage

Coverage compares settled best-path bets against the latest matched official report for the bet side.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| Covered side report | 14 | 6-8-0 | -$29.61 | -8.64% | `1/14` positive, `+7.14%`, `-0.39 pts` spread line, `+2.02 pp` spread price, `+1.57 pp` spread no-vig, `+0.067` spread close EV | Latest matched official report exists for the bet side. |
| Fully covered matchup | 14 | 6-8-0 | -$29.61 | -8.64% | `1/14` positive, `+7.14%`, `-0.39 pts` spread line, `+2.02 pp` spread price, `+1.57 pp` spread no-vig, `+0.067` spread close EV | Both team sides had latest matched official reports available. |
| Uncovered side report | 456 | 252-202-2 | +$1457.72 | +11.32% | `53/456` positive, `+11.62%`, `-0.52 pts` spread line, `+2.03 pp` spread price, `+1.74 pp` spread no-vig, `+0.087` spread close EV | No matched official report exists for the bet side. |

### Status Flags

Status flags use the latest matched official reports only. They do not weight player importance or lineup value.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| Side has any out | 14 | 6-8-0 | -$29.61 | -8.64% | `1/14` positive, `+7.14%`, `-0.39 pts` spread line, `+2.02 pp` spread price, `+1.57 pp` spread no-vig, `+0.067` spread close EV | Latest matched side report includes at least one `out`. |
| Side has any questionable | 6 | 2-4-0 | -$31.95 | -21.41% | `0/6` positive, `0.00%`, `-0.12 pts` spread line, `+2.07 pp` spread price, `+1.35 pp` spread no-vig, `+0.043` spread close EV | Latest matched side report includes at least one `questionable`. |
| Opponent has any out | 14 | 6-8-0 | -$29.61 | -8.64% | `1/14` positive, `+7.14%`, `-0.39 pts` spread line, `+2.02 pp` spread price, `+1.57 pp` spread no-vig, `+0.067` spread close EV | Latest matched opponent report includes at least one `out`. |
| Opponent has any questionable | 5 | 2-3-0 | -$34.42 | -30.90% | `1/5` positive, `+20.00%`, `-0.12 pts` spread line, `+1.90 pp` spread price, `+1.16 pp` spread no-vig, `+0.046` spread close EV | Latest matched opponent report includes at least one `questionable`. |

### Latest Update Timing

Timing buckets use the latest matched side update relative to tip when the stored timing fields support it.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| 361+ min before tip | 1 | 1-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side update landed more than six hours before tip. Insufficient sample below 5 settled bets. |

## Close-Market Coverage

| Metric | Tracked | Missing / Unmatched | Notes |
| --- | ---: | ---: | --- |
| Spread line CLV | 470/470 (+100.00%) | 0/470 (0.00%) | Missing when no closing spread line can be matched. |
| Spread price CLV | 470/470 (+100.00%) | 0/470 (0.00%) | Tracks executable price movement against the stored close. |
| Spread no-vig close delta | 470/470 (+100.00%) | 0/470 (0.00%) | Uses the stored closing consensus after removing vig. |
| Spread closing EV | 470/470 (+100.00%) | 0/470 (0.00%) | Most direct execution-quality check for qualified spread bets. |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 132 | 19 | 4 | 109 | +14.39% | -0.46 pts | +1.83 pp | +1.64 pp | +0.063 | none |
| `2025` | 190 | 24 | 12 | 154 | +12.63% | -0.45 pts | +1.96 pp | +1.59 pp | +0.099 | none |
| `2026` | 148 | 11 | 7 | 130 | +7.43% | -0.65 pts | +2.30 pp | +2.00 pp | +0.093 | none |
| Aggregate | 470 | 54 | 23 | 393 | +11.49% | -0.52 pts | +2.03 pp | +1.73 pp | +0.087 | none |

## Spread Segment Attribution

### Expected Value Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 199 | +42.34% | +$274.67 | +6.68% | +0.036 |
| `6% to 8%` | 157 | +33.40% | +$297.63 | +6.81% | +0.102 |
| `8% to 10%` | 63 | +13.40% | +$378.72 | +17.09% | +0.144 |
| `10%+` | 51 | +10.85% | +$477.09 | +18.90% | +0.168 |

### Probability Edge Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 358 | +76.17% | +$488.86 | +5.64% | +0.066 |
| `10%+` | 10 | +2.13% | +$173.31 | +26.11% | +0.144 |
| `6% to 8%` | 87 | +18.51% | +$565.82 | +18.06% | +0.151 |
| `8% to 10%` | 15 | +3.19% | +$200.12 | +26.14% | +0.160 |

### Season Phase

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Established` | 470 | +100.00% | +$1428.11 | +10.80% | +0.087 |

### Line Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Priced Range` | 152 | +32.34% | +$297.38 | +7.48% | +0.056 |
| `Tight` | 318 | +67.66% | +$1130.72 | +12.22% | +0.101 |

### Book Depth

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Mid Depth` | 12 | +2.55% | -$92.62 | -30.68% | +0.055 |
| `High Depth` | 458 | +97.45% | +$1520.73 | +11.77% | +0.087 |

### Conference Matchup

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Non-Conference` | 46 | +10.00% | +$24.57 | +1.91% | +0.067 |
| `Same Conference` | 414 | +90.00% | +$1306.08 | +11.18% | +0.089 |

### Conference Group

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Unknown` | 5 | +1.06% | +$11.95 | +10.92% | +0.017 |
| `Other` | 465 | +98.94% | +$1416.16 | +10.80% | +0.087 |

### Tip Window

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0 to 6h` | 470 | +100.00% | +$1428.11 | +10.80% | +0.087 |


## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- When the timing layer is enabled, spread bets are evaluated from a six-hour pre-tip snapshot and only early bets with favorable predicted closing-line movement are kept.
- CLV is measured against the stored closing consensus. Spread now tracks line delta, raw price delta, no-vig close delta, and model EV at the close quote; moneyline tracks normalized implied-probability delta.
- The positive/neutral/negative CLV counts still use spread line movement for spread bets and no-vig close delta for moneyline bets. The added spread price and close-EV columns are supplemental execution measurements.
- When a backtest scores the closing snapshot itself, spread line CLV should be near-neutral, but price CLV and closing EV can still move because the executable quote and the stored close consensus are not always identical.
- Close-market coverage uses tracked settled bets as the denominator for each market-specific signal.
- Official availability data can now be stored and surfaced in shadow form for diagnostics, but it is still excluded from the promoted live and backtest model paths.
- The spread segment tables are aggregate attribution views for qualified spread bets only. They are intended for research diagnostics, not direct causal claims.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
