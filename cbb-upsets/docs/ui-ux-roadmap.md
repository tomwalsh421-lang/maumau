# UI/UX Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [Model Documentation](model.md)
- [System Architecture](architecture.md)
- [Current Best-Model Report](results/best-model-3y-backtest.md)

Updated: `2026-03-12`

## Goal

Prepare the code base so the frontend is no longer tightly coupled to CLI,
modeling, and storage implementation details.

Immediate target for this run:

- introduce a middleware boundary that the frontend connects to
- keep the dashboard presentation layer thin
- preserve current local behavior and CLI entry points
- stop short of Kubernetes-resident always-on services and background refresh
  workers

## Working Agreement

- `ux_researcher` maintains this document.
- `implementer` only executes items explicitly approved by the parent task or
  clearly marked approved here.
- Immediate refactor work belongs here; later cluster topology and continuous
  runtime concerns belong in a later phase.

## Current Audit

Files reviewed for this refresh:

- [src/cbb/ui/app.py](../src/cbb/ui/app.py)
- [src/cbb/ui/service.py](../src/cbb/ui/service.py)
- [src/cbb/ui/snapshot.py](../src/cbb/ui/snapshot.py)
- [src/cbb/cli.py](../src/cbb/cli.py)
- [docs/architecture.md](architecture.md)

Repo-specific findings:

- [src/cbb/ui/app.py](../src/cbb/ui/app.py) is a presentation-layer WSGI app,
  but it imports a UI service that already knows about caching, prediction
  refresh, snapshot freshness, report loading, and database-backed team views.
- [src/cbb/ui/service.py](../src/cbb/ui/service.py) imports directly from
  `cbb.db`, `cbb.modeling.*`, and `cbb.ui.snapshot`, so the current frontend
  boundary is package-level only, not architectural.
- [src/cbb/ui/snapshot.py](../src/cbb/ui/snapshot.py) calls
  `generate_best_backtest_report()` directly and owns snapshot freshness
  decisions that are really backend orchestration concerns.
- [src/cbb/cli.py](../src/cbb/cli.py) is already close to the right shape for
  `dashboard`: it mostly launches the server. The main coupling problem is not
  the CLI command itself; it is the fact that the UI package still reaches
  directly into report, prediction, artifact, and database code paths.
- The repo does not yet need Kubernetes always-on services for this refactor.
  The immediate need is a stable in-repo backend contract that the frontend can
  depend on before deployment topology changes.

## Design Direction

The next frontend step should not be a visual rewrite. It should be a
structural split:

1. move dashboard backend orchestration out of `src/cbb/ui/`
2. define typed middleware responses for dashboard pages and supporting data
3. let the frontend depend on that middleware contract instead of direct model
   and database imports
4. keep the existing CLI `dashboard` command as a thin launcher

That gives the repo a clean path to a separately deployed frontend later
without forcing that infrastructure change now.

## Ranked Improvements

### UX-FE-1: Extract a dashboard middleware package from the UI package

Status: approved
Implementation: completed `2026-03-12`

Problem:
The current UI package mixes presentation concerns with backend orchestration.

User impact:
Frontend work is hard to change safely because every page path is coupled to
prediction, report, snapshot, artifact, and database code in the same package.

Evidence:
- [src/cbb/ui/service.py](../src/cbb/ui/service.py) imports `get_engine`,
  `get_team_view`, `load_artifact`, `predict_best_bets`,
  `summarize_closing_line_value`, and `load_dashboard_snapshot`.
- The same file owns page DTOs, caching, report warmup, prediction refresh,
  team search queries, and page-specific formatting.

Proposed solution:
Create a backend-facing dashboard middleware package that owns data loading,
snapshot/report orchestration, prediction refresh, cache policy, and typed page
payload construction. The UI package should become presentation-only.

Implementation sketch:
- create a new package for dashboard backend logic outside `src/cbb/ui/`
- move dashboard service, snapshot helpers, and cache helpers into that package
- keep narrow compatibility wrappers only where they reduce migration risk
- leave `src/cbb/ui/` with WSGI routing, templates, static assets, and thin
  request/response mapping

