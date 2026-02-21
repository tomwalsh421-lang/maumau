# CBB Upsets

A clean, reproducible pipeline for predicting NCAA men’s basketball upsets using Postgres, Python (Typer CLI), and Streamlit.

---

## 🧭 Architecture Overview

- **Clean modular Python package** (`src/cbb/`)
- **Postgres** houses all data (schema in `sql/schema.sql`)
- **Deterministic CLI** via `src/cbb/cli.py` (Typer)
- **Minimal dependencies**: see [`requirements.txt`](requirements.txt)
- **No scraping from restricted sources** — only official APIs and datasets

Agent prompt specs are found in [`prompts/`](prompts/) (see `prompts/architect_agent.md`, etc.).

---

## 🚀 Installation & Setup

1. **Install dependencies**
    ```bash
    pip install -r requirements.txt
    # Or, for editable dev setup:
    pip install -e .
    ```
    - Required: [Typer](https://typer.tiangolo.com), SQLAlchemy, psycopg2-binary, python-dotenv, streamlit, pytest

2. **Configure your environment**
    ```bash
    cp .env.example .env
    # Then edit .env with your DATABASE_URL, ODDS_API_KEY, etc.
    ```

3. **Initialize database schema**
    ```bash
    psql "$DATABASE_URL" -f sql/schema.sql
    ```

---

## 🏃 Running the CLI

```bash
python -m cbb.cli [command] [options]
```
Key commands:
- Ingest odds: `python -m cbb.cli ingest-odds --date YYYY-MM-DD`
- Compute metrics: `python -m cbb.cli compute-metrics --season 2026`
- Build features: `python -m cbb.cli build-features --season 2026`
- Train model: `python -m cbb.cli train --season 2026`
- Score games: `python -m cbb.cli score --date YYYY-MM-DD`
- Dashboard: `python -m cbb.cli dashboard`

---

## 🧪 Testing

- Tests go in `tests/`
- Run with `pytest` after installing requirements

## 🧭 Typer CLI template

- The package exposes a Typer CLI, so you can test individual pipeline stages with:
  ```bash
  python -m cbb.cli ingest-odds --date 2026-02-21
  python -m cbb.cli compute-metrics --season 2026
  python -m cbb.cli build-features --season 2026
  python -m cbb.cli train --season 2026
  python -m cbb.cli score --date 2026-02-21
  python -m cbb.cli dashboard
  ```
  Each command accepts the shared config from the `.env` file described above.

## 🚢 Helm deployment (local k3d/kind)

- This repo ships `chart/cbb-upsets`, which packages the nginx frontend plus Bitnami PostgreSQL and the ingress controller.
- Before deploying, make sure Helm knows the upstream repositories:
  ```bash
  helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
  helm repo add bitnami https://charts.bitnami.com/bitnami
  helm repo update
  helm dependency update chart/cbb-upsets
  ```
- Deploy into your local cluster (you can keep `values-local.yaml` next to `values.yaml` to override service types for this environment):
  ```bash
  helm upgrade --install cbb-upsets chart/cbb-upsets \
    -f chart/cbb-upsets/values.yaml \
    -f chart/cbb-upsets/values-local.yaml
  ```
- The chart now defaults to `ClusterIP` for the Postgres service; use `kubectl port-forward` before running `psql`. A tiny helper script lives in `scripts/test-postgres-forward.sh` if you want to check the connection quickly.

## ⛳ Postgres access (local)

- Port-forward the service:
  ```bash
  kubectl port-forward svc/cbb-upsets-postgresql 5432:5432 -n default &
  ```
- Connect with the values over that tunnel:
  ```bash
  PGPASSWORD=cbbpass psql -h 127.0.0.1 -p 5432 -U cbb -d cbb_upsets
  ```
- Once inside `psql` you can list tables with `\dt` (or use `\d` to describe relations).

---

## ⚙️ Kubernetes Dev Environment (Local, via k3d)

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

## 📝 Notes

- All config in `.env` and accessed via `src/cbb/config.py`
- See [`prompts/`](prompts/) for detailed agent roles/specs

---
