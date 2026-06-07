"""
tests/unit/test_handlers.py
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers import _parse_watch_text, BotHandlers
from src.services.omdb import MediaMeta


# ------------------------------------------------------------------ #
# Pure function tests                                                  #
# ------------------------------------------------------------------ #

class TestParseWatchText:
    def test_title_with_rating(self):
        title, rating = _parse_watch_text("The Batman - 8.4/10")
        assert title == "The Batman"
        assert rating == "8.4/10"

    def test_title_only(self):
        title, rating = _parse_watch_text("Dune")
        assert title == "Dune"
        assert rating == "No Rating"

    def test_integer_rating(self):
        title, rating = _parse_watch_text("Interstellar - 9/10")
        assert rating == "9/10"

    def test_extra_spaces(self):
        title, rating = _parse_watch_text("  Oppenheimer  -  8/10  ")
        assert title == "Oppenheimer"
        assert rating == "8/10"


# ------------------------------------------------------------------ #
# Handler command tests                                                #
# ------------------------------------------------------------------ #

def _make_update(text: str, user: str = "Alice") -> MagicMock:
    update = MagicMock()
    update.message.from_user.first_name = user
    update.message.reply_text = AsyncMock()
    update.message.reply_photo = AsyncMock()
    return update


def _make_context(*args: str) -> MagicMock:
    ctx = MagicMock()
    ctx.args = list(args)
    return ctx


def _make_handlers(db, omdb_meta=None, platforms="📺 Stream on: Netflix") -> BotHandlers:
    omdb = MagicMock()
    omdb.fetch.return_value = omdb_meta or MediaMeta(
        content_type="movie",
        poster="https://example.com/poster.jpg",
        title="The Batman",
        imdb_id="tt1877830",
    )
    watchmode = MagicMock()
    watchmode.fetch_platforms.return_value = platforms
    return BotHandlers(db=db, omdb=omdb, watchmode=watchmode)


class TestWatchCommand:
    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self, tmp_db):
        h = _make_handlers(tmp_db)
        update = _make_update("")
        await h.watch(update, _make_context())
        update.message.reply_text.assert_called_once()
        assert "Format:" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_new_entry_saved_with_poster(self, tmp_db):
        h = _make_handlers(tmp_db)
        update = _make_update("The Batman - 8.4/10")
        await h.watch(update, _make_context("The", "Batman", "-", "8.4/10"))
        update.message.reply_photo.assert_called_once()
        assert tmp_db.find_by_title("The Batman") is not None

    @pytest.mark.asyncio
    async def test_duplicate_shows_warning(self, tmp_db):
        h = _make_handlers(tmp_db)
        ctx = _make_context("The", "Batman", "-", "8.4/10")
        # First save
        await h.watch(_make_update(""), ctx)
        # Duplicate attempt
        update2 = _make_update("")
        await h.watch(update2, ctx)
        update2.message.reply_text.assert_called_once()
        assert "already on the dashboard" in update2.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_no_poster_falls_back_to_text(self, tmp_db):
        meta = MediaMeta(content_type="movie", poster="", title="Silent Film", imdb_id="tt0000001")
        h = _make_handlers(tmp_db, omdb_meta=meta)
        update = _make_update("")
        await h.watch(update, _make_context("Silent", "Film"))
        update.message.reply_text.assert_called_once()
        update.message.reply_photo.assert_not_called()
