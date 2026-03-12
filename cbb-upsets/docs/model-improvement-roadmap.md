# Model Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

Updated: `2026-03-12`

## Goal

This document is the current research roadmap for improving the deployable NCAA
men's basketball model.

The optimization target is unchanged:

- long-run ROI
- stability across seasons
- realistic betting activity
- no material drawdown increase

The strategy changed after another full repo review:

- the current edge still looks more calibration- and execution-driven than raw
  spread-line-driven
- repeated same-signal tuning has mostly failed to survive the full
  three-season window
- the largest missing information classes are still exogenous data that the
  repo does not store yet
- new data should land as replayable ingest plus shadow analysis before it is
  allowed to influence live betting policy

The top roadmap lane is now data acquisition, not more tuning of the current
signal set.

## Current Baseline

The current deployable path is still the spread-first `best` strategy. The
main code paths remain:

- training: [src/cbb/modeling/train.py](../src/cbb/modeling/train.py)
- features: [src/cbb/modeling/features.py](../src/cbb/modeling/features.py)
- quote execution: [src/cbb/modeling/execution.py](../src/cbb/modeling/execution.py)
- backtesting: [src/cbb/modeling/backtest.py](../src/cbb/modeling/backtest.py)
- policy: [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py)
- prediction: [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py)
- canonical reporting: [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)

Current tracked baseline from
[docs/results/best-model-3y-backtest.md](results/best-model-3y-backtest.md):

- aggregate: `+$268.02` on `536` bets, ROI `+7.20%`
- seasons: `2024=-6.66%`, `2025=+13.49%`, `2026=+10.06%`
- profitable seasons: `2/3`
- max drawdown: `8.78%`
- aggregate spread close EV: `+0.086`
- aggregate spread line CLV: `-0.47 pts`
- aggregate spread price CLV: `+1.91 pp`
- aggregate spread no-vig close delta: `+1.61 pp`

Interpretation:

- the repo has a positive multi-season deployable baseline
- the edge is still not proving a durable raw spread-line advantage
- the promoted gains have mostly come from calibration, uncertainty control,
  quote selection, and risk shaping
- more expressiveness on the same stored signal set has not produced a stable
  promotion result

## Why The Roadmap Pivoted

The repo's durable docs already call out the missing inputs:

- [docs/model.md](model.md) says the system still does not ingest true player
  availability, roster-turnover, coaching, or news feeds
- [docs/model.md](model.md) and
  [docs/architecture.md](architecture.md) both note that reproducible
  travel-distance, altitude, and timezone features are still blocked on a
  stable team-location foundation
- [sql/schema.sql](../sql/schema.sql) and
  [src/cbb/ingest/persistence.py](../src/cbb/ingest/persistence.py) currently
  store only games, odds snapshots, and ingest checkpoints; there is no
  supported availability source yet

That diagnosis now drives roadmap priority.

The first bounded source is official NCAA tournament player availability
reporting:

- NCAA announced the reporting rollout on `2025-10-30`
- NCAA published the public process details on `2026-03-04`
- reports are public on `ncaa.com`
- teams submit an initial report by `9 p.m.` local venue time the night before
  competition and updates by `2 hours` before tip
- public statuses are `available`, `questionable`, and `out`

This is the right first lane because it is official, bounded, high-signal, and
small enough to add without widening into speculative infrastructure.

The official team-location lane based on College Scorecard / IPEDS latitude and
longitude remains plausible, but it is a second-phase foundation after the
first availability source is stored and audited.

## Roadmap Rules For New Data

Any new source promoted from this document should follow the same sequence:

1. add one source at a time
2. store provenance, timestamps, and replayable raw payloads
3. expose shadow analysis first through import summaries, audits, and report
   segments
4. require walk-forward evidence before live model use
5. keep the current model architecture mostly stable while the data layer grows

## Completed Repo-Local Work For This Cycle

### D-1 [`completed`] Official NCAA tournament availability storage foundation

**Hypothesis**

The highest-value repo-local improvement is to store official NCAA tournament
availability reports in a way that can be replayed, audited, and joined back to
existing game rows without changing live model behavior.

**Implementation sketch**

- Extend [sql/schema.sql](../sql/schema.sql) with additive tables for official
  report snapshots and normalized player statuses. Keep the scope narrow to the
  supported first source rather than introducing a generic source abstraction.
- Persist source provenance and replayability fields directly in those tables:
  source name, source URL, captured time, report publication/effective time,
  import time, raw payload, and a stable dedupe key or content hash.
- Attach reports to existing games through current canonical identifiers first:
  `games.source_event_id`, `games.ncaa_game_code`, `games.commence_time`, and
  canonical teams via `teams.team_id` / `teams.ncaa_team_code`.
