# Model Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-5y-backtest.md)

Updated: `2026-03-28`

## Goal

This cycle is now post-repair card shaping for the deployable `best` path.

The repaired historical market dataset already changed the incumbent and the
current report shows the remaining deployable bottleneck inside the same-day
five-bet card, not in bankroll width. The next repo-local questions are:

- whether the bankroll-applied same-day ordering is still choosing the best
  five bets after the repaired-data recalibration pass
- whether the cap-day skipped tail contains avoidable weak bets that can be
  removed or demoted with existing candidate fields
- whether any ranking-only/card-shaping change can improve realized results
  without widening Kelly or daily exposure
- whether the next credible move remains inside ranking/card shaping or has to
  move back to a new-information lane

The evaluation bar stays the same:

- protect long-run ROI
- protect stability across seasons
- do not widen drawdown materially
- do not promote changes based only on the latest season
- keep live prediction, backtest, and report behavior aligned
- require the challenger to stay at least as credible on close-quality
  evidence, especially spread price delta, no-vig close delta, and spread
  closing EV

## Current Repo State

The repo now has materially stronger stored market data than the earlier
spread-policy cycle, and the repaired dataset is now the only valid baseline
for promotion work:

- `17499` stored games, `17439` completed games, and `509532` stored odds
  snapshots in the live local database
- historical closing coverage now spans all three featured markets used by the
  modeling layer:
  - `h2h`: `156364` closing snapshots across `77` books and `15386` games
  - `spreads`: `165968` closing snapshots across `56` books and `15377` games
  - `totals`: `168736` closing snapshots across `57` books and `15389` games
- broader current-odds coverage is also in place, so upcoming-book support is
  no longer as thin as the earlier deployable-policy search assumed

The core model stack already consumes much of that market information:

- [src/cbb/modeling/features.py](../src/cbb/modeling/features.py) already
  includes open/close consensus, dispersion, book counts, weighted quote
  profiles, and spread/h2h/totals interaction terms
- [src/cbb/modeling/execution.py](../src/cbb/modeling/execution.py),
  [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py), and
  [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) already expose
  cross-book survivability controls through `min_positive_ev_books` and
  `min_median_expected_value`
- the deployable spread baseline now uses a stricter survivability floor:
  `min_positive_ev_books=4`, no Kelly widening, and a five-bet same-day cap
- the current report still shows the main deployment bottleneck inside that
  cap, not in raw bankroll width:
  `76.79%` requested stake capture, `40.67%` average active-day exposure,
  `32` bet-cap days, `2` exposure-cap days, and `163` qualified bets skipped by
  the same-day cap
- the cap-day diagnostics show the placed side is still stronger overall than
  the skipped tail:
  placed bets average `+0.077` EV, `+0.033` median EV, `91.97%` coverage, and
  `+0.091` spread close EV, while skipped bets average `+0.052` EV,
  `+0.024` median EV, `89.15%` coverage, and `+0.033` spread close EV
- that means the next lane is not "widen the card" or "widen bankroll", but
  to test whether the same-day five-slot ordering is using the right score once
  the repaired-data support fields are already available

What the current stored history does not obviously support yet:

- a rich new opening-depth feature lane; the current stored history appears to
  have nearly identical open-vs-close bookmaker breadth on most completed-game
  records
- a promoted travel-input lane; the repo now has a tracked team home-location
  catalog and travel/timezone diagnostics, but the first direct feature
  challenger did not clear the promotion bar
- deployable official availability features; that lane remains shadow-only and
  sample-limited

## Why The Next Promotion Attempt Should Be Card-Shaping Driven

The repaired-data reoptimization already improved the baseline materially. The
next credible repo-local move is not more calibration churn or bankroll
widening; it is to improve which bets make the five-slot same-day card.

The current best path still shows the repo's main signal:

- spread line CLV is still negative, but spread price delta, no-vig close
  delta, and spread closing EV are positive
- that means the remaining edge still looks more execution- and
  calibration-driven than raw line prediction-driven
- the report shows requested stake capture is still below full deployment, but
  daily exposure is not the real cap; the bet cap is the binding constraint on
  materially more days than the exposure cap
- the current code also still uses a simpler pure-EV sort inside
  [apply_bankroll_limits_with_diagnostics()](../src/cbb/modeling/policy.py)
  than the support-aware candidate ordering used earlier in the selection path
- that makes same-day card ordering the highest-confidence repo-local lane to
  test before opening any new model or data lane

Availability and travel remain lower-priority for this cycle:

- stored availability is still shadow-only and sample-limited
- the retained home-location foundation is now good enough for diagnostics, but
  the first direct travel-feature challenger failed on full-window evidence
- neither lane should displace a ranking/card-shaping loop unless the current
  selection-first experiments fail clearly

## Data Repair Status

This run also included a bounded historical-odds repair loop because the live
DB still had too many completed games with no usable pregame priced market.

Baseline before repair:

- completed games: `17439`
- games with no pregame snapshot before tip: `2049`
- games missing `h2h`: `2059`
- games missing `spreads`: `2088`
- games missing `totals`: `2049`
- gap shape:
  `2049` no snapshots at all, `47` games with pregame data but at least one
  market still missing

Final state after the bounded repair loop:

- games with no pregame snapshot before tip: `2031`
- games missing `h2h`: `2043`
- games missing `spreads`: `2052`
- games missing `totals`: `2049`
- recovered in this run:
  `18` no-pregame games, `16` h2h gaps, and `36` spread gaps
- remaining no-pregame gaps are still concentrated in `1504` checkpointed
  historical snapshot slots across all three featured markets, which is now
  strong evidence that the large residual bucket is mostly provider-limited or
  would require a more aggressive historical timing design than this bounded
  loop justified

### D-1 [`approved` -> `completed`] Alias-aware historical outcome matching

Problem:

- provider outcome names such as `Michigan St` versus stored canonical names
  such as `Michigan State` could leave one side of a recovered quote unset even
  when the event itself matched

Implementation:

- [src/cbb/ingest/persistence.py](../src/cbb/ingest/persistence.py) now maps
  historical `h2h` and `spreads` outcomes by team aliases instead of exact
  string equality only

Why this was approved:

- no schema change
- no fabricated prices or lines
- directly improves recoverability from already returned provider payloads

### D-2 [`approved` -> `completed`] Previous-snapshot fallback plus swapped historical event matching

Problem:

- exact tip-time historical requests were being checkpointed even when they
  produced no match, and neutral-site/home-away reversals could still prevent a
  correct event from linking back to the stored game row

Implementation:

- [src/cbb/ingest/closing_lines.py](../src/cbb/ingest/closing_lines.py) now:
  - retries the provider's `previous_timestamp` once when the exact request
    leaves unmatched candidates
  - caches repeated historical request times within one run so fallback windows
    are not refetched unnecessarily
  - allows swapped team-pair matching while still persisting prices in stored
    `team1/team2` orientation
- [src/cbb/ingest/clients/odds_api.py](../src/cbb/ingest/clients/odds_api.py)
  now retries transient `429/5xx` provider failures with bounded backoff

Why this was approved:

- no schema change
- preserves checkpoint semantics on the original slot while still giving the
  repair path one bounded second chance
- explicitly targeted the largest no-credit-repairable miss bucket before
  broader spend

### D-3 [`approved` -> `completed`] Bounded live repair windows

Commands executed:

- `cbb ingest closing-odds --start-date 2026-03-01 --end-date 2026-03-13 --market h2h --regions us,us2,uk,eu,au --ignore-checkpoints`
- `cbb ingest closing-odds --start-date 2023-03-08 --end-date 2023-03-17 --market spreads --regions us,us2,uk,eu,au --ignore-checkpoints`
- day-by-day `h2h` repairs for:
  `2026-03-10`, `2025-11-04`, `2023-11-07`, `2023-11-10`, `2023-11-18`,
  `2023-12-02`, `2023-12-30`
- `cbb ingest closing-odds --start-date 2023-11-18 --end-date 2023-11-18 --market spreads --regions us,us2,uk,eu,au --ignore-checkpoints`
- `cbb ingest closing-odds --start-date 2023-11-18 --end-date 2023-11-18 --market totals --regions us,us2,uk,eu,au --ignore-checkpoints`

Measured recovery:

- March 2026 `h2h` broad no-pregame bucket:
  `48` candidates, `1` matched, `4050` credits spent
- March 2023 missing-spreads bucket:
  `31` candidates, `24` matched, `1650` credits spent
- targeted h2h tail across seven day windows:
  `83` candidates, `15` matched, `4900` credits spent
- `2023-11-18` spreads:
  `23` candidates, `12` matched, `1250` credits spent
- `2023-11-18` totals:
  `23` candidates, `12` matched, `1250` credits spent

Total spend and quota state:

- credits spent this run: `13100`
- quota after final command:
  `used=593834`, `remaining=4406166`, total monthly limit `5000000`
- current usage share:
  `11.88%`
- headroom before the `70%` stop line:
  `2906166` credits

### D-4 [`deferred`] Broad rerun of the remaining no-pregame bucket

Why it is deferred:

- after the repair logic landed, the large residual no-pregame bucket still
  sat in `1504` already-checkpointed broad-region slots
- the first broad re-run on the recent March 2026 window recovered only
  `1/48` candidate games, which is too weak to justify a blind all-history
  expansion

Conclusion:

- the remaining no-pregame bucket is now more likely provider-limited than
  logic-limited
- any future attempt should target a demonstrably high-yield date/market slice,
  not another sweeping replay

## Current Baseline

The deployable baseline is still the spread-first `best` path documented in
[docs/results/best-model-5y-backtest.md](results/best-model-5y-backtest.md).

The key modeling paths remain:

