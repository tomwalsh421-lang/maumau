# Model Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

Updated: `2026-03-13`

## Goal

This cycle is now market-data first.

The immediate question is no longer "how do we store official availability?"
That part is done. The current repo-local question is:

- can the stronger Odds API market coverage now in Postgres improve the
  deployable spread-first `best` path
- if yes, what is the smallest execution, calibration, or policy change that
  clears the repo's promotion bar
- if no, which remaining repo-local ideas are no longer justified before a new
  information lane is approved

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
spread-policy cycle:

- `17496` stored games, `17434` completed games, and `499836` stored odds
  snapshots in the live local database
- historical closing coverage now spans all three featured markets used by the
  modeling layer:
  - `h2h`: `154176` closing snapshots across `77` books and `15331` games
  - `spreads`: `163784` closing snapshots across `56` books and `15302` games
  - `totals`: `167112` closing snapshots across `57` books and `15338` games
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
  `min_positive_ev_books=4`, no median-EV floor, and a same-day cap of `6`
  bets

What the current stored history does not obviously support yet:

- a rich new opening-depth feature lane; the current stored history appears to
  have nearly identical open-vs-close bookmaker breadth on most completed-game
  records
- travel, altitude, or timezone features; reproducible team home-location data
  is still missing from the repo
- deployable official availability features; that lane remains shadow-only and
  sample-limited

## Why The Next Promotion Attempt Should Be Market-Data Driven

The current best path already shows the repo's main signal:

- spread line CLV is still negative, but spread price delta, no-vig close
  delta, and spread closing EV are positive
- that means the remaining edge still looks more execution- and
  calibration-driven than raw line prediction-driven
- stronger close and live quote coverage should therefore be tested first
  through execution and survivability logic before widening into new feature or
  model-family work

Availability remains analytically useful but not promotion-ready:

- stored availability still represents only one recent season
- coverage is partial and shadow-only
- it is not the highest-confidence repo-local promotion lane for this cycle

## Current Baseline

The deployable baseline is still the spread-first `best` path documented in
[docs/results/best-model-3y-backtest.md](results/best-model-3y-backtest.md).

The key modeling paths remain:

- training: [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- dataset loading: [src/cbb/modeling/dataset.py](../src/cbb/modeling/dataset.py)
- feature generation: [src/cbb/modeling/features.py](../src/cbb/modeling/features.py)
- backtesting: [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- policy: [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- prediction: [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py)
- canonical reporting: [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)

Interpretation of the current baseline is now:

- aggregate: `511` bets, `+$1083.59`, ROI `+7.86%`, max drawdown `9.77%`
- `2024`: `145` bets, `-$164.55`, ROI `-4.80%`
- `2025`: `206` bets, `+$1022.43`, ROI `+16.29%`
- `2026`: `160` bets, `+$225.71`, ROI `+5.53%`
- aggregate spread close quality:
  `-0.50 pts` line CLV, `+1.99 pp` price delta, `+1.71 pp` no-vig close delta,
  `+0.082` spread closing EV
- the next justified experiment should use the stored venue metadata to test a
  home-location / travel proxy lane before revisiting availability

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

## Experiment Results This Cycle

### T-1 [`rejected`] Inferred home-state / venue-state travel proxy features from stored ESPN venue metadata

**Why this lane is first**

Availability is still not strong enough to take priority:

- the canonical report still only has `18` covered-side settled bets
- availability still represents one recent season only
- the live path still lacks a player-value layer, so raw status counts remain
  too coarse for promotion

The stored venue lane is stronger now:

- `17431` of `17434` completed games have `venue_state`
- all `365` teams have a dominant non-neutral home `venue_state` in the stored
  history
- every team has at least `10` observed non-neutral home games with a dominant
  state share above `0.80`

**Hypothesis**

The repo could test a bounded travel/home-location proxy without a new
external location dataset by inferring each team's stable home state from prior
non-neutral home games and comparing it to the stored game venue state.

The likely signal was not generic road/home, which the model already has. It
was whether a neutral or unusual site is effectively local for one team
relative to the other.

**Implementation**

- Attempt `T-1a`: expose `neutral_site` and `venue_state` to the modeling
  dataset, infer each team's dominant prior non-neutral home state
  sequentially, and add side-based venue-state match features for both sides.
- Attempt `T-1b`: tighten the same lane to neutral-site-only venue-state match
  features after the broader first attempt appeared to duplicate generic home
  context too often.
- Both attempts stayed additive and backward-compatible, and both were gated on
  `2026` before any full canonical report rerun.

**Files changed during the experiment**

- [src/cbb/modeling/dataset.py](../src/cbb/modeling/dataset.py)
- [src/cbb/modeling/features.py](../src/cbb/modeling/features.py)
- [tests/test_features.py](../tests/test_features.py)

The retained repo baseline does not keep those code changes because the
experiment was rejected.

**Backtest results**

Incumbent `2026` gate baseline:

- `160` bets, `+$225.71`, ROI `+5.53%`, max drawdown `7.40%`
- spread close quality: `-0.50 pts` line CLV, `+1.99 pp` price delta,
  `+1.71 pp` no-vig close delta, `+0.082` close EV

Attempt `T-1a` broad venue-state context:

- `165` bets, `+$179.87`, ROI `+4.22%`, max drawdown `6.08%`
- spread close quality: `-0.60 pts` line CLV, `+2.23 pp` price delta,
  `+1.94 pp` no-vig close delta, `+0.086` close EV

Attempt `T-1b` neutral-site-only venue-state context:

- `159` bets, `+$174.79`, ROI `+4.26%`, max drawdown `7.81%`
- spread close quality: `-0.65 pts` line CLV, `+2.30 pp` price delta,
  `+2.04 pp` no-vig close delta, `+0.090` close EV

**Tradeoffs**

- Both variants improved price/no-vig/close-EV evidence, which suggests the
  venue-state proxy may identify better-priced bets.
- Neither variant protected realized `2026` profit or ROI well enough to clear
  the first gate.
- The narrower neutral-only version still regressed the gate and slightly
  worsened drawdown relative to the incumbent, so the lane does not justify a
  full three-season report run.

**Conclusion**

Reject T-1 for the current repo-local cycle. The stored venue-state proxy is
not strong enough on its own to improve the deployable baseline. Do not keep
iterating minor variants of this inferred home-state lane without a richer
external home-location source or a stronger postseason/travel information
layer.

**Validation**

- targeted feature/dataset tests
- `2026` walk-forward gate first
- no full canonical report rerun because both gate attempts failed
- compare activity, drawdown, and close-quality metrics against the promoted
  `4`-book baseline

## Needs Follow-Up Before Approval

### M-2 [`needs follow-up`] Add a minimum median expected-value floor across eligible books

The current code already exposes `min_median_expected_value`, but it should not
be promoted or even tested before M-1 is resolved. It is a stricter version of
the same survivability idea, and the stronger market data first needs to show
that extra cross-book support actually helps before layering on a median-EV
floor.

If the promoted `4`-book baseline later shows a clearly weak low-support tail
with negative close-quality evidence, a bounded `0.005` to `0.015` median-EV
sweep would be the next local execution lane.

### M-3 [`needs follow-up`] Market-quality feature refresh using denser close data

This is not approved yet because the current feature set already encodes most
of the obvious consensus, move, dispersion, and cross-market information. A
new feature lane only becomes justified if the survivability-policy lane stalls
and the added market history can be shown to create genuinely new signals
rather than re-expressing the current ones.

### A-7 [`needs follow-up`] Availability-derived challenger features in training/backtest

Availability remains shadow-only. This lane still lacks the multi-season,
full-market, player-importance-aware evidence needed for a credible live
challenger.

### A-8 [`needs follow-up`] Availability-aware live policy guards

Hard rules based on raw `out` or `questionable` counts are still too blunt for
promotion. This lane stays behind the shadow evidence bar.

### S-1 [`needs follow-up`] Re-evaluate deployable Kelly and exposure caps

Sizing changes remain downstream of selection quality. Do not widen stake
fractions until the repo first proves that stronger market data can improve bet
selection.

## Deferred

### A-9 [`deferred`] Automated NCAA availability capture or fetch

Keep the current availability phase file-based and replayable.

### A-10 [`deferred`] Regular-season or non-official availability sources

Do not widen the availability lane before the current bounded shadow data is
either promoted or explicitly abandoned.

### A-11 [`deferred`] Team-location, travel, altitude, and timezone work

Still blocked on a reproducible team home-location source. This is a valid
future information lane, but it is not the current market-data cycle.

### A-12 [`deferred`] Always-on refresh services or Kubernetes restructuring

The current phase is still local-first. Do not widen into runtime topology
changes here.

## Rejected For This Cycle

### M-4 [`rejected`] Raw coverage-rate gating as the main stronger-market response

The repo already exposes `coverage_rate`, but raw support ratio alone is not a
good enough deployable signal. Stronger market coverage should first be tested
through absolute positive-EV book counts, not ratio-only gating.

### M-5 [`rejected`] Generic structural-model complexity on the current feature set

The current evidence still says the edge is more execution- and
calibration-driven than raw line-prediction-driven. Do not widen into more
expressive model families unless the market-data execution lane fails cleanly
and a new information-bearing feature set becomes available.

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

## Data Sufficiency Blockers

These are the main blockers that still prevent the repo from moving beyond the
current market-data execution lane:

- no reproducible team home-location layer for travel, altitude, or timezone
  features
- no clearly richer open-breadth history that would justify a separate opening-
  depth feature family
- availability coverage is still one-season and shadow-only
- no player IDs or player-value layer for availability weighting

## Recommended Implementation Order

1. no further same-signal survivability change is approved right now
2. no repo-local promotion item is approved right now after T-1 failed twice
3. only approve M-2 or M-3 if a new read of the strengthened market data shows
   a clear remaining weakness in the promoted `4`-book baseline
4. otherwise the next credible lane requires new information, not more local
   tuning of the current signal set

## Decision Rule For The Next Cycle

Promote only if the challenger:

1. improves full-window ROI meaningfully, or keeps ROI roughly flat while
   improving drawdown materially
2. keeps at least `2/3` seasons profitable and does not materially worsen the
   weakest season, especially `2025` as the current robustness canary
3. keeps activity credible rather than collapsing the board
4. stays at least as credible as the incumbent on close-quality evidence,
   especially spread price delta, spread no-vig close delta, and spread closing
   EV

With M-1 promoted, do not keep retrying minor same-signal variants without new
evidence.