- Add typed ingest models alongside the existing summaries in
  [src/cbb/ingest/models.py](../src/cbb/ingest/models.py) or a dedicated
  availability module, and add idempotent upsert helpers beside the existing
  game/odds persistence code in
  [src/cbb/ingest/persistence.py](../src/cbb/ingest/persistence.py).

**Expected impact**

- no immediate bankroll change
- creates the first official player-availability dataset in the repo
- enables later shadow analysis keyed to an authoritative public source

**Risks**

- tournament-only scope means sparse coverage at first
- player-name matching can be noisy without roster IDs
- game matching may need explicit fallbacks when upstream identifiers are absent

**Validation plan**

- targeted schema and persistence tests for idempotent reruns
- confirm one report can be imported twice without duplicating snapshot or
  player-status rows
- verify game/team linkage works against stored `games` rows, with unmatched
  rows surfaced explicitly rather than silently dropped

**Promotion / rejection criteria**

- promote this item if the repo can store official snapshots end to end, retain
  raw payloads, and expose normalized queryable rows without changing existing
  betting behavior
- reject or reduce scope if the design requires speculative generic abstractions
  or cannot be made idempotent

### D-2 [`completed`] Replayable local import workflow for official report captures

**Hypothesis**

A file-based import path is the correct first executable workflow because it
supports the official NCAA source cleanly without pretending the repo already
has a stable live fetcher or always-on runtime.

**Implementation sketch**

- Add one additive CLI entry point under the existing ingest surface in
  [src/cbb/cli.py](../src/cbb/cli.py), following the pattern used by
  `ingest_data_command()` and `ingest_closing_odds_command()`.
- Keep the first supported input contract explicit and bounded: import captured
  official NCAA availability report payloads from local files plus source
  metadata, not live scraping and not generic injury feeds.
- Add a dedicated parser/normalizer module under
  [src/cbb/ingest/](../src/cbb/ingest/) for this source. The import command
  should emit a concrete summary: snapshots imported, player rows imported,
  games matched, teams matched, rows unmatched, and duplicates skipped.
- Support reruns through dedupe keys or content hashes so the command is safe
  to replay on the same capture set.
- Add a read-only audit helper if needed, but keep it tied to the stored source
  and existing repo semantics rather than a new service layer.

**Expected impact**

- no immediate bankroll change
- establishes a real, replayable ingest workflow for the first official source
- lets the repo collect data now without waiting on later infrastructure work

**Risks**

- upstream payload structure may change before the repo has enough captured
  examples
- if the import contract is too generic, the first phase will turn into
  scaffolding instead of supported behavior

**Validation plan**

- targeted CLI and parser tests using checked-in fixtures
- verify import summaries stay deterministic across reruns
- verify unmatched rows are counted and surfaced in command output

**Promotion / rejection criteria**

- promote this item if the repo can import captured official reports from local
  fixtures end to end with deterministic summaries and no hidden side effects
- reject any implementation that claims live public fetching support without a
  verified upstream contract and tests

### D-3 [`completed`] Shadow analysis in the canonical report and dashboard snapshot

**Hypothesis**

The first useful use of the new source is visibility, not live prediction.
Adding shadow analysis to the canonical report path will make the data quality
legible and keep promotion decisions evidence-based.

**Implementation sketch**

- Extend the reporting path in
  [src/cbb/modeling/report.py](../src/cbb/modeling/report.py) so
  `build_best_backtest_report()` / `render_best_backtest_report()` can include a
  compact availability-data section when stored official reports exist.
- Focus the first segment on coverage and recency, not model claims:
  games with official reports, snapshot counts, latest-update timing relative
  to tip, status counts, unmatched import counts, and season/tournament scope.
- Keep this read-only and shadow-only. Do not change
  [src/cbb/modeling/features.py](../src/cbb/modeling/features.py),
  [src/cbb/modeling/train.py](../src/cbb/modeling/train.py), or
  [src/cbb/modeling/policy.py](../src/cbb/modeling/policy.py) for this phase.
- Mirror the same read model into the dashboard snapshot / middleware path so
  the UI can expose the new data without coupling itself to ingest internals.

**Expected impact**

- no immediate bankroll change
- makes the new data observable and auditable from the repo's canonical report
  path
- provides the evidence base needed before feature promotion

**Risks**

- sparse first-phase coverage could be misread as model evidence if the report
  language is not explicit
- dashboard additions can drift if the report and snapshot read models are not
  kept aligned

**Validation plan**

- targeted report and dashboard tests
- verify the report renders a clear "no official availability data loaded"
  state when appropriate