- training: [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- dataset loading: [src/cbb/modeling/dataset.py](../src/cbb/modeling/dataset.py)
- feature generation: [src/cbb/modeling/features.py](../src/cbb/modeling/features.py)
- backtesting: [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- policy: [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- prediction: [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py)
- canonical reporting: [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)

Interpretation of the current baseline is now:

- aggregate: `253` bets, `+$639.53`, ROI `+9.47%`, max drawdown `4.81%`
- `2022`: `12` bets, `+$110.53`, ROI `+34.04%`
- `2023`: `35` bets, `+$334.41`, ROI `+32.36%`
- `2024`: `107` bets, `-$137.91`, ROI `-5.48%`
- `2025`: `56` bets, `+$153.35`, ROI `+9.61%`
- `2026`: `43` bets, `+$179.16`, ROI `+13.98%`
- aggregate spread close quality:
  `-0.69 pts` line CLV, `+2.18 pp` price delta, `+1.94 pp` no-vig close delta,
  `+0.186` spread closing EV
- capital usage:
  `95.42%` requested stake capture, `25.16%` average active-day exposure,
  `7` bet-cap days, `0` exposure-cap days
- the main repaired-data issue is now recent-season action collapse rather than
  the five-slot same-day card

## Current Card-Shaping Loop

### C-1 [`approved` -> `rejected`] Replace pure-EV same-day card ordering with the existing support-aware candidate score

**Hypothesis**

The deployable path already computes cross-book support fields such as coverage
rate, positive-EV book count, and median expected value, but the final
same-day bankroll step still fills the five-slot card by raw expected value
first. Reusing the support-aware candidate order at that cap should improve the
cap-hit days without widening bankroll settings.

**Implementation sketch**

- Add a replay-safe research toggle in
  [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py) and
  [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py) so the
  day-level bankroll sort can be switched between the incumbent pure-EV order
  and the existing support-aware candidate order
- Keep the change ranking-only; do not touch Kelly, max daily exposure, or the
  five-bet cap
- Add a direct policy test that proves day-level bet-cap ordering now respects
  support-first candidate ranking

**Why this was approved**

- it targets the exact five-slot bottleneck shown by the canonical report
- it uses fields the deployable path already computes and surfaces
- it is the smallest behavior change that can improve which bets survive the
  cap without widening action

**Outcome**

- the code-path mismatch remains real in the incumbent:
  upstream selection is support-aware, but the deployable five-slot cap still
  defaults to the simpler pure-EV bankroll sort
- a replay-safe research surface now exists in
  [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py),
  [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py), and
  [tests/test_modeling.py](../tests/test_modeling.py) so the challenger can be
  rerun without editing the incumbent default
- `2026` gate improved:
  incumbent `121` bets, `+$275.14`, `+9.01%` ROI, max drawdown `5.35%`,
  `+2.09 pp` price delta, `+1.76 pp` no-vig delta, `+0.076` close EV
  became `121` bets, `+$316.77`, `+10.41%` ROI, max drawdown `5.35%`,
  `+2.03 pp` price delta, `+1.68 pp` no-vig delta, and `+0.072` close EV
- full-window promotion failed immediately on the weakest season:
  the canonical report run finished `2024` at `123` bets, `-$386.46`,
  `-13.69%` ROI versus the incumbent `123` bets, `-$197.31`, `-6.51%` ROI
- because that regression materially worsened the weakest season, the report
  run was stopped, the code change was reverted, and the incumbent remained the
  deployable baseline

**Conclusion**

- reject support-aware same-day reranking as the default five-slot card policy
  on the repaired dataset
- the current pure-EV day order appears to be part of the incumbent's
  cross-season robustness, even though the support-aware version improved the
  latest-season gate

### C-2 [`deferred`] Add a bounded median-EV tie-break or weak-tail penalty inside the five-slot sort

This is deferred after `C-1` failed. The current placed-versus-skipped report
still shows the skipped tail is weaker overall, and a stronger support-aware
day sort already made the weakest season materially worse. A median-EV or
weak-tail penalty is now a higher-risk version of the same card-shaping idea,
not an independently justified approved item.

### C-3 [`deferred`] Replay `max_bets_per_day=6` against the repaired-data incumbent

This is deferred for now because the current cap-day diagnostics still show
placed bets outperforming skipped bets overall, so another widen-the-card replay
is lower value than improving the ranking inside the existing five-slot card.
`C-1` also strengthened the case against widening: a same-day selection change
that helped `2026` still broke `2024`, so the skipped tail still does not look
like a safe promotion lane by itself.

### C-4 [`deferred`] Open another information lane before card shaping is exhausted

Travel/home-location and availability stay deferred in this cycle unless the
ranking/card-shaping experiments fail clearly and leave no credible repo-local
selection work behind. After `C-1`, that is now the most likely next move.

## Previously Completed Reoptimization Work

### R-1 [`approved` -> `completed`] Simplify and retune spread calibration / residual overrides for repaired-data stability

**Hypothesis**

The repaired dataset may have shifted the calibration regime enough that the
current spread override stack is now too aggressive or too segmented. Positive
close EV with a materially negative `2024` season is consistent with stale
probability calibration or residual-scale selection on the repaired
distribution.

**Implementation sketch**

- Add bounded, explicit repaired-data challengers around the spread calibration
  and residual-selection seams in
  [src/cbb/modeling/train.py](../src/cbb/modeling/train.py), especially:
  `_select_spread_line_calibrations()`,
  `_select_spread_conference_calibrations()`,
  `_select_spread_season_phase_calibrations()`,
  `_select_spread_line_residual_scales()`,
  `_select_spread_season_phase_residual_scales()`, and
  `_select_spread_book_depth_residual_scales()`.
- Test simpler variants that reduce or disable some repaired-data overrides
  rather than automatically assuming more segmentation is better.
- Keep artifact loading backward compatible if new toggles are stored.

**Expected impact**

- best chance to reduce overconfident repaired-data bets while keeping the
  existing market-signal edge
- directly targets the current "positive close EV, weak realized season"
  mismatch

**Risks**

- could wash out genuine edge in `2025` and `2026`
- easy to overfit if too many segmented variants are added at once

**Validation plan**

- first compare repaired-data walk-forward challengers with the same deployable
  policy
- then rerun the canonical report for any serious challenger

**Promotion / rejection criteria**

- promote only if the simpler or retuned calibration stack improves aggregate
  performance and weak-season stability without materially weakening close
  quality

**Outcome**

- completed in
  [src/cbb/modeling/train.py](../src/cbb/modeling/train.py) and
  [tests/test_modeling.py](../tests/test_modeling.py), with an additional
  repaired-data stability adjustment in
  [src/cbb/modeling/features.py](../src/cbb/modeling/features.py) and
  [tests/test_features.py](../tests/test_features.py)
- specialized spread line, conference, and season-phase calibration overrides
  now require a chronological holdout win over the default spread calibration
  before they survive into the artifact
- this made the repaired-data spread calibration stack more conservative
  without changing the core margin-regression family
- spread bookmaker-quality weighting is now also more stable when history is
  thin, using a heavier spread prior and bounded spread-quality transform so
  repaired sparse-book history cannot swing weighted spread quote features as
  aggressively
- the refreshed canonical report improved the deployable baseline from
  `+$787.71`, `+5.73%` ROI, max drawdown `13.00%` to
  `+$905.30`, `+7.94%` ROI, max drawdown `8.06%`
- `2024` improved from `-$294.86` to `-$197.31` while `2025` and `2026`
  remained positive

### R-2 [`approved` -> `completed`] Expand repaired-data spread policy reoptimization beyond the old auto-tune grid

**Hypothesis**

The current deployable thresholds were promoted against the pre-repair dataset,
and the built-in spread policy search now covers too little of the real live
policy surface to be trusted as the only reoptimization path.

**Implementation sketch**

- Extend the spread replay grid in
  [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py) so bounded
  repaired-data policy search can also test existing deployable controls such
  as `min_positive_ev_books` and the spread
  `uncertainty_probability_buffer`, not just the older
  `min_edge` / `min_confidence` / `min_probability_edge` sweep.
- Keep `kelly_fraction` and `max_daily_exposure_fraction` fixed unless a later
  challenger clears a much higher evidence bar.
- Keep the five-bet cap as the default starting point and only retest it if a
  broader repaired-data policy challenger clearly requires that comparison.

**Expected impact**

- best chance to repair the `2024` weakness without inventing new data
- could recover aggregate ROI by trimming repaired-data tails the pre-repair
  thresholds now admit too often

**Risks**

- overfitting to repaired-data noise if the grid gets too wide
- collapsing activity if support and uncertainty controls are tightened too far

**Validation plan**

- run a bounded `2026` walk-forward gate first
- then run the full canonical five-season report only for serious challengers
- compare aggregate and per-season profit, ROI, drawdown, bet count, and close
  quality against the repaired-data incumbent

**Promotion / rejection criteria**

- promote only if the challenger improves aggregate performance without
  materially sacrificing `2025` or `2026`, and ideally reduces the `2024`
  damage materially
- reject if it only improves close quality while realized profit and season
  stability remain worse

**Outcome**

- completed in
  [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py) and
  [tests/test_backtest_reoptimization.py](../tests/test_backtest_reoptimization.py)
- the spread auto-tuner now:
  - builds replayable candidate blocks with relaxed tuning guards
  - sweeps the existing threshold grid
  - adds a bounded support-control pass for `min_positive_ev_books` and
    `min_median_expected_value`
  - runs one final threshold-refinement pass around the best replayable
    challenger
- bounded repaired-data challengers showed that the easy survivability-only
  fixes do not solve the problem by themselves:
  - `min_positive_ev_books=5` exactly reproduced the old `2024` result
  - adding `min_median_expected_value=0.005` or a stricter
    `min_positive_ev_books=6`, `min_median_expected_value=0.010` floor made
    `2024` worse
- the broader tuner is now a better research/comparison path, but this loop's
  promoted improvement still came from the deployable baseline after the model-
  stability fixes rather than from promoting a new fixed threshold set

### R-4 [`approved` -> `completed`] Add explicit 2024-failure diagnostics before promoting repaired-data challengers

**Hypothesis**

The report already shows aggregate segment attribution, but the post-repair
promotion problem is specifically the `2024` regression. The repo needs one
explicit, reusable way to compare that season's placed bets against the stronger
`2025` / `2026` cohorts before a new challenger is promoted.

**Implementation sketch**

- Extend [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py) and
  [src/cbb/modeling/report.py](../src/cbb/modeling/report.py) with per-season
  spread segment attribution or a season-comparison diagnostic focused on
  placed-bet mix and weak tails.
- Keep it additive and report-only; do not change live behavior by itself.
- Use it to judge whether a repaired-data challenger fixes the right problem or
  just shifts profit between already-good seasons.

**Expected impact**

- makes the `2024` regression explainable enough to approve or reject
  challengers more quickly

**Risks**

- report complexity rises
- diagnostics alone do not improve the model unless the implementation loop
  uses them

**Validation plan**

- targeted report/backtest tests
- verify the new diagnostics align with current aggregate season totals

**Promotion / rejection criteria**

- this item is support work; it is complete when the repaired-data regression is
  diagnosable from canonical report output without ad hoc queries

**Outcome**

- the current canonical report/backtest surface was sufficient for this pass:
  - per-season season tables exposed the repaired-data `2024` weakness directly
  - `Five-Slot Selection Pressure` exposed the placed-versus-skipped cap-day
    mix
  - expected-value bucket diagnostics highlighted the non-monotonic repaired-
    data tail that kept pointing back toward calibration and feature stability
- no new report contract was required to promote or reject the challengers in
  this loop

## Completed

### A-1 [`completed`] Official NCAA availability storage foundation

The repo now stores source-specific official NCAA availability report snapshots
and normalized player-status rows with replayable payloads, provenance, timing,
dedupe keys, and explicit unmatched linkage handling.

### A-2 [`completed`] Replayable local import workflow

The repo now supports deterministic file-based import through
[src/cbb/ingest/availability.py](../src/cbb/ingest/availability.py) and
`cbb ingest availability ...`.

### A-3 [`completed`] Shadow-only report and dashboard visibility

The canonical report and dashboard snapshot now expose high-level availability
shadow coverage without changing live prediction, backtest, or staking
behavior.

### A-4 [`completed`] Persist queryable official timing fields needed for shadow analysis

The repo now persists official `effective_at` and row `source_updated_at` when
the upstream source provides them, and the shadow readers now prefer those
official fields over capture-time fallbacks.

### A-5 [`completed`] Build a game-side availability shadow read model for analysis

The repo now exposes game-side availability summaries through
[src/cbb/db.py](../src/cbb/db.py), and the canonical report uses that read
model for coverage and status slices.

### A-6 [`completed`] Add availability-enriched evaluation slices to the canonical report

The canonical report now renders shadow-only coverage and status slices for the
current best-path backtest without changing the headline deployable metrics.

### A-11 [`completed`] Expand the shadow lane with wrapped free-source conference archives

The repo can now import wrapped HD Intelligence archive captures for ACC,
Atlantic 10, Big 12, Big East, Big Ten, MVC, SEC, and NCAA-style sources
through the same `cbb ingest availability ...` command.

### S-2 [`completed`] Raise the default notional bankroll and surface stake ranges

Completed on `2026-03-13`.

The parent task explicitly approved a safer operator-facing sizing change:
leave Kelly and exposure percentages alone, but raise the default notional
bankroll from `+$1,000.00` to `+$3,750.00` so the current best-path stake
profile lands around one `$25` unit by default.

This cycle also adds explicit stake-range visibility to the canonical report
and dashboard so operators can see the typical, smallest, and largest settled
bet sizes without inferring them from total staked or unit math.

Why this was safe to complete:

- no new stored data or schema work
- no Kelly or exposure-policy widening
- bankroll-relative staking still scales linearly, so ROI and drawdown
  percentages stay comparable while the default dollar presentation becomes
  more realistic

### P-4 [`completed`] Add capital-usage diagnostics to the canonical backtest report

Completed on `2026-03-13`.

The repo now exposes the actual bankroll-deployment evidence that was missing
from the earlier policy cycle. The backtest summary and canonical report now
show requested stake versus placed stake, active-day exposure usage, clipped
bet counts, and how often same-day bet caps or daily exposure caps bound the
strategy.

Why this was safe to complete:

- no schema or artifact changes
- no deployable threshold widening by itself
- directly supports the existing evidence gate on Kelly and exposure changes

Current incumbent evidence from the canonical report:

- requested stake capture: `71.47%`
- average active-day exposure usage: `44.84%`
- peak active-day exposure usage: `100.00%`
- active betting days: `158/158`
- days hitting the same-day bet cap: `45`
- days hitting the daily exposure cap: `6`
- skipped bets from the same-day bet cap: `223`

### M-6 [`completed`] Make stored survivability metrics replayable in policy evaluation

Completed on `2026-03-13`.

The repo can now carry quote-support diagnostics through candidate replay so
bounded policy sweeps can actually evaluate survivability controls, not just
headline edge thresholds. Candidate replay now preserves side-level support
counts and median expected value, which makes `min_positive_ev_books` and
`min_median_expected_value` testable on the same raw walk-forward candidate
set without retraining for every variant.

Why this was safe to complete:

- policy-only internal refactor
- no schema work
- keeps live prediction, backtest, and report paths aligned
- directly unblocks bounded M-2 policy sweeps

## Completed Detail

### A-4 [`completed`] Persist queryable official timing fields needed for shadow analysis

**Hypothesis**

The current stored availability timing is not queryable enough to support good
analysis. The parser already normalizes official `effective_at` and row
`updated_at`, but the persisted schema and read path do not expose those fields
cleanly.

**Implementation sketch**

- Add additive columns for official report `effective_at` and row `updated_at`
  to the availability tables in [sql/schema.sql](../sql/schema.sql).
- Extend [src/cbb/ingest/persistence.py](../src/cbb/ingest/persistence.py) and
  [src/cbb/ingest/availability.py](../src/cbb/ingest/availability.py) so those
  fields are stored idempotently during import.
- Extend the read-only summary path in [src/cbb/db.py](../src/cbb/db.py) to
  prefer the official timing fields when computing availability recency and
  minutes-before-tip summaries.

**Why this is approved**

- safe additive schema change
- source-specific, not speculative
- improves shadow analysis immediately without changing model behavior

**Validation**

- targeted ingest and persistence tests
- confirm reruns remain idempotent
- confirm timing summaries prefer queryable official timing fields over fallback
  report timestamps

### A-5 [`completed`] Build a game-side availability shadow read model for analysis

**Hypothesis**

The repo needs one explicit, reusable game-side summary before any report slice
or feature test can be trusted. Aggregate counts alone are too coarse.

**Implementation sketch**

- Add a read helper in [src/cbb/db.py](../src/cbb/db.py) or a small modeling
  read module that summarizes current stored availability by game and side.
- Keep the first summary intentionally simple and honest:
  `has_official_report`, `team_any_out`, `team_any_questionable`,
  `opponent_any_out`, `opponent_any_questionable`, `team_out_count`,
  `opponent_out_count`, `matched_row_count`, `unmatched_row_count`, and latest
  official update timing.
- Use only currently stored official rows. Do not infer player importance or
  build lineup-value estimates.
- Keep the read model shadow-only. Do not feed it into training, prediction, or
  policy yet.

**Why this is approved**

- bounded repo-local work
- directly grounded in the current schema
- necessary for realistic shadow analysis

**Validation**

- targeted database read-model tests from imported fixtures
- explicit tests for matched vs unmatched rows
- deterministic output across reruns

### A-6 [`completed`] Add availability-enriched evaluation slices to the canonical report

**Hypothesis**

Before any live feature promotion, the report should answer a narrower
question: how did the current deployable system perform on games and settled
bets that had official availability coverage?

**Implementation sketch**

- Extend [src/cbb/modeling/report.py](../src/cbb/modeling/report.py) to join
  completed games and settled best-path bets against the A-5 read model.
- Add shadow-only slices such as:
- covered vs uncovered games
- side/opponent has `out`
- side/opponent has `questionable`
- recency buckets when the stored timing fields support them
- Render "insufficient sample" states instead of unstable ROI claims when a
  slice is too small.
- Keep the canonical headline metrics unchanged. These slices are diagnostics,
  not promotion evidence by themselves.

**Why this is approved**

- no live behavior change
- uses the currently stored data realistically
- gives the repo an evidence base for later feature decisions

**Validation**

- targeted report tests
- verify the slices disappear or render clearly when coverage is absent
- verify the report language stays explicit that these are shadow diagnostics

## Completed This Cycle

### Q-1 [`completed`] Add five-slot placed-vs-skipped diagnostics to the canonical report

**Hypothesis**

The current five-bet cap could only be improved credibly if the repo could
show exactly what the cap was discarding. Aggregate capital-usage counts alone
were not enough to justify a ranking change.

**Implementation**

- Extended [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py) so
  bankroll replay tracks which bets were placed on cap-hit days and which
  additional qualified bets were skipped by the same-day cap.
- Extended [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py) so
  those replay diagnostics, plus close-quality observations for both groups,
  flow through the backtest summary.
- Extended [src/cbb/modeling/report.py](../src/cbb/modeling/report.py) so the
  canonical report compares cap-day placed bets versus skipped bets on average
  expected value, probability edge, positive-EV books, median expected value,
  coverage rate, book depth, equal-stake ROI, close quality, and stable
  segment mixes.

**Files changed**

- [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- [tests/test_modeling.py](../tests/test_modeling.py)
- [tests/test_report.py](../tests/test_report.py)
- [README.md](../README.md)
- [docs/model.md](model.md)
- [docs/architecture.md](architecture.md)
- [docs/model-improvement-roadmap.md](model-improvement-roadmap.md)

**Backtest results**

Canonical baseline stayed unchanged:

- aggregate: `470` bets, `+$1428.11`, ROI `+10.80%`, max drawdown `8.17%`
- `2024`: `132` bets, `+$29.18`, ROI `+0.89%`
- `2025`: `190` bets, `+$1089.85`, ROI `+18.09%`
- `2026`: `148` bets, `+$309.07`, ROI `+7.87%`

New report evidence for the five-slot bottleneck:

- cap-day placed bets: `205` candidates, avg EV `+0.074`, avg probability edge
  `+0.057`, avg positive-EV books `9.35`, avg median EV `+0.032`, avg coverage
  `+88.88%`, equal-stake ROI `+8.69%`, spread close EV `+0.087`
- skipped by bet cap: `173` candidates, avg EV `+0.052`, avg probability edge
  `+0.048`, avg positive-EV books `9.27`, avg median EV `+0.022`, avg coverage
  `+86.02%`, equal-stake ROI `-6.22%`, spread close EV `+0.031`
- the skipped tail is concentrated in weaker expected-value buckets:
  `84.97%` of skipped candidates sit in `ev_4_to_6`, versus `27.32%` of
  cap-day placed bets

**Tradeoffs**

- no deployable behavior changed by itself
- the canonical report is denser, but same-day ranking claims are now auditable
- the new evidence materially narrows which current-data ranking ideas are
  still worth testing

**Conclusion**

Completed. The canonical report now gives the evidence base required for
selection-first work, and that evidence says the skipped tail is materially
weaker than the cap-day placed portfolio.

### P-1 [`completed`] Tighten the deployable same-day top-of-board cap from `6` to `5`

**Hypothesis**

The current spread-first baseline may still be overdeploying capital on the
heaviest slates even after the `4`-book survivability upgrade. A tighter
same-day top-of-board cap could keep capital concentrated on the strongest
ranked bets, improve weakest-season behavior, and reduce drawdown without
needing a new model family.

**Implementation**

- Ran a bounded policy loop on the current spread-first `best` baseline using
  the existing same-day ranking and bankroll logic in:
  - [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
  - [src/cbb/modeling/execution.py](../src/cbb/modeling/execution.py)
  - [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
  - [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- Tested a looser capital-usage challenger first by raising
  `max_daily_exposure_fraction` to `0.06` on the `2026` walk-forward gate.
- Tested tighter same-day caps of `5` and then `4` using the same walk-forward
  gate.
- Promoted the `5`-bet challenger by changing the shared deployable spread
  default in [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py), then
  refreshed the canonical report and dashboard snapshot.

**Files changed**

- [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- [tests/test_modeling.py](../tests/test_modeling.py)
- [README.md](../README.md)
- [docs/model.md](model.md)
- [docs/architecture.md](architecture.md)
- [docs/model-improvement-roadmap.md](model-improvement-roadmap.md)

**Backtest results**

- Prior incumbent full window:
  `511` bets, `+$1083.59`, ROI `+7.86%`, max drawdown `9.77%`,
  profitable seasons `2/3`
- Promoted `5`-bet cap full window:
  `470` bets, `+$1428.11`, ROI `+10.80%`, max drawdown `8.17%`,
  profitable seasons `3/3`
- Per-season comparison:
  - `2024`: `145` bets, `-$164.55`, ROI `-4.80%` -> `132` bets,
    `+$29.18`, ROI `+0.89%`
  - `2025`: `206` bets, `+$1022.43`, ROI `+16.29%` -> `190` bets,
    `+$1089.85`, ROI `+18.09%`
  - `2026`: `160` bets, `+$225.71`, ROI `+5.53%` -> `148` bets,
    `+$309.07`, ROI `+7.87%`
- Aggregate close-quality comparison:
  - spread line CLV: `-0.50 pts` -> `-0.52 pts`
  - spread price delta: `+1.99 pp` -> `+2.03 pp`
  - spread no-vig close delta: `+1.71 pp` -> `+1.73 pp`
  - spread close EV: `+0.082` -> `+0.087`

**Tradeoffs**

- Activity declined moderately (`511` bets -> `470`) without collapsing.
- The promoted policy uses less capital overall but deploys it more
  efficiently on heavier slates.
- Spread line CLV softened slightly, but the more execution-relevant price,
  no-vig, and close-EV evidence improved.

**Conclusion**

The five-bet same-day cap is clearly promotable. It improves aggregate profit,
ROI, drawdown, and weakest-season behavior while keeping activity credible and
maintaining positive close-quality evidence.

### M-1 [`completed`] Re-evaluate spread cross-book survivability with the stronger market coverage

**Hypothesis**

The current deployable spread floor of `min_positive_ev_books=2` was set when
market coverage was thinner. With materially stronger close and current-book
depth now stored, requiring support from more books may trim weak edge cases
without collapsing activity.

**Implementation**

- Ran a bounded walk-forward policy study on the current spread-first `best`
  baseline using the existing survivability controls already exposed in:
  - [src/cbb/modeling/execution.py](../src/cbb/modeling/execution.py)
  - [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
  - [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
  - [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py)
- Tested `min_positive_ev_books=3` first on the `2026` walk-forward gate.
- Because the `3`-book challenger improved drawdown but not profit, tested
  `min_positive_ev_books=4` on the same gate.
- Promoted the `4`-book challenger by changing the shared deployable spread
  default in [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py) and
  then refreshing the canonical report and dashboard snapshot.

**Files changed**

- [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- [tests/test_modeling.py](../tests/test_modeling.py)
- [tests/test_cli.py](../tests/test_cli.py)
- [README.md](../README.md)
- [docs/model.md](model.md)
- [docs/model-improvement-roadmap.md](model-improvement-roadmap.md)

**Backtest results**

- Incumbent `2026` gate:
  `176` bets, `+$88.08`, ROI `+2.06%`, max drawdown `9.57%`,
  spread price delta `+2.29 pp`, no-vig close delta `+2.02 pp`,
  spread close EV `+0.093`
- `3`-book `2026` gate:
  `168` bets, `+$80.65`, ROI `+1.96%`, max drawdown `7.96%`,
  spread price delta `+2.22 pp`, no-vig close delta `+1.94 pp`,
  spread close EV `+0.088`
- Promoted `4`-book full window:
  `512` bets, `+$1022.22`, ROI `+7.47%`, max drawdown `9.77%`,
  profitable seasons `2/3`
- Prior incumbent full window:
  `537` bets, `+$891.08`, ROI `+6.23%`, max drawdown `9.77%`,
  profitable seasons `2/3`
- Per-season comparison:
  - `2024`: `149` bets, `-$103.01`, ROI `-2.90%` -> `145` bets,
    `-$164.55`, ROI `-4.80%`
  - `2025`: `212` bets, `+$906.01`, ROI `+13.98%` -> `206` bets,
    `+$1022.43`, ROI `+16.29%`
  - `2026`: `176` bets, `+$88.08`, ROI `+2.06%` -> `161` bets,
    `+$164.34`, ROI `+4.13%`
- Aggregate close-quality comparison:
  - spread line CLV: `-0.53 pts` -> `-0.49 pts`
  - spread price delta: `+2.06 pp` -> `+1.97 pp`
  - spread no-vig close delta: `+1.77 pp` -> `+1.68 pp`
  - spread close EV: `+0.086` -> `+0.081`

**Tradeoffs**

- Activity declined modestly (`537` bets -> `512`) without collapsing.
- `2024` worsened, so the gain is not uniform across seasons.
- Aggregate drawdown stayed flat rather than improving.
- Price/no-vig/close-EV softened slightly, but all three stayed clearly
  positive and line CLV improved slightly.

**Conclusion**

The `4`-book survivability floor is promotable. It improves full-window ROI
and profit materially, improves both `2025` and `2026`, keeps drawdown flat,
and preserves enough activity to remain deployable. No further same-signal
survivability variant is approved right now.

**Why this was approved**

- uses stronger market data already in the database
- requires no new schema, ingest lane, or external source
- keeps live, backtest, and report paths aligned because the control already
  exists in the shared policy surface

**Validation**

- 2026 walk-forward gate first
- full `cbb model report` only if the gate is acceptable
- compare aggregate and per-season ROI, profit, activity, max drawdown, spread
  price delta, spread no-vig close delta, and spread closing EV

## Needs Follow-Up Before Approval

### M-2 [`rejected`] Add a bounded minimum median expected-value floor across eligible books

Completed evaluation on `2026-03-13`.

The gating work cleared, so the repo ran the bounded median-EV sweep on the
same replayable raw spread candidate set. It did not beat the incumbent.

Replay comparison on the widened candidate set:

- incumbent `4` books, no median floor, five-bet cap:
  `399` bets, `+$1081.52`, ROI `+9.36%`, max drawdown `8.81%`
- `4` books, median EV `0.005`, five-bet cap:
  `352` bets, `+$707.98`, ROI `+7.12%`, max drawdown `8.81%`
- `4` books, median EV `0.010`, five-bet cap:
  `316` bets, `+$535.80`, ROI `+5.90%`, max drawdown `8.81%`
- `4` books, median EV `0.005`, six-bet cap:
  `378` bets, `+$477.40`, ROI `+4.69%`, max drawdown `10.38%`
- `5` books, no median floor, five-bet cap:
  `387` bets, `+$971.66`, ROI `+8.70%`, max drawdown `8.81%`

Conclusion:

- the incumbent still produced the best profit and ROI
- stricter support rules cut too much activity without improving drawdown
- the higher-activity six-bet variant with a median floor materially worsened
  both ROI and drawdown

Do not promote a median-EV floor on the current spread-first baseline.

### R-5 [`needs follow-up`] Add repaired-data qualification guards for weak tails only if R-4 finds stable, repeatable failure buckets

This is not approved yet because the current repaired-data report still shows
only small weak tails rather than one obviously universal deployable blocker.
For example:

- `mid_depth` is poor but only `11` bets
- `non-conference` is weak but only `44` bets
- the `8% to 10%` EV bucket is negative despite positive average close EV,
  which suggests calibration or qualification mismatch rather than a simple
  one-rule exclusion

If R-4 shows a stable, season-specific weak tail that survives walk-forward
review, then a bounded segment-aware guard may become justified. Until then,
do not hard-code new exclusions from the current aggregate segment table alone.

### M-3 [`needs follow-up`] Market-quality feature refresh using denser close data

This is still not approved ahead of R-1 through R-3 because the current
feature set already encodes most of the obvious consensus, move, dispersion,
and cross-market information. A new feature lane only becomes justified if the
repaired-data family and calibration work fail cleanly.

### A-7 [`needs follow-up`] Availability-derived challenger features in training/backtest

Availability remains shadow-only. This lane still lacks the multi-season,
full-market, player-importance-aware evidence needed for a credible live
challenger.

### A-16 [`approved` -> `completed`] Surface per-game availability shadow context in prediction outputs

Problem:

- the repo already has page-level availability usage state and aggregate shadow
  diagnostics, but the live board and `predict.v1` upcoming rows still cannot
  say which specific game has stored official coverage
- [docs/ui-ux-roadmap.md](ui-ux-roadmap.md) keeps
  `UX-AV-4` in `needs follow-up` status until the prediction contract exposes
  explicit per-game availability usage or confidence metadata
- the dashboard should not synthesize per-game availability context from
  database state outside the prediction contract

Approved implementation shape:

- add one additive, shadow-only availability context field to
  [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) for
  `UpcomingGamePrediction` and `LiveBoardGame`
- populate that field from the existing
  [src/cbb/db.py](../src/cbb/db.py) availability game-side read model for the
  current live-board game set only
- keep the payload explicitly descriptive, not prescriptive:
  report presence, source name, latest update timing, and side/opponent
  `out` / `questionable` counts
- extend the additive machine-readable upcoming-game payload in
  [src/cbb/cli.py](../src/cbb/cli.py) so `predict.v1` surfaces the same
  per-game shadow context

Explicit non-goals:

- no change to qualification, ranking, staking, or live deployable policy
- no player-importance scoring or inferred availability adjustment
- no report or snapshot contract change in this pass

Outcome:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) now attaches one
  additive `availability_context` payload to upcoming-game and live-board rows
  using the existing availability game-side shadow read model
- [src/cbb/cli.py](../src/cbb/cli.py) now carries that same shadow-only context
  into `predict.v1` upcoming-game JSON rows without changing text-mode betting
  output
- the helper fails open to an empty context when the local database or
  availability tables are unavailable, so the additive metadata cannot block
  normal prediction paths
- [README.md](../README.md), [docs/model.md](model.md), and
  [docs/architecture.md](architecture.md) now document that this field is
  descriptive only and not part of qualification or staking
- targeted prediction and CLI tests, `ruff check`, and `mypy` all pass, and
  this now gives `UX-AV-4` a real prediction-contract field to consume

### A-17 [`completed`] Add prediction-level availability shadow summary

Problem:

- the live prediction path now exposes row-level `availability_context`, but
  neither `PredictionSummary` nor `predict.v1` tells operators how much of the
  current slate has stored official-report coverage without scanning each row

Repo evidence:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) builds per-game
  availability context but `PredictionSummary` still only tracks generic game
  and recommendation counts
- [src/cbb/cli.py](../src/cbb/cli.py) serializes `predict.v1` with summary
  fields for `available_games`, `candidates_considered`, `deferred_count`, and
  `recommendations_count`, but no aggregate availability coverage block
- the text `cbb model predict` output prints freshness, policy, and risk
  guardrails, but it does not summarize whether the upcoming board has any
  stored official availability coverage

Implementation shape:

- add an additive prediction-level availability summary computed from the
  upcoming-game prediction rows
- expose that summary in `PredictionSummary`, `predict.v1`, and the text CLI
  output without changing recommendation, wait, or pass decisions
- keep the change shadow-only and contract-additive; do not feed availability
  into ranking, qualification, staking, or backtest behavior

Acceptance criteria:

- `PredictionSummary` exposes how many upcoming games currently carry
  availability shadow context plus a simple coverage-status breakdown
- `predict.v1` includes that additive summary so downstream consumers do not
  need to scan every row to know whether the slate has stored official coverage
- text `cbb model predict` output surfaces the same high-level availability
  shadow summary without changing bet-selection behavior
- targeted prediction and CLI tests cover both covered and uncovered upcoming
  slates

Explicit non-goals:

- using availability as a betting feature or guardrail
- changing live-board or dashboard contracts beyond additive compatibility
- changing report or backtest selection behavior

Outcome:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) now computes one
  additive slate-level availability summary from the upcoming-game prediction
  rows alongside the existing per-game context
- [src/cbb/cli.py](../src/cbb/cli.py) now surfaces that summary in the text
  prediction header and under `predict.v1.summary.availability_shadow`
- [README.md](../README.md), [docs/model.md](model.md), and
  [docs/architecture.md](architecture.md) now document the new shadow summary
  as descriptive-only metadata
- targeted prediction and CLI tests, `ruff check`, and `mypy` all pass without
  changing recommendation, wait, or pass behavior

### A-18 [`completed`] Add availability freshness summary to prediction outputs

Problem:

- the prediction contract now summarizes how many upcoming rows have stored
  official-report coverage, but operators still cannot tell from the summary
  whether that coverage is recent or stale without opening individual row-level
  availability payloads

Repo evidence:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) already carries
  per-side `latest_update_at` and `latest_minutes_before_tip` values inside
  each upcoming-row `availability_context`
- [src/cbb/cli.py](../src/cbb/cli.py) now emits aggregate coverage counts
  under `predict.v1.summary.availability_shadow`, but it does not summarize the
  freshest available official update or the closest stored report to tip
- the text `cbb model predict` output now reports coverage counts, but not the
  recency of the covered slate

Implementation shape:

- extend the additive prediction-level availability summary with one latest
  official update timestamp and one closest report-to-tip timing value derived
  from the existing upcoming-row shadow context
- surface those freshness fields in `PredictionSummary`, `predict.v1`, and the
  text CLI output without changing qualification, ranking, staking, or
  backtest behavior
- keep the change shadow-only and summary-level; do not add player-value or
  policy logic

Acceptance criteria:

- the prediction availability summary exposes the freshest stored official
  update and closest report timing when covered upcoming rows exist
- `predict.v1.summary.availability_shadow` includes the same additive freshness
  fields in a machine-readable shape
- text `cbb model predict` output surfaces the same freshness summary without
  changing recommendation, wait, or pass behavior
- targeted prediction and CLI tests cover both covered and uncovered slates

Explicit non-goals:

- using freshness as a hard betting guardrail
- changing dashboard or live-board behavior in this pass
- changing report or backtest outputs

Outcome:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) now carries one
  latest official update timestamp and one closest report-to-tip value in the
  additive prediction-level availability summary
- [src/cbb/cli.py](../src/cbb/cli.py) now surfaces those freshness fields in
  both the text prediction summary and
  `predict.v1.summary.availability_shadow`
- [README.md](../README.md), [docs/model.md](model.md), and
  [docs/architecture.md](architecture.md) now document that the shadow summary
  covers both coverage and freshness while staying descriptive-only
- targeted prediction and CLI tests, `ruff check`, and `mypy` all pass without
  changing recommendation, wait, or pass behavior

### A-19 [`completed`] Add availability matching-quality summary to prediction outputs

Problem:

- the live prediction path now exposes per-side matched and unmatched
  availability row counts, but the prediction summary still cannot tell
  operators whether the current covered slate has clean matching quality
  without scanning each game row

Repo evidence:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) already carries
  `matched_row_count` and `unmatched_row_count` inside each side-level
  `availability_context`
- [src/cbb/cli.py](../src/cbb/cli.py) serializes those row-level counts in
  `predict.v1.upcoming_games[*].availability_context`, but the additive
  `summary.availability_shadow` block still stops at coverage and freshness
- [docs/ui-ux-roadmap.md](ui-ux-roadmap.md) already calls out matching quality
  as part of the availability-visibility contract, so the summary layer should
  expose whether current slate coverage is cleanly matched

Implementation shape:

- extend the additive prediction-level availability summary with bounded
  matching-quality counts derived from the existing per-game shadow context
- expose those counts in `PredictionSummary`, `predict.v1`, and the text
  `cbb model predict` output without changing qualification, ranking, staking,
  or backtest behavior
- keep the change shadow-only and descriptive; do not infer player importance
  or turn unmatched-row counts into a live guardrail

Acceptance criteria:

- the prediction availability summary exposes how many covered upcoming games
  currently contain unmatched availability rows
- the same summary exposes how many team-side versus opponent-side contexts
  contain unmatched rows
- `predict.v1.summary.availability_shadow` includes the additive
  matching-quality counts in a machine-readable shape
- text `cbb model predict` output surfaces the same matching-quality summary
  without changing recommendation, wait, or pass behavior
- targeted prediction and CLI tests cover both clean and partially unmatched
  upcoming slates

Explicit non-goals:

- changing live policy, ranking, or staking behavior
- changing dashboard presentation in this pass
- inventing a new confidence score beyond the existing descriptive counts

Outcome:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) now summarizes how
  many upcoming covered games carry unmatched availability rows and whether the
  unmatched rows sit on the team side or opponent side
- [src/cbb/cli.py](../src/cbb/cli.py) now surfaces those matching-quality
  counts in both the text prediction summary and
  `predict.v1.summary.availability_shadow`
- [README.md](../README.md), [docs/model.md](model.md), and
  [docs/architecture.md](architecture.md) now document that the shadow summary
  covers matching quality as well as coverage and freshness
- targeted prediction and CLI tests, `ruff check`, and `mypy` all pass without
  changing recommendation, wait, or pass behavior

### A-20 [`completed`] Add availability status-mix summary to prediction outputs

Problem:

- the prediction summary now covers coverage, freshness, and matching quality,
  but operators still cannot tell from the header whether the covered slate
  actually contains any stored `out` or `questionable` statuses without
  scanning row-level availability payloads

Repo evidence:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) already carries
  per-side `any_out` and `any_questionable` flags inside each upcoming-row
  `availability_context`
- [src/cbb/cli.py](../src/cbb/cli.py) serializes those row-level flags in
  `predict.v1.upcoming_games[*].availability_context`, but the additive
  `summary.availability_shadow` block still stops at coverage, freshness, and
  matching quality
- the current text `cbb model predict` summary answers "how much coverage do
  we have?" but not "does this covered slate actually include any reported
  outs or questionables?"

Implementation shape:

- extend the additive prediction-level availability summary with bounded
  per-game counts for covered upcoming rows that currently contain any `out`
  or any `questionable` status
- expose those counts in `PredictionSummary`, `predict.v1`, and the text
  `cbb model predict` output without changing qualification, ranking, staking,
  or backtest behavior
- keep the change shadow-only and descriptive; do not promote status presence
  into a live betting guardrail

Acceptance criteria:

- the prediction availability summary exposes how many covered upcoming games
  currently contain at least one `out` or at least one `questionable` status
- `predict.v1.summary.availability_shadow` includes the same additive status-
  mix counts in a machine-readable shape
- text `cbb model predict` output surfaces the same status-mix summary without
  changing recommendation, wait, or pass behavior
- targeted prediction and CLI tests cover both status-bearing and empty-status
  slates

Explicit non-goals:

- changing live policy, ranking, or staking behavior
- inferring player importance from raw status presence
- changing dashboard presentation in this pass

Outcome:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) now summarizes how
  many covered upcoming rows currently carry any stored `out` status or any
  stored `questionable` status
- [src/cbb/cli.py](../src/cbb/cli.py) now surfaces those status-mix counts in
  both the text prediction summary and
  `predict.v1.summary.availability_shadow`
- [README.md](../README.md), [docs/model.md](model.md), and
  [docs/architecture.md](architecture.md) now document that the shadow summary
  covers status mix as well as coverage, freshness, and matching quality
- targeted prediction and CLI tests, `ruff check`, and `mypy` all pass without
  changing recommendation, wait, or pass behavior

### A-21 [`completed`] Add availability source summary to prediction outputs

Problem:

- the prediction summary now covers coverage, freshness, matching quality, and
  status mix, but operators still cannot tell from the header which stored
  availability sources are actually contributing to the covered upcoming slate
  without scanning row-level payloads

Repo evidence:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) already carries a
  `source_name` per side inside each upcoming-row `availability_context`
- the availability lane now includes NCAA plus wrapped archive-source coverage,
  so the current slate may mix source labels even while the prediction summary
  stays silent about them
- [src/cbb/cli.py](../src/cbb/cli.py) serializes those source labels row by
  row in `predict.v1`, but `summary.availability_shadow` still does not expose
  one slate-level source summary

Implementation shape:

- extend the additive prediction-level availability summary with one stable
  list of distinct source labels derived from the covered upcoming rows
- expose that list in `PredictionSummary`, `predict.v1`, and the text
  `cbb model predict` output without changing qualification, ranking, staking,
  or backtest behavior
- keep the change shadow-only and descriptive; do not turn source presence into
  a live guardrail or weighting rule

Acceptance criteria:

- the prediction availability summary exposes the distinct source labels that
  contribute to the covered upcoming slate
- `predict.v1.summary.availability_shadow` includes the same additive source
  list in a machine-readable shape
- text `cbb model predict` output surfaces the same source summary without
  changing recommendation, wait, or pass behavior
- targeted prediction and CLI tests cover both named-source and no-source
  slates

Explicit non-goals:

- changing live policy, ranking, or staking behavior
- inferring source quality from source labels alone
- changing dashboard presentation in this pass

Outcome:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) now summarizes the
  distinct source labels that contribute to the covered upcoming slate
