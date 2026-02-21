# CBB Upsets

Predict NCAA men’s basketball upsets with a clean, reproducible, PyPostgres-backed pipeline.

---

## 📦 Structure

All code lives in `src/cbb/`, following strict module boundaries:
- `odds/` – Odds ingestion and normalization (provider interface)
- `metrics/` – Team metrics
- `features/` – Feature assembly for modeling
- `model/` – Training, scoring, model artifacts
- `app/` – Dashboard UI (Streamlit)
- `db.py` – DB connection/utilities
- `config.py` – Load config/env
- `cli.py` – Typer CLI orchestrator

SQL schema: [`sql/schema.sql`](sql/schema.sql) runs on Postgres.

---

## 🚦 Quickstart

1. **Install dependencies**
