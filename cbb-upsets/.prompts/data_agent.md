You are the Data Agent.

Task: implement NCAA men’s basketball odds ingestion from The Odds API (or a stub provider interface if API key not present).

Requirements:
- Provider interface: fetch_games(date) -> list[GameOdds]
- Normalize team names consistently
- Store snapshots in Postgres with timestamps
- Idempotent inserts (avoid duplicates)
- Write unit-testable code (pure functions for mapping)
- Include a CLI command: cbb ingest-odds --date YYYY-MM-DD
Return: code changes + schema changes (sql) + sample .env.example entries.
