# Best Model Backtest Report

Generated: `2026-03-13T12:10:21-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260313_121844.md`

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

- Verdict: The current deployable path is positive across the full window, but season-to-season stability is mixed.
- Strongest evidence: aggregate spread price CLV `+1.99 pp` and spread close EV `+0.082` remain positive.
- Main risk: season stability is mixed; `2024` is the weakest season at `-$164.55`.
- Stake profile: typical settled bet `+$25.00`; smallest `+$7.78`; largest `+$77.76`
- Close-quality coverage: spread close EV `511/511`
- Next action: verify the close-market coverage table before promoting new structural model changes.

## Assessment

The current deployable path is positive across the full window, but season-to-season stability is mixed.

- Aggregate result: `+$1083.59` on `511` bets, ROI `+7.86%`
- Aggregate CLV: `57/511` positive, `+11.15%`, `-0.50 pts` spread line, `+1.99 pp` spread price, `+1.71 pp` spread no-vig, `+0.082` spread close EV
- Close-market coverage: spread close EV `511/511`
- Latest season `2026`: `+$225.71`, ROI `+5.53%`
- Latest season CLV: `11/160` positive, `+6.88%`, `-0.63 pts` spread line, `+2.25 pp` spread price, `+1.98 pp` spread no-vig, `+0.090` spread close EV
- Stake sizing: average `+$26.99`, median `+$25.00`, smallest `+$7.78`, largest `+$77.76`
- Availability shadow data: Shadow-only coverage is stored for `468` games, `7328` status rows, `4409` unmatched. It is not consumed by the live or backtest model paths yet.
- Best season: `2025` with `+$1022.43`
- Worst season: `2024` with `-$164.55`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 145 | -$164.55 | -4.80% | -6.58u | +6.69% | 70-75-0 | `21/145` positive, `+14.48%`, `-0.45 pts` spread line, `+1.82 pp` spread price, `+1.61 pp` spread no-vig, `+0.057` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=4, max_bets_per_day=6, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 206 | +$1022.43 | +16.29% | +40.90u | +9.77% | 116-88-2 | `25/206` positive, `+12.14%`, `-0.43 pts` spread line, `+1.91 pp` spread price, `+1.56 pp` spread no-vig, `+0.094` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=4, max_bets_per_day=6, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 160 | +$225.71 | +5.53% | +9.03u | +7.40% | 85-75-0 | `11/160` positive, `+6.88%`, `-0.63 pts` spread line, `+2.25 pp` spread price, `+1.98 pp` spread no-vig, `+0.090` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, min_positive_ev_books=4, max_bets_per_day=6, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 511 | +$1083.59 | +7.86% | +43.34u | +9.77% | 2/3 |

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
| Covered side report | 18 | 7-11-0 | -$64.42 | -15.79% | `1/18` positive, `+5.56%`, `-0.41 pts` spread line, `+1.95 pp` spread price, `+1.64 pp` spread no-vig, `+0.054` spread close EV | Latest matched official report exists for the bet side. |
| Fully covered matchup | 17 | 7-10-0 | -$45.52 | -11.70% | `1/17` positive, `+5.88%`, `-0.42 pts` spread line, `+1.99 pp` spread price, `+1.64 pp` spread no-vig, `+0.056` spread close EV | Both team sides had latest matched official reports available. |
| Uncovered side report | 493 | 264-227-2 | +$1148.01 | +8.58% | `56/493` positive, `+11.36%`, `-0.50 pts` spread line, `+1.99 pp` spread price, `+1.71 pp` spread no-vig, `+0.083` spread close EV | No matched official report exists for the bet side. |

### Status Flags

