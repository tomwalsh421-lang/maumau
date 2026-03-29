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

That migration rule is now satisfied. As of `UX-REACT-10`, the supported
frontend route surface is React-only, and the remaining Python UI role is the
small HTML shell plus the JSON/middleware boundary behind it.

The later `2026-03-28` hosting request also explicitly approved one bounded
topology slice beyond the earlier `no Kubernetes always-on middleware service
or background worker rollout` rule:

- keep the public frontend pod always up in cluster
- run the dashboard middleware in a separate pod behind that frontend
- let the scheduled runtime job persist the normalized upcoming-bets cache
- let the UI read that stored cache instead of recomputing live picks per
  request

That hosting override still must stay:

- additive and mergeable
- honest about the cache-backed route surface the UI is actually serving
- grounded in the existing dashboard and prediction contracts
- free of dashboard-owned ingest or training controls

## Working Agreement

- `ux_researcher` maintains this document.
- `implementer` only executes items explicitly approved by the parent task or
  clearly marked approved here.
- The completed middleware split remains the architectural baseline.
- This cycle is now about React-only route polish plus additive hosting slices
  that preserve the existing middleware and JSON boundaries.

## Current Audit

Files reviewed for this refresh:

- [src/cbb/dashboard/service.py](../src/cbb/dashboard/service.py)
- [src/cbb/dashboard/snapshot.py](../src/cbb/dashboard/snapshot.py)
- [src/cbb/ui/app.py](../src/cbb/ui/app.py)
- [src/cbb/ui/templates/react_app.html](../src/cbb/ui/templates/react_app.html)
- [frontend/src/App.tsx](../frontend/src/App.tsx)
- [frontend/src/app.css](../frontend/src/app.css)
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
- The supported browser routes are now React-only. The old `/classic/*`
  fallbacks and `/app/*` beta aliases have been removed, which makes the route
  surface easier to reason about and removes stale migration copy from the UI.
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

### UX-REACT-3 [`completed`] Cut over `/upcoming` to the React client while preserving a classic fallback

Classification:
Approved by the parent task and safe as the next bounded migration slice. It
reuses the existing upcoming-page JSON contract and keeps the server-rendered
recommendations view available at a legacy route instead of deleting it.

Problem:

- the React recommendations client exists only under `/app/upcoming`, while the
  live operator-facing `/upcoming` route still points to the old Jinja page
- that leaves the migration stuck in beta-only mode and prevents the frontend
  layer from actually replacing a primary page

Repo evidence:

- `src/cbb/ui/app.py` still routes `/upcoming` to `upcoming.html`
- `frontend/src/App.tsx` already has a working recommendations view, but it
  only recognizes `/app/upcoming` as that route
- the classic templates and tests already give the repo a safe legacy fallback
  path if the React cutover stays additive

Implementation shape:

- switch `/upcoming` to render the React shell as the primary recommendations
  route
- preserve the server-rendered recommendations page at one explicit legacy
  route such as `/classic/upcoming`
- update the React shell and docs so operators can still reach the classic
  fallback during the migration

Acceptance criteria:

- `/upcoming` serves the React recommendations shell and still reads
  `/api/upcoming`
- the server-rendered recommendations page remains available at a documented
  legacy path
- no-JavaScript and operator fallback copy points to the classic route rather
  than leaving the page stranded
- targeted dashboard UI tests cover the primary cutover plus the fallback route

Explicit non-goals:

