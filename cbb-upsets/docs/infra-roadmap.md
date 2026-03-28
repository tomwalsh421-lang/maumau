# Infra Improvement Roadmap

Canonical links:

- [Repository README](../README.md)
- [System Architecture](architecture.md)
- [Model Documentation](model.md)

Updated: `2026-03-23`

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
