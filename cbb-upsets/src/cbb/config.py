from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    odds_api_key: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env and update it.")

    odds_api_key = os.getenv("ODDS_API_KEY", "").strip() or None
    return Settings(database_url=database_url, odds_api_key=odds_api_key)