- migrating the overview, performance, models, or picks routes in the same pass
- changing `/api/upcoming` semantics for the sake of the route cutover
- deleting the classic recommendations template entirely

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/upcoming` now serves the React recommendations shell as the primary route,
  while `/classic/upcoming` preserves the old server-rendered page as the
  documented fallback during the migration

### UX-REACT-4 [`completed`] Cut over `/` to the React overview while preserving a classic fallback

Classification:
Approved by the parent task and safe as the next bounded migration slice. It
reuses the existing dashboard JSON contract and keeps the old server-rendered
overview reachable at a legacy path instead of deleting it.

Problem:

- the React overview exists only under `/app`, while the primary dashboard root
  at `/` still serves the old Jinja page
- that leaves the app split between a React recommendations primary route and a
  server-rendered overview primary route

Repo evidence:

- `src/cbb/ui/app.py` still routes `/` to `dashboard.html`
- `frontend/src/App.tsx` already has a working overview client backed by
  `/api/dashboard`, but it still frames overview as beta-only
- the dashboard route tests already cover both the root overview and the React
  alias, so they can pin a safe primary cutover plus fallback path

Implementation shape:

- switch `/` to render the React overview shell as the primary dashboard route
- preserve the server-rendered overview at one explicit legacy path such as
  `/classic`
- update the React shell copy and docs so operators can tell the difference
  between the primary route, the beta alias, and the classic fallback

Acceptance criteria:

- `/` serves the React overview shell and still reads `/api/dashboard`
- the classic overview remains available at a documented legacy path
- the React overview copy and fallback links are route-aware instead of calling
  the primary route a beta view
- targeted dashboard UI tests cover the root cutover plus the classic fallback

Explicit non-goals:

- migrating performance, models, or picks in the same pass
- changing `/api/dashboard` semantics for the sake of the route cutover
- deleting the classic dashboard template entirely

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/` now serves the React overview shell as the primary dashboard route, while
  `/classic` preserves the old server-rendered dashboard and `/app` remains as
  the React overview alias during the migration

### UX-REACT-5 [`completed`] Cut over `/performance` to React while preserving a classic fallback

Classification:
Approved by the parent task and safe as the next bounded migration slice. It
reuses the existing performance-page JSON contract and keeps the old
server-rendered performance page reachable at a legacy path instead of
deleting it.

Problem:

- the performance route is still server-rendered even though the primary
  overview and recommendations routes now run through the React client
- that leaves one of the core operator inspection routes outside the migration,
  even though the performance API already carries the needed data

Repo evidence:

- `src/cbb/ui/app.py` still routes `/performance` to `performance.html`
- `src/cbb/dashboard/service.py` already exposes a structured
  `PerformancePage` payload through `/api/performance`
- `frontend/src/App.tsx` currently handles only overview and recommendations,
  so the route and shell still need one bounded performance view

Implementation shape:

- switch `/performance` to render a React shell backed by `/api/performance`
- preserve the server-rendered performance page at one explicit legacy route
  such as `/classic/performance`
- add one React performance view that renders the key window, summary, chart,
  season-card, and settled-row sections from the existing payload

Acceptance criteria:

- `/performance` serves the React shell and still reads `/api/performance`
- the classic performance page remains available at a documented legacy path
- the React shell exposes route-aware navigation and fallback links for the
  performance route
- targeted dashboard UI tests cover the primary performance cutover plus the
  fallback path

Explicit non-goals:

- migrating models or picks in the same pass
- changing `/api/performance` semantics for the sake of the route cutover
- deleting the classic performance template entirely

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/performance` now serves the React shell as the primary route, while
  `/classic/performance` preserves the old server-rendered page and
  `/app/performance` remains as the React alias during the migration

### UX-REACT-6 [`completed`] Cut over `/picks` to React while preserving a classic fallback

Classification:
Approved by the parent task and safe as the next bounded migration slice. It
reuses the existing picks-page JSON contract and keeps the old server-rendered
history page reachable at a legacy path instead of deleting it.

Problem:

- the primary bet-history route still lives in the old server-rendered layer
  even though the rest of the main operator flow has moved to React
- that leaves the filterable historical review path outside the migration, even
  though the picks API already exposes a structured page payload

Repo evidence:

- `src/cbb/ui/app.py` still routes `/picks` to `picks.html`
- `src/cbb/dashboard/service.py` already exposes `PicksPage` through
  `/api/picks`, including normalized filters, season options, sportsbook
  options, and matched rows
- `frontend/src/App.tsx` currently has no picks route or filter-submit flow,
  so the client still cannot own the historical review path

Implementation shape:

- switch `/picks` to render a React shell backed by `/api/picks`
- preserve the server-rendered picks page at one explicit legacy path such as
  `/classic/picks`
- add one React picks view that can submit the existing filter shape and render
  the matched historical rows from the existing payload

Acceptance criteria:

- `/picks` serves the React shell and still reads `/api/picks`
- the classic picks page remains available at a documented legacy path
- the React picks view can apply the existing filter shape without changing the
  backend API semantics
- targeted dashboard UI tests cover the primary picks cutover plus the fallback
  path

Explicit non-goals:

- migrating the models page in the same pass
- changing `/api/picks` semantics for the sake of the route cutover
- deleting the classic picks template entirely

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/picks` now serves the React shell as the primary route, while
  `/classic/picks` preserves the old server-rendered history page and
  `/app/picks` remains as the React alias during the migration

