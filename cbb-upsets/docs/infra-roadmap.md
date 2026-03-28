# Infra Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [System Architecture](architecture.md)
- [Model Documentation](model.md)

Updated: `2026-03-28`

## Goal

Keep infra and local-cluster work organized, local-first, and manually runnable
from dedicated worktrees without reintroducing a background supervisor.

This lane is intentionally narrower than the model and UI roadmaps:

- local cluster automation first
- operator workflow hardening first
- dedicated worktrees and manual review first
- strict source allowlist and bounded task selection

## Working Agreement

- `infra_researcher` maintains this document.
- `infra_implementer` executes only one approved infra item at a time in a
  dedicated worktree.
- `infra_verifier` gates manual review by source, scope, and verification
  compliance before a local commit.
- This roadmap is infra-only. Model, ingest, dashboard, and UI work remain on
  their existing roadmaps.

## Manual Workflow Note

The old autonomous supervisor and auto-commit flow were retired on
`2026-03-28`. Keep the historical automation items below as context only. Do
not reintroduce background scheduling or auto-commit behavior without explicit
user direction.

## Current Expansion Override

The `2026-03-28` infra and UX architectural loop explicitly approved bounded
runtime work beyond the earlier manual-helper-only scope. Infra items in this
phase may add:

- a runnable CLI image with the repo code installed
- chart wiring for that runtime
- safe in-cluster scheduled refresh resources
- explicit config, secret, and operator workflow updates for those paths

The same local-first standards still apply:

- one bounded slice per pass
- explicit roadmap evidence before coding
- no paid ingest verification loops
- no auto-commit or hidden background supervisor behavior

## In-Cluster Runtime Epic

### INFRA-RUNTIME-1 [`completed`] Build a supported CLI container image

Problem:

- the chart can only deploy PostgreSQL plus a small NGINX helper today, so the
  repo has no supported runtime image foundation for later in-cluster CLI jobs
  such as a scheduled refresh loop

Repo evidence:

- the repo root has no `Dockerfile`, `.dockerignore`, or image-build helper
- `docs/architecture.md` states that the main application logic does not run
  in cluster today
- `README.md` documents only the local virtualenv path for CLI execution and
  does not give operators a supported container build workflow

Implementation shape:

- add one explicit container build for the CLI with the repo code and tracked
  runtime data installed
- keep the runtime image local-first and manual; this slice only creates the
  image foundation and operator build path, not a scheduled cluster workload
- document how the new image fits the chart-driven local workflow and later
  runtime slices

Acceptance criteria:

- a reproducible repo-local image build succeeds and exposes the `cbb` CLI as
  the runtime entrypoint
- the image includes the tracked files needed by repo-root-relative runtime
  paths such as `sql/schema.sql` and `data/team_home_locations.csv`
- operators have one supported build command in the repo workflow docs
- architecture and infra docs describe this as the first in-cluster runtime
  foundation slice rather than a full automation rollout

Explicit non-goals:

- adding a Kubernetes job, CronJob, or always-on controller in this pass
- changing ingest, model, or dashboard behavior
- exercising paid data-refresh commands during verification

Implementation note:

- completed in the dedicated `2026-03-28` infra runtime worktree cycle
- the repo now ships a supported `Dockerfile`, `.dockerignore`, and
  `make cli-image-build` helper for a non-root CLI image rooted at `/app`

### INFRA-RUNTIME-2 [`completed`] Wire the CLI runtime image into the chart as an opt-in agent Deployment

Problem:

- the repo now has a runnable CLI image, but the Helm chart still has no
  value-driven way to run that image in cluster for periodic refresh work

Repo evidence:

- `chart/cbb-upsets/values.yaml` only exposes `nginx` and `postgresql`
  settings today
- `chart/cbb-upsets/templates/` has no runtime Deployment, Job, or CronJob
  template for the new CLI image
- the current CLI already has a long-running `cbb agent --delay-mins ...`
  loop that fits an opt-in singleton Deployment better than a speculative
  supervisor rewrite