- [src/cbb/cli.py](../src/cbb/cli.py) now surfaces that source summary in both
  the text prediction header and `predict.v1.summary.availability_shadow`
- [README.md](../README.md), [docs/model.md](model.md), and
  [docs/architecture.md](architecture.md) now document that the shadow summary
  covers source labels as well as coverage, freshness, matching quality, and
  status mix
- targeted prediction and CLI tests, `ruff check`, and `mypy` all pass without
  changing recommendation, wait, or pass behavior

### A-8 [`needs follow-up`] Availability-aware live policy guards

Hard rules based on raw `out` or `questionable` counts are still too blunt for
promotion. This lane stays behind the shadow evidence bar.

### S-1 [`needs follow-up`] Re-evaluate Kelly and exposure widening after the promoted five-bet cap

The new capital-usage diagnostics now make the gating reason explicit:
requested stake capture is only `71.47%`, average active-day exposure is
`44.84%`, the exposure cap bound only `6` days, and the same-day bet cap
skipped `223` otherwise qualified bets across `45` days. The current
bottleneck is still selection quality under the five-bet portfolio, not raw
bankroll percentage limits.

Do not widen Kelly or daily exposure again unless a later cycle shows that the
best available sub-cap opportunities are still being underfunded after the
post-repair model and calibration problem is solved.

