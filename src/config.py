"""
src/config.py
Centralized configuration loaded from environment variables.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# Populate os.environ from a local .env (if present) BEFORE values are read.
# Must run at import time — the Config singleton below is built on import.
load_dotenv()


@dataclass(frozen=True)
class Config:
    telegram_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )
    omdb_api_key: str = field(
        default_factory=lambda: os.getenv("OMDB_API_KEY", "")
    )
    watchmode_api_key: str = field(
        default_factory=lambda: os.getenv("WATCHMODE_API_KEY", "")
    )
    db_file: str = field(
        default_factory=lambda: os.getenv("DB_FILE", "movies.db")
    )
    refresh_interval_seconds: int = field(
        default_factory=lambda: int(os.getenv("REFRESH_INTERVAL_SECONDS", str(7 * 24 * 60 * 60)))
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
    ollama_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:12b-it-qat")
    )
    host: str = field(
        default_factory=lambda: os.getenv("HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("PORT", "8000"))
    )
    watchmode_region: str = field(
        default_factory=lambda: os.getenv("WATCHMODE_REGION", "US")
    )

    def validate(self) -> None:
        """Raise ValueError if any required key is missing."""
        missing = []
        if not self.telegram_token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.omdb_api_key:
            missing.append("OMDB_API_KEY")
        if not self.watchmode_api_key:
            missing.append("WATCHMODE_API_KEY")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")


# Module-level singleton — import this everywhere
config = Config()