Implementation shape:

- add one disabled-by-default `runtime` values block for the CLI image,
  container args, env, secret import, and resources
- render one optional singleton Deployment that runs the existing looping
  `cbb agent` path from the new image
- derive `DATABASE_URL` from an explicit runtime override or the chart-managed
  PostgreSQL release defaults so the in-cluster runtime can talk to the same
  database without a local port-forward

Acceptance criteria:

- the chart can render an opt-in runtime Deployment without changing the
  existing default release contents
- operators can configure image repository, tag, pull policy, args, resources,
  plain env, and one optional secret import through values
- the rendered runtime pod gets `DATABASE_URL` from either `runtime.databaseUrl`
  or the chart-managed PostgreSQL connection settings
- README and architecture docs describe this as the first chart wiring slice
  for in-cluster refresh, still disabled by default

Explicit non-goals:

- enabling the runtime Deployment by default
- adding a CronJob and Deployment in the same pass
- executing paid ingest loops during verification

Implementation note:

- completed in the dedicated `2026-03-28` infra runtime worktree cycle
- the chart now has a disabled-by-default `runtime` Deployment that can run
  the existing looping `cbb agent` path after operators set an image tag and
  any needed secret-backed env

### INFRA-RUNTIME-3 [`completed`] Add a one-shot agent mode for scheduled runtime jobs

Problem:

- the chart can now run the agent loop as a singleton Deployment, but the CLI
  still has no supported one-shot mode for CronJob-style scheduled refresh

Repo evidence:

- `src/cbb/cli.py` currently hard-codes `cbb agent` as an infinite `while True`
  loop that always sleeps between iterations
- the new chart runtime wiring can run `cbb agent`, but that shape only fits an
  always-on Deployment today, not a scheduled job that should do one sync and
  exit
- `tests/test_cli.py` already covers the loop behavior and provides a clear
  place to pin a bounded run-once path without changing the existing default

Implementation shape:

- add one explicit `--run-once` mode to `cbb agent`
- keep the current infinite-loop behavior as the default when that flag is not
  set
- make run-once mode exit after one sync without sleeping, and fail the command
  when that single sync raises the same runtime errors the loop currently logs

Acceptance criteria:

- `cbb agent --run-once` performs exactly one sync iteration and exits without
  sleeping
- loop mode still prints the existing start, iteration, sleep, and interrupt
  messages
- run-once mode returns a non-zero exit when the single sync iteration fails
- README and architecture docs describe the run-once path as the scheduled-job
  friendly runtime command

Explicit non-goals:

- changing the default looping behavior of `cbb agent`
- adding a CronJob template in the same pass
- widening into model or dashboard behavior changes

Implementation note:

- completed in the dedicated `2026-03-28` infra runtime worktree cycle
- `cbb agent --run-once` now executes one bounded refresh-and-scan iteration,
  exits without sleeping, and returns a non-zero status when that single run
  hits the same operational/runtime failures that loop mode logs and continues
  through

### INFRA-RUNTIME-4 [`completed`] Add an opt-in runtime CronJob wired to `cbb agent --run-once`

Problem:

- the chart can now run the CLI image as an always-on Deployment, and the CLI
  now has a one-shot mode, but there is still no supported chart path for a
  scheduled in-cluster refresh job

Repo evidence:

- `chart/cbb-upsets/values.yaml` exposes only the looping `runtime.enabled`
  Deployment path today
- `chart/cbb-upsets/templates/` has no Job or CronJob template for the new
  one-shot `cbb agent --run-once` command
- `src/cbb/cli.py` now supports `--run-once`, which is the right command shape
  for a bounded scheduled workload instead of the older infinite loop

Implementation shape:

- add one disabled-by-default `runtime.schedule` values block for schedule,
  history retention, concurrency policy, suspend state, and job retry knobs
- render one optional CronJob that reuses the runtime image/env wiring but runs
  `cbb agent --run-once`