## Deferred

### R-3 [`deferred`] Run bounded spread model-family challengers on the repaired dataset

The repo already supports a spread `hist_gradient_boosting` challenger, but
there is not yet strong contrary evidence that the repaired-data problem is
primarily raw model-family expressiveness. The current report still points more
toward calibration and threshold mismatch on the existing margin-regression
path.

This lane becomes justified only if R-1 and R-2 fail to produce a promotable
challenger or if those runs uncover clear evidence that the repaired-data edge
is bottlenecked by linear model shape rather than calibration stability.

### A-9 [`deferred`] Automated NCAA availability capture or fetch

Keep the current availability phase file-based and replayable.

### A-10 [`deferred`] Regular-season or non-official availability sources

Do not widen the availability lane before the current bounded shadow data is
either promoted or explicitly abandoned.

### A-11 [`completed`] Reproducible team home-location foundation

The repo now has a tracked auditable home-location catalog at
`data/team_home_locations.csv`, generated from each team's dominant stored
non-neutral home venue and geocoded into city/state coordinates, timezone, and
elevation. The modeling layer also now carries that context through examples
and bet metadata so the canonical report can slice qualified spread bets by
venue context, travel bucket, and timezone crossings without recomputing or
guessing at locations.

### A-12 [`deferred`] Always-on refresh services or Kubernetes restructuring

