# CBB Application Instructions

These instructions apply to `cbb-upsets/`. Inherit the working and commit rules
from [../AGENTS.md](../AGENTS.md). All paths and commands below are relative to
this directory; run `cd cbb-upsets` first when starting at the repository root.

## Read the relevant context

- [README.md](README.md): setup, CLI commands, dashboard, and deployment.
- [docs/architecture.md](docs/architecture.md): engineering and data flow.
- [docs/model.md](docs/model.md): modeling, evaluation, and deployable policy.
- [Current model report](docs/results/best-model-5y-backtest.md): the latest
  tracked evaluation. Read it for existing results; `cbb model report` runs
  backtests and rewrites outputs, so do not run it merely to inspect metrics.

Use the relevant roadmap for planned work: [model](docs/model-improvement-roadmap.md),
[UI](docs/ui-ux-roadmap.md), or [infra](docs/infra-roadmap.md). Update that roadmap
when implementing or evaluating one of its items. Ordinary fixes do not need
a new roadmap entry or a dedicated worktree.

## Application map

- `src/cbb/cli.py`: Typer commands; the installed entry point is `cbb`.
- `src/cbb/ingest/`: ESPN games, Odds API markets, and availability imports.
- `src/cbb/db.py` and `sql/schema.sql`: PostgreSQL access and schema.
- `src/cbb/modeling/`: features, training, walk-forward evaluation, prediction,
  policy, artifacts, tournament analysis, and reports.
- `src/cbb/agent.py`: the application's live data refresh and prediction cycle.
  This is runtime application code, independent of Codex instruction files.
- `src/cbb/dashboard/`: dashboard services, snapshots, and caching.
- `src/cbb/ui/app.py`: HTTP routes, JSON endpoints, and the React document shell.
- `frontend/src/`: React/TypeScript UI; `src/cbb/ui/static/react/` contains its
  tracked build output. There is no Jinja page-rendering layer.
- `chart/cbb-upsets/` and `Makefile`: local cluster and deployment workflows.

## Runtime and local operations

- Use the existing `.venv`: `.venv/bin/python -m cbb.cli ...`, or activate it
  and run `cbb ...`. `make install` installs the Python development environment.
- Read settings names in `.env.example` and `src/cbb/config.py`. Actual local
  credentials belong in ignored `.env` or secret overrides, never in output.
- The usual cluster is `cbb-upsets-cluster`; the chart release is `cbb-upsets`
  in namespace `default`. Inspect current state with `make k8s-status`,
  `make helm-status`, and `kubectl get pods -n default` before changing it.
- `make db-port-forward` exposes cluster Postgres on `127.0.0.1:5432`.
  Reuse an existing forward. Use cluster Postgres as the CBB system of record
  unless the user requests another database.
- The chart supports an NGINX frontend, optional Python middleware, and either
  a looping runtime Deployment or a scheduled CronJob. Do not enable both
  runtime modes. The middleware can read job-produced predictions using
  `--prediction-source cache`; preserve that separation when editing the UI.
- Base chart values leave middleware and runtime disabled. Inspect deployed
  overrides before a Helm upgrade so a maintenance task does not disable an
  existing dashboard or change its refresh schedule.
- `make k8s-down` deletes the shared cluster. Database imports, cluster/PVC
  deletion, and restore operations require explicit user intent; a request to
  inspect, test, or clean source files does not authorize those actions.

## Paid requests and data integrity

- Treat Odds API credits as real spend. Current/historical odds ingestion,
  `cbb agent` (including `--run-once`), and enabled runtime jobs can spend them.
  Run paid collection only within the user's authorized scope and budget.
- For an authorized ESPN-only refresh, `cbb agent --run-once --no-odds`
  disables the paid odds leg, but still fetches ESPN and writes to the database.
  Use fixtures and mocked clients for routine verification.
- Preserve idempotent imports, ingest checkpoints, canonical team identities,
  and the distinction between missing data and a real zero.
- Keep schema initialization in `sql/schema.sql` safe to rerun. Prefer additive
  changes; preserve column meanings, checkpoint keys, and artifact semantics.
- Preserve existing CLI commands, `predict.v1` JSON, and dashboard API contracts
  unless the task explicitly calls for a change. Keep `load_artifact()` backward
  compatible where practical and test older artifacts when the format changes.

## Modeling and dashboard rules

- `best` uses spread when available, with moneyline as a fallback when spread
  cannot train or load. Fixed deployable policy is the default; auto-tuning
  and timing-layer experiments are opt-in. Verify defaults in source before
  changing them rather than copying values from historical roadmap entries.
- Keep feature construction chronological and free of future information.
  Assess walk-forward and per-season results, including risk and closing-price
  evidence. Training accuracy or one favorable season does not justify promotion.
- Keep prediction, backtesting, and report policy aligned. A promoted model or
  policy change requires regenerating `cbb model report` and committing the
  canonical report and affected docs with the change. Never hand-edit metrics.
- Keep betting and date-bucketing logic in the existing Python model/middleware
  boundaries. React consumes JSON and owns presentation and interaction.
  Preserve cache timestamps and distinguish cached recommendations from
  historical backtest results. Opening the UI must not trigger paid ingestion.

## Implementation and verification

Use Python 3.11+ syntax, typed interfaces, explicit errors, and small functions.
Keep Python dependencies in `pyproject.toml`; use the Ruff/mypy configuration
there. Prefer regression tests for meaningful behavior over tests that merely
mirror implementation. Avoid new abstractions and dependencies without a
concrete need. Keep Helm declarative and use pinned image versions for new work.

Run checks appropriate to the changed surface:

| Change | Verification |
| --- | --- |
| Python behavior | `.venv/bin/pytest -q tests/test_<area>.py`, `make lint`, `make typecheck` |
| Shared CLI, schema, or modeling behavior | Full `.venv/bin/pytest -q` plus lint/type checks and relevant model evidence |
| React UI | In `frontend/`, use `npm ci` if dependencies are missing, then `npm run build`; commit regenerated `src/cbb/ui/static/react/` assets |
| Dashboard contract or UI integration | `.venv/bin/pytest -q tests/test_dashboard_ui.py tests/test_dashboard_snapshot.py` and a browser check for visual changes |
| Helm/Make deployment paths | `make helm-check` plus the applicable `helm-*-check` target; these validate without deploying |
| Instructions/docs/config only | Check referenced paths/commands, parse changed config, and run `git diff --check`; no unrelated model runs or cluster changes |

`make check` runs Python lint, type checks, tests, and base Helm checks; it does
not build the React client. Run runtime smoke tests only when relevant and
within the authorized database and paid-request scope. Report any checks that
could not run and why.

## Documentation and generated files

- Update the existing README and architecture/model docs when their described
  behavior changes. Prefer those over new standalone planning documents.
- Keep `docs/results/best-model-5y-backtest.md` as the tracked canonical report.
  History copies and `docs/results/best-model-dashboard-snapshot.json` stay
  ignored. The report command updates the dashboard snapshot for canonical
  report settings.
- Keep `artifacts/`, `backups/`, `.env`, and `.codex/local/` untracked. Do not
  delete local models, backups, or old worktrees as incidental cleanup.
- Commit completed task changes under the repository-wide rule. Include tracked
  frontend build output when changing its source; exclude runtime scratch,
  secrets, and unrelated files.
