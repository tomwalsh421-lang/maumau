# CBB Upsets

A reproducible NCAA men’s basketball upset-prediction scaffold using Postgres, Python (Typer CLI), and a local Helm chart.

---

## Architecture Overview

- **Clean modular Python package** (`src/cbb/`)
- **Postgres** houses all data (schema in `sql/schema.sql`)
- **Deterministic CLI** via `src/cbb/cli.py` (Typer)
- **Editable install** via `pyproject.toml`
- **Local Kubernetes chart** under `chart/cbb-upsets`

---

## Installation & Setup

1. **Install dependencies**
    ```bash
    make install
    source .venv/bin/activate
    ```

2. **Configure your environment**
    ```bash
    cp .env.example .env
    # Then edit .env if you are not using the default local Postgres tunnel
    ```

3. **Bring up Postgres locally**
    ```bash
    helm upgrade --install cbb-upsets chart/cbb-upsets \
      -f chart/cbb-upsets/values.yaml \
      -f chart/cbb-upsets/values-local.yaml

    kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default
    ```

4. **Initialize the schema**
    ```bash
    cbb init-db
    ```

## Running the CLI

Use either `cbb ...` in an activated virtualenv or `.venv/bin/cbb ...` directly.

Implemented commands:
- `cbb init-db`
- `cbb compute-metrics 2026`

Scaffolded but still placeholder commands:
- `cbb ingest-odds 2026`
- `cbb build-features 2026`
- `cbb train 2026`
- `cbb predict 2026 --games games.csv`
- `cbb dashboard`

---

## Testing

```bash
make test
```

## Helm Deployment

- This repo ships `chart/cbb-upsets`, which packages a simple nginx deployment plus Bitnami PostgreSQL and the ingress controller.
- Before deploying, make sure Helm knows the upstream repositories:
  ```bash
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
  helm repo add bitnami https://charts.bitnami.com/bitnami
  helm repo update
  helm dependency update chart/cbb-upsets
  ```
- Deploy into your local cluster (you can keep `values-local.yaml` next to `values.yaml` to override service types for this environment):
  ```bash
  make helm-template
  make helm-lint
  ```
- The application service is `NodePort` by default and the Postgres service is `ClusterIP`.
- The nginx service name renders as `<release>-cbb-upsets-nginx`.
- A small helper script lives in `scripts/test-postgres-forward.sh` if you want to check Postgres connectivity quickly.

## Postgres Access

```bash
kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default &
PGPASSWORD=cbbpass psql -h 127.0.0.1 -p 5432 -U cbb -d cbb_upsets
```

---

## Kubernetes Dev Environment

You can use [k3d](https://k3d.io/) for a fast local Kubernetes cluster in Docker on macOS.

### Prerequisites
- [Homebrew](https://brew.sh/) for package management
- Docker Desktop for Mac (running)

### Install tools
```bash
brew install k3d kubectl helm
```

### Local cluster setup/teardown/ingress

```bash
# Create cluster, 2 agents, 1 server, LoadBalancer
make k8s-up

# Check cluster status
make k8s-status

# Tear down cluster
make k8s-down

# Deploy NGINX ingress controller
make ingress-up
```

### Troubleshooting

- Make sure Docker Desktop is running before using k3d.
- If ports 8080/8443 are unavailable, edit them in the Makefile.
- Use `k3d cluster list` and `kubectl get nodes/pods` to inspect state.
- For networking issues and advanced usage, see [k3d FAQ](https://k3d.io/docs/faq/faq/).

---

## Notes

- Runtime config is read from `.env` via `src/cbb/config.py`
- The currently implemented pipeline stage is `compute-metrics`, which derives team win percentages from completed games and upserts them into `team_metrics`
- Prompt specs live in `.prompts/`

---