The current phase is still local-first. Do not widen into runtime topology
changes here.

## Rejected For This Cycle

### P-2 [`rejected`] Raise max daily exposure fraction to `0.06`

This already failed on the repaired policy cycle's evidence standard. Higher
same-board capital usage improved some close-quality metrics but did not
improve realized profit or ROI enough to clear promotion.

### P-3 [`rejected`] Tighten the same-day top-of-board cap further from `5` to `4`

This already failed the earlier bounded gate. It improved some close-quality
metrics but cut realized profit too much to justify promotion.

### P-5 [`rejected`] Re-rank same-day bankroll deployment by survivability before raw EV

Attempted on `2026-03-13`.

Hypothesis:

- because quote survivability already matters in quote and game selection,
  same-day bankroll deployment might improve if it preserved that survivability
  priority instead of re-sorting by expected value alone

Full-window result:

- incumbent baseline: `470` bets, `+$1428.11`, ROI `+10.80%`
- challenger: `471` bets, `+$876.08`, ROI `+6.97%`

Season impact:

- `2024`: `+$29.18` -> `-$277.41`
- `2025`: `+$1089.85` -> `+$1063.87`
- `2026`: `+$309.07` -> `+$89.61`

Close-quality impact:

- aggregate spread closing EV softened from `+0.087` to `+0.077`

