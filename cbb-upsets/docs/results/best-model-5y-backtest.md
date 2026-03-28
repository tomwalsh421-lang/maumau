# Best Model Backtest Report

Generated: `2026-03-28T11:43:27-04:00`
Output: `docs/results/best-model-5y-backtest.md`
History Copy: `docs/results/history/best-model-5y-backtest_20260328_121107.md`

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

- Verdict: The current deployable path is positive across the full window, but season-to-season stability is mixed.
- Strongest evidence: aggregate spread price CLV `+2.18 pp` and spread close EV `+0.186` remain positive.
- Main risk: season stability is mixed; `2024` is the weakest season at `-$137.91`.
- Stake profile: typical settled bet `+$24.30`; smallest `+$15.12`; largest `+$75.18`
- Capital usage: requested stake capture `+95.42%`; average active-day exposure `+25.16%`; bet-cap days `7/142`
- Close-quality coverage: spread close EV `253/253`
- Next action: verify the close-market coverage table before promoting new structural model changes.

## Assessment

The current deployable path is positive across the full window, but season-to-season stability is mixed.

- Aggregate result: `+$639.53` on `253` bets, ROI `+9.47%`
- Aggregate CLV: `23/253` positive, `+9.09%`, `-0.69 pts` spread line, `+2.18 pp` spread price, `+1.94 pp` spread no-vig, `+0.186` spread close EV
- Close-market coverage: spread close EV `253/253`
- Latest season `2026`: `+$179.16`, ROI `+13.98%`
- Latest season CLV: `3/43` positive, `+6.98%`, `-1.08 pts` spread line, `+3.15 pp` spread price, `+2.84 pp` spread no-vig, `+0.093` spread close EV
- Stake sizing: average `+$26.68`, median `+$24.30`, smallest `+$15.12`, largest `+$75.18`
- Capital deployment: requested stake capture `+95.42%`, average active-day exposure `+25.16%`, peak active-day exposure `+96.78%`, average bets per active day `1.78`, bet-cap days `7`, exposure-cap days `0`
- Official availability: `Shadow only`. Coverage is stored for `468` games, `7328` status rows, `4409` unmatched. It is not consumed by the live or backtest model paths.
- Best season: `2023` with `+$334.41`
- Worst season: `2024` with `-$137.91`
- Zero-bet seasons: `none`

## Capital Deployment

| Metric | Value | Notes |
| --- | --- | --- |
| Active betting days | `142/142` | Days with at least one settled bet after bankroll limits. |
| Requested stake capture | `+95.42%` | Placed stake divided by requested Kelly stake across qualified candidates. |
| Average active-day exposure | `+25.16%` | Average share of the daily exposure cap used on active days. |
| Peak active-day exposure | `+96.78%` | Largest single-day share of the daily exposure cap that was used. |
| Average bets per active day | `1.78` | Mean number of placed bets on days where the strategy was active. |
| Days hitting bet cap | `7` | Days where more qualified bets existed than the same-day cap allowed. |
| Days hitting exposure cap | `0` | Days where the daily exposure limit clipped or blocked additional stake. |
| Clipped bets | `0` | Placed bets whose requested stake was reduced by the daily exposure cap. |
| Bets skipped by bet cap | `18` | Qualified bets left unplaced because the same-day cap was already full. |

## Five-Slot Selection Pressure

These diagnostics compare the bets that actually filled the five-slot portfolio on cap-hit days against the additional qualified bets that were skipped because the cap was already full.

| Group | Candidates | Avg EV | Avg Prob Edge | Avg Pos-EV Books | Avg Median EV | Avg Coverage | Avg Book Depth | Equal-Stake ROI | Close quality |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Cap-day placed | 35 | 0.078 | 0.060 | 11.00 | 0.035 | +91.84% | 12.06 | +10.94% | `5/35` positive, `+14.29%`, `-0.53 pts` spread line, `+2.05 pp` spread price, `+1.81 pp` spread no-vig, `+0.103` spread close EV |
| Skipped by bet cap | 18 | 0.047 | 0.045 | 9.67 | 0.015 | +78.08% | 12.78 | +20.26% | `3/18` positive, `+16.67%`, `-0.39 pts` spread line, `+1.59 pp` spread price, `+1.43 pp` spread no-vig, `+0.017` spread close EV |

### Expected Value Buckets

| Value | Placed | Placed Share | Skipped | Skipped Share |
| --- | ---: | ---: | ---: | ---: |
| `ev_10_plus` | 6 | +17.14% | 0 | 0.00% |
| `ev_4_to_6` | 8 | +22.86% | 18 | +100.00% |
| `ev_6_to_8` | 13 | +37.14% | 0 | 0.00% |
| `ev_8_to_10` | 8 | +22.86% | 0 | 0.00% |