- make the chart fail clearly if operators try to enable both the looping
  Deployment and scheduled CronJob at the same time

Acceptance criteria:

- the chart can render an opt-in runtime CronJob without changing the default
  release contents
- operators can configure the cron schedule and bounded job policy through
  values without editing templates
- the runtime CronJob uses `cbb agent --run-once` instead of inheriting the
  looping agent command
- Helm validation proves the default chart still renders, the CronJob render
  succeeds when enabled, and the chart fails clearly on conflicting runtime
  modes

Explicit non-goals:

- enabling scheduled refresh by default
- executing paid ingest loops during verification
- adding secret-management or operator log helpers in the same pass

Implementation note:

- completed in the dedicated `2026-03-28` infra runtime worktree cycle
- the chart now exposes a disabled-by-default `runtime.schedule` CronJob that
  defaults to `cbb agent --run-once`, reuses the existing runtime env wiring,
  and fails fast if operators try to enable the looping Deployment and CronJob
  together

## Manual Backlog

### INFRA-MANUAL-1 [`completed`] Local Helm deploy and Postgres port-forward helpers

Keep the manual local-cluster path explicit without reviving a supervisor by
adding supported `Make` shortcuts for the two repeated operator steps that
happen after `make k8s-up`:

- deploy the local Helm release with the tracked chart and local values files
- port-forward the chart-managed PostgreSQL service on `127.0.0.1:5432`

Accepted scope:

- update `Makefile` only for the helper targets and shared variables they need
- update the operator docs that describe the local cluster workflow
- do not add background processes, task scheduling, or auto-merge behavior

Implementation note:

- completed in the dedicated `2026-03-28` manual infra worktree cycle

Acceptance criteria:

- `make helm-up` runs the local `helm upgrade --install` flow with the tracked
  chart values
- `make db-port-forward` forwards `svc/cbb-upsets-postgresql` on
  `127.0.0.1:5432`
- README and architecture docs point operators at the supported helper targets
  for the manual path

### INFRA-MANUAL-2 [`completed`] Manual Helm validation helper target

Problem:

- the manual local-cluster docs now expose `make helm-up` and
  `make db-port-forward`, but the required chart-validation path still lives as
  two separate low-level Helm commands, which makes the supported operator
  workflow less explicit than deploy and port-forward

Repo evidence:

- `Makefile` has `helm-lint` and `helm-template` with shared chart/value
  variables, but no single helper target for running both together
- `README.md` points operators at `make k8s-up`, `make helm-up`, and
  `make db-port-forward`, while `AGENTS.md` and the verification checklist
  still require both Helm validation commands explicitly
- `docs/architecture.md` describes the manual local-cluster loop but does not
  name a supported validation shortcut for chart changes

Implementation shape:

- add one bounded `make helm-check` helper that runs `helm-lint` and
  `helm-template` with the tracked chart/value configuration
- document that helper in the README and architecture doc as the supported
  manual validation step before or alongside chart deploy work
- keep the workflow local-only and manual; do not add background automation or
  change the Helm release contents

Acceptance criteria:

- `make helm-check` succeeds by running the existing lint and template steps
  against `chart/cbb-upsets` with `values.yaml` and `values-local.yaml`
- README and architecture docs mention `make helm-check` as the supported
  chart-validation shortcut in the local operator workflow
- the change stays inside infra files and does not alter chart semantics

Implementation note:

- completed in the dedicated `2026-03-28` manual infra worktree cycle

Explicit non-goals:

- changing rendered Kubernetes resources or chart defaults
- auto-deploying after validation
- widening into model, ingest, dashboard, or UI work

### INFRA-MANUAL-3 [`completed`] Manual Helm dependency bootstrap helper

Problem:

- fresh roadmap worktrees do not inherit the local chart dependency tarballs
  under `chart/cbb-upsets/charts/`, so the supported `make helm-check` path can
  fail in a clean worktree until the operator manually rebuilds dependencies