- verify the canonical snapshot stays backward compatible for existing UI views

**Promotion / rejection criteria**

- promote this item if official availability data becomes visible in the
  canonical report flow without changing live bet selection
- reject any implementation that leaks shadow-only fields into live execution
  logic or rewrites artifact semantics

## Needs Follow-Up Before Any Live Model Use

### D-4 [`needs follow-up`] Promote official availability into features or policy

**Why this is not approved now**

The first official source is tournament-scoped and only recently standardized.
That is enough to justify storage and shadow analysis now, but not enough to
justify immediate live-model promotion.

**Follow-up requirements**

- accumulate enough stored official reports to evaluate coverage and matching
  quality
- define a stable feature contract from the stored statuses to model inputs
- run walk-forward comparisons that check aggregate ROI, drawdown, activity, and
  per-season stability
- prove the new feature helps without relying on one short tournament slice

**Promotion criteria**

- no promotion from shadow analysis to live features unless the change improves
  walk-forward evidence and does not materially break earlier windows

## Deferred Future Data-Source Work

### D-5 [`deferred`] Automated NCAA availability capture or fetch

Defer live source retrieval until the public upstream contract is validated
against real samples and the repo can support it without brittle scraping
claims. The first supported phase is file-based import of captured official
reports.

### D-6 [`deferred`] Official team-location foundation for travel, timezone, and altitude

The second-phase location lane should start from official institution latitude
and longitude sources such as College Scorecard / IPEDS, then add a narrow team
location table that can support reproducible travel features. This is
explicitly later than the first availability lane.

### D-7 [`deferred`] Offseason regime data: transfers, continuity, and coaching changes

These are still attractive information classes, but they need a bounded,
authoritative source choice and a clearer replay story than the repo currently
has.

### D-8 [`deferred`] Always-on runtime, scheduled refresh, or Kubernetes data services

The user explicitly deferred cluster/runtime restructuring. Keep this phase
local-first and additive to the current CLI-driven workflows.

## Rejected Or Demoted Same-Signal Lanes

These lanes are now demoted behind new data acquisition unless a future source
changes the information set materially.

### R-1 [`rejected`] More same-signal recalibration and segmentation passes

Adaptive recalibration, phase-specific thresholds, and similar policy retuning
have repeatedly failed to survive the full walk-forward window.

### R-2 [`rejected`] More expressive model families on the current stored data alone

The repo-local failures on nonlinear ensembles and other richer same-signal
variants are enough to demote this lane until the input information set changes
meaningfully.

### R-3 [`rejected`] Segment-based kill switches on current report slices

The current report slices still do not show a stable region that is both large
enough and clearly negative on close-EV evidence. Keep the segment views as
diagnostics, not live blocking rules.

### R-4 [`rejected`] Promoting neutral-site or postseason tuning ahead of new data

The venue and postseason data foundation already landed, but the first
repo-local experiment improved the latest season while losing aggregate ROI and
activity. That lane is not the best next use of time.

## Recommended Ownership Lanes For Implementation

These approved items are narrow enough for `2-3` implementation workers with
mostly disjoint ownership:

1. **Schema and persistence lane**
   - [sql/schema.sql](../sql/schema.sql)
   - [src/cbb/ingest/models.py](../src/cbb/ingest/models.py) or a new
     availability ingest module
   - [src/cbb/ingest/persistence.py](../src/cbb/ingest/persistence.py)
   - responsibility: new tables, typed records, idempotent upserts, matching
     helpers
2. **Import and CLI lane**
   - [src/cbb/ingest/](../src/cbb/ingest/)
   - [src/cbb/cli.py](../src/cbb/cli.py)
   - related ingest / CLI tests
   - responsibility: file-based import command, parser/normalizer, deterministic
     summaries, fixture-driven tests
3. **Shadow analysis and UI read-model lane**
   - [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
   - [src/cbb/dashboard/](../src/cbb/dashboard/)
   - [src/cbb/ui/](../src/cbb/ui/)
   - docs and report/dashboard tests
   - responsibility: report section, snapshot payload, UI visibility, explicit
     shadow-only wording

## Current Blockers And Risky Assumptions

- The official NCAA source is recent and tournament-scoped, so live-model use
  is blocked on sample size even if ingest lands cleanly.
- The exact public payload shape may not yet be stable enough to justify an
  automated fetcher; the first supported phase should therefore stay file-based.
- Player-name normalization may require conservative matching and explicit
  unmatched-row reporting before any downstream feature work.
- The current repo should not infer that later official sources already exist.
  Team-location, transfers, and coaching data are separate future lanes.
