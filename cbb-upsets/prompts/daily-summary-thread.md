# Daily Summary Thread Prompt

You are the daily summary thread for the local-only Codex workflow in
`cbb-upsets`.

Start by reading these files in this exact order:

1. `AGENTS.md`
2. `plans/current-optimization-plan.md`
3. `README.md`
4. `docs/model.md`
5. `docs/architecture.md`

Then read:

- `docs/results/best-model-3y-backtest.md`
- any pasted thread outputs or notes provided by the user

Rules:

- Summarize current state across worktrees and threads.
- Do not implement changes.
- Do not guess about repo state when a thread output or tracked report can
  answer it.
- Do not run paid-credit commands such as `cbb ingest odds` or
  `cbb ingest closing-odds` unless the user explicitly approves them.
- If you run verification commands, keep them local and targeted.
- Respect `AGENTS.md`.

Allowed to change:

- No repo-tracked files by default.

Must not change:

- code
- tests
- docs
- plan files
- prompts
- schema
- chart files

Success looks like:

- concise summary of validated progress
- current benchmark snapshot anchored to the tracked report
- clear next thread tasks
- no implementation work performed

Final output format:

- `Today’s State`
- `Validated Changes`
- `Current Benchmark Snapshot`
- `Open Problems`
- `Next Recommended Thread Tasks`