Conclusion:

- reject this same-day ranking change for the current cycle
- the incumbent EV-first day ordering appears to be part of the current
  baseline's robustness
- do not keep retrying minor same-day ordering variants without a clearer
  segment-level justification

### M-4 [`rejected`] Raw coverage-rate gating as the main stronger-market response

The repo already exposes `coverage_rate`, but raw support ratio alone is not a
good enough deployable signal. Stronger market coverage should first be tested
through absolute positive-EV book counts, not ratio-only gating.

### M-5 [`rejected`] Generic structural-model complexity on the current feature set

The current evidence still says the edge is more execution- and
calibration-driven than raw line-prediction-driven. Do not widen into
speculative new model families beyond the already supported spread
`hist_gradient_boosting` challenger unless the repaired-data reoptimization
cycle fails cleanly.

### T-1 [`rejected`] Inferred home-state / venue-state travel proxy features from stored ESPN venue metadata

This repo-local proxy was already tested and failed to clear the gate. Do not
keep retrying small venue-state variants without a richer external
home-location source.

### T-2 [`rejected`] Promote direct travel/timezone features into the trained model now

Hypothesis:

- the new tracked home-location catalog plus stored ESPN venue metadata might
  add enough neutral-site / travel / timezone information to improve the
  deployable spread path

Implementation:

- added the tracked home-location catalog at `data/team_home_locations.csv`
- added `src/cbb/team_home_locations.py` and
  `scripts/generate_team_home_locations.py`
- replayed one direct challenger that added neutral-site, travel-distance, and
  timezone-crossing values to the trained feature vector

Files changed:

- `data/team_home_locations.csv`
- `scripts/generate_team_home_locations.py`
- `src/cbb/team_home_locations.py`
- retained runtime/report plumbing in
  `src/cbb/modeling/dataset.py`,
  `src/cbb/modeling/features.py`,
  `src/cbb/modeling/policy.py`, and
  `src/cbb/modeling/report.py`

Backtest results:

- incumbent baseline used for the experiment:
  `417` bets, `+$905.30`, ROI `+7.94%`, max drawdown `8.06%`,
  aggregate spread price delta `+1.94 pp`, no-vig delta `+1.63 pp`,
  spread close EV `+0.084`, and `2024` profit `-$197.31`
- `2026` gate challenger:
  `137` bets, `+$565.26`, ROI `+13.88%`, max drawdown `4.20%`,
  spread price delta `+2.01 pp`, no-vig delta `+1.71 pp`,
  spread close EV `+0.095`
- full-window challenger:
  `446` bets, `+$812.16`, ROI `+6.04%`, max drawdown `12.20%`,
  aggregate spread price delta `+1.93 pp`, no-vig delta `+1.59 pp`,
  spread close EV `+0.098`, and `2024` profit `-$273.74`

Tradeoffs:

- the new information clearly helped the latest season, but it weakened the
  weakest season materially and worsened the full-window drawdown
- the data foundation itself is still worth keeping because it now powers
  auditable coverage tests and report slices without changing deployable
  behavior

Conclusion:

- keep the home-location foundation and report diagnostics
- do not promote direct travel/timezone model features into the current
  deployable baseline

### A-13 [`rejected`] Promote availability directly into the deployable model now

The evidence bar is not met. The current repo cannot justify a deployable
availability-aware feature promotion from one recent tournament-scoped source.

### A-14 [`rejected`] Hard auto-pass or bankroll cuts based only on raw status presence

`Any out` or `any questionable` is too blunt. Without player impact weighting,
those rules would mostly be guesswork disguised as discipline.

### A-15 [`rejected`] Treat shadow-slice ROI on covered games as sufficient promotion evidence

Even if covered-slate performance looks good, that would still be a small,
selection-biased subset. Promotion requires stronger evidence than "the covered
tournament slice looked better."

### TM-1 [`approved`] Add a bounded tournament-mode bracket path for the 2026 men's field

Parent-task approval:

- explicitly approved by the `2026-03-18` tournament-mode request

Problem:

- the existing live path can score the current upcoming board, but it cannot
  produce one bracket-wide pick set for the NCAA tournament
- `model predict --market best` is spread-first and betting-oriented, which is
  the wrong default for straight-up bracket advancement
- the local DB currently has the March `19-20`, `2026` first-round slate and
  current odds, but the upcoming ESPN rows do not consistently expose usable
  tournament metadata for selection or bracket structure

Approved implementation shape:

- add a new CLI entrypoint next to `model predict`, scoped to tournament use
- keep bracket winner selection on the moneyline artifact, not the deployable
  `best` spread-first market
- load the official `2026` men's field from a tracked local bracket spec rather
  than trying to infer the bracket tree from incomplete upcoming-game metadata
- reuse live stored game rows and live odds for First Four / first-round games
  that already exist in the DB
- synthesize in-memory neutral-site matchup records for later-round hypothetical
  games and score them through the existing feature + artifact stack
- expose one deterministic bracket plus simulation-based advancement odds so the
  operator can see both the model's picks and its uncertainty

Explicit non-goals for this step:

- no schema changes
- no dashboard or snapshot contract changes
- no attempt to promote spread-based bracket picks without real future-round
  lines
- no automatic NCAA-bracket fetcher; the bracket structure is a tracked local
  input for this cycle

Implementation status:

- the current worktree now carries the bounded `cbb model tournament` path, the
  tracked `2026` bracket spec, and dedicated CLI / simulation tests
- the resumed `2026-03-18` verification pass tightened bracket-spec validation
  and restored the missing dashboard test fixture that was blocking repo-health
  checks
- current verification: `pytest` on tournament + dashboard slices, `ruff
  check`, and `mypy` all pass on the working tree

### TM-2 [`approved`] Add a bounded prior-years tournament backtest path for completed men's brackets

Parent-task approval:

- explicitly approved by the `2026-03-18` tournament-backtest request

Problem:

- the bounded tournament wrapper can score the current field, but it cannot yet
  measure how that bracket-filling path behaved on completed NCAA tournaments
- replaying prior brackets with the current `latest` moneyline artifact would
  leak future seasons and give dishonest evidence
- the repo previously only tracked the current `2026` bracket spec, so the last
  completed men's tournaments had no local input files for replay

Approved implementation shape:

- add a `cbb model tournament-backtest` CLI entrypoint next to
  `cbb model tournament`
- track local men's bracket specs for completed `2023-2025` tournaments under
  `data/tournaments/`
- train one moneyline artifact per evaluation season on the configured trailing
  seasons of completed games, including the evaluation season only up to the
  first play-in tip
- freeze any known First Four / round-of-64 market inputs at that pre-tournament
  anchor and keep later rounds synthetic so the replay matches the live
  bracket-fill constraints
- compare deterministic bracket picks to the actual completed tournament path
  with per-round and per-season summaries

Explicit non-goals for this step:

- no dashboard or snapshot contract changes
- no attempt to promote the tournament wrapper into the live deployable betting
  path
- no inferred bracket reconstruction from incomplete stored metadata; the
  bracket specs remain tracked local inputs

Implementation status:

- the current worktree now carries the `cbb model tournament-backtest` path plus
  tracked `2023-2025` men's bracket specs
- initial `2023-2025` smoke evidence from `2026-03-18`: `58/201` correct picks
  (`28.9%`), `0/3` champion hits, and `48.7%` average probability on the actual
  winner
- round accuracy in that initial replay is concentrated early: First Four
  `6/12` (`50.0%`) and round of `64 43/96` (`44.8%`), with no correct picks in
  the Elite 8, Final Four, or championship slots

### TM-3 [`approved`] Add a marketless fallback scorer for synthetic tournament matchups

Parent-task approval:

- explicitly approved by the `2026-03-18` tournament-improvement request

Problem:

- TM-2 showed that the bounded bracket wrapper was acceptable only while real
  early-round market rows existed; once later rounds turned synthetic, the
  moneyline artifact was being asked to score many rows with its market-heavy
  feature block zero-filled
- the initial replay collapsed after the first weekend: round of 32 `7/48`
  (`14.6%`), Sweet 16 `2/24` (`8.3%`), and no correct picks at all in the
  Elite 8, Final Four, or championship rounds
- that failure shape pointed to a wrapper mismatch, not necessarily a missing
  tournament-specific data source or a reason to change the promoted live
  betting path

Approved implementation shape:

- keep using the stored moneyline artifact whenever the bracket matchup has a
  usable moneyline market row
- train one transient tournament-only fallback logistic model on the same
  completed-game window, but restrict it to the common team-state feature block
  instead of the full market-heavy moneyline feature set
- route synthetic or otherwise marketless bracket rows through that fallback so
  later-round probabilities are driven by pregame team state rather than
  zero-filled market fields
- keep live `cbb model tournament` and replayed `cbb model tournament-backtest`
  aligned on the same routing rule

Explicit non-goals for this step:

- no schema changes
- no report, snapshot, JSON, or dashboard contract changes
- no attempt to promote tournament behavior into the live deployable betting
  policy
- no seed-only hard-coded bracket heuristic replacing the learned scorer

Implementation status:

- the current worktree now trains and applies that marketless fallback inside
  [src/cbb/modeling/tournament.py](../src/cbb/modeling/tournament.py) for
  bracket rows without usable moneyline prices
- integrated `2023-2025` replay evidence on `2026-03-18` improved from
  `58/201` correct picks (`28.9%`) and `0/3` champion hits to `91/201`
  (`45.3%`) and `1/3` champion hits
- average probability on the actual winner improved from `48.7%` to `50.5%`
- the biggest gains now land in the synthetic later rounds:
  round of 32 `7/48 -> 19/48`, Sweet 16 `2/24 -> 9/24`, Elite 8 `0/12 -> 4/12`,
  Final Four `0/6 -> 2/6`, championship `0/3 -> 1/3`
- the remaining weakness is mostly `2023`, where the local DB still only has
  the evaluation season's own pre-tournament sample available for training

### TM-4 [`approved` -> `completed`] Add tournament source-split diagnostics before changing matchup routing

Parent-task approval:

- explicitly approved by the current `2026-03-28` model-loop request

Problem:

- the current tournament replay still has one obvious open question: should the
  next challenger focus on routing more bracket rows through stored moneyline
  markets instead of the synthetic fallback
