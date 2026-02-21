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
    psql \"$DATABASE_URL\" -f sql/schema.sql
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

---

## 📝 Notes

- All config in `.env` and accessed via `src/cbb/config.py`
- See [`prompts/`](prompts/) for detailed agent roles/specs

---