# UI/UX Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-5y-backtest.md)

Updated: `2026-03-28`

## Goal

Keep the dashboard stable, useful, and honest while model work starts moving
closer to the new official NCAA availability data.

Immediate target for this cycle:

- preserve the existing dashboard and middleware architecture
- expose stored availability data clearly enough to evaluate coverage and
  matching quality without reading raw markdown
- make report, snapshot, middleware, and UI language truthful if availability
  moves from shadow-only diagnostics toward research or live model use
- prevent regressions in the dashboard JSON and snapshot contracts

Explicit non-goals for this cycle:

- no major frontend rewrite
- no separate SPA
- no dashboard-owned ingest, training, or model-refresh controls
- no Kubernetes always-on middleware service or background worker rollout

## Current Expansion Override

The `2026-03-28` infra and UX architectural loop explicitly approved a bounded
React migration for the frontend layer. That override supersedes the earlier
`no major frontend rewrite` rule for this run only, provided each pass stays:

- additive and mergeable
- honest about any still-server-rendered surfaces
- grounded in the existing middleware and JSON boundaries
- free of dashboard-owned ingest, training, or model-refresh controls

This migration still must not become a big-bang rewrite. The working rule is:

`one React slice at a time while the classic pages remain usable`

## Working Agreement

- `ux_researcher` maintains this document.
- `implementer` only executes items explicitly approved by the parent task or
  clearly marked approved here.
- The completed middleware split remains the architectural baseline.
- This cycle is about small additive UI and middleware work only.

## Current Audit

Files reviewed for this refresh:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py)
- [src/cbb/dashboard/snapshot.py](../src/cbb/dashboard/snapshot.py)
- [src/cbb/ui/app.py](../src/cbb/ui/app.py)
- [src/cbb/ui/templates/dashboard.html](../src/cbb/ui/templates/dashboard.html)
- [src/cbb/ui/templates/models.html](../src/cbb/ui/templates/models.html)
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py)
- [src/cbb/db.py](../src/cbb/db.py)
- [tests/test_dashboard_ui.py](../tests/test_dashboard_ui.py)
- [tests/test_dashboard_snapshot.py](../tests/test_dashboard_snapshot.py)
- [tests/test_report.py](../tests/test_report.py)

Repo-specific findings:

- The middleware split is already in place. The presentation layer in
  [src/cbb/ui/app.py](../src/cbb/ui/app.py) talks to
  [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) rather than
  importing modeling or DB code directly.
- The reporting path already carries availability shadow data through
  [src/cbb/modeling/report.py](../src/cbb/modeling/report.py), and the
  snapshot layer already round-trips that summary in
  [src/cbb/dashboard/snapshot.py](../src/cbb/dashboard/snapshot.py).
- The read model in [src/cbb/db.py](../src/cbb/db.py) is intentionally
  defensive and read-only. That is the right shape for UI use during this
  phase.
- The dashboard currently exposes availability only as one overview card built
  in [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py). That is
  enough for shadow visibility, but it is too compressed if model experiments
  start consuming the data.
- Current report and dashboard copy still hard-code the assumption that
  official availability is strictly shadow-only. That is accurate today, but
  it will become misleading if research or live paths start using the data in
  any bounded way.
- The models and upcoming templates do not yet have a dedicated place to show
  an explicit availability usage state, coverage details, or matching quality.
- The snapshot tests already cover backward-compatible loading for missing
  availability payloads, which is the right base for the next additive
  contract step.

## Design Direction

The next UI cycle should stay small and additive.

The repo does not need another architecture pass. It needs a clearer contract
for one question:

`What role does official availability data play in the current report and live board?`

That contract should flow through the existing backend shape:

`DB read model -> report/snapshot identity -> dashboard middleware -> UI copy`

The UI should not infer this from scattered hard-coded strings.

## React Migration Epic

### UX-REACT-1 [`completed`] Scaffold the React frontend and mount a beta overview route

Problem:

- the current UI layer is entirely Python-rendered, so there is no supported
  frontend build pipeline or mounted React surface to migrate pages into

Repo evidence:

- the repo has no `package.json`, `package-lock.json`, `tsconfig.json`, or
  frontend build config
- `src/cbb/ui/app.py` serves only Jinja templates and flat static assets
- `src/cbb/dashboard/service.py` already exposes typed page payloads and JSON
  endpoints that are suitable as a backend boundary for a React client

Implementation shape:

- add one bounded React workspace with a deterministic local build
- emit built assets into the Python static tree so the repo stays runnable
  without introducing a separate frontend server requirement
- mount one beta `/app` route that renders a React overview against the
  existing dashboard JSON contract while leaving the classic pages intact

Acceptance criteria:

- the repo has one supported frontend install/build path for the React client
- `/app` serves a working React shell from built local assets
- the React shell reads the existing dashboard JSON contract rather than
  importing modeling or database code directly
- the classic server-rendered routes continue to work unchanged for this pass

Explicit non-goals:

- replacing every dashboard page in one pass
- removing the classic Jinja templates
- changing report, snapshot, or model semantics for the sake of the new shell

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- this slice stayed UI-only by mounting `/app` against the existing
  `/api/dashboard` middleware contract while leaving the classic pages intact

### UX-REACT-2 [`completed`] Add a React recommendations view backed by `/api/upcoming`

Classification:
Approved by the parent task and safe as a UI-only React migration step. It
reuses the existing upcoming-page JSON contract and does not require a model
roadmap item first.

Problem:

- the React beta currently proves only the overview route, while the more
  operational recommendations surface still lives exclusively in the classic
  Jinja path

Repo evidence:

- `frontend/src/App.tsx` currently loads only `/api/dashboard`
- `src/cbb/ui/app.py` serves the React shell only at `/app`, not a nested
  React recommendations path
- `src/cbb/ui/templates/upcoming.html` and `/api/upcoming` already carry the
  policy note, availability summary, live picks, timing watchlist, and
  live-board context needed for a meaningful next React slice

Implementation shape:

- extend the React beta shell so `/app/upcoming` mounts through the same WSGI
  template and bundle
- add one React recommendations view that consumes `/api/upcoming` and renders
  the key operator-facing sections from the classic page
- keep the classic `/upcoming` page intact and keep the JSON contract additive
  and backward compatible

Acceptance criteria:

- `/app/upcoming` returns the React shell from the Python app
- the React bundle fetches and renders the existing `/api/upcoming` payload
- the React beta exposes navigation between overview and recommendations
  without removing the classic routes
- targeted dashboard UI tests cover the new shell route and asset serving

Explicit non-goals:

- removing the classic upcoming template
- changing prediction semantics or the `/api/upcoming` contract for this pass
- migrating models, performance, or picks in the same slice

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- this slice kept the migration UI-only by mounting `/app/upcoming` against the
  existing `/api/upcoming` contract while leaving `/upcoming` intact

## Completed Foundation

### UX-OP-1 [`completed`] Add FanDuel links to agent-mode qualified bets

Completed on `2026-03-27`.

Classification:
Approved by the parent task and implemented as a UI-only CLI workflow change.

Problem:
The local `cbb agent` loop printed the recommended side, price, and unit-sized
stake, but operators still had to manually search FanDuel after each accepted
bet.

Implemented shape:

- append one separate FanDuel college-basketball team-page URL under each
  qualified bet in agent mode
- keep the existing unit-based stake output unchanged
- keep the change inside CLI rendering only, with no report, snapshot, or
  prediction contract change
- use the repo's canonical team-name normalization to build deterministic URLs
  and avoid ad hoc slug logic

### UX-FE-1 [`completed`] Dashboard middleware boundary outside the UI package

Completed on `2026-03-12`.

The backend-facing dashboard orchestration now lives under
[src/cbb/dashboard/](../src/cbb/dashboard/) and the UI package is presentation-
first again.

### UX-FE-2 [`completed`] Typed middleware contract and JSON response surface

Completed on `2026-03-12`.

The dashboard now exposes a stable middleware-backed HTML and JSON surface for
the major views.

### UX-FE-3 [`completed`] Backend-owned snapshot/bootstrap orchestration

Completed on `2026-03-12`.

Snapshot readiness and refresh policy are backend concerns instead of UI-owned
startup logic.

### UX-FE-4 [`completed`] Durable docs for the frontend/backend split

Completed on `2026-03-12`.

The README and architecture docs now describe the dashboard middleware layer
and explicitly defer always-on runtime work.

### UX-FE-9 [`completed`] Compatibility work for approved model/report changes

Completed on `2026-03-12`.

The dashboard snapshot and middleware contract already absorb additive policy
and availability-summary fields without breaking older payloads.

### UX-PF-1 [`completed`] Expand performance charts beyond latest-window recency bias

Completed on `2026-03-12`.

Classification:
Approved by the parent task and implemented as a UI-only change.

