# Current Optimization Plan: Spread Deployability

## Current State

The canonical benchmark for this cycle is
[docs/results/best-model-3y-backtest.md](/Users/tomwalsh/git/maumau/cbb-upsets/docs/results/best-model-3y-backtest.md).

Current tracked baseline:

- `2024`: `89` bets, `-$26.24`, `ROI -8.52%`
- `2025`: `119` bets, `-$34.23`, `ROI -4.22%`
- `2026`: `104` bets, `-$12.92`, `ROI -3.92%`
- Aggregate: `312` bets, `-$73.39`, `ROI -5.07%`

## Current Bottleneck

- Spread deployability remains inconsistent and unprofitable across seasons.
- Inactivity must never be treated as tuner success.
- `best` remains spread-first. Moneyline is secondary until spread is robust.

## Top Priority

- Stabilize and validate spread tuner activity constraints.
- Stabilize and validate margin-vs-market spread modeling.

## Allowed Next Tasks

- Refine the spread tuner objective and activity floors.
- Refine spread residual-to-probability calibration.
- Add spread feature improvements supported by the existing schema.
- Keep backtest, predict, and report behavior aligned.
- Add or tighten targeted tests for tuning, calibration, artifact
  compatibility, and reporting behavior.

## Blocked / Forbidden Tasks

- Do not add another classifier family.
- Do not widen moneyline scope yet.
- Do not run paid Odds API ingest commands unless the user explicitly approves
  them.
- Do not reinterpret schema or artifact semantics without explicit need.
- Do not add cloud-specific workflow assumptions.

## Success Metrics

- `cbb model report` shows no zero-bet seasons.
- Aggregate ROI improves versus the tracked baseline above.
- Per-season drawdown does not regress materially.
- `model backtest`, `model predict`, and `model report` remain aligned.

## Benchmark Commands

```bash
cbb model backtest --market spread --evaluation-season 2024 --auto-tune-spread-policy
cbb model backtest --market spread --evaluation-season 2025 --auto-tune-spread-policy
cbb model backtest --market spread --evaluation-season 2026 --auto-tune-spread-policy
cbb model report
```

## Validation Commands

```bash
./.venv/bin/python -m pytest -q tests/test_modeling.py tests/test_report.py tests/test_cli.py
./.venv/bin/python -m ruff check src tests
./.venv/bin/python -m mypy
```

## Rollback Criteria

- A change reintroduces any zero-bet season.
- Tracked aggregate ROI worsens without a documented per-season tradeoff.
- `model predict`, `model backtest`, and `model report` drift out of alignment.
- The change requires paid-credit commands to evaluate safely.

## Paid-Credit Restrictions

Forbidden without explicit approval:

- `cbb ingest odds`
- `cbb ingest closing-odds`

Safe local evaluation commands include:

- `cbb model backtest`
- `cbb model report`
- local tests, lint, typecheck, and read-only inspection commands