- the repo does not currently surface how many replayed bracket picks actually
  scored through the priced moneyline artifact versus the synthetic common-
  feature fallback, so that decision is still too hand-wavy

Repo evidence:

- `src/cbb/modeling/tournament.py` currently summarizes replay accuracy only by
  season and round, not by matchup source
- the bounded local audit on `2026-03-28` showed that the replayed bracket is
  overwhelmingly synthetic at tournament tip:
  `2023` known rows `32/32` source `none`,
  `2024` known rows `31 none / 1 both-priced`,
  `2025` known rows `31 none / 1 both-priced`
- that means a routing-first challenger is unlikely to move many games unless
  the summary proves otherwise

Implementation shape:

- extend the tournament backtest summary with source-split diagnostics for
  predicted picks, covering the priced moneyline artifact versus the synthetic
  common-feature fallback
- surface those diagnostics in both CLI text output and machine-readable JSON
- keep the change report-only; do not change tournament scoring behavior in the
  same pass

Acceptance criteria:

- `cbb model tournament-backtest` reports source-split pick counts and
  accuracy without changing the existing round summaries
- targeted tournament tests cover the new source diagnostics
- the pass ends with an explicit promote/reject decision on the routing-first
  hypothesis using the new evidence

Explicit non-goals:

- changing live deployable betting policy behavior
- retraining the promoted `best` artifact
- adding new tournament data sources or schema changes in the same pass

Outcome:

- completed in
  [src/cbb/modeling/tournament.py](../src/cbb/modeling/tournament.py),
  [src/cbb/cli.py](../src/cbb/cli.py),
  [tests/test_tournament.py](../tests/test_tournament.py), and
  [tests/test_cli.py](../tests/test_cli.py)
- `cbb model tournament-backtest` now emits one additive scoring-source summary
  in both text and JSON output so the operator can see how many bracket picks
  actually scored through the moneyline market artifact versus the synthetic
  common-feature fallback
- the bounded local audit on `2026-03-28` showed the next routing-first idea is
  too small to matter yet:
  `2023` priced `0/67`, `2024` priced `1/67`, `2025` priced `1/67`, for an
  estimated total of only `2/201` picks with both moneyline prices available at
  the tournament anchor

Conclusion:

- reject a routing-first tournament challenger for now
- the next credible tournament improvement lane is still synthetic-path model
  quality or tournament-specific diagnostics, not trying to squeeze more value
  out of a priced-market path that currently touches too few bracket games

### TM-5 [`approved` -> `completed`] Add round-by-round scoring-source diagnostics before changing the synthetic path

Parent-task approval:

- explicitly approved by the current `2026-03-28` model-loop request

Problem:

- TM-4 rejected a routing-first tournament challenger, but the current replay
  still does not show whether the remaining synthetic-path weakness is mostly a
  late-round problem or whether synthetic scoring dominates the bracket more
  broadly
- the backtest currently reports round accuracy and source accuracy
  separately, which is not enough to decide whether a late-round-only heuristic
  is the next credible move

Repo evidence:

- `src/cbb/modeling/tournament.py` currently emits `round_summaries` and
  `source_summaries`, but not the intersection of those two views
- the post-`TM-4` evidence already says priced-market routing is too small to
  matter overall, which makes the next useful question about where the
  synthetic path is still failing, not whether to route more rows back to
  priced markets

Implementation shape:

- extend tournament backtest summaries with round-level source splits for the
  moneyline market artifact versus the synthetic common-feature fallback
- surface those splits in CLI text and JSON output
- keep the pass diagnostics-only; do not change tournament scoring behavior in
  the same pass

Acceptance criteria:

- `cbb model tournament-backtest` reports source-split accuracy within each
  round summary
- JSON output carries the same round-level source diagnostics
- targeted tournament tests cover the new nested source summaries
- the pass ends with an explicit promote/reject decision on a late-round-only
  heuristic using the new evidence

Explicit non-goals:

- changing tournament pick behavior in the same pass
- changing the live deployable betting policy
- adding bracket-specific hard-coded heuristics or new data sources

Outcome:

- completed in
  [src/cbb/modeling/tournament.py](../src/cbb/modeling/tournament.py),
  [src/cbb/cli.py](../src/cbb/cli.py),
  [tests/test_tournament.py](../tests/test_tournament.py), and
  [tests/test_cli.py](../tests/test_cli.py)
- `cbb model tournament-backtest` now nests scoring-source summaries inside
  each round summary in both text and JSON output, so the replay can show
  whether priced or synthetic picks are succeeding differently by round
- bounded evidence from
  `cbb model tournament-backtest --seasons 3 --max-season 2025 --output-format json`
  on `2026-03-28` showed the path is still overwhelmingly synthetic across the
  whole bracket: `199/201` picks used the synthetic fallback and only `2/201`
  used the priced moneyline artifact
- the same evidence showed the weakest synthetic accuracy does worsen late, but
  the synthetic path still dominates every round:
  synthetic first four `7/10` (`70.0%`), round of 64 `59/96` (`61.5%`), round
  of 32 `25/48` (`52.1%`), Sweet 16 `12/24` (`50.0%`), Elite 8 `7/12`
  (`58.3%`), Final Four `2/6` (`33.3%`), championship `1/3` (`33.3%`)

Conclusion:

- reject a late-round-only tournament heuristic as the next challenger
- the degradation is not isolated to a tiny priced-market pocket or one
  special late-round rule target; it is a broad synthetic-path quality issue
  that simply becomes more visible in the smallest later rounds
- the next credible tournament lane is general synthetic-path improvement or
  richer tournament-specific diagnostics, not a round-specific hard-coded
  policy

### TM-6 [`approved` -> `completed`] Add round-level actual-winner-probability diagnostics before shrinking late rounds

Parent-task approval:

- explicitly approved by the current `2026-03-28` model-loop request

Problem:

- TM-5 showed that synthetic accuracy weakens most clearly in the smallest
  later rounds, but accuracy alone still does not show whether the path is also
  overconfident there
- without round-level actual-winner-probability diagnostics, the repo cannot
  tell whether a late-round confidence-shrink idea is calibrating a real
  problem or just reacting to a tiny-sample accuracy dip

Repo evidence:

- `src/cbb/modeling/tournament.py` currently reports
  `average_actual_winner_probability` only at the season and aggregate summary
  level
- the new TM-5 round/source summaries already isolate where the synthetic path
  weakens, which makes calibration-by-round the next bounded question before
  any hard-coded round shrink is considered

Implementation shape:

- extend tournament backtest round and source summaries with additive
  actual-winner-probability diagnostics
- surface those diagnostics in CLI text and JSON output
- keep the pass diagnostics-only; do not change tournament scoring behavior in
  the same pass

Acceptance criteria:

- `cbb model tournament-backtest` reports actual-winner probability inside the
  round and source summaries
- JSON output carries the same additive diagnostics
- targeted tournament tests cover the new fields
- the pass ends with an explicit promote/reject decision on a late-round
  confidence-shrink heuristic using the new evidence

Explicit non-goals:

- changing tournament pick behavior in the same pass
- changing the live deployable betting policy
- introducing hard-coded bracket heuristics or new stored data

Outcome:

- completed in
  [src/cbb/modeling/tournament.py](../src/cbb/modeling/tournament.py),
  [src/cbb/cli.py](../src/cbb/cli.py),
  [tests/test_tournament.py](../tests/test_tournament.py), and
  [tests/test_cli.py](../tests/test_cli.py)
- `cbb model tournament-backtest` now carries additive
  `average_actual_winner_probability` diagnostics inside both round and
  source summaries in text and JSON output
- bounded evidence from
  `cbb model tournament-backtest --seasons 3 --max-season 2025 --output-format json`
  on `2026-03-28` showed the later-round synthetic path is weaker, but not
  cleanly overconfident in a way that supports a simple hard-coded shrink:
  round of 32 `54.3%` actual winner probability at `52.1%` accuracy,
  Sweet 16 `51.1%` at `50.0%`, Elite 8 `52.6%` at `58.3%`, Final Four `51.8%`
  at `33.3%`, championship `45.4%` at `33.3%`
- the same evidence also kept the broader context from TM-5 intact:
  `199/201` bracket picks still use the synthetic fallback, so any future
  calibration move would still mostly be a synthetic-path change rather than a
  priced-market routing tweak

Conclusion:

- reject a late-round confidence-shrink heuristic as the next challenger
- the weakest later rounds are small-sample and noisy, but the new actual-
  winner-probability view does not show a stable monotonic overconfidence
  pattern strong enough to justify a hard-coded round rule
- the next credible tournament lane is still a general synthetic-path quality
  improvement or richer diagnostics, not a round-specific probability haircut

### TM-7 [`approved` -> `completed`] Add favorite-versus-upset tournament diagnostics before adding a seed guardrail

Parent-task approval:

- explicitly approved by the current `2026-03-28` model-loop request

Problem:

- TM-4 through TM-6 rejected routing-first and late-round-only tournament
  heuristics, but the replay still does not say whether the synthetic path is
  specifically too aggressive on upset-style picks versus seed favorites
- without one stable favorite/upset summary, any seed-based guardrail would
  still be guesswork

Repo evidence:

- `TournamentGamePick` already carries `home_seed`, `away_seed`, and
  `winner_seed`, which is enough to classify each replayed pick as a favorite,
  upset, or same-seed result
- `src/cbb/modeling/tournament.py` currently aggregates tournament-backtest
  evidence only by season, round, and scoring source
- the existing CLI and JSON surfaces therefore cannot answer whether the next
  bounded synthetic-path challenger should be a seed-based upset haircut or
  whether that idea should be rejected before it changes behavior

Implementation shape:

- extend tournament backtest summaries with additive favorite/upset diagnostics
  for predicted picks and actual results
- surface those diagnostics in CLI text and machine-readable JSON output
- keep the pass diagnostics-only; do not change tournament scoring behavior in
  the same pass

Acceptance criteria:

- `cbb model tournament-backtest` reports favorite/upset summaries with pick
- count, accuracy, and actual-winner probability
- JSON output carries the same additive seed-role summaries
- targeted tournament tests cover the new summary fields
- the pass ends with an explicit promote/reject decision on a seed-guardrail
  hypothesis using the new evidence

Explicit non-goals:

- changing the live deployable betting policy
- changing tournament pick behavior in the same pass
- introducing hard-coded seed rules before the diagnostics exist

Outcome:

- completed in
  [src/cbb/modeling/tournament.py](../src/cbb/modeling/tournament.py),
  [src/cbb/cli.py](../src/cbb/cli.py),
  [src/cbb/modeling/__init__.py](../src/cbb/modeling/__init__.py),
  [tests/test_tournament.py](../tests/test_tournament.py), and
  [tests/test_cli.py](../tests/test_cli.py)
- `cbb model tournament-backtest` now emits additive `pick_seed_role_summaries`
  in both text and JSON output at the season and aggregate levels, classifying
  bracket picks as `favorite_pick`, `upset_pick`, or `same_seed_pick`