Status flags use the latest matched official reports only. They do not weight player importance or lineup value.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| Side has any out | 18 | 7-11-0 | -$64.42 | -15.79% | `1/18` positive, `+5.56%`, `-0.41 pts` spread line, `+1.95 pp` spread price, `+1.64 pp` spread no-vig, `+0.054` spread close EV | Latest matched side report includes at least one `out`. |
| Side has any questionable | 8 | 3-5-0 | -$32.93 | -17.85% | `0/8` positive, `0.00%`, `-0.19 pts` spread line, `+1.95 pp` spread price, `+1.46 pp` spread no-vig, `+0.036` spread close EV | Latest matched side report includes at least one `questionable`. |
| Opponent has any out | 17 | 7-10-0 | -$45.52 | -11.70% | `1/17` positive, `+5.88%`, `-0.42 pts` spread line, `+1.99 pp` spread price, `+1.64 pp` spread no-vig, `+0.056` spread close EV | Latest matched opponent report includes at least one `out`. |
| Opponent has any questionable | 5 | 2-3-0 | -$34.47 | -31.45% | `1/5` positive, `+20.00%`, `-0.12 pts` spread line, `+1.90 pp` spread price, `+1.16 pp` spread no-vig, `+0.046` spread close EV | Latest matched opponent report includes at least one `questionable`. |

### Latest Update Timing

Timing buckets use the latest matched side update relative to tip when the stored timing fields support it.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| 361+ min before tip | 1 | 1-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side update landed more than six hours before tip. Insufficient sample below 5 settled bets. |

## Close-Market Coverage

| Metric | Tracked | Missing / Unmatched | Notes |
| --- | ---: | ---: | --- |
| Spread line CLV | 511/511 (+100.00%) | 0/511 (0.00%) | Missing when no closing spread line can be matched. |
| Spread price CLV | 511/511 (+100.00%) | 0/511 (0.00%) | Tracks executable price movement against the stored close. |
| Spread no-vig close delta | 511/511 (+100.00%) | 0/511 (0.00%) | Uses the stored closing consensus after removing vig. |
| Spread closing EV | 511/511 (+100.00%) | 0/511 (0.00%) | Most direct execution-quality check for qualified spread bets. |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 145 | 21 | 6 | 118 | +14.48% | -0.45 pts | +1.82 pp | +1.61 pp | +0.057 | none |
| `2025` | 206 | 25 | 13 | 168 | +12.14% | -0.43 pts | +1.91 pp | +1.56 pp | +0.094 | none |
| `2026` | 160 | 11 | 7 | 142 | +6.88% | -0.63 pts | +2.25 pp | +1.98 pp | +0.090 | none |
| Aggregate | 511 | 57 | 26 | 428 | +11.15% | -0.50 pts | +1.99 pp | +1.71 pp | +0.082 | none |

## Spread Segment Attribution

### Expected Value Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 231 | +45.21% | +$47.21 | +1.02% | +0.033 |
| `6% to 8%` | 166 | +32.49% | +$193.15 | +4.31% | +0.099 |
| `8% to 10%` | 63 | +12.33% | +$376.13 | +17.29% | +0.144 |
| `10%+` | 51 | +9.98% | +$467.10 | +18.81% | +0.168 |

### Probability Edge Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 396 | +77.50% | +$165.13 | +1.79% | +0.062 |
| `10%+` | 10 | +1.96% | +$171.47 | +26.19% | +0.144 |
| `6% to 8%` | 90 | +17.61% | +$550.15 | +17.49% | +0.148 |
| `8% to 10%` | 15 | +2.94% | +$196.84 | +26.21% | +0.160 |

### Season Phase

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Established` | 511 | +100.00% | +$1083.59 | +7.86% | +0.082 |

### Line Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Priced Range` | 165 | +32.29% | +$138.59 | +3.32% | +0.054 |
| `Tight` | 346 | +67.71% | +$945.00 | +9.83% | +0.095 |

### Book Depth

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Mid Depth` | 12 | +2.35% | -$91.48 | -30.84% | +0.055 |
| `High Depth` | 499 | +97.65% | +$1175.06 | +8.71% | +0.083 |

### Conference Matchup

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Non-Conference` | 50 | +10.02% | -$0.61 | -0.05% | +0.065 |
| `Same Conference` | 449 | +89.98% | +$941.99 | +7.76% | +0.084 |

### Conference Group

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Unknown` | 6 | +1.17% | +$43.49 | +31.13% | +0.024 |
| `Other` | 505 | +98.83% | +$1040.10 | +7.62% | +0.083 |

### Tip Window

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0 to 6h` | 511 | +100.00% | +$1083.59 | +7.86% | +0.082 |


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