### Probability Edge Buckets

| Value | Placed | Placed Share | Skipped | Skipped Share |
| --- | ---: | ---: | ---: | ---: |
| `edge_4_to_6` | 19 | +54.29% | 18 | +100.00% |
| `edge_6_to_8` | 15 | +42.86% | 0 | 0.00% |
| `edge_8_to_10` | 1 | +2.86% | 0 | 0.00% |

### Season Phase

| Value | Placed | Placed Share | Skipped | Skipped Share |
| --- | ---: | ---: | ---: | ---: |
| `established` | 35 | +100.00% | 18 | +100.00% |

### Line Bucket

| Value | Placed | Placed Share | Skipped | Skipped Share |
| --- | ---: | ---: | ---: | ---: |
| `priced_range` | 8 | +22.86% | 9 | +50.00% |
| `tight` | 27 | +77.14% | 9 | +50.00% |

### Book Depth

| Value | Placed | Placed Share | Skipped | Skipped Share |
| --- | ---: | ---: | ---: | ---: |
| `high_depth` | 34 | +97.14% | 18 | +100.00% |
| `mid_depth` | 1 | +2.86% | 0 | 0.00% |

### Same-Conference Mix

| Value | Placed | Placed Share | Skipped | Skipped Share |
| --- | ---: | ---: | ---: | ---: |
| `nonconference` | 6 | +17.14% | 3 | +16.67% |
| `same_conference` | 26 | +74.29% | 14 | +77.78% |
| `unknown` | 3 | +8.57% | 1 | +5.56% |

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2022` | 12 | +$110.53 | +34.04% | +4.42u | +1.26% | 8-4-0 | `0/12` positive, `0.00%`, `-0.80 pts` spread line, `+1.25 pp` spread price, `+1.08 pp` spread no-vig, `+1.946` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2023` | 35 | +$334.41 | +32.36% | +13.38u | +2.32% | 22-12-1 | `5/35` positive, `+14.29%`, `-0.41 pts` spread line, `+1.51 pp` spread price, `+1.26 pp` spread no-vig, `+0.141` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2024` | 107 | -$137.91 | -5.48% | -5.52u | +4.81% | 48-58-1 | `10/107` positive, `+9.35%`, `-0.59 pts` spread line, `+2.08 pp` spread price, `+1.88 pp` spread no-vig, `+0.077` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 56 | +$153.35 | +9.61% | +6.13u | +3.34% | 30-26-0 | `5/56` positive, `+8.93%`, `-0.75 pts` spread line, `+2.25 pp` spread price, `+1.96 pp` spread no-vig, `+0.117` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 43 | +$179.16 | +13.98% | +7.17u | +2.95% | 24-19-0 | `3/43` positive, `+6.98%`, `-1.08 pts` spread line, `+3.15 pp` spread price, `+2.84 pp` spread no-vig, `+0.093` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, uncertainty_probability_buffer=0.0075, min_games_played=8, kelly_fraction=0.100, max_bet_fraction=0.020, max_daily_exposure_fraction=0.050, min_positive_ev_books=4, max_bets_per_day=5, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5 | 253 | +$639.53 | +9.47% | +25.58u | +4.81% | 4/5 |

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
| Covered side report | 3 | 2-1-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched official report exists for the bet side. Insufficient sample below 5 settled bets. |
| Fully covered matchup | 2 | 1-1-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Both team sides had latest matched official reports available. Insufficient sample below 5 settled bets. |
| Uncovered side report | 250 | 130-118-2 | +$589.65 | +8.85% | `22/250` positive, `+8.80%`, `-0.69 pts` spread line, `+2.16 pp` spread price, `+1.92 pp` spread no-vig, `+0.188` spread close EV | No matched official report exists for the bet side. |

### Status Flags

Status flags use the latest matched official reports only. They do not weight player importance or lineup value.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| Side has any out | 3 | 2-1-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side report includes at least one `out`. Insufficient sample below 5 settled bets. |
| Side has any questionable | 2 | 1-1-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side report includes at least one `questionable`. Insufficient sample below 5 settled bets. |
| Opponent has any out | 2 | 1-1-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched opponent report includes at least one `out`. Insufficient sample below 5 settled bets. |
| Opponent has any questionable | 1 | 0-1-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched opponent report includes at least one `questionable`. Insufficient sample below 5 settled bets. |

### Latest Update Timing

Timing buckets use the latest matched side update relative to tip when the stored timing fields support it.

| Slice | Bets | W-L-P | Profit | ROI | Close quality | Notes |
| --- | ---: | --- | ---: | ---: | --- | --- |
| After tip | 1 | 1-0-0 | `insufficient sample` | `insufficient sample` | `insufficient sample` | Latest matched side update timestamp landed after the stored tip time. Insufficient sample below 5 settled bets. |

## Close-Market Coverage

| Metric | Tracked | Missing / Unmatched | Notes |
| --- | ---: | ---: | --- |
| Spread line CLV | 253/253 (+100.00%) | 0/253 (0.00%) | Missing when no closing spread line can be matched. |
| Spread price CLV | 253/253 (+100.00%) | 0/253 (0.00%) | Tracks executable price movement against the stored close. |
| Spread no-vig close delta | 253/253 (+100.00%) | 0/253 (0.00%) | Uses the stored closing consensus after removing vig. |
| Spread closing EV | 253/253 (+100.00%) | 0/253 (0.00%) | Most direct execution-quality check for qualified spread bets. |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2022` | 12 | 0 | 0 | 12 | 0.00% | -0.80 pts | +1.25 pp | +1.08 pp | +1.946 | none |
| `2023` | 35 | 5 | 0 | 30 | +14.29% | -0.41 pts | +1.51 pp | +1.26 pp | +0.141 | none |
| `2024` | 107 | 10 | 5 | 92 | +9.35% | -0.59 pts | +2.08 pp | +1.88 pp | +0.077 | none |
| `2025` | 56 | 5 | 0 | 51 | +8.93% | -0.75 pts | +2.25 pp | +1.96 pp | +0.117 | none |
| `2026` | 43 | 3 | 0 | 40 | +6.98% | -1.08 pts | +3.15 pp | +2.84 pp | +0.093 | none |
| Aggregate | 253 | 23 | 5 | 225 | +9.09% | -0.69 pts | +2.18 pp | +1.94 pp | +0.186 | none |

