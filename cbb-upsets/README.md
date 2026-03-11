# CBB Upsets

## Project Overview

CBB Upsets is a Python CLI for building and operating a college basketball
betting workflow against a local PostgreSQL database. It ingests NCAA men's
basketball results from ESPN, ingests current and historical odds from The Odds
API, stores both in Postgres, trains deployable moneyline and spread models,
backtests them walk-forward, and produces a live bet slip from the current
slate.

The supported production scope remains one sport: NCAA men's basketball. Model,
execution, and evaluation behavior are intentionally sport-specific rather than
generalized across leagues.

The major components are:

- a Typer-based CLI for database, ingest, and modeling workflows
- a PostgreSQL schema for teams, games, odds snapshots, and ingest checkpoints
- a modeling pipeline for feature generation, training, backtesting, and
  prediction
- a local Helm chart used to run PostgreSQL and supporting cluster services in
  Kubernetes

## Quick Start

This is the shortest realistic end-to-end path to first success for a new
engineer. It uses the moneyline market because that only requires one
historical odds backfill. The current deployable path is spread-only when a
spread artifact is available, but moneyline is still the fastest onboarding
path.

The commands below assume `source .venv/bin/activate`. If you do not want to
activate the environment, replace `cbb ...` with
`.venv/bin/python -m cbb.cli ...`.