Acceptance criteria:
- `src/cbb/ui/` no longer imports directly from `cbb.db` or `cbb.modeling.*`
- backend orchestration has a clear package boundary outside the UI package
- current CLI and dashboard behavior still work

Suggested ownership:
- backend/middleware extraction thread

Delivered:
- dashboard backend orchestration now lives under `src/cbb/dashboard/`
- `src/cbb/ui/service.py`, `src/cbb/ui/snapshot.py`, and `src/cbb/ui/cache.py`
  now act as compatibility aliases rather than the primary implementation
- the presentation layer now imports dashboard middleware types from the new
  backend package

### UX-FE-2: Introduce a typed middleware contract and JSON response surface

Status: approved
Implementation: completed `2026-03-12`

Problem:
The frontend currently consumes Python objects directly inside the same process
boundary, which makes it harder to evolve toward a separately deployed
frontend.

User impact:
Any future frontend change remains tied to Python import paths instead of a
stable contract.

Evidence:
- [src/cbb/ui/app.py](../src/cbb/ui/app.py) renders HTML pages directly from a
  concrete `DashboardService`.
- The only JSON path today is team search, which is too narrow to serve as the
  main frontend boundary.

Proposed solution:
Define typed middleware response models and expose them through a small JSON
API surface for the dashboard pages and supporting views.

Implementation sketch:
- define stable page/section payload serializers in the new middleware layer
- add JSON endpoints for dashboard, models, performance, upcoming picks, pick
  history, teams, and team detail
- let the UI layer depend on the middleware contract rather than internal model
  functions

Acceptance criteria:
- the repo has a clear frontend-facing data contract for major dashboard views
- page handlers can be tested against middleware responses without reaching
  directly into model/database code
- future frontend transport changes do not require reworking modeling imports

Suggested ownership:
- UI transport and contract thread

Delivered:
- the dashboard backend now exposes a typed `DashboardMiddleware` contract
- `src/cbb/ui/app.py` now serves JSON endpoints for dashboard, models,
  performance, upcoming picks, pick history, teams, and team detail views
- the team-search JSON path is now part of a broader frontend-facing response
  surface instead of a one-off exception

### UX-FE-3: Make dashboard bootstrap and refresh orchestration backend-owned

Status: approved
Implementation: completed `2026-03-12`

Problem:
Snapshot freshness and prediction/report warmup are still framed as UI startup
behavior instead of backend service behavior.

User impact:
Operational logic is harder to reason about because dashboard boot and backend
data refresh policy are bundled together.

Evidence:
- [src/cbb/ui/app.py](../src/cbb/ui/app.py) calls
  `ensure_dashboard_snapshot_fresh()` during server startup.
- [src/cbb/ui/service.py](../src/cbb/ui/service.py) owns background report
  warmup and prediction refresh threads.

Proposed solution:
Move refresh policy and startup orchestration behind the middleware boundary so
the CLI launcher and WSGI app only bootstrap the frontend and middleware.

Implementation sketch:
- move snapshot freshness checks into backend bootstrap helpers
- keep current local warm-cache behavior, but make it a backend concern
- keep the CLI `dashboard` command as a thin launcher around the new boundary

Acceptance criteria:
- frontend startup code does not own report/prediction orchestration policy
- refresh behavior remains functionally equivalent for local use
- the future path to a long-running middleware service is clearer

Suggested ownership:
- backend/bootstrap thread

Delivered:
- backend bootstrap helpers now live in `src/cbb/dashboard/bootstrap.py`
- snapshot readiness is prepared through the dashboard backend package before
  the WSGI app serves requests
- the CLI `dashboard` command remains a thin launcher over the new backend
  boundary

### UX-FE-4: Document the new frontend/backend split and explicit phase boundary

Status: approved
Implementation: completed `2026-03-12`

Problem:
Without durable docs, the repo will regress toward putting new backend logic in
the UI package again.

User impact:
Future contributors will not know where dashboard code should live or which
phase owns cluster runtime concerns.

Evidence:
- [docs/architecture.md](architecture.md) currently describes the dashboard as
  a UI package plus snapshot flow, but it does not yet draw a middleware layer
  between presentation and data orchestration.

