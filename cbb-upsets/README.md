# CBB Upsets

CLI for loading NCAA men's basketball game data and odds into Postgres.

## Prerequisites

- Python 3.11+
- Helm
- kubectl
- A running local Kubernetes cluster

## Setup

Create the virtualenv, install the package, and activate it:

```bash
make install
source .venv/bin/activate
cp .env.example .env
```

`make install` creates `.venv`. After activation, the CLI is available as `cbb`.
Without activation, use `.venv/bin/cbb`.

Update `.env`:

- `DATABASE_URL` should point at your forwarded local Postgres
- `ODDS_API_KEY` is required for `cbb ingest odds` and
  `cbb ingest closing-odds`

Start Postgres in the local cluster and forward it:

```bash
helm upgrade --install cbb-upsets chart/cbb-upsets \
  -f chart/cbb-upsets/values.yaml \
  -f chart/cbb-upsets/values-local.yaml

kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default
```

Initialize or refresh the schema:

```bash
cbb db init
```

`db init` also seeds the canonical men's D1 team directory used to filter non-D1
opponents and normalize provider name variants.

## CLI

Inspect commands:

```bash
cbb --help
```

Load the default 3-year historical game backfill from ESPN:

```bash
cbb ingest data
```

Backfill one year of historical closing moneylines from The Odds API:

```bash
cbb ingest closing-odds
```

Limit a paid historical odds run to a small number of requests:

```bash
cbb ingest closing-odds --max-snapshots 10
```

Load current odds and recent scores:

```bash
cbb ingest odds
```

Train the baseline moneyline model on the last three loaded seasons:

```bash
cbb model train
```

The deployable moneyline model trains only on completed games with stored
pregame prices. The full game history is still used to build rolling team form
and Elo state.

Backtest the current strategy on the latest loaded season:

```bash
cbb model backtest
```

Rank the current best bets from the trained artifacts:

```bash
cbb model predict
```

Implementation notes for the current model stack are in
`docs/model-implementation.md`.

Inspect what is stored:

```bash
cbb db summary
```

Create a repo-local SQL backup under `backups/`:

```bash
cbb db backup
```

Import a saved SQL backup back into the configured database:

```bash
cbb db import cbb_upsets_20260308_120000.sql
```

View one team's five most recent completed games:

```bash
cbb db view team "Duke Blue Devils"
```

View current in-progress and upcoming games:

```bash
cbb db view upcoming
```

Verify stored games against ESPN event IDs and final scores:

```bash
cbb db audit --start-date 2025-11-01 --end-date 2025-11-30
```

## Notes

- `cbb ingest data` skips completed date slices unless you pass
  `--force-refresh`
- `cbb ingest data` and `cbb ingest odds` skip games that do not resolve to a
  canonical D1 team pair
- `cbb ingest closing-odds` only targets completed games missing a stored
  closing line and checkpoints historical snapshot requests
- `cbb model train` writes JSON artifacts under `artifacts/models/`, which is
  gitignored, and any named train also refreshes the default `latest` artifact
- `cbb model predict` requires a trained artifact and current odds from
  `cbb ingest odds`
- the default model policy is intentionally conservative and may return no bets
  when the stored pricing history does not justify action
- `cbb db backup` writes plain SQL dumps to `backups/`, which is gitignored
- `cbb db import` replaces the configured database contents with a saved SQL
  dump
- `cbb db view team` accepts an exact team name or alias, and suggests nearby
  names when it cannot resolve one
- `db audit` is read-only and uses ESPN requests, not paid Odds API credits
- `cbb ingest odds` and `cbb ingest closing-odds` use API credits

## Test

```bash
make check
```
