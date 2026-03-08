# CBB Upsets

## Project Overview

CBB Upsets is a Python CLI for building and operating a college basketball
betting workflow against a local PostgreSQL database. It ingests NCAA men's
basketball results from ESPN, ingests current and historical odds from The Odds
API, stores both in Postgres, trains deployable moneyline and spread models,
backtests them walk-forward, and produces a live bet slip from the current
slate.

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
historical odds backfill. The current deployable path is still spread-first,
but moneyline is the fastest onboarding path.

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
```

## Documentation

- Model documentation: [docs/model.md](docs/model.md)
- System architecture: [docs/architecture.md](docs/architecture.md)
- Current deployable results: [docs/results/best-model-3y-backtest.md](docs/results/best-model-3y-backtest.md)

The README, [docs/model.md](docs/model.md), and
[docs/architecture.md](docs/architecture.md) describe the durable system. The
generated report in `docs/results/` is where current tuned performance and
season-by-season results belong.

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
cbb model backtest --market best --auto-tune-spread-policy
cbb model report
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
  upcoming games.

```bash
cbb db view team "Duke Blue Devils"
```

- `cbb db view upcoming`: show in-progress and upcoming games from the local
  database.

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
  API.

```bash
cbb ingest closing-odds --years-back 3 --market h2h
```

- `cbb model train`: train a moneyline or spread artifact from the loaded
  seasons. Use `--model-family hist_gradient_boosting` for the spread
  challenger.

```bash
cbb model train --market spread --artifact-name audited_backfill_v5
```

- `cbb model backtest`: run a walk-forward bankroll backtest. Use
  `--spread-model-family hist_gradient_boosting` to compare the tree-based
  spread challenger against the deployable logistic default.

```bash
cbb model backtest --market best --evaluation-season 2026 --auto-tune-spread-policy
```

- `cbb model report`: backtest the current deployable `best` model over the
  last loaded seasons, refresh the tracked latest report under `docs/results/`,
  and write a timestamped history copy under `docs/results/history/`. Use
  `--spread-model-family ...` when you want a non-default spread-family report.

```bash
cbb model report
```

- `cbb model predict`: load trained artifacts, score the current slate, and
  print a simplified bet slip.

```bash
cbb model predict --market best --artifact-name audited_backfill_v5
```
