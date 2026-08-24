"""
tests/unit/test_main_tasks.py
Covers refresh_all_platforms and Config parsing.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from main import refresh_all_platforms
from src.config import Config
from src.db.database import WatchEntry
from src.services.errors import ExternalAPIError


def _entry(title: str, imdb_id: str = "tt0000001") -> WatchEntry:
    return WatchEntry(
        user="Alice", title=title,
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        content_type="movie", poster="",
        imdb_id=imdb_id, platforms="old-platform", genres="",
    )


class TestRefreshAllPlatforms:
    async def test_updates_platforms(self, tmp_db):
        tmp_db.insert_entry(_entry("Dune"))
        watchmode = MagicMock()
        watchmode.fetch_platforms.return_value = "Netflix"

        await refresh_all_platforms(tmp_db, watchmode)

        assert tmp_db.all_entries()[0].platforms == "Netflix"

    @pytest.mark.parametrize("delay", [0])
    async def test_api_error_keeps_old_platforms(self, tmp_db, delay):
        tmp_db.insert_entry(_entry("Dune"))
        watchmode = MagicMock()
        watchmode.fetch_platforms.side_effect = ExternalAPIError("down")

        await refresh_all_platforms(tmp_db, watchmode)

        # Old data must NOT be overwritten with empty/failed results
        assert tmp_db.all_entries()[0].platforms == "old-platform"

    async def test_unexpected_error_is_isolated(self, tmp_db):
        tmp_db.insert_entry(_entry("Dune"))
        watchmode = MagicMock()
        watchmode.fetch_platforms.side_effect = RuntimeError("boom")

        # Should not raise; loop continues
        await refresh_all_platforms(tmp_db, watchmode)
        assert tmp_db.all_entries()[0].platforms == "old-platform"


class TestConfig:
    def test_defaults(self, monkeypatch):
        for var in ("TELEGRAM_BOT_TOKEN", "OMDB_API_KEY", "WATCHMODE_API_KEY",
                    "HOST", "PORT", "WATCHMODE_REGION"):
            monkeypatch.delenv(var, raising=False)
        cfg = Config()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 8000
        assert cfg.watchmode_region == "US"

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("HOST", "127.0.0.1")
        monkeypatch.setenv("PORT", "9001")
        monkeypatch.setenv("WATCHMODE_REGION", "GB")
        cfg = Config()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 9001
        assert cfg.watchmode_region == "GB"
