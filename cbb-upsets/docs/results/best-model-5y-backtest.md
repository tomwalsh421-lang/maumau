# Best Model Backtest Report

Generated: `2026-03-29T18:44:23-04:00`
Output: `docs/results/best-model-5y-backtest.md`
History Copy: `docs/results/history/best-model-5y-backtest_20260329_192008.md`

## Scope

- Market: `best`
- Auto-tuned spread policy: `disabled`
- Timing layer: `disabled`
- Spread model family: `logistic`
- Seasons: `2022`, `2023`, `2024`, `2025`, `2026`
- Starting bankroll: `+$3750.00`
- Unit size: `+$25.00`
- Retrain cadence: `30 days`

## Decision Snapshot

- Verdict: The current deployable path is positive in every season where it actually placed bets.
- Strongest evidence: aggregate spread price CLV `+2.77 pp` and spread close EV `+0.326` remain positive.
- Main risk: there are no losing active seasons in the current window.
- Stake profile: typical settled bet `+$35.76`; smallest `+$26.66`; largest `+$75.13`
- Capital usage: requested stake capture `+100.00%`; average active-day exposure `+26.65%`; bet-cap days `0/53`
- Close-quality coverage: spread close EV `70/70`
- Next action: verify the close-market coverage table before promoting new structural model changes.

## Assessment

The current deployable path is positive in every season where it actually placed bets.

- Aggregate result: `+$874.31` on `70` bets, ROI `+32.23%`
- Aggregate CLV: `7/70` positive, `+10.00%`, `-0.91 pts` spread line, `+2.77 pp` spread price, `+2.59 pp` spread no-vig, `+0.326` spread close EV
- Close-market coverage: spread close EV `70/70`
- Latest season `2026`: `+$186.01`, ROI `+26.08%`
- Latest season CLV: `1/17` positive, `+5.88%`, `-1.29 pts` spread line, `+4.24 pp` spread price, `+4.02 pp` spread no-vig, `+0.111` spread close EV
- Stake sizing: average `+$38.75`, median `+$35.76`, smallest `+$26.66`, largest `+$75.13`
- Capital deployment: requested stake capture `+100.00%`, average active-day exposure `+26.65%`, peak active-day exposure `+83.12%`, average bets per active day `1.32`, bet-cap days `0`, exposure-cap days `0`
- Official availability: `Shadow only`. Coverage is stored for `468` games, `7328` status rows, `4409` unmatched. It is not consumed by the live or backtest model paths.
- Best season: `2024` with `+$237.79`
- Worst season: `2022` with `+$87.68`
- Zero-bet seasons: `none`

## Capital Deployment

| Metric | Value | Notes |
| --- | --- | --- |
| Active betting days | `53/53` | Days with at least one settled bet after bankroll limits. |
| Requested stake capture | `+100.00%` | Placed stake divided by requested Kelly stake across qualified candidates. |
| Average active-day exposure | `+26.65%` | Average share of the daily exposure cap used on active days. |
| Peak active-day exposure | `+83.12%` | Largest single-day share of the daily exposure cap that was used. |
| Average bets per active day | `1.32` | Mean number of placed bets on days where the strategy was active. |
| Days hitting bet cap | `0` | Days where more qualified bets existed than the same-day cap allowed. |
| Days hitting exposure cap | `0` | Days where the daily exposure limit clipped or blocked additional stake. |
| Clipped bets | `0` | Placed bets whose requested stake was reduced by the daily exposure cap. |
| Bets skipped by bet cap | `0` | Qualified bets left unplaced because the same-day cap was already full. |

## Five-Slot Selection Pressure

