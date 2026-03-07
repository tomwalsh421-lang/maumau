# CBB Upsets

Small CLI for loading NCAA men's basketball data into Postgres.

## What is here

- PostgreSQL schema in `sql/schema.sql`
- Typer CLI in `src/cbb/cli.py`
- Historical game ingest from ESPN scoreboard
- Current odds ingest from The Odds API
- Local Kubernetes chart for Postgres under `chart/cbb-upsets`

## Prerequisites

- Python 3.11+
- Helm
- kubectl
- A running local Kubernetes cluster

## Setup

```bash
make install
cp .env.example .env
```

Update `.env`:

- `DATABASE_URL` should point at your forwarded local Postgres
- `ODDS_API_KEY` is only required for `ingest-odds`

Bring up Postgres and forward it locally:

```bash
helm upgrade --install cbb-upsets chart/cbb-upsets \
  -f chart/cbb-upsets/values.yaml \
  -f chart/cbb-upsets/values-local.yaml

kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default
```

Initialize the schema:

```bash
.venv/bin/cbb init-db
```

## CLI

Show commands:

```bash
.venv/bin/cbb --help
```

Load the default 3-year historical backfill:

```bash
.venv/bin/cbb ingest-data
```

Load a smaller historical slice:

```bash
.venv/bin/cbb ingest-data --years-back 1
```

Load current odds and recent scores:

```bash
.venv/bin/cbb ingest-odds
```

Inspect what is stored:

```bash
.venv/bin/cbb db-summary
```

## Notes

- `ingest-data` skips dates that were already completed unless you pass `--force-refresh`
- `ingest-odds` uses API credits; `ingest-data` does not

## Test

```bash
make test
```