Problem:
The performance page emphasized short recent windows and could make the latest
late-season run read like the whole story.

User impact:
Operators could overread the end of the current season and miss weaker earlier
seasons that still matter for promotion decisions.

Repo evidence:

- [src/cbb/ui/templates/performance.html](../src/cbb/ui/templates/performance.html)
  previously centered the page on one selected recent-window sparkline.
- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) already had
  access to the full settled bet history and per-season summaries through the
  snapshot-backed report.
- [docs/results/best-model-dashboard-snapshot.json](results/best-model-dashboard-snapshot.json)
  already stores multi-season `historical_bets` and `season_summaries`, so no
  new report or snapshot contract was required.

Implemented shape:

- add a full-window cumulative profit chart on the performance page
- add a normalized season-overlay chart where each season restarts at zero
- keep per-season summary cards visible alongside the recent-window section
- mark season boundaries so the current hot streak is visible in context

### UX-PF-2 [`completed`] Surface the default stake range on the dashboard

Completed on `2026-03-13`.

Classification:
Approved by the parent task and implemented as an additive middleware and UI
change.

Problem:
The report showed starting bankroll and unit size, but the dashboard did not
make the actual bet-size scale obvious. Operators still had to infer whether
the default board was sizing closer to `$5`, `$25`, or `$50`.

Implemented shape:

- add a stake-range overview card to the dashboard and models pages
- derive the card from canonical report bet history, so the UI uses the same
  settled stake distribution as the report
- keep the snapshot contract unchanged for this step; the middleware computes
  the range from the rehydrated report payload
- align the UI with the report, which now calls out typical, smallest, and
  largest settled bet sizes explicitly

### UX-LB-1 [`completed`] Keep the live board visible after tip-off

Completed on `2026-03-13`.

Classification:
Approved by the parent task and implemented as a dashboard/prediction contract
change rather than a template-only tweak.

Problem:
The live board dropped games once they tipped because the current prediction
payload only exposed future games. Operators could not tell whether an
in-progress or just-finished game had been a bet, a watch-only angle, or a
pass.

User impact:
The board looked cleaner than reality and made same-slate audit work harder,
especially when checking whether a finished game had actually been on the live
board.

Repo evidence:

- [src/cbb/modeling/infer.py](../src/cbb/modeling/infer.py) previously built
  board rows from a future-only record set.
- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) had no row
  model that could separate game state from board decision.
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  previously rendered only upcoming angles and had no place for a live or
  final result.

Implemented shape:

- add a live-board record window that spans recent finals, in-progress games,
  and upcoming games while still using stored pregame odds for the board
  decision
- keep the actionable pick and watchlist sections future-only
- add a dedicated live-board row model in the dashboard middleware
- render game state, board decision, selected side, and live/final result on
  the upcoming page

### UX-PF-3 [`completed`] Add interactive inspection to the time-series charts

Completed on `2026-03-13`.

Classification:
Approved by the parent task and implemented as a UI/middleware contract change.

Problem:
The performance page drew time-series SVGs, but they were still static images.
Operators could not hover a point, inspect the exact cumulative value, or
isolate one season without reading the summary cards and tables separately.

User impact:
The page looked like a report, not a time-series dashboard. It made it slower
to answer simple interaction questions such as "what happened here?" or "how
did 2025 finish versus 2026?"

Repo evidence:

- [src/cbb/ui/templates/performance.html](../src/cbb/ui/templates/performance.html)
  rendered static polylines with no hover/focus affordance.
- [src/cbb/ui/static/dashboard.js](../src/cbb/ui/static/dashboard.js) only
  handled team search and report warmup refresh.
- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) exposed line
  geometry only, not point-level labels for interaction.

Implemented shape:

- add point-level chart metadata to the middleware contract for the performance
  charts
- add hover/focus inspection panels for the full-history and season-overlay
  charts
- make the season overlay legend clickable so one season can be isolated
  without leaving the page
- keep the page server-rendered and read-only; the interaction layer is a
  small progressive enhancement, not a SPA rewrite

### UX-PF-4 [`completed`] Break out min and max bet size by performance window

Completed on `2026-03-13`.

Classification:
Approved by the parent task and implemented as an additive UI/middleware
change. This is UI-only relative to the model/report/snapshot stack; it uses
existing settled bet history already rehydrated from the canonical report.

Problem:
The dashboard already surfaced one aggregate stake-range card, but the
performance page did not show how bet size changed across the `7`, `14`, `30`,
`90`, and season windows.

