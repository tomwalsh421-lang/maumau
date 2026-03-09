# Thread Roles

## Purpose

This repository supports parallel local Codex work through separate git
worktrees. The goal is to keep threads from stepping on each other while still
allowing fast local iteration.

## Thread Ownership Matrix

- `Triage`
  - Primary owner: `plans/current-optimization-plan.md`
  - Default behavior: read-only on repo code and docs
- `Implementation`
  - Primary owner: `src/`, `tests/`, and only the minimum adjacent files
    required by the assigned task
- `Validation`
  - Primary owner: none
  - Default behavior: read-only verification only
- `Docs`
  - Primary owner: `README.md`, `docs/model.md`, `docs/architecture.md`,
    `docs/results/best-model-3y-backtest.md`
- `Workflow Meta`
  - `AGENTS.md`, `plans/thread-roles.md`, and `prompts/*.md` are off-limits
    during normal optimization work unless the task is explicitly a
    workflow-maintenance task assigned to one thread

## Worktree Rules

- Use one thread per git worktree.
- Each thread begins by running:

```bash
git rev-parse --show-toplevel
git branch --show-current
git status --short
```

- Each thread must declare its intended touch set before editing.
- If the intended files overlap another thread's reserved area, stop and hand
  off instead of editing.

## Normal Handoff Flow

- Triage defines or refines the task in `plans/current-optimization-plan.md`.
- Implementation changes code and adjacent tests.
- Validation runs independent checks and reports pass/fail without editing.
- Docs updates canonical docs and the tracked latest report only after behavior
  changes are real.
- Daily summary consolidates thread outputs. It does not drive code changes
  directly.

## Conflict Rules

- Implementation does not edit canonical docs except for tiny unblockers. Docs
  owns final doc updates.
- Validation never edits application code.
- Triage never edits application code.
- Docs never edits `src/`, `tests/`, `sql/`, or `chart/`.
