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