## Spread Segment Attribution

### Expected Value Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 113 | +44.66% | -$152.54 | -6.86% | +0.049 |
| `8% to 10%` | 29 | +11.46% | +$144.24 | +15.32% | +0.179 |
| `10%+` | 29 | +11.46% | +$491.97 | +35.10% | +0.189 |
| `6% to 8%` | 82 | +32.41% | +$155.87 | +7.14% | +0.377 |

### Probability Edge Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `4% to 6%` | 184 | +72.73% | -$246.26 | -6.00% | +0.133 |
| `8% to 10%` | 8 | +3.16% | +$194.31 | +50.42% | +0.161 |
| `10%+` | 6 | +2.37% | +$31.31 | +7.94% | +0.191 |
| `6% to 8%` | 55 | +21.74% | +$660.17 | +35.39% | +0.368 |

### Season Phase

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Established` | 253 | +100.00% | +$639.53 | +9.47% | +0.186 |

### Line Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Priced Range` | 79 | +31.23% | +$248.27 | +12.29% | +0.071 |
| `Tight` | 174 | +68.77% | +$391.26 | +8.27% | +0.238 |

### Book Depth

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Mid Depth` | 5 | +1.98% | -$74.78 | -67.78% | +0.052 |
| `High Depth` | 208 | +82.21% | +$309.65 | +5.64% | +0.091 |
| `Low Depth` | 40 | +15.81% | +$404.65 | +35.15% | +0.699 |

### Venue Context

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Neutral Site` | 34 | +13.44% | +$193.23 | +18.55% | +0.066 |
| `Home Venue` | 219 | +86.56% | +$446.30 | +7.82% | +0.205 |

### Travel Bucket

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Long Trip` | 14 | +5.58% | +$56.46 | +16.00% | +0.078 |
| `Regional Trip` | 68 | +27.09% | +$357.76 | +19.32% | +0.100 |
| `Local Trip` | 169 | +67.33% | +$230.16 | +5.12% | +0.232 |

### Timezone Crossings

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `One Timezone` | 25 | +9.96% | +$83.36 | +11.26% | +0.064 |
| `Two+ Timezones` | 7 | +2.79% | +$58.70 | +32.94% | +0.100 |
| `Same Timezone` | 219 | +87.25% | +$502.32 | +8.68% | +0.204 |

### Conference Matchup

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Same Conference` | 206 | +84.43% | +$375.75 | +6.81% | +0.095 |
| `Non-Conference` | 38 | +15.57% | +$219.99 | +22.16% | +0.703 |

### Conference Group

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `Unknown` | 5 | +1.98% | -$11.40 | -8.55% | +0.057 |
| `Other` | 248 | +98.02% | +$650.93 | +9.84% | +0.189 |

### Tip Window

| Segment | Bets | Share | Profit | ROI | Avg Spread Closing EV |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0 to 6h` | 253 | +100.00% | +$639.53 | +9.47% | +0.186 |


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