Repo evidence:

- `Chart.yaml` and `Chart.lock` are tracked, but the vendored dependency
  tarballs under `chart/cbb-upsets/charts/` are not tracked in git
- the prior infra verification run in a fresh worktree failed on
  `helm template ...` until `helm dependency build chart/cbb-upsets` was run
  locally from that worktree
- the docs currently name `make helm-check` as the supported validation path,
  but they do not tell operators how to bootstrap Helm dependencies when
  starting from a clean worktree

Implementation shape:

- add one bounded manual helper target for rebuilding chart dependencies from
  the tracked lockfile in the current worktree
- wire the validation helper through that dependency bootstrap step so the
  supported `make helm-check` path works in fresh worktrees without extra
  operator guesswork
- document the supported dependency bootstrap behavior in the local operator
  docs without committing generated chart tarballs

Acceptance criteria:

- one supported Make target rebuilds chart dependencies from `Chart.lock`
- `make helm-check` succeeds in a fresh worktree after running the supported
  helper path, without requiring operators to invent a raw Helm command
- README and architecture docs describe the dependency bootstrap step for
  manual worktrees
- generated chart dependency tarballs remain uncommitted

Explicit non-goals:

- committing vendored chart archives to git
- changing chart contents or dependency versions
- adding background automation, cluster orchestration, or runtime services

Implementation note:

- completed in the dedicated `2026-03-28` manual infra worktree cycle

### INFRA-MANUAL-4 [`completed`] Quiet Helm render verification helper

Problem:

- `make helm-check` is now the supported validation path, but it still streams
  the full `helm template` manifest to stdout, which buries the actual
  validation result in large YAML output during manual roadmap loops

Repo evidence:

- `Makefile` currently points `helm-check` at `helm-lint` and `helm-template`
  directly, so every validation run prints the entire rendered chart
- fresh-worktree infra verification showed the helper now succeeds, but the
  useful signal is still mixed into more than a thousand lines of rendered
  manifests
- there is no separate explicit helper for operators who do want the full
  rendered manifest on demand

Implementation shape:

- keep one explicit render helper for operators who want the full manifest
- route the supported `make helm-check` path through a quieter render-
  verification helper that still proves `helm template` succeeds
- document the difference between quiet validation and explicit manifest render
  in the local operator docs

Acceptance criteria:

- `make helm-check` remains the supported validation shortcut but no longer
  dumps the entire rendered manifest to stdout on success
- operators still have one explicit helper target that prints the full
  `helm template` output on demand
- README and architecture docs describe the quiet validation path versus the
  explicit render path
- Helm validation still fails loudly when linting or templating breaks

Explicit non-goals:

- changing rendered resources or chart defaults
- hiding validation failures
- adding background automation or cluster lifecycle behavior

Implementation note:

- completed in the dedicated `2026-03-28` manual infra worktree cycle
- `make helm-check` now proves lint and template success without dumping the
  full manifest, while `make helm-template` remains the explicit full-render
  helper

### INFRA-MANUAL-5 [`completed`] Helm deploy preflight through the supported validation path

Problem:

- `make helm-up` is now the supported local deploy helper, but it still jumps
  straight from dependency bootstrap to `helm upgrade --install` without
  proving that the chart passes the repo's supported lint and template checks
  first

Repo evidence:

- `Makefile` currently wires `helm-up` only through `helm-bootstrap`, while
  `helm-check` separately owns the supported validation path
- README and architecture docs point operators at both `make helm-check` and
  `make helm-up`, but they do not say whether deploy reuses the validation
  helper or requires the operator to remember that sequencing manually
- the repo's verification checklist already treats Helm lint and template as
  the baseline gate for infra changes, so the supported manual deploy shortcut
  should be at least that strict

Implementation shape:

- route `make helm-up` through the existing `helm-check` helper before running
  `helm upgrade --install`
- keep the deploy helper local and manual; do not add cluster lifecycle logic
  or background automation