### UX-REACT-7 [`completed`] Cut over `/models` to React while preserving a classic fallback

Classification:
Approved by the parent task and safe as the next bounded migration slice. It
reuses the existing models-page JSON contract and keeps the server-rendered
review page available at a legacy route instead of deleting it.

Problem:

- `/models` still routes through the old server-rendered template even though
  the rest of the main review loop now reaches React-backed overview,
  performance, picks, and recommendations surfaces
- that leaves the promoted-path review, artifact inventory, and availability
  diagnostics outside the migration, even though the middleware already serves
  those sections through `/api/models`

Repo evidence:

- `src/cbb/ui/app.py` still routes `/models` directly to `models.html`
- `src/cbb/dashboard/service.py` already exposes `ModelsPage` through
  `/api/models`, including overview cards, artifact inventory, per-season
  stability, availability diagnostics, and glossary content
- `frontend/src/App.tsx` currently has no models route or models-page render
  path, so the React client still cannot own the best-path review surface

Implementation shape:

- switch `/models` to render a React shell backed by `/api/models`
- preserve the server-rendered models page at one explicit legacy route such
  as `/classic/models`
- add one React models view that renders the existing promoted-path, artifact,
  season, diagnostics, and glossary sections from the current payload

Acceptance criteria:

- `/models` serves the React shell and still reads `/api/models`
- the classic models page remains available at a documented legacy path
- the React models view renders the existing review sections without changing
  the backend API semantics
- targeted dashboard UI tests cover the primary models cutover plus the
  fallback path

Explicit non-goals:

- migrating teams or introducing search-driven React routes in the same pass
- changing `/api/models` semantics for the sake of the route cutover
- deleting the classic models template entirely

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/models` now serves the React shell as the primary route, while
  `/classic/models` preserves the old server-rendered review page and
  `/app/models` remains as the React alias during the migration

### UX-REACT-8 [`completed`] Cut over `/teams` to React while preserving a classic fallback

Classification:
Approved by the parent task and safe as the next bounded migration slice. It
reuses the existing teams-page JSON contract and keeps the server-rendered team
search page available at a legacy route instead of deleting it.

Problem:

- the team-search landing page still routes through the old server-rendered
  template even though the main review surfaces now run through React
- that keeps team discovery outside the migration, even though the middleware
  already exposes a typed `/api/teams` payload for query-driven results and
  featured teams

Repo evidence:

- `src/cbb/ui/app.py` still routes `/teams` directly to `teams.html`
- `src/cbb/dashboard/service.py` already exposes `TeamsPage` through
  `/api/teams`, including the current query, matched results, and featured
  teams from the live board
- `frontend/src/App.tsx` currently has no teams route or query-submit flow, so
  the React client still cannot own the team-search landing surface

Implementation shape:

- switch `/teams` to render a React shell backed by `/api/teams`
- preserve the server-rendered teams landing page at one explicit legacy route
  such as `/classic/teams`
- add one React teams view that can submit the existing `q` query and render
  matched results plus featured teams from the current payload

Acceptance criteria:

- `/teams` serves the React shell and still reads `/api/teams`
- the classic teams landing page remains available at a documented legacy path
- the React teams view can submit the existing `q` query without changing the
  backend API semantics
- targeted dashboard UI tests cover the primary teams cutover plus the
  fallback path

Explicit non-goals:

- migrating `/teams/<team_key>` detail pages in the same pass
- reintroducing the classic progressive-search JavaScript behavior in the same
  slice
- changing `/api/teams` or `/api/teams/search` semantics for the route cutover

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/teams` now serves the React shell as the primary route, while
  `/classic/teams` preserves the old server-rendered search landing page,
  `/app/teams` remains as the React alias, and `/teams/<team_key>` detail
  pages stay server-rendered for now