User impact:
Operators could see recent profit and total risked, but they still had to
infer whether the selected window contained mostly smaller or larger settled
stakes than the broader report range.

Repo evidence:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) already
  derives each performance window from settled historical bets, including
  `stake_amount`.
- [src/cbb/ui/templates/performance.html](../src/cbb/ui/templates/performance.html)
  previously rendered window selectors and a selected-window metric grid
  without any per-window min/max stake breakout.
- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py) already computes
  aggregate stake-range summaries for the full report, so no new model or
  snapshot data source was needed for this narrower page-level view.

Implemented shape:

- add min/max stake labels to the performance-window middleware payload
- show min/max stake directly on each time-frame selector so the page compares
  window scale at a glance
- add min/max stake rows to the selected-window detail grid
- keep the snapshot contract unchanged; the middleware derives the breakout
  from existing settled bet history

## Approved Focus Cycle

### UX-FC-1 [`completed`] Refocus the primary dashboard around the best model, performance, upcoming recommendations, and season-filterable bet history

Completed on `2026-03-23`.

Classification:
Approved by the parent task and implemented as an additive dashboard
middleware and UI pass.

Problem:
The current UI already exposes most of the useful information, but it spreads
it across too many primary destinations and still gives secondary surfaces such
as team exploration and availability diagnostics too much visual priority for
the operator's core workflow.

User impact:
An operator who mainly wants to understand the current `best` path, review
interactive performance, inspect upcoming recommendations, and scan historical
bets by season still has to bounce between pages that duplicate copy, expose
lower-priority diagnostics, or force date-based filtering when the real review
question is often season-based.

Repo evidence:

- [src/cbb/ui/app.py](../src/cbb/ui/app.py) currently exposes six primary nav
  items, including `Team Explorer`, even though the main deployable workflow
  centers on the best model, performance, upcoming picks, and pick history.
- [src/cbb/ui/templates/dashboard.html](../src/cbb/ui/templates/dashboard.html)
  currently mixes model framing, recent performance, upcoming picks, recent
  settled rows, and a metric glossary into one landing page.
- [src/cbb/ui/templates/models.html](../src/cbb/ui/templates/models.html)
  currently prioritizes artifact inventory and availability diagnostics over a
  clearer explanation of how the promoted best-path model works and why the
  report trusts it.
- [src/cbb/ui/templates/performance.html](../src/cbb/ui/templates/performance.html)
  already has the interactive chart base the user wants.
- [src/cbb/ui/templates/picks.html](../src/cbb/ui/templates/picks.html) already
  shows the season on each historical row, but the filters are still date/team/
  result/market/sportsbook only.
- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) already has
  enough report-derived state to support a season filter and a tighter
  best-model-first presentation without changing the report or prediction
  sources.

Proposed solution:
Keep the existing server-rendered architecture and route surface, but simplify
the primary dashboard experience so the main workflow is:

`best model -> performance -> upcoming recommendations -> historical bets by season`

Implemented shape:

- narrow the primary navigation to `Overview`, `Performance`,
  `Recommendations`, and `Bet History`, while keeping `Model Review` and
  `Team Explorer` directly reachable as secondary routes
- rewrite the landing page around the operator loop and move season-filtered
  history handoff into dedicated season cards
- refocus the models page on the promoted path, report trust checks, artifact
  inventory, and season stability before secondary diagnostics
- keep the interactive performance charts as the main inspection surface and
  link every season card directly into season-filtered bet history
- add an explicit season filter to pick history and keep the existing team /
  result / market / sportsbook filters
- keep this additive to the existing dashboard middleware and route surface;
  no SPA or dashboard-owned operational controls were introduced

Acceptance criteria:

- the primary nav and landing-page copy clearly center the best model,
  performance, recommendations, and historical review workflow
- the performance page remains interactive and becomes the obvious place to
  inspect multi-season behavior
- the picks page can filter directly by season
- no report, snapshot, or prediction-contract change is required for this pass
- team and other lower-priority views can remain available without competing
  with the main workflow in the primary nav

Smallest coherent delivery scope:

- narrow the primary nav to the best-model overview, performance,
  recommendations, and bet-history workflow while keeping lower-priority
  routes available directly
- rewrite the landing page to emphasize best-path explanation, performance
  snapshot, upcoming recommendations, and a clear handoff into filtered bet
  history
- refocus the models page around how the promoted path works and why the
  report trusts it, while keeping artifact inventory and availability
  diagnostics as secondary detail
