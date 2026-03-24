# Infra Automation Roadmap

Canonical links:

- [Repository README](../README.md)
- [System Architecture](architecture.md)
- [Model Documentation](model.md)

Updated: `2026-03-23`

## Goal

Create a safe local-first automation lane that can keep improving the repo's
devops / infra posture continuously without turning the main application into an
always-on in-cluster service yet.

This lane is intentionally narrower than the model and UI roadmaps:

- local cluster automation first
- operator workflow hardening first
- local-only auto-commit on a dedicated branch
- strict source allowlist and bounded task selection

## Working Agreement

- `infra_researcher` maintains this document.
- `infra_implementer` executes only one approved infra item at a time.
- `infra_verifier` gates local auto-commit by source, scope, and verification
  compliance.
- This roadmap is infra-only. Model, ingest, dashboard, and UI work remain on
  their existing roadmaps.

## Approved Backlog

### INFRA-LOOP-1 [`approved`] Local supervisor and worktree isolation

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

### INFRA-LOOP-2 [`approved`] Cluster readiness and managed Postgres port-forward

Teach the supervisor to verify or start the local prerequisites it depends on:

- `k3d` cluster reachable
- Helm release present
- Postgres port-forward available on `127.0.0.1:5432`

Acceptance criteria:

- the loop reports a clear failure when cluster prerequisites are missing
- the loop can reuse an existing port-forward or start one locally
- runtime state records the managed port-forward PID when started by the loop

### INFRA-LOOP-3 [`approved`] Heartbeat, status, and stop controls

Add operator-facing controls for:

- starting the loop
- checking heartbeat / last run / last commit
- stopping the loop cleanly

Acceptance criteria:

- `make infra-loop-up` starts the local supervisor
- `make infra-loop-status` shows a useful summary
- `make infra-loop-stop` stops the supervisor and any managed port-forward

## Next Proposal Lane

### INFRA-LOOP-4 [`proposal`] Local-cluster-to-k8s migration prep

Prepare the automation lane so it can eventually move into the local cluster
without changing task selection or policy semantics.

This is not approved yet. The local supervisor remains the shipping baseline.
