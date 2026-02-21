# CBB Upsets

A clean, reproducible pipeline for predicting NCAA men’s basketball upsets using Postgres, Python (Typer CLI), and Streamlit.

---

## 🏗️ Architectural Principles

- **Modular repo structure** for maintainability
- **Deterministic CLI**: every step is reproducible
- **Postgres** as the source of truth
- **Minimal dependencies**; easy setup
- **No forbidden scraping**: official APIs and datasets are preferred

These principles and module boundaries are fully described in [`PROMPTS.md`](PROMPTS.md).

---

## 📁 Repository Structure

```plaintext
.
├── README.md
├── pyproject.toml / requirements.txt
├── .env.example                  # List of required config variables
├── sql/
│   └── schema.sql                # Postgres schema
└── src/
    └── cbb/
        ├── __init__.py
        ├── config.py             # Config loader (from .env)
        ├── db.py                 # PostgreSQL interface
        ├── odds/
        │   ├── __init__.py
        │   └── odds_api.py       # Odds ingestion/provider interface
        ├── metrics/
        │   ├── __init__.py
        │   └── team_metrics.py   # Team metrics assembly
        ├── features/
        │   ├── __init__.py
        │   └── build_features.py # Model-ready feature assembly
        ├── model/
        │   ├── __init__.py
        │   ├── train.py          # Training baseline model
        │   └── predict.py        # Scoring with baseline model
        ├── cli.py                # Main Typer CLI orchestrator
        └── app/
            └── dashboard.py      # Streamlit dashboard
```

---

## ⚡ Setup & Installation

1. **Clone the repo and install dependencies**
    ```bash
    git clone https://github.com/your-org/cbb-upsets.git
    cd cbb-upsets
    pip install -e .
    ```
    Or use:
    ```bash
    pip install -r requirements.txt
    ```

2. **Configure your environment**
    - Copy `.env.example` to `.env` and fill out values:
        ```dotenv
        DATABASE_URL=postgresql://user:password@localhost:5432/cbb_upsets
        ODDS_API_KEY=your_odds_api_key   # Leave blank for stub provider
        ```
    - (Optional) Set `PYTHONPATH` if running from project root:
        ```bash
        export PYTHONPATH=src
        ```

3. **Initialize the database**
    ```bash
    psql \"$DATABASE_URL\" -f sql/schema.sql
    ```

---

## 🚦 Command Line Pipeline

All core functionality is accessible via the CLI:

```bash
python -m cbb.cli [COMMAND] [OPTIONS]
```

### Ingest odds for a date

```bash
python -m cbb.cli ingest-odds --date YYYY-MM-DD
```

### Compute team metrics

```bash
python -m cbb.cli compute-metrics --season 2026
```

### Build features

```bash
python -m cbb.cli build-features --season 2026
```

### Train the baseline model

```bash
python -m cbb.cli train --season 2026
```

### Score games for a date

```bash
python -m cbb.cli score --date YYYY-MM-DD
```

### Launch the Streamlit dashboard

```bash
python -m cbb.cli dashboard
```

See each command’s help for usage/options:

```bash
python -m cbb.cli --help
python -m cbb.cli ingest-odds --help
```

---

## 🧪 Testing

- Place tests in `tests/` and run with:
    ```bash
    pytest
    ```
- Use pure functions and dependency injection for maximal unit-testability (mock DB and I/O).
- Data layer is instrumented for idempotency and repeatable ML runs.

---

## 🔗 Additional Notes

- All config via `.env` and loaded in Python via `config.py` (never hardcoded secrets).
- All major agent and pipeline design details are specified in [`PROMPTS.md`](PROMPTS.md).
- Pull requests must respect idempotency, reproducibility, and minimal-dependency requirements of MVP.

---