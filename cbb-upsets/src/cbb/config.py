from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    database_url: str
    odds_api_key: str | None = None
    odds_api_base_url: str = "https://api.the-odds-api.com/v4"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load and cache application settings from the environment.

    Returns:
        The resolved application settings.

    Raises:
        RuntimeError: If ``DATABASE_URL`` is not set.
    """
    load_dotenv()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and update it."
        )

    odds_api_key = os.getenv("ODDS_API_KEY", "").strip() or None
    odds_api_base_url = os.getenv(
        "ODDS_API_BASE_URL", "https://api.the-odds-api.com/v4"
    ).strip()
    return Settings(
        database_url=database_url,
        odds_api_key=odds_api_key,
        odds_api_base_url=odds_api_base_url,
    )