- add a season filter to the picks page and link season cards directly into
  season-filtered bet history from the dashboard and performance pages

Change boundary:

- this is not template-only; it requires additive dashboard middleware changes
  for pick-history filter state and page payload reshaping
- it does not require report, snapshot, or live prediction-contract changes

Suggested ownership:

- dashboard middleware, template, and UI verification thread

## Ranked Improvements For The Availability Cycle

### UX-AV-1 [`completed`] Add an explicit availability usage-state contract

Completed on `2026-03-23`.

Classification:
Approved by the parent task and implemented across the report, snapshot,
dashboard middleware, and read-only UI surfaces.

Problem:
The report and dashboard currently rely on hard-coded shadow-only language.
That is accurate today, but it will become misleading if availability data
starts informing research predictions or later live decisions.

User impact:
Operators could misread the current board or report and not know whether
availability is merely stored, used in experiments, or used in the promoted
path.

Evidence:

- [src/cbb/modeling/report.py](../src/cbb/modeling/report.py) renders fixed
  shadow-only language in the canonical report.
- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) renders an
  overview card that also assumes diagnostic-only usage.
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  currently has no dedicated place to say whether the live board is using
  official availability data.

Implemented shape:
Add one additive usage-state field that travels through the report, snapshot,
middleware, and UI surfaces.

Implementation sketch:

- define a small explicit state set such as `not_loaded`, `shadow_only`,
  `research_only`, and `live_path`
- carry that state and a short operator-facing note through the canonical
  report identity and dashboard snapshot
- default missing older payloads to the current repo truth: `shadow_only`
- render the same state consistently in report copy, models view, and upcoming
  board copy

Acceptance criteria:

- report and dashboard language stop relying on scattered hard-coded wording
- the UI can state clearly whether availability affects the current live board
- older snapshot payloads remain readable without migration work

Suggested ownership:

- report/snapshot/middleware compatibility thread

### UX-AV-2 [`completed`] Promote availability diagnostics from one card to one compact models-page section

Completed on `2026-03-23`.

Classification:
Approved by the parent task and implemented as an additive models-page
middleware and template section.

Problem:
The current overview card is too compressed to judge whether the stored
availability data is actually usable for model work.

User impact:
A single card can show that some data exists, but it cannot explain coverage,
timing, matching quality, scope, or status mix well enough for promotion
decisions.

Evidence:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) already has
  structured access to `AvailabilityShadowSummary`.
- [src/cbb/ui/templates/models.html](../src/cbb/ui/templates/models.html)
  currently renders overview cards only; there is no dedicated availability
  diagnostics block.
- [src/cbb/db.py](../src/cbb/db.py) already provides the fields needed for a
  compact diagnostic panel: coverage, unmatched counts, timing, seasons,
  source labels, scope labels, and status counts.

Implemented shape:
Keep the dashboard overview card, but add one compact detail section on the
models page for availability diagnostics.

Implementation sketch:

- extend the middleware models-page payload with a structured availability
  diagnostic block
- render a compact section showing:
  - usage state
  - games covered
  - reports loaded
  - player rows loaded
  - unmatched rows
  - latest or average timing before tip
  - season / scope / source labels
  - status mix
- keep the dashboard landing page summary card, but link users to the models
  view for detail instead of duplicating a large new dashboard panel

Acceptance criteria:

- operators can review availability coverage quality from the UI without
  opening the markdown report
- the models page stays compact and server-rendered
- no per-player table, ingest UI, or workflow control surface is added

Suggested ownership:

- dashboard middleware and models-page template thread

### UX-AV-3 [`completed`] Add backward-compatible snapshot and JSON contract coverage for availability usage changes

Completed on `2026-03-23`.

Classification:
Approved by the parent task and implemented with snapshot/UI compatibility
tests plus backward-compatible state normalization.

Problem:
If availability fields expand ad hoc, the dashboard snapshot and JSON endpoints
can drift or break older saved payloads.

User impact:
A small additive modeling change could create avoidable dashboard regressions.

Evidence:

- [tests/test_dashboard_snapshot.py](../tests/test_dashboard_snapshot.py)
  already proves the repo values backward-compatible snapshot loading.
- [tests/test_dashboard_ui.py](../tests/test_dashboard_ui.py) already covers
  overview-card exposure, but it does not yet cover a future usage-state field
  or a richer models-page diagnostic section.

Implemented shape:
Extend compatibility tests before or alongside the additive contract change.

Implementation sketch:

- add snapshot tests for missing or older availability usage-state fields
- add dashboard/UI tests for the richer availability diagnostic payload
- keep JSON serialization explicit and additive

Acceptance criteria:

- older snapshots still load cleanly
- `/api/dashboard` and `/api/models` stay stable as availability fields grow
- the new copy and diagnostics are covered by targeted tests

Suggested ownership:

- dashboard snapshot and UI verification thread

### UX-AV-4 [`approved` -> `completed`] Surface per-game availability context on the live board

Problem:

- the upcoming page already explains the global availability usage state, but
  operators still cannot see which specific live-board rows have stored
  official coverage
- the model lane now exposes explicit per-game `availability_context` metadata
  on live-board and upcoming prediction rows, so the UI no longer needs to
  infer or synthesize that state from database reads

Approved implementation shape:

- keep the dashboard read-only and middleware-first
- extend the live-board row view model in
  [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) with one
  additive availability label and detail string derived only from the existing
  prediction contract field
- render that context in
  [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  inside the live-board table without adding a new page or operator control
- keep `/api/upcoming` additive and backward compatible by exposing the same
  row-level fields in the serialized page payload

Explicit non-goals:

- no extra database read path in the dashboard layer
- no attempt to quantify player importance or predicted availability impact
- no ingest, refresh, or operational controls in the UI

Outcome:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) now derives
  one additive availability label and detail string for each live-board row
  using only the model-owned `availability_context` payload
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  now renders that context inline on the live board without changing the
  page structure or adding operator controls
- `/api/upcoming` stays additive because the serialized live-board row now
  carries the same new fields
- targeted dashboard/UI tests, `ruff check`, and `mypy` all pass

### UX-AV-9 [`completed`] Surface upcoming-board availability coverage summary

Problem:

- the upcoming page now has a global availability usage-state callout plus
  row-level live-board labels, but operators still cannot tell at a glance how
  much of the current upcoming slate has prediction-owned availability coverage
  without scanning every row

Repo evidence:

- the model lane now exposes an additive prediction-level availability summary
  for the upcoming slate, but
  [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) and
  [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  still ignore it
- the current upcoming-page hero only shows the broad usage state and a link to
  diagnostics, so it cannot answer the narrower operator question
  "how many current rows have stored official coverage?"
- the page already renders row-level availability labels only when coverage
  exists, which makes the lack of one board-level summary more noticeable on
  mixed-coverage slates

Implementation shape:

- keep the dashboard middleware read-only and derive one additive upcoming-page
  summary directly from the prediction-owned availability summary
- extend the upcoming-page payload and template with one compact coverage
  summary that shows how many current upcoming rows have stored official
  reports plus the simple coverage-status breakdown
- keep `/api/upcoming` additive and backward compatible; do not add new ingest
  or model controls

Acceptance criteria:

- the upcoming page hero surfaces a compact availability coverage summary for
  the current upcoming slate
- the middleware derives that summary only from the prediction contract, not a
  new database read
- `/api/upcoming` exposes the same additive summary fields
- targeted dashboard/UI tests cover both covered and uncovered cases

Explicit non-goals:

- changing model behavior or prediction contract ownership
- adding operator controls for import, refresh, or audit
- building a new page or widening into a frontend rewrite

Outcome:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) now derives
  one compact upcoming-page availability summary directly from the model-owned
  prediction summary without adding a new database read
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  now renders that summary in the existing hero callout so operators can see
  current-slate coverage before scanning row-level details
- `/api/upcoming` stays additive because the serialized page payload now
  carries the same new summary block
- targeted dashboard/UI tests, `ruff check`, and `mypy` all pass

### UX-AV-10 [`completed`] Surface upcoming-board availability freshness summary

Problem:

- the upcoming page now summarizes how many current rows have stored official
  coverage, but it still hides the freshness portion of the model-owned
  availability summary, so operators cannot tell whether that coverage is
  recent without drilling into row-level details

Repo evidence:

- the model lane now exposes additive availability freshness fields on the
  prediction summary, but
  [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) and
  [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  do not surface them yet
- the current upcoming-page hero summary answers "how many rows are covered?"
  but not "how fresh is that coverage?"
- the row-level availability details already carry update timing, so the lack
  of one board-level freshness summary still forces unnecessary scanning on
  mixed or crowded slates

Implementation shape:

- keep the dashboard middleware read-only and derive one additive freshness
  note from the existing prediction-owned availability summary
- extend the upcoming-page payload and hero callout with the freshness portion
  of that summary without adding controls or a new page
- keep `/api/upcoming` additive and backward compatible

Acceptance criteria:

- the upcoming page hero surfaces the latest covered-report update time and
  closest report-to-tip timing when the prediction summary has them
- the middleware derives that note only from the prediction contract
- `/api/upcoming` exposes the same additive freshness fields
- targeted dashboard/UI tests cover both fresh and missing-freshness cases

Explicit non-goals:

- changing model behavior or prediction contract ownership
- adding operator controls for import, refresh, or audit
- widening into a frontend rewrite or a new page

Outcome:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) now derives
  one additive freshness note for the upcoming-page availability summary using
  only the model-owned prediction summary fields
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  now renders that freshness note in the existing hero callout when the
  prediction summary carries it
- `/api/upcoming` stays additive because the serialized page payload now
  carries the same freshness note
- targeted dashboard/UI tests, `ruff check`, and `mypy` all pass

### UX-AV-11 [`completed`] Surface upcoming-board availability matching quality

Problem:

- the upcoming page now summarizes coverage and freshness for the current slate,
  but it still hides whether the covered rows are cleanly matched or still
  carry unmatched availability records

Repo evidence:

- the model lane now exposes additive matching-quality counts on the
  prediction-level availability summary, but
  [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) and
  [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  do not surface them yet
- row-level live-board availability details already show unmatched counts when
  present, which makes the lack of one board-level summary more noticeable on
  mixed-quality slates
- the availability-cycle goal in this roadmap explicitly calls out matching
  quality, so the upcoming-page hero should reflect the same contract without
  forcing row-by-row inspection

Implementation shape:

- keep the dashboard middleware read-only and derive one additive matching-
  quality note from the existing prediction-owned availability summary
- extend the upcoming-page payload and hero callout with that note without
  adding controls or a new page
- keep `/api/upcoming` additive and backward compatible

Acceptance criteria:

- the upcoming page hero surfaces whether covered rows currently have unmatched
  availability records, plus the team-side versus opponent-side split when
  present
- the middleware derives that note only from the prediction contract
- `/api/upcoming` exposes the same additive matching-quality field
- targeted dashboard/UI tests cover both clean and partially unmatched cases

Explicit non-goals:

- changing model behavior or prediction contract ownership
- adding operator controls for import, refresh, or audit
- widening into a new page or frontend rewrite

Outcome:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) now derives
  one additive matching-quality note for the upcoming-page availability summary
  using only the model-owned prediction summary fields
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  now renders that matching-quality note in the existing hero callout when the
  prediction summary carries it
- `/api/upcoming` stays additive because the serialized page payload now
  carries the same matching-quality note
- targeted dashboard/UI tests, `ruff check`, and `mypy` all pass

### UX-AV-12 [`completed`] Surface upcoming-board availability status mix

Problem:

- the upcoming page now summarizes coverage, freshness, and matching quality
  for the current slate, but it still hides whether the covered rows actually
  include any stored `out` or `questionable` statuses without row-by-row
  inspection

Repo evidence:

- the model lane now exposes additive status-mix counts on the prediction-level
  availability summary, but
  [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) and
  [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  do not surface them yet
- row-level availability details already show `out` and `questionable` counts
  when present, which makes the lack of one board-level status summary more
  noticeable on covered slates
- the availability-cycle goal in this roadmap is to make matching quality and
  usage state legible from the UI; the same constraint applies to status mix
  once the model contract exposes it

Implementation shape:

- keep the dashboard middleware read-only and derive one additive status-mix
  note from the existing prediction-owned availability summary
- extend the upcoming-page payload and hero callout with that note without
  adding controls or a new page
- keep `/api/upcoming` additive and backward compatible

Acceptance criteria:

- the upcoming page hero surfaces how many covered rows currently have any
  stored `out` status or any stored `questionable` status
- the middleware derives that note only from the prediction contract
- `/api/upcoming` exposes the same additive status-mix field
- targeted dashboard/UI tests cover both empty-status and status-bearing cases

Explicit non-goals:

- changing model behavior or prediction contract ownership
- adding operator controls for import, refresh, or audit
- widening into a new page or frontend rewrite

Outcome:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) now derives
  one additive status-mix note for the upcoming-page availability summary using
  only the model-owned prediction summary fields
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  now renders that status-mix note in the existing hero callout when the
  prediction summary carries it
- `/api/upcoming` stays additive because the serialized page payload now
  carries the same status-mix note
