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
- `ODDS_API_KEY` is required for `ingest-odds` and `ingest-closing-odds`

Start Postgres in the local cluster and forward it:

```bash
helm upgrade --install cbb-upsets chart/cbb-upsets \
  -f chart/cbb-upsets/values.yaml \
  -f chart/cbb-upsets/values-local.yaml

kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default
```

Initialize or refresh the schema:

```bash
cbb init-db
```

## CLI

Inspect commands:

```bash
cbb --help
```

Load the default 3-year historical game backfill from ESPN:

```bash
cbb ingest-data
```

Backfill one year of historical closing moneylines from The Odds API:

```bash
cbb ingest-closing-odds
```

Limit a paid historical odds run to a small number of requests:

```bash
cbb ingest-closing-odds --max-snapshots 10
```

Load current odds and recent scores:

```bash
cbb ingest-odds
```

Inspect what is stored:

```bash
cbb db-summary
```

## Notes

- `ingest-data` skips completed date slices unless you pass `--force-refresh`
- `ingest-closing-odds` only targets completed games missing a stored closing line and checkpoints historical snapshot requests
- `ingest-odds` and `ingest-closing-odds` use API credits

## Test

```bash
make test
```