### UX-REACT-9 [`approved` -> `completed`] Migrate `/teams/<team_key>` into React and retire the classic team templates

Classification:
Approved by the parent task and safe as the next bounded migration slice. This
is UI-only because it reuses the existing typed `/api/teams/<team_key>`
contract and does not change model, report, or snapshot semantics.

Problem:

- the team explorer still ejects users out of the React flow into the old
  server-rendered detail template
- that leaves one meaningful Python-rendered product surface in place, which
  works against the current goal of finishing the frontend cleanup and making
  the experience feel like one consistent betting workspace

Repo evidence:

- `src/cbb/ui/app.py` still renders `team_detail.html` for `/teams/<team_key>`
- `src/cbb/ui/app.py` already exposes `/api/teams/<team_key>`, so the detail
  payload exists at the middleware boundary today
- `frontend/src/App.tsx` still labels the team links as opening the classic
  detail page, which is the clearest remaining React-migration seam in the UI

Implementation shape:

- teach the React client to handle one team-detail route backed by the existing
  `/api/teams/<team_key>` payload
- route `/teams/<team_key>` through the React shell instead of the Jinja
  template
- retire the classic teams landing/detail templates and routes in the same pass
  once the React team flow covers both search and detail

Acceptance criteria:

- `/teams/<team_key>` serves the React shell and renders the existing team
  detail payload
- the React team explorer links stay inside the React flow for both search and
  detail
- the classic teams landing/detail routes and templates are removed if they are
  no longer needed after the React cutover
- targeted dashboard UI tests cover the React team detail route and the retired
  classic path

Explicit non-goals:

- changing `/api/teams/<team_key>` semantics for the sake of the route cutover
- broad dashboard copy polish outside the team flow in the same pass
- moving team analytics or model logic into the frontend

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/teams/<team_key>` now serves the React shell against the existing
  `/api/teams/<team_key>` payload, and `/app/teams/<team_key>` remains as the
  beta alias
- the old team-search and team-detail Jinja templates plus the `/classic/teams`
  route were removed once the React team flow covered both search and detail

### UX-REACT-10 [`approved` -> `completed`] Retire the remaining classic and beta React aliases

Classification:
Approved by the parent task and safe as the next bounded frontend-cleanup
slice. This is UI-only because it removes transition-era routes and copy while
continuing to use the existing dashboard, picks, models, performance, and
upcoming JSON contracts unchanged.

Problem:

- the product now serves every meaningful page from React, but the route layer
  still advertises `/classic/*` fallbacks and `/app/*` beta aliases from the
  migration phase
- that keeps the frontend feeling temporary and template-driven even though the
  React client is already the supported primary experience

Repo evidence:

- `src/cbb/ui/app.py` still dispatches `/classic`, `/classic/models`,
  `/classic/performance`, `/classic/upcoming`, `/classic/picks`, and `/app/*`
  routes even though the primary `/`, `/models`, `/performance`, `/upcoming`,
  `/picks`, and `/teams` routes already render the React shell
- `frontend/src/App.tsx` still labels the interface as a migration surface and
  still renders classic-fallback links for the pages that already have React
  parity
- `src/cbb/ui/templates/` still carries legacy Jinja page templates for
  overview, models, performance, picks, and upcoming that no longer define the
  supported user workflow

Implementation shape:

- remove the remaining `/classic/*` and `/app/*` routes once the primary React
  routes cover those surfaces
- delete the obsolete legacy Jinja page templates that only backed those
  fallback routes
- simplify the React shell copy and navigation so it no longer talks about
  beta routes or server-rendered fallbacks

Acceptance criteria:

- the supported browser routes are the primary React routes plus the existing
  JSON/API routes, with no `/classic/*` or `/app/*` frontend aliases left
- the obsolete classic Jinja page templates for overview, models,
  performance, picks, and upcoming are removed
- the React shell no longer advertises migration-era fallback links or "React
  Beta" framing on the supported routes
- targeted dashboard UI tests cover the retired aliases and the cleaned-up
  shell

Explicit non-goals:

- changing dashboard, report, snapshot, or prediction JSON semantics
- redesigning every visual section of the React client in the same pass
- removing the Python middleware or the small HTML shell that mounts the React
  bundle

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- the remaining `/classic/*` and `/app/*` aliases are gone, the obsolete Jinja
  page templates were deleted, and the React shell copy now speaks as the
  canonical frontend rather than as a migration surface

### UX-REACT-11 [`approved` -> `completed`] Refocus `/` into a day-first betting workspace

Classification:
Approved by the parent task and safe as the next bounded UX-only slice. This
pass stays inside the existing dashboard JSON contract and does not require a
model-roadmap dependency first.

Problem:

- the route cleanup removed migration clutter, but the landing page still reads
  like a generic dashboard: metrics first, operator notes second, and the
  current slate only after several abstract summary blocks
- that works against the actual daily workflow, which starts with today's card,
  cached recommendations, freshness, and the next set of games to decide on

Repo evidence:

- `frontend/src/App.tsx` still renders the overview route as status cards,
  metric cards, season bars, and then one three-panel board section
- `src/cbb/dashboard/service.py` already supplies the data needed for a
  bettor-first landing route: cached picks, board rows, recent settled rows,
  recent-window summary, and overview cards
- no backend contract change is needed to lead with the current card and push
  broader report context lower on the page

Implementation shape:

- restructure the React overview route so the first screen answers:
  what is on today's card, how fresh is it, and what else is on the board
- promote cached picks and current-board rows above generic metric grids
- keep the historical and model-trust context available, but demote it below
  the current decision-making surface

Acceptance criteria:

- `/` opens with a day-board layout centered on current recommendations,
  freshness, and near-term board context
- the recent performance summary and wider report metrics remain available, but
  no longer dominate the first read of the route
- the pass stays UI-only and keeps the existing `/api/dashboard` payload
  unchanged
- targeted dashboard UI tests and the frontend build cover the new structure

Explicit non-goals:

- changing the dashboard middleware payload or prediction semantics
- redesigning every route in the same pass
- inventing new model metrics, confidence language, or bankroll advice

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/` now leads with the current card, cache freshness, and near-term board
  context before broader report posture, while keeping the same
  `/api/dashboard` payload and moving the trust-check metrics lower on the
  route

### UX-REACT-12 [`approved` -> `completed`] Rebuild `/upcoming` as a slate-first betting workspace

Classification:
Approved by the parent task and safe as the next bounded UX-only slice. This
pass stays inside the existing `/api/upcoming` payload and does not require a
model-roadmap dependency first.

Problem:

- the supported recommendations route is React-only now, but it still reads
  like a status dashboard: generic top cards, equal-weight panels, and the
  current decision flow split between qualified picks, watch rows, and board
  context
- that works against the actual operator workflow, which starts with one
  question: what is actionable on today's slate, what is close behind it, and
  what else still deserves a quick scan before placing anything

Repo evidence:

- `frontend/src/App.tsx` currently renders `/upcoming` as four status cards,
  then one recommendations panel, one watchlist panel, and one broad live-board
  context panel
- `src/cbb/dashboard/service.py` already exposes `recommendation_rows`,
  `watch_rows`, and `board_rows` inside the existing `UpcomingPage` payload,
  but the React route does not currently use `board_rows`
- no middleware change is required to promote the active slate, freshness, and
  next-best opportunities above the broader in-progress/final board context

Implementation shape:

- restructure `/upcoming` around a bettor-first slate summary using the
  existing cache freshness, recommendation, watch, and board-row payloads
- surface the open board queue from `board_rows` as a first-class route section
  instead of sending the user straight from picks to broad live-board context
- keep the older live/in-progress/final board state available, but demote it
  below the main slate decision surface

Acceptance criteria:

- `/upcoming` opens with a slate-first summary that makes the current action
  order obvious: qualified bets, close-watch rows, then the rest of the active
  board
- the React route uses the existing `UpcomingPage` payload unchanged
- the broader live-board state remains available, but no longer dominates the
  route before the current decision surface
- targeted dashboard UI verification plus the frontend build cover the new
  structure

Explicit non-goals:

- changing prediction semantics or recommendation ranking
- widening the `/api/upcoming` middleware contract in the same pass
- redesigning unrelated routes while this one slate-focused surface is moving

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/upcoming` now leads with slate freshness, the current qualified card, the
  close-watch queue, and the remaining active non-pass board rows before it
  drops into broader in-progress/final board context
- the pass stayed UI-only by using the existing `recommendation_rows`,
  `watch_rows`, `board_rows`, and availability fields already present in the
  `/api/upcoming` payload

### UX-REACT-13 [`approved` -> `completed`] Refocus `/performance` into a pre-bet trust brief

Classification:
Approved by the parent task and safe as the next bounded UX-only slice. This
pass stays inside the existing `/api/performance` payload and does not require
model-roadmap work first.

Problem:

- the React performance route still reads like an analytics page: summary cards
  first, then charts, then season cards, then detail rows
- that is useful for post-hoc review, but a bettor deciding on today's card
  needs the performance page to answer one faster question: should the current
  slate be trusted right now, and which seasons/windows are doing the work

Repo evidence:

- `frontend/src/App.tsx` currently renders `/performance` as a generic status
  grid followed by charts, with no clear first-screen handoff back to the
  active slate or the settled history
- the existing `PerformancePage` payload already has the pieces needed for a
  bettor-first trust brief: selected-window summary, stake range, close
  quality, risk posture, season cards, and chart data
- no middleware contract change is needed to promote the trust decision and
  season posture above the heavier chart reading

Implementation shape:

- restructure `/performance` so the first screen behaves like a trust brief for
  the selected window rather than a generic analytics dashboard
- promote the selected-window headline, stake/risk/close-quality summary, and
  season posture above the charts
- keep the charts and settled rows intact, but demote them below the initial
  trust read

Acceptance criteria:

- `/performance` opens with a trust-brief layout centered on current form,
  close quality, risk posture, and quick actions back to the slate/history
- season posture is visible before the heavier charts
- the route uses the existing `/api/performance` payload unchanged
- targeted dashboard UI verification plus the frontend build cover the new
  structure

Explicit non-goals:

- changing report math, performance windows, or model semantics
- widening the `/api/performance` payload in the same pass
- redesigning unrelated routes while this trust-focused surface is moving

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `/performance` now opens with a trust brief that promotes current-window
  profit, ROI, close quality, bankroll exposure, season posture, and direct
  links back to the active slate or settled history before the charts and rows
- the pass stayed UI-only by using the existing `PerformancePage` payload
  unchanged and simply reordering the React presentation around
  `summary`, `season_cards`, `season_comparison_chart`, `full_history_chart`,
  and `rows`

### UX-REACT-14 [`approved` -> `completed`] Move shared frontend chrome out of the Python shell

Classification:
Approved by the parent task and safe as the next bounded React-only cleanup
slice. This pass does not change dashboard JSON contracts or model behavior.

Problem:

- the primary routes are React-only, but the user still sees a Python-rendered
  header, nav, and footer from `base.html` before the React app takes over
- that leftover shell keeps the frontend feeling template-driven even though
  the supported route surface already lives in React
- the old `src/cbb/ui/static/dashboard.js` enhancement bundle is now dead code
  because none of its classic hooks remain in the supported route surface

Repo evidence:

- `src/cbb/ui/templates/react_app.html` still extends `base.html`, which
  renders the shared site header/footer and loads `/static/dashboard.js`
- `src/cbb/ui/app.py` still builds `PRIMARY_NAV_ITEMS` and
  `SECONDARY_NAV_ITEMS` for that template layer even though the supported route
  navigation now lives in `frontend/src/App.tsx`
- no remaining supported template or React surface references
  `data-team-search`, `data-refresh-dashboard`, or `data-interactive-chart`,
  which means `src/cbb/ui/static/dashboard.js` no longer owns active behavior

Implementation shape:

- make the React route template a minimal document shell that mounts the React
  root directly instead of inheriting the Python-rendered site chrome
- keep `base.html` only for the small error path
- remove the dead dashboard enhancement script and any Python-side route-chrome
  plumbing it no longer needs

Acceptance criteria:

- the supported React routes no longer render the Python header/footer chrome
  before the React app
- the dead `dashboard.js` bundle is removed from the supported path
- targeted dashboard UI verification plus the frontend build still pass

Explicit non-goals:

- changing dashboard JSON contracts
- redesigning every route in the same pass
- changing the Python middleware/API boundary

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- `react_app.html` now serves as a minimal document shell for the supported
  React routes instead of inheriting the old Python-rendered header/footer
  chrome from `base.html`
- the React app now owns the visible brand and workflow framing, and the dead
  `src/cbb/ui/static/dashboard.js` bundle was removed because no supported
  route still exposes its old enhancement hooks
- the pass stayed UI-only by preserving the existing `/api/*` middleware
  contracts and keeping `base.html` only for the small error path

### UX-REACT-15 [`approved` -> `completed`] Group the live slate into explicit day buckets

Classification:
Approved by the parent task and safe as the next bounded UX slice. This pass
widens the dashboard JSON contract additively, but keeps the date-bucket logic
in the middleware instead of recreating it ad hoc in React.

Problem:

- the overview and upcoming routes now lead with the right bettor-first
  sections, but the current card still reads like one long undifferentiated
  list of rows
- that makes it harder to answer the day-specific question the product is
  supposed to support: what is worth considering today, what can wait until
  tomorrow, and which later rows should only stay in peripheral view

Repo evidence:

- `frontend/src/App.tsx` currently renders cached picks, watch rows, and board
  rows as flat lists even though every row already carries a rendered
  `commence_label`
- `src/cbb/dashboard/service.py` already owns timezone-aware timestamp
  formatting for those rows, so it is the correct boundary for one additive
  day-bucket label instead of pushing relative-date logic into the frontend
- the existing page payloads already distinguish the board surfaces that matter
  most to betting decisions; they just do not currently organize those surfaces
  around the actual day they belong to

Implementation shape:

- add one additive `commence_bucket_label` field to the shared pick-row
  contract using middleware-owned local-time day bucketing
- keep the new label backward compatible for cached payloads by tolerating
  missing bucket values
- regroup the React overview and upcoming card surfaces around those day
  buckets so the current slate reads like a day board instead of a template
  list

Acceptance criteria:

- the shared pick-row contract exposes one additive local-time day bucket label
- `/` and `/upcoming` visually group current-card rows by that bucket instead
  of rendering one flat list
- older cached payloads still deserialize safely when the new field is absent
- targeted dashboard/UI verification plus the frontend build cover the new
  grouping behavior

Explicit non-goals:

- changing recommendation ranking or board semantics
- widening into a full route redesign for every page in the same pass
- moving relative-date logic into React-only utilities without middleware
  support

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- the shared pick-row contract now carries one additive
  `commence_bucket_label`, older cached payloads still deserialize when that
  field is missing, and the React overview/upcoming/current-card surfaces now
  group rows into explicit local-time day sections instead of one flat list

### UX-REACT-16 [`approved` -> `completed`] Add one persistent day focus across the React board

Classification:
Approved by the parent task and safe as the next bounded UX slice. This stays
UI-only because it reuses the existing `commence_bucket_label` contract without
changing middleware, snapshot, or model behavior.

Problem:

- the React overview and slate routes now group rows by day, but the operator
  still has to visually scan every bucket on every visit instead of telling the
  workspace which date they actually want to bet
- that keeps the product closer to a dashboard report than a daily betting
  workspace, especially when the near-term window spans multiple slate days

Repo evidence:

- `frontend/src/App.tsx` already renders exact day buckets on the overview and
  upcoming routes, but it does not expose any persistent selector for one
  target day
- the hero counts and action links still summarize the full near-term board,
  which is less useful when the user only cares about one specific date
- the middleware already exposes stable local-time bucket labels through
  `commence_bucket_label`, so React can build a focused day control without
  widening the backend contract

Implementation shape:

- add one frontend-owned day selector that derives its options from the
  existing bucket labels on the overview and upcoming routes
- keep the selected day in the browser query string so the same focus survives
  between the two main board surfaces
- recast the route counts, headings, and board sections around the active day
  instead of the whole near-term window

Acceptance criteria:

- `/` and `/upcoming` expose one obvious active-day selector driven by the
  existing bucket labels
- the overview and slate route counts, headings, and action links reflect the
  selected day rather than the entire near-term window
- moving between overview and slate preserves the focused day
- targeted UI verification plus the frontend build cover the new day-focus
  workflow

Explicit non-goals:

- changing recommendation ranking or board semantics
- widening into a new middleware query contract
- redesigning unrelated routes in the same pass

Implementation note:

- completed in the dedicated `2026-03-28` UX worktree cycle
- the overview and upcoming routes now expose one obvious day-focus selector
  driven entirely by the existing `commence_bucket_label` values
- the React client persists that focus in the browser query string, so the same
  selected slate day survives between `/` and `/upcoming`
- the route counts, headings, and primary board sections now collapse around
  the active day instead of always summarizing the full near-term window

## Cache-Backed UI Hosting Epic

### UX-HOST-1 [`completed`] Serve the cluster UI through a separate cache-backed middleware pod

Classification:
Approved by the parent task and safe to implement now. This is not UI-only
because it touches chart wiring, CLI flags, dashboard storage, and middleware
hosting, but it stays out of model-quality changes and reuses the existing
prediction/page contracts. No model-roadmap item is required first.

Problem:

- the React migration moved the browser routes onto the middleware JSON
  boundary, but the supported cluster topology still assumes the dashboard
  runs only as a local CLI process
- the live UI path still recalculates the upcoming board on request, which is a
  poor fit for an always-on middleware pod when the repo already has a
  scheduled runtime job path

Repo evidence:

- `src/cbb/ui/app.py` and `src/cbb/dashboard/service.py` already separate UI
  presentation from dashboard orchestration, which makes a dedicated
  middleware pod feasible without moving modeling or DB code into the frontend
- `chart/cbb-upsets/templates/` had a public NGINX pod plus runtime workloads,
  but no dedicated dashboard middleware Deployment or Service
- `src/cbb/agent.py` already runs the scheduled refresh-and-scan flow, but it
  did not persist a normalized UI-facing upcoming snapshot for a separate
  always-on middleware process to serve

Implementation shape:

- keep NGINX as the stable always-on frontend pod and proxy browser traffic to
  one separate Python middleware Deployment when enabled
- let the scheduled runtime job persist one normalized upcoming-board cache in
  Postgres
- teach the middleware to serve `/api/upcoming` and the React shell from that
  stored cache via one explicit `--prediction-source cache` mode

Acceptance criteria:

- the chart can render an optional middleware Deployment and Service without
  changing the default release contents
- the NGINX frontend can proxy all traffic to that middleware when the new
  hosting mode is enabled
- `cbb agent --run-once` can persist the normalized upcoming snapshot into
  Postgres through one explicit opt-in flag
- `cbb dashboard --prediction-source cache` can read that stored snapshot and
  keep the existing page and JSON surfaces working even when no live inference
  runs inside the request path

Explicit non-goals:

- replacing NGINX with a separate static-asset image in the same pass
- moving ingest, training, or model-refresh controls into the UI
- rewriting the React client again to fit the hosting change

Implementation note:

- completed in the current `2026-03-28` hosting worktree cycle
- the chart now supports an optional middleware Deployment and Service behind
  the existing NGINX frontend pod
- the runtime CronJob path now opts into `--cache-predictions`, and the
  dashboard middleware can serve the stored upcoming-board cache through
  `--prediction-source cache`
- the overview and picks routes now also surface the latest cached
  recommendations so the always-on frontend shows current job-backed picks
  without replacing the older snapshot-backed historical sections

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