Proposed solution:
Update the durable docs to describe the new boundary and explicitly defer
always-on services, schedulers, and cluster deployment changes.

Implementation sketch:
- update README and architecture docs with the new dashboard stack
- describe the middleware layer as the immediate target
- explicitly defer continuous refresh workers and Kubernetes service topology

Acceptance criteria:
- docs explain where frontend logic stops and backend orchestration begins
- later infrastructure work is clearly called out as a separate phase

Suggested ownership:
- docs and verification thread

Delivered:
- the README and architecture doc now describe the new `src/cbb/dashboard/`
  middleware layer
- the docs now explicitly separate this refactor from later Kubernetes and
  always-on worker work

## Deferred Follow-On Work

### UX-FE-5: Run the middleware as an always-on Kubernetes service

Status: deferred

Reason:
This is a deployment-topology change, not the first refactor step. The repo
first needs a clean in-process middleware boundary before deciding how to run
it continuously in the cluster.

### UX-FE-6: Add continuous report/model refresh workers

Status: deferred

Reason:
A background scheduler changes runtime behavior and operational ownership. That
should follow the middleware split, not be bundled into it.

### UX-FE-7: Replace the current server-rendered UI with a separate SPA

Status: needs follow-up

Reason:
That may become reasonable later, but it is not required to achieve the
current decoupling goal. The repo should first prove the middleware contract.

### UX-FE-8: Move training, ingest, or model refresh into the dashboard UI

Status: rejected

Reason:
That would widen scope and make the frontend boundary worse, not better.

### UX-FE-9: Keep dashboard contracts aligned with deployable policy changes

Status: approved
Implementation: completed `2026-03-12`

Reason:
The current phase is model-first. The dashboard does not need another visual or
architectural rewrite, but it does need to stay aligned when report, snapshot,
or policy payloads change under an approved model experiment.

Scope for this run:

- preserve snapshot compatibility when policy fields expand
- keep middleware payloads and UI rendering working without reintroducing
  direct modeling imports into the presentation layer
- prefer test coverage and small copy updates over new UI feature work

Delivered:

- the dashboard snapshot policy payload now accepts the new optional
  `max_bets_per_day` field without breaking older snapshot files
- the dashboard JSON helper now uses an explicit dataclass serialization path
  that stays `mypy`-clean
- dashboard/UI tests now cover backward-compatible snapshot loading for the
  expanded deployable policy contract

## Approved Implementation Order

Use this order for the current run:

1. `UX-FE-1` backend/middleware extraction
2. `UX-FE-2` typed middleware contract and JSON surface
3. `UX-FE-3` backend-owned bootstrap/refresh policy
4. `UX-FE-4` docs and verification cleanup
5. `UX-FE-9` compatibility edits required by approved model/report changes

Current coordinator state after the latest model promotion:

- every currently approved repo-local UI item is completed
- no further UI refactor or frontend feature work is approved in this phase
  unless a later approved model/report change requires compatibility work
- larger deployment-topology, scheduler, or frontend-stack changes remain
  intentionally deferred

## Research Log

- date: `2026-03-12`
- area reviewed: dashboard package structure, WSGI app boundary, snapshot
  orchestration, CLI launch path
- findings:
  - the real dashboard problem is architectural coupling, not missing pages or
    visual polish
  - the UI package already behaves like a mixed frontend/backend module
  - the clean next step is an in-repo middleware boundary, not Kubernetes work
- proposed next step: treat always-on middleware deployment and continuous
  refresh as a later infrastructure phase
- status: completed

- date: `2026-03-12`
- area reviewed: dashboard middleware, snapshot freshness flow, JSON endpoints,
  and policy/report coupling after the latest model-roadmap refresh
- findings:
  - the dashboard architecture is already in the right place for this repo
  - the immediate UI risk is regression from backend policy/report changes, not
    missing frontend capabilities
  - policy/schema compatibility work is the only approved UI lane for the
    current model-focused phase
- proposed next step: keep the middleware and snapshot contract aligned while
  deferring any larger UI or deployment changes
- status: completed