- document that the supported deploy path now validates first and only reaches
  Helm upgrade after the chart passes the existing checks

Acceptance criteria:

- `make helm-up` reuses the supported Helm validation path before deploy
- operators can still call `make helm-check` or `make helm-template`
  independently for validation-only work
- README and architecture docs describe the preflight validation behavior
- the change does not alter chart contents, values, or release semantics

Explicit non-goals:

- adding cluster readiness probes or auto-start behavior
- changing rendered resources or chart defaults
- widening into Kubernetes runtime automation beyond the manual helper

Implementation note:

- completed in the dedicated `2026-03-28` manual infra worktree cycle
- `make helm-up` now reuses `make helm-check`, so the supported deploy path
  runs the existing lint and template preflight before `helm upgrade --install`

### INFRA-MANUAL-6 [`completed`] Local Helm release status helper

Problem:

- the supported local cluster path now has explicit helpers for validation,
  deploy, and Postgres port-forwarding, but operators still need to remember a
  raw Helm or kubectl command to inspect the current release state after deploy

Repo evidence:

- README currently walks operators through `make helm-up` and then a raw
  `kubectl get pods`, but there is no supported helper for the release-level
  view that Helm already owns
- `Makefile` has `helm-check`, `helm-template`, and `helm-up`, but no
  corresponding `helm-status` shortcut
- the infra roadmap goal is to make the manual operator path explicit and
  local-first, which should include one bounded helper for post-deploy release
  inspection

Implementation shape:

- add one manual `make helm-status` helper that reports the current Helm
  release state for the tracked local release name
- document that helper as the supported post-deploy release inspection step in
  the local operator workflow
- keep the helper read-only and local; do not add rollout waiting, cluster
  startup, or background automation

Acceptance criteria:

- `make helm-status` runs the tracked Helm release status command for the
  local release
- README and architecture docs mention the helper in the supported local
  operator flow
- the change stays read-only and does not alter chart contents or deploy
  semantics

Explicit non-goals:

- adding rollout wait loops or readiness polling
- changing rendered resources or chart defaults
- widening into cluster lifecycle automation

Implementation note:

- completed in the dedicated `2026-03-28` manual infra worktree cycle
- `make helm-status` now gives the supported release-level inspection command
  for the tracked local Helm release after deploy

## Archived Automation Backlog

### INFRA-LOOP-1 [`archived`] Local supervisor and worktree isolation

Implement a local supervisor that:

- runs forever from the developer machine
- creates an isolated git worktree per iteration
- drives `infra_researcher`, `infra_implementer`, and `infra_verifier`
- auto-commits locally on `auto/infra-loop` only after verifier approval

Acceptance criteria:

- a local start command launches the supervisor
- each iteration uses a throwaway worktree
- failed iterations do not dirty the main workspace
- accepted iterations produce one local commit on the dedicated branch

### INFRA-LOOP-2 [`archived`] Cluster readiness and managed Postgres port-forward

Teach the supervisor to verify or start the local prerequisites it depends on:

- `k3d` cluster reachable
- Helm release present
- Postgres port-forward available on `127.0.0.1:5432`

Acceptance criteria:

- the loop reports a clear failure when cluster prerequisites are missing
- the loop can reuse an existing port-forward or start one locally
- runtime state records the managed port-forward PID when started by the loop

### INFRA-LOOP-3 [`archived`] Heartbeat, status, and stop controls

Add operator-facing controls for:

- starting the loop
- checking heartbeat / last run / last commit
- stopping the loop cleanly

Acceptance criteria:

- `make infra-loop-up` starts the local supervisor
- `make infra-loop-status` shows a useful summary
- `make infra-loop-stop` stops the supervisor and any managed port-forward

## Retired Proposal Lane

### INFRA-LOOP-4 [`retired`] Local-cluster-to-k8s migration prep

Prepare the automation lane so it can eventually move into the local cluster
without changing task selection or policy semantics.

This proposal was tied to the removed supervisor workflow and is not active.