- bounded evidence from
  `cbb model tournament-backtest --seasons 3 --max-season 2025 --output-format json`
  on `2026-03-28` showed a stable favorite-versus-upset gap across the replay:
  aggregate favorite picks `89/134` (`66.4%`) at `57.95%` average actual-
  winner probability, upset picks `15/49` (`30.6%`) at `46.88%`, same-seed
  picks `10/18` (`55.6%`) at `51.98%`
- the same pattern held by season:
  `2023` favorites `22/43` versus upsets `7/19`,
  `2024` favorites `33/49` versus upsets `4/12`,
  `2025` favorites `34/42` versus upsets `4/18`

Conclusion:

- promote a bounded seed-aware upset challenger as the next credible
  tournament experiment
- do not promote a hard-coded guardrail directly from diagnostics alone; the
  next pass still needs a measured challenger and a full replay before any
  tournament behavior changes

### TM-8 [`approved` -> `completed`] Apply a bounded synthetic upset floor in tournament picks

Parent-task approval:

- explicitly approved by the current `2026-03-28` model-loop request

Problem:

- TM-7 showed that synthetic upset picks are the weakest part of the current
  bracket path, but diagnostics alone do not improve the replay
- the next bounded question is whether a simple synthetic-only upset floor can
  improve tournament replay without widening scope into new features or data

Repo evidence:

- TM-7 showed aggregate favorite picks at `89/134` (`66.4%`) versus upset picks
  at `15/49` (`30.6%`)
- the bounded local threshold sweep on `2026-03-28` showed that requiring at
  least `60%` confidence before keeping a synthetic upset improved the
  `2023-2025` replay from `114/201` (`56.7%`) to `121/201` (`60.2%`) while
  keeping champion hits at `1/3`
- that same sweep improved or held every replay season:
  `2023 31 -> 31`, `2024 41 -> 42`, `2025 42 -> 48`

Implementation shape:

- apply one bounded synthetic-only upset floor inside the tournament matchup
  evaluation path
- keep priced-market rows unchanged
- keep the pass scoped to tournament picks and tournament backtest behavior;
  do not touch the promoted live betting policy

Acceptance criteria:

- low-confidence synthetic upset picks flip back to the lower-seed favorite in
  the deterministic bracket path and the advancement simulation path
- targeted tournament tests cover the new guardrail behavior
- the pass ends with an explicit promote/reject decision using a rerun of the
  `2023-2025` tournament replay

Explicit non-goals:

- changing the deployable `best` betting path
- adding new features, schema work, or tournament data sources
- introducing round-specific heuristics in the same pass

Outcome:

- completed in
  [src/cbb/modeling/tournament.py](../src/cbb/modeling/tournament.py) and
  [tests/test_tournament.py](../tests/test_tournament.py)
- the tournament wrapper now flips low-confidence synthetic upset picks back to
  the lower-seed favorite before both deterministic bracket picks and
  advancement simulation sampling, while leaving priced rows and high-
  confidence synthetic upsets unchanged
- bounded replay evidence from
  `cbb model tournament-backtest --seasons 3 --max-season 2025 --output-format json`
  on `2026-03-28` improved the `2023-2025` bracket backtest from `114/201`
  (`56.7%`) and `54.72%` average actual-winner probability to `126/201`
  (`62.7%`) and `55.41%`
- per-season replay improved or held across the whole window:
  `2023 31/67 -> 34/67`,
  `2024 41/67 -> 42/67`,
  `2025 42/67 -> 50/67`
- champion hits held at `1/3`, with the correct champion now landing in `2024`
  instead of the old `2025` path

Conclusion:

- promote the bounded synthetic upset floor into the tournament wrapper
- keep the change scoped to tournament-mode behavior only; it does not justify
  any change to the promoted live `best` betting path

### TM-9 [`approved` -> `completed`] Add seed-gap tournament diagnostics before any extreme-upset ban

Classification:
Approved by the parent task and safe as the next bounded tournament cycle. This
pass is diagnostics-first and does not change the live `best` betting path.

Problem:

- TM-8 materially improved the `2023-2025` tournament replay, but the
  remaining misses still do not say whether a next guardrail should care about
  exact seed-gap size or whether the remaining errors are spread across many
  bracket shapes
- without one additive seed-gap summary, any follow-up rule such as “ban large
  synthetic upsets” would still be guessing from anecdotes rather than replay
  evidence

Repo evidence:

- TM-7 showed a broad favorite-versus-upset gap and TM-8 improved replay by
  flipping low-confidence synthetic upsets back to the favorite
- the current tournament backtest output now has round summaries,
  source summaries, and favorite/upset summaries, but it still cannot answer
  whether the residual misses cluster at specific seed gaps like `1`, `5`, or
  `8`
- `TournamentGamePick` already carries `home_seed`, `away_seed`, and
  `winner_seed`, so one additive seed-gap rollup can be derived without new
  data sources, schema work, or prediction-surface changes

Implementation shape:

- extend tournament backtest season and aggregate summaries with additive
  exact-seed-gap diagnostics for deterministic picks
- expose the same seed-gap summaries through the CLI text output and JSON
  output next to the existing round/source/seed-role diagnostics
- keep the pass report-only; do not change tournament pick behavior in the
  same cycle

Acceptance criteria:

- `cbb model tournament-backtest` reports exact seed-gap summaries with pick
  counts, accuracy, and average actual-winner probability
- JSON output carries the same additive seed-gap summaries
- targeted tournament tests cover the new summary fields and CLI rendering
- the pass ends with an explicit promote/reject decision on an extreme-gap
  upset ban as the next tournament challenger

Explicit non-goals:

- changing tournament pick behavior in the same pass
- adding new tournament data sources or schema work
- changing the promoted live `best` policy or canonical five-season report

Outcome:

- completed in
  [src/cbb/modeling/tournament.py](../src/cbb/modeling/tournament.py),
  [src/cbb/cli.py](../src/cbb/cli.py),
  [tests/test_tournament.py](../tests/test_tournament.py), and
  [tests/test_cli.py](../tests/test_cli.py)
- the tournament backtest season and aggregate summaries now expose additive
  exact seed-gap buckets with pick counts, accuracy, and average actual-winner
  probability
- the CLI text output now renders a `Pick Seed Gap Accuracy` section, and the
  JSON payload now carries the same `pick_seed_gap_summaries` contract for
  both aggregate and per-season results
- targeted tournament verification passed:
  `pytest -q tests/test_tournament.py tests/test_cli.py -k tournament`,
  `ruff check src tests scripts`, and `mypy src`

Conclusion:

- reject an immediate extreme-gap upset ban as the next tournament behavior
  challenger
- TM-8 already improved the `2023-2025` replay by flipping broad low-
  confidence synthetic upsets back to favorites, and that existing evidence
  still does not isolate one exact seed-gap family as the clear next lever
- keep the new seed-gap summaries as the durable research surface for future
  tournament work, but do not add another hard seed-gap rule until later
  replay evidence shows a stable failure pocket

### D-5 [`approved` -> `completed`] Expand historical coverage and move canonical workflows to five seasons

Parent-task approval:

- explicitly approved by the `2026-03-18` five-year data/default request

Problem:

- TM-3 still showed a `2023` tournament weakness because the local DB lacked
  `2021-2022` pre-tournament history and tracked bracket specs for those years
- the repo still defaulted to a three-season reporting/training window even
  though the requested backtest scope had moved to five years
- the historical close repair path only handled one market at a time and one
  malformed provider payload could abort a long backfill

Approved implementation shape:

- load historical ESPN game data back through the `2021` season and repair the
  team-catalog fallback path for recently departed Division I teams needed by
  that ingest
- track local men's bracket specs for `2021` and `2022`, including the `2021`
  Oregon-over-VCU walkover as an explicit actual-result override
- extend historical close repair so it can request
  `h2h,spreads,totals` together, skip malformed provider events, and commit one
  snapshot slot at a time so large backfills are resumable
- move the historical ingest, closing-odds ingest, verification, training,
  tournament-backtest, report, and dashboard canonical defaults to five seasons
  and move the tracked report path to
  [docs/results/best-model-5y-backtest.md](results/best-model-5y-backtest.md)

Implementation status:

- the current worktree now carries tracked men's bracket specs for
  `2021-2026`, plus the former-D1 catalog repair in
  [src/cbb/team_catalog.py](../src/cbb/team_catalog.py) and the resumable
  combined-market close repair in
  [src/cbb/ingest/closing_lines.py](../src/cbb/ingest/closing_lines.py)
- the five-season combined close repair on `2026-03-18` attempted all `5320`
  missing snapshot slots for `h2h,spreads,totals` with the preferred four-book
  set and spent `217890` credits
- remaining provider-limited residue after that pass is still material by
  season: `2021 496`, `2022 681`, `2023 610`, `2024 546`, `2025 560` games
  missing at least one of the three markets
- tournament evidence improved materially on the comparable `2023-2025` window:
  `91/201` (`45.3%`) correct picks and `50.5%` average actual-winner
  probability became `114/201` (`56.7%`) and `54.7%`; the biggest lift is
  `2023`, which improved from `20/67` to `31/67`
- the new `2021-2025` tournament replay lands at `172/335` (`51.3%`),
  `1/5` champion hits, and `53.2%` average actual-winner probability
- betting evidence is mixed rather than promotable on the comparable
  `2024-2026` window: the prior tracked three-season baseline of `420` bets,
  `+$1058.93`, and `+9.23%` ROI became `206` bets, `+$194.60`, and `+3.61%`
  ROI after the repaired-data rerun
- the canonical five-season report on `2022-2026` is still positive overall at
  `253` bets, `+$639.53`, and `+9.47%` ROI, but the action profile is much
  smaller than the old three-season baseline and `2024` remains the weakest
  season

## Data Sufficiency Blockers

These are the main blockers that still prevent the repo from moving beyond the
current policy-and-execution lane:

- no clearly richer open-breadth history that would justify a separate opening-
  depth feature family
- availability coverage is still one-season and shadow-only
- no player IDs or player-value layer for availability weighting
- the current home-location layer is good enough for diagnostics, but not yet
  sufficient evidence for a promoted direct travel-feature lane

## Recommended Implementation Order

1. keep the repaired-data incumbent as the active baseline until a challenger
   clears the full promotion bar
2. implement R-4 first so the `2024` regression is diagnosable without ad hoc
   queries
3. run R-1 next so the repaired dataset gets a real deployable policy
   reoptimization rather than the narrower pre-repair grid
4. only move to deferred R-3 if R-1 and R-2 fail or expose strong contrary
   evidence that the repaired-data bottleneck is model-family shape rather than
   calibration stability
5. only revisit R-5, M-3, S-1, or new-data lanes after the existing
   margin-regression path has had a full repaired-data robustness pass

## Decision Rule For The Next Cycle

Promote only if the challenger:

1. improves full-window ROI meaningfully, or keeps ROI roughly flat while
   improving drawdown materially
2. keeps at least `2/3` seasons profitable and materially improves the current
   `2024` weakness or offsets it with stronger aggregate and stability evidence
3. keeps activity credible rather than collapsing the board
4. stays at least as credible as the incumbent on close-quality evidence,
   especially spread price delta, spread no-vig close delta, and spread closing
   EV

With the repaired dataset now in place, do not keep retrying minor pre-repair
selection variants or jumping to new model families before the existing spread
margin-regression path has had a full repaired-data calibration and threshold
reoptimization pass.