The same-day bet cap did not skip any qualified bets in this window.

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2022` | 3 | +$87.68 | +95.47% | +3.51u | 0.00% | 3-0-0 | `0/3` positive, `0.00%`, `-1.00 pts` spread line, `+1.14 pp` spread price, `+1.23 pp` spread no-vig, `+3.888` spread close EV | `min_edge=0.060, min_confidence=0.518, min_probability_edge=0.060, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2023` | 11 | +$170.39 | +36.96% | +6.82u | +1.65% | 7-4-0 | `3/11` positive, `+27.27%`, `-0.30 pts` spread line, `+1.58 pp` spread price, `+1.41 pp` spread no-vig, `+0.204` spread close EV | `min_edge=0.060, min_confidence=0.518, min_probability_edge=0.060, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2024` | 18 | +$237.79 | +39.44% | +9.51u | +1.73% | 12-5-1 | `2/18` positive, `+11.11%`, `-0.74 pts` spread line, `+2.53 pp` spread price, `+2.39 pp` spread no-vig, `+0.156` spread close EV | `min_edge=0.060, min_confidence=0.518, min_probability_edge=0.060, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 21 | +$192.45 | +22.81% | +7.70u | +3.34% | 13-8-0 | `1/21` positive, `+4.76%`, `-1.07 pts` spread line, `+2.65 pp` spread price, `+2.41 pp` spread no-vig, `+0.200` spread close EV | `min_edge=0.060, min_confidence=0.518, min_probability_edge=0.060, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 17 | +$186.01 | +26.08% | +7.44u | +1.42% | 11-6-0 | `1/17` positive, `+5.88%`, `-1.29 pts` spread line, `+4.24 pp` spread price, `+4.02 pp` spread no-vig, `+0.111` spread close EV | `min_edge=0.060, min_confidence=0.518, min_probability_edge=0.060, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 70 | +$874.31 | +32.23% | +34.97u | +3.34% | 5/5 |

## Official Availability

- Usage state: `Shadow only`
- Usage note: Official availability is stored for diagnostics only. It does not change the promoted live board, backtest, or betting-policy path.

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

These diagnostics join settled best-path bets to the latest matched official availability report for the bet side. They do not change the canonical headline metrics and they are not promotion evidence by themselves.

Rows with fewer than `5` settled bets are marked `insufficient sample`.

### Coverage

Coverage compares settled best-path bets against the latest matched official report for the bet side.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| Covered side report | 1 | 1-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched official report exists for the bet side. Insufficient sample below 5 settled bets. |
| Fully covered matchup | 0 | 0-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Both team sides had latest matched official reports available. No settled best-path bets landed in this slice. |
| Uncovered side report | 69 | 45-23-1 | +$827.42 | +30.98% | `6/69` positive, `+8.70%`, `-0.93 pts` spread line, `+2.72 pp` spread price, `+2.55 pp` spread no-vig, `+0.330` spread close EV | No matched official report exists for the bet side. |

### Status Flags

Status flags use the latest matched official reports only. They do not weight player importance or lineup value.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| Side has any out | 1 | 1-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side report includes at least one `out`. Insufficient sample below 5 settled bets. |
| Side has any questionable | 1 | 1-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side report includes at least one `questionable`. Insufficient sample below 5 settled bets. |

### Latest Update Timing

Timing buckets use the latest matched side update relative to tip when the stored timing fields support it.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| After tip | 1 | 1-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side update timestamp landed after the stored tip time. Insufficient sample below 5 settled bets. |

## Close-Market Coverage