- targeted dashboard/UI tests, `ruff check`, and `mypy` all pass

### UX-AV-13 [`completed`] Surface upcoming-board availability sources

Problem:

- the upcoming page now summarizes coverage, freshness, matching quality, and
  status mix, but it still hides which stored availability sources are
  contributing to the covered slate without row-by-row inspection

Repo evidence:

- the model lane now exposes additive source labels on the prediction-level
  availability summary, but
  [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) and
  [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  do not surface them yet
- the availability lane can now mix NCAA and wrapped archive-source coverage,
  so one board-level source summary is more honest than implying one source
  from scattered row labels
- the availability-cycle goal is to keep the dashboard contract legible without
  forcing row-by-row interpretation when the model contract already has the
  summary

Implementation shape:

- keep the dashboard middleware read-only and derive one additive source note
  from the existing prediction-owned availability summary
- extend the upcoming-page payload and hero callout with that note without
  adding controls or a new page
- keep `/api/upcoming` additive and backward compatible

Acceptance criteria:

- the upcoming page hero surfaces the distinct source labels contributing to
  the covered upcoming slate
- the middleware derives that note only from the prediction contract
- `/api/upcoming` exposes the same additive source-summary field
- targeted dashboard/UI tests cover both named-source and no-source cases

Explicit non-goals:

- changing model behavior or prediction contract ownership
- inferring source quality from source labels alone
- widening into a new page or frontend rewrite

Outcome:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py) now derives
  one additive source note for the upcoming-page availability summary using
  only the model-owned prediction summary fields
- [src/cbb/ui/templates/upcoming.html](../src/cbb/ui/templates/upcoming.html)
  now renders that source note in the existing hero callout when the
  prediction summary carries it
- `/api/upcoming` stays additive because the serialized page payload now
  carries the same source note
- targeted dashboard/UI tests, `ruff check`, and `mypy` all pass

### UX-AV-5 [`deferred`] Add dashboard controls for availability import or audit

Reason:
The supported import workflow remains CLI-first through
`cbb ingest availability PATH...`. Adding operator controls to the dashboard
would widen scope and blur the boundary between read-only UI and operational
ingest workflows.

### UX-AV-6 [`deferred`] Run middleware, refresh, or ingest as always-on Kubernetes services

Reason:
This is a later runtime-topology phase, not a UI clarity phase. The current
need is contract honesty, not continuous service rollout.

### UX-AV-7 [`rejected`] Major frontend rewrite or separate SPA for the availability cycle

Reason:
The problem is not the rendering stack. The current server-rendered UI is
already capable of showing the needed information once the middleware contract
is clearer.

### UX-AV-8 [`rejected`] Move ingest, training, or model-refresh actions into the dashboard

Reason:
That would make the frontend boundary worse and would conflict with the repo's
CLI-first operating model.

## Availability Cycle Status

The approved availability-cycle items are now complete:

1. `UX-AV-1` explicit usage-state contract
2. `UX-AV-2` compact models-page diagnostic section
3. `UX-AV-3` backward-compatible snapshot and JSON coverage
4. `UX-AV-4` per-game live-board availability context
5. `UX-AV-9` upcoming-board coverage summary
6. `UX-AV-10` upcoming-board freshness summary
7. `UX-AV-11` upcoming-board matching-quality summary
8. `UX-AV-12` upcoming-board status-mix summary
9. `UX-AV-13` upcoming-board source summary

Constraint:
Do not widen this UI lane further unless a model-roadmap change explicitly
expands the prediction or report contract.

## Key Risks

- Hard-coded shadow-only language will become misleading the moment
  availability enters any research or live model path.
- Tournament-only coverage is still sparse and can be over-read if the UI does
  not keep the usage state and coverage state separate.
- Snapshot and JSON drift are the main regression risk, not rendering
  complexity.
- Per-game availability display should not be invented before the prediction
  contract exposes it explicitly.

## Research Log

- date: `2026-03-12`
- area reviewed: dashboard middleware, snapshot contract, availability read
  model, report copy, models/upcoming templates, and related tests
- findings:
  - the architectural frontend/backend split is already complete for this repo
  - availability shadow data is present in the report and snapshot layers, but
    the UI still compresses it too aggressively
  - the next risk is honesty and compatibility, not missing frontend
    infrastructure
- proposed next step: add a small explicit availability usage-state contract
  and one compact models-page diagnostic section while deferring larger UI and
  runtime changes
- status: completed
