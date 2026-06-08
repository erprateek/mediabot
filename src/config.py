"""
src/config.py
Centralized configuration loaded from environment variables.
"""

import os
from dataclasses import dataclass, field


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
