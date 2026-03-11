# Best Model Backtest Report

Generated: `2026-03-10T21:17:38-04:00`
Output: `docs/results/best-model-3y-backtest.md`
History Copy: `docs/results/history/best-model-3y-backtest_20260310_211738.md`

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

- Aggregate result: `+$216.48` on `718` bets, ROI `+4.24%`
- Aggregate CLV: `106/718` positive, `+14.76%`, `-0.39 pts` spread line, `+1.74 pp` spread price, `+1.44 pp` spread no-vig, `+0.069` spread close EV
- Latest season `2026`: `+$208.36`, ROI `+10.54%`
- Latest season CLV: `27/261` positive, `+10.34%`, `-0.43 pts` spread line, `+1.77 pp` spread price, `+1.44 pp` spread no-vig, `+0.071` spread close EV
- Best season: `2026` with `+$208.36`
- Worst season: `2024` with `-$116.38`
- Zero-bet seasons: `none`

## Season Results

| Season | Bets | Profit | ROI | Units | Max Drawdown | Wins-Losses-Pushes | CLV | Final Policy |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| `2024` | 215 | -$116.38 | -9.14% | -4.66u | +14.87% | 99-115-1 | `40/215` positive, `+18.60%`, `-0.38 pts` spread line, `+1.69 pp` spread price, `+1.44 pp` spread no-vig, `+0.050` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2025` | 242 | +$124.50 | +6.72% | +4.98u | +8.51% | 132-107-3 | `39/242` positive, `+16.12%`, `-0.35 pts` spread line, `+1.76 pp` spread price, `+1.44 pp` spread no-vig, `+0.084` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |
| `2026` | 261 | +$208.36 | +10.54% | +8.33u | +8.60% | 148-113-0 | `27/261` positive, `+10.34%`, `-0.43 pts` spread line, `+1.77 pp` spread price, `+1.44 pp` spread no-vig, `+0.071` spread close EV | `min_edge=0.040, min_confidence=0.518, min_probability_edge=0.040, min_games_played=8, min_positive_ev_books=2, min_median_expected_value=none, max_spread_abs_line=10.0, max_abs_rest_days_diff=3.0` |

## Aggregate

| Seasons | Bets | Profit | ROI | Units | Max Drawdown | Profitable Seasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3 | 718 | +$216.48 | +4.24% | +8.66u | +14.87% | 2/3 |

## Closing-Line Value

| Season | Bets Tracked | Positive | Neutral | Negative | Positive Rate | Avg Spread Line CLV | Avg Spread Price CLV | Avg Spread No-Vig Close Delta | Avg Spread Closing EV | Avg Moneyline CLV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `2024` | 215 | 40 | 15 | 160 | +18.60% | -0.38 pts | +1.69 pp | +1.44 pp | +0.050 | none |
| `2025` | 242 | 39 | 17 | 186 | +16.12% | -0.35 pts | +1.76 pp | +1.44 pp | +0.084 | none |
| `2026` | 261 | 27 | 19 | 215 | +10.34% | -0.43 pts | +1.77 pp | +1.44 pp | +0.071 | none |
| Aggregate | 718 | 106 | 51 | 561 | +14.76% | -0.39 pts | +1.74 pp | +1.44 pp | +0.069 | none |

## Notes

- `best` is the current deployable spread-only path when a spread artifact is available. Moneyline is only used when spread cannot train or load.
- When the timing layer is enabled, spread bets are evaluated from a six-hour pre-tip snapshot and only early bets with favorable predicted closing-line movement are kept.
- CLV is measured against the stored closing consensus. Spread now tracks line delta, raw price delta, no-vig close delta, and model EV at the close quote; moneyline tracks normalized implied-probability delta.
- The positive/neutral/negative CLV counts still use spread line movement for spread bets and no-vig close delta for moneyline bets. The added spread price and close-EV columns are supplemental execution measurements.
- When a backtest scores the closing snapshot itself, spread line CLV should be near-neutral, but price CLV and closing EV can still move because the executable quote and the stored close consensus are not always identical.
- A `0`-bet season means the active policy did not find qualifying opportunities in that season.
- Refresh this report with `cbb model report`.