Before you start, install the dependencies listed in
[Required Dependencies](#required-dependencies).

1. Create the virtualenv and local config.

```bash
make install
cp .env.example .env
source .venv/bin/activate
```

2. Create the local Kubernetes cluster.

```bash
make k8s-up
kubectl cluster-info
```

3. Deploy the Helm chart.

```bash
helm upgrade --install cbb-upsets chart/cbb-upsets \
  -f chart/cbb-upsets/values.yaml \
  -f chart/cbb-upsets/values-local.yaml

kubectl get pods
```

4. Forward PostgreSQL from the cluster.

```bash
kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default
```

5. Initialize the schema and verify the CLI can talk to the database.

```bash
cbb db init
cbb db summary
```

6. Load the minimum data needed for a first end-to-end model run.

These commands spend Odds API credits:

```bash
cbb ingest data --years-back 1
cbb ingest closing-odds --years-back 1 --market h2h
cbb ingest odds
```

7. Train a model artifact.

```bash
cbb model train --market moneyline --artifact-name quickstart
```

8. Run a prediction command.

```bash
cbb model predict --market moneyline --artifact-name quickstart
```

If the prediction command prints `No bets qualified under the current policy.`,
that still counts as a successful end-to-end run. It means the pipeline worked
and the current slate did not clear the betting thresholds.

To move from onboarding to the current deployable path, add historical spread
odds and then use `best`:

```bash
cbb ingest closing-odds --years-back 1 --market spreads
cbb model train --market spread --artifact-name latest
cbb model predict --market best --artifact-name latest
cbb model predict --market best --artifact-name latest --output-format json
```

That default `best` path now uses the fixed deployable spread policy. The older
spread auto-tuning path is still available with `--auto-tune-spread-policy` for
research comparisons. The fixed deployable spread path also includes a small
rest-gap quality guard, so unusual schedule spots are filtered before staking.
The current fixed spread baseline is intentionally tighter than the earlier
version: it now requires more established teams and larger model-vs-market
agreement before a bet qualifies.
`model predict` now returns one deterministic decision per upcoming game in the
live path: `bet`, `wait`, or `pass`. Text output remains human-readable, while
`--output-format json` emits the canonical `predict.v1` payload with sportsbook,
cross-book survivability, freshness, and min-acceptable execution bounds.
For cross-book execution research, `model backtest`, `model predict`, and
`model report` now also support survivability controls such as
`--min-positive-ev-books` and `--min-median-expected-value`. Those controls are
intended for research comparisons, not the default deployable path.
The opt-in auto-tuned path now ranks spread policies by walk-forward profit
first, but only promotes them when their out-of-sample spread closing EV stays
non-negative.
For spread research, `--use-timing-layer` adds an opt-in closing-line filter:
it only keeps early spread bets when the auxiliary timing model expects the
market to move in your favor, and otherwise surfaces them as a wait list.

## Documentation

- Model documentation: [docs/model.md](docs/model.md)
- System architecture: [docs/architecture.md](docs/architecture.md)
- Current deployable results: [docs/results/best-model-3y-backtest.md](docs/results/best-model-3y-backtest.md)

The README, [docs/model.md](docs/model.md), and
[docs/architecture.md](docs/architecture.md) describe the durable system. The
generated report in `docs/results/` is where current tuned performance and
season-by-season results belong.

One durable modeling detail worth knowing up front: the deployable spread path
is no longer trained as a raw cover/no-cover classifier. The default
`--model-family logistic` spread path now predicts expected margin relative to
the market spread, converts that estimate into cover probability, and then
calibrates it against held-out priced examples.

## Local Development Setup

This repository assumes local development happens against Kubernetes running on
your machine. The normal path is:

1. create a local `k3d` cluster
2. deploy the Helm chart, which includes PostgreSQL
3. port-forward PostgreSQL to `127.0.0.1:5432`
4. run the CLI locally from a Python virtualenv

The CLI is the primary application interface. Most workflows, including ingest,
training, backtesting, prediction, audit, and backup, run from your shell
against the forwarded local Postgres instance.

Copy `.env.example` to `.env` before running the CLI. The required settings are:

- `DATABASE_URL`: SQLAlchemy Postgres URL for the forwarded local database
- `ODDS_API_KEY`: required for current and historical odds ingest
- `ODDS_API_BASE_URL`: defaults to The Odds API v4 base URL

## Required Dependencies

- Docker: container runtime used by `k3d` to run the local Kubernetes cluster.
  Recommended install: Docker Desktop on macOS or Windows, Docker Engine on
  Linux.
- `k3d`: local Kubernetes cluster manager used by `make k8s-up`. Recommended
  install: `brew install k3d` or the official `k3d` release binary.
- `kubectl`: used to inspect the cluster and port-forward PostgreSQL.
  Recommended install: `brew install kubectl`.
- Helm 3: used to deploy `chart/cbb-upsets`. Recommended install:
  `brew install helm`.
- Python 3.11+: used for the CLI, ingest code, and modeling pipeline.
  Recommended install: `pyenv` or `brew install python@3.11`.
- Make: used for local workflow shortcuts such as `make install`,
  `make k8s-up`, and `make check`. Recommended install: Xcode Command Line Tools
  on macOS or your system package manager on Linux.
- PostgreSQL client tools: used by `cbb db backup` and `cbb db import`.
  Recommended install: `brew install libpq` or `brew install postgresql@16`.
- An Odds API account and API key: used by `cbb ingest odds` and
  `cbb ingest closing-odds`.

## Running the System Locally

1. Create the Python environment and local config.

```bash
make install
cp .env.example .env
source .venv/bin/activate
```

2. Start the local Kubernetes cluster.

```bash
make k8s-up
kubectl cluster-info
```

3. Deploy the local services. This starts PostgreSQL in the cluster and applies
   the chart's supporting resources.

```bash
helm upgrade --install cbb-upsets chart/cbb-upsets \
  -f chart/cbb-upsets/values.yaml \
  -f chart/cbb-upsets/values-local.yaml

kubectl get pods
```

4. Forward PostgreSQL from the cluster to your local shell and point
   `DATABASE_URL` at it. The default local chart values use database
   `cbb_upsets`, user `cbb`, and password `cbbpass`.

```bash
kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default
```

Example `.env` value:

```bash
DATABASE_URL=postgresql+psycopg2://cbb:cbbpass@127.0.0.1:5432/cbb_upsets
```

5. Initialize the schema and seed the canonical Division I team catalog.

```bash
cbb db init
```

6. Run the application workflows from the CLI.

```bash
cbb db summary
cbb ingest data --years-back 3
cbb ingest closing-odds --years-back 3 --market h2h
cbb ingest closing-odds --years-back 3 --market spreads
cbb ingest odds
cbb model train --market spread --artifact-name latest
cbb model backtest --market best
cbb model report
cbb model report recent --days 7
cbb model predict --market best --artifact-name latest
```

The two Odds API commands above spend credits. The generated three-season
performance summary is tracked separately in
`docs/results/best-model-3y-backtest.md`.

Use `make check` for the standard local verification path:

```bash
make check
```

## CLI Overview

- `cbb db init`: initialize `sql/schema.sql` and seed the canonical D1 team
  catalog.

```bash
cbb db init
```

- `cbb db summary`: show counts, date range, and stored sample rows from the
  current database.

```bash
cbb db summary
```

- `cbb db audit`: verify stored games against ESPN coverage and final scores.

```bash
cbb db audit --years-back 3
```

- `cbb db backup`: create a repo-local SQL dump under `backups/`.

```bash
cbb db backup --name audited_snapshot.sql
```

- `cbb db import`: replace the configured database with a saved SQL dump.

```bash
cbb db import audited_snapshot.sql
```

- `cbb db view team`: inspect one team's recent results and any current or
  upcoming games. When there is an upcoming matchup and live model artifacts
  are available, the command also prints the current model lean, confidence,
  and edge for that game. By default it refreshes current odds and recent
  scores first; add `--no-refresh-stats` to read the stored DB state without
  spending Odds API credits.

```bash
cbb db view team "Duke Blue Devils"
```

- `cbb db view upcoming`: show in-progress and upcoming games from the local
  database. Like `db view team`, it refreshes live odds and recent scores by
  default; add `--no-refresh-stats` to skip that refresh.

```bash
cbb db view upcoming --limit 10
```

- `cbb ingest data`: backfill historical ESPN game results.

```bash
cbb ingest data --years-back 3
```

- `cbb ingest odds`: ingest current odds and optional recent scores from The
  Odds API.

```bash
cbb ingest odds --sport basketball_ncaab
```

- `cbb ingest closing-odds`: backfill historical closing odds from The Odds
  API. The default path only requests snapshot times for games still missing a
  closing line and skips snapshot times already checkpointed. Use
  `--ignore-checkpoints` for recent repair windows when you want to revisit
  checkpointed missing-close slots without widening to every completed game in
  the date range.

```bash
cbb ingest closing-odds --years-back 3 --market h2h
```

- `cbb model train`: train a moneyline or spread artifact from the loaded
  seasons. The default deployable spread artifact uses the `logistic` family
  flag for a margin-versus-market residual model. Use
  `--model-family hist_gradient_boosting` for the research-only spread
  challenger.

```bash
cbb model train --market spread --artifact-name audited_backfill_v5
```

- `cbb model backtest`: run a walk-forward bankroll backtest. The default
  deployable `best` and `spread` paths now use the fixed searched spread
  policy; use `--auto-tune-spread-policy` only when you want the research
  walk-forward tuner. Use `--spread-model-family hist_gradient_boosting` to
  compare the tree-based spread challenger against the deployable default
  `logistic` spread path.

```bash
cbb model backtest --market best --evaluation-season 2026
```

- `cbb model report`: backtest the current deployable `best` model over the
  last loaded seasons, refresh the tracked latest report under `docs/results/`,
  and write a timestamped history copy under `docs/results/history/`. The
  default report uses the fixed deployable spread policy; use
  `--auto-tune-spread-policy` when you want the research auto-tuned version.
  Use `--spread-model-family ...` when you want a non-default spread-family
  report. The report now also tracks closing-line value, including spread line
  movement, spread price/no-vig close deltas, and spread closing EV, so
  strategies that win short-run ROI but do not beat the close are visible
  before promotion.

```bash
cbb model report
```

- `cbb model report recent`: run the current walk-forward backtest settings and
  print the most recent simulated settled bets, anchored to the latest bet in
  the evaluation window. This is the quickest way to inspect what the model
  would recently have bet without rewriting the canonical Markdown report.
  Default text output uses the same compact slip style as `model predict`;
  add `--verbose` for the full field-level diagnostics.

```bash
cbb model report recent --days 7
```

- `cbb model predict`: load trained artifacts, score the current slate, and
  emit one deterministic decision per upcoming game. The default text output
  prints the summary header, applied policy, risk guardrails, bet slip, wait
  list, and optional upcoming-game table. Add `--output-format json` for the
  canonical machine interface, and `--show-upcoming-games` to render one best
  angle per game in text mode. The default deployable spread path requires
  positive EV to survive at multiple books before it will take the best
  executable quote, and live output includes sportsbook, coverage, freshness,
  and uncertainty-disclosure context. Bet-slip rows also begin with an explicit
  `bet=...` instruction so the action to place is obvious before the metrics.

```bash
cbb model predict --market best --artifact-name audited_backfill_v5
```
