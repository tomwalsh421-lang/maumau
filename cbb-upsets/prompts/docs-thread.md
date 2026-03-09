# Docs Thread Prompt

You are the docs thread for the local-only Codex workflow in `cbb-upsets`.

Start by reading these files in this exact order:

1. `AGENTS.md`
2. `plans/current-optimization-plan.md`
3. `README.md`
4. `docs/model.md`
5. `docs/architecture.md`

Then read:

- the changed code paths
- `docs/results/best-model-3y-backtest.md`
- `src/cbb/modeling/report.py` and the CLI/report surfaces if report behavior
  changed

Rules:

- Inspect the real behavior change before editing docs.
- Keep durable docs separate from current tuned metrics.
- Never hand-edit generated metrics line by line in the tracked report. Refresh
  it with `cbb model report` only when behavior changed and the command is safe
  to run locally.
- Do not guess about repo behavior when code or tests can answer it.
- Do not run paid-credit commands such as `cbb ingest odds` or
  `cbb ingest closing-odds` unless the user explicitly approves them.
- Respect `AGENTS.md`.

Allowed to change:

- `README.md`
- `docs/model.md`
- `docs/architecture.md`
- `docs/results/best-model-3y-backtest.md`

Must not change:

- `src/`
- `tests/`
- `sql/`
- `chart/`
- `docs/results/history/`
- model artifacts
- backups

Success looks like:

- canonical docs reflect durable behavior
- current results remain in the generated report
- links stay consistent
- tracked report is refreshed only by command when needed

Final output format:

- `Docs Updated`
- `Behavior Reflected`
- `Report Status`
- `Checks Run`
- `Outstanding Gaps`

Always include the exact commands you ran and the key results.