| Metric | Tracked | Missing / Unmatched | Notes |
| --- | ---: | ---: | --- |
| Spread line CLV | 70/70 (+100.00%) | 0/70 (0.00%) | Missing when no closing spread line can be matched. |
| Spread price CLV | 70/70 (+100.00%) | 0/70 (0.00%) | Tracks executable price movement against the stored close. |
| Spread no-vig close delta | 70/70 (+100.00%) | 0/70 (0.00%) | Uses the stored closing consensus after removing vig. |
| Spread closing EV | 70/70 (+100.00%) | 0/70 (0.00%) | Most direct execution-quality check for qualified spread bets. |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2022` | 3 | 0 | 0 | 3 | 0.00% | -1.00 pts | +1.14 pp | +1.23 pp | +3.888 | none |
| `2023` | 11 | 3 | 0 | 8 | +27.27% | -0.30 pts | +1.58 pp | +1.41 pp | +0.204 | none |
| `2024` | 18 | 2 | 1 | 15 | +11.11% | -0.74 pts | +2.53 pp | +2.39 pp | +0.156 | none |
| `2025` | 21 | 1 | 0 | 20 | +4.76% | -1.07 pts | +2.65 pp | +2.41 pp | +0.200 | none |
| `2026` | 17 | 1 | 0 | 16 | +5.88% | -1.29 pts | +4.24 pp | +4.02 pp | +0.111 | none |
| Aggregate | 70 | 7 | 1 | 62 | +10.00% | -0.91 pts | +2.77 pp | +2.59 pp | +0.326 | none |

## Spread Segment Attribution

### Expected Value Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `8% to 10%` | 23 | +32.86% | +$153.97 | +19.81% | +0.178 |
| `10%+` | 29 | +41.43% | +$496.31 | +35.26% | +0.189 |
| `6% to 8%` | 18 | +25.71% | +$224.04 | +42.43% | +0.735 |

### Probability Edge Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `8% to 10%` | 8 | +11.43% | +$195.29 | +50.73% | +0.161 |
| `10%+` | 6 | +8.57% | +$30.01 | +7.59% | +0.191 |
| `6% to 8%` | 56 | +80.00% | +$649.01 | +33.59% | +0.364 |

### Season Phase

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Established` | 70 | +100.00% | +$874.31 | +32.23% | +0.326 |

### Line Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Priced Range` | 16 | +22.86% | +$150.37 | +22.90% | +0.109 |
| `Tight` | 54 | +77.14% | +$723.94 | +35.21% | +0.390 |

### Book Depth

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `High Depth` | 59 | +84.29% | +$563.64 | +24.86% | +0.153 |
| `Low Depth` | 11 | +15.71% | +$310.67 | +69.83% | +1.252 |

### Venue Context

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Neutral Site` | 12 | +17.14% | +$172.72 | +30.80% | +0.071 |
| `Home Venue` | 58 | +82.86% | +$701.60 | +32.60% | +0.379 |

### Travel Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Long Trip` | 2 | +2.86% | +$16.04 | +17.94% | +0.106 |
| `Regional Trip` | 21 | +30.00% | +$369.10 | +43.65% | +0.135 |
| `Local Trip` | 47 | +67.14% | +$489.16 | +27.52% | +0.421 |

### Timezone Crossings

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `One Timezone` | 9 | +12.86% | +$129.75 | +33.28% | +0.098 |
| `Two+ Timezones` | 1 | +1.43% | +$51.69 | +96.15% | +0.102 |
| `Same Timezone` | 60 | +85.71% | +$692.87 | +30.54% | +0.364 |

### Conference Matchup

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Same Conference` | 57 | +85.07% | +$637.30 | +28.92% | +0.146 |
| `Non-Conference` | 10 | +14.93% | +$134.09 | +33.05% | +1.396 |

### Conference Group

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Unknown` | 2 | +2.86% | +$61.48 | +100.10% | +0.104 |
| `Other` | 68 | +97.14% | +$812.83 | +30.66% | +0.333 |

### Tip Window

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0 to 6h` | 70 | +100.00% | +$874.31 | +32.23% | +0.326 |


## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- When the timing layer is enabled, spread bets are evaluated from a six-hour pre-tip snapshot and only early bets with favorable predicted closing-line movement are kept.
- CLV is measured against the stored closing consensus. Spread now tracks line delta, raw price delta, no-vig close delta, and model EV at the close quote; moneyline tracks normalized implied-probability delta.
- The positive/neutral/negative CLV counts still use spread line movement for spread bets and no-vig close delta for moneyline bets. The added spread price and close-EV columns are supplemental execution measurements.
- When a backtest scores the closing snapshot itself, spread line CLV should be near-neutral, but price CLV and closing EV can still move because the executable quote and the stored close consensus are not always identical.
- Close-market coverage uses tracked settled bets as the denominator for each market-specific signal.
- Official availability usage: Official availability is stored for diagnostics only. It does not change the promoted live board, backtest, or betting-policy path.
- The spread segment tables are aggregate attribution views for qualified spread bets only. They are intended for research diagnostics, not direct causal claims.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
