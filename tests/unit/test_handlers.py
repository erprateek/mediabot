"""
tests/unit/test_handlers.py
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.handlers import BotHandlers, _parse_rate_text
from src.services.ollama import ParsedWatch
from src.services.omdb import MediaMeta


class TestParseRateText:
    def test_title_with_decimal_score(self):
        title, score = _parse_rate_text("The Batman - 4.5")
        assert title == "The Batman"
        assert score == 4.5

    def test_title_with_integer_score(self):
        _, score = _parse_rate_text("Dune - 4")
        assert score == 4.0

    def test_score_clamped_to_5(self):
        _, score = _parse_rate_text("Movie - 9")
        assert score == 5.0

    def test_missing_score_returns_none(self):
        _, score = _parse_rate_text("Interstellar")
        assert score is None

    def test_score_out_of_ten_converted(self):
        title, score = _parse_rate_text("Lanterns 8.5/10")
        assert title == "Lanterns"
        assert score == 4.25

    def test_dash_with_slash_ten(self):
        title, score = _parse_rate_text("Dune - 9/10")
        assert title == "Dune"
        assert score == 4.5

    def test_score_out_of_five(self):
        title, score = _parse_rate_text("Movie 3/5")
        assert title == "Movie"
        assert score == 3.0

    def test_out_of_ten_clamped_to_5(self):
        _, score = _parse_rate_text("Best Movie Ever 11/10")
        assert score == 5.0


def _make_update(user="Alice"):
    update = MagicMock()
    update.message.from_user.first_name = user
    update.message.reply_text  = AsyncMock()
    update.message.reply_photo = AsyncMock()
    return update

def _make_context(*args):
    ctx = MagicMock()
    ctx.args = list(args)
    return ctx

def _make_handlers(db, omdb_meta=None, platforms="Netflix", parsed: ParsedWatch = None):
    omdb = MagicMock()
    omdb.fetch.return_value = omdb_meta or MediaMeta(
        content_type="movie", poster="https://example.com/p.jpg",
        title="The Batman", imdb_id="tt1877830", genres=["Action", "Crime"],
        plot="When a sadistic serial killer murders an elite family...",
        actors=["Robert Pattinson", "Zoë Kravitz"],
        director="Matt Reeves",
    )
    watchmode = MagicMock()
    watchmode.fetch_platforms.return_value = platforms
    ollama = MagicMock()
    ollama.parse_watch_message.return_value = parsed or ParsedWatch(
        title="The Batman", rating=None, comment=None
    )
    return BotHandlers(db=db, omdb=omdb, watchmode=watchmode, ollama=ollama)


class TestWatchCommand:
    @pytest.mark.asyncio
    async def test_no_args_shows_usage(self, tmp_db):
        h = _make_handlers(tmp_db)
        update = _make_update()
        await h.watch(update, _make_context())
        update.message.reply_text.assert_called()

    @pytest.mark.asyncio
    async def test_new_entry_saved(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update(), _make_context("The", "Batman"))
        assert tmp_db.find_by_title("The Batman") is not None

    @pytest.mark.asyncio
    async def test_genres_stored(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update(), _make_context("The", "Batman"))
        entry = tmp_db.find_by_title("The Batman")
        assert "Action" in entry.genres

    @pytest.mark.asyncio
    async def test_rating_upserted_when_parsed(self, tmp_db):
        parsed = ParsedWatch(title="The Batman", rating=4.5, comment=None)
        h = _make_handlers(tmp_db, parsed=parsed)
        await h.watch(_make_update("Alice"), _make_context("just", "watched", "batman", "4.5/5"))
        ratings = tmp_db.ratings_for_title("The Batman")
        assert len(ratings) == 1
        assert ratings[0].score == 4.5

    @pytest.mark.asyncio
    async def test_no_rating_when_not_parsed(self, tmp_db):
        parsed = ParsedWatch(title="The Batman", rating=None, comment=None)
        h = _make_handlers(tmp_db, parsed=parsed)
        await h.watch(_make_update(), _make_context("The", "Batman"))
        assert tmp_db.ratings_for_title("The Batman") == []

    @pytest.mark.asyncio
    async def test_duplicate_title_with_rating_upserts_only(self, tmp_db):
        h = _make_handlers(tmp_db, parsed=ParsedWatch("The Batman", None, None))
        await h.watch(_make_update(), _make_context("The", "Batman"))

        # Second user — same title but includes a rating
        h2 = _make_handlers(tmp_db, parsed=ParsedWatch("The Batman", 3.5, None))
        update2 = _make_update("Bob")
        await h2.watch(update2, _make_context("the", "batman", "3.5"))
        # Should NOT insert a duplicate entry
        assert len(tmp_db.all_entries()) == 1
        # Should have upserted the rating
        ratings = tmp_db.ratings_for_title("The Batman")
        assert any(r.user == "Bob" and r.score == 3.5 for r in ratings)

    @pytest.mark.asyncio
    async def test_duplicate_title_no_rating_prompts_rate(self, tmp_db):
        h = _make_handlers(tmp_db, parsed=ParsedWatch("The Batman", None, None))
        await h.watch(_make_update(), _make_context("The", "Batman"))
        update2 = _make_update("Bob")
        await h.watch(update2, _make_context("The", "Batman"))
        update2.message.reply_text.assert_called()
        call_text = update2.message.reply_text.call_args[0][0]
        assert "rate" in call_text.lower()

    @pytest.mark.asyncio
    async def test_no_poster_falls_back_to_text(self, tmp_db):
        meta = MediaMeta(content_type="movie", poster="", title="Silent Film",
                         imdb_id="tt0000001", genres=[])
        h = _make_handlers(tmp_db, omdb_meta=meta,
                           parsed=ParsedWatch("Silent Film", None, None))
        update = _make_update()
        await h.watch(update, _make_context("Silent", "Film"))
        update.message.reply_text.assert_called()
        update.message.reply_photo.assert_not_called()

    @pytest.mark.asyncio
    async def test_metadata_stored_on_new_entry(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update(), _make_context("The", "Batman"))
        entry = tmp_db.find_by_title("The Batman")
        assert entry.plot.startswith("When a sadistic serial killer")
        assert entry.actors == "Robert Pattinson,Zoë Kravitz"
        assert entry.director == "Matt Reeves"


class TestRemoveCommand:
    @pytest.mark.asyncio
    async def test_remove_existing_title(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update(), _make_context("The", "Batman"))
        assert tmp_db.find_by_title("The Batman") is not None

        update = _make_update("Bob")
        await h.remove(update, _make_context("The", "Batman"))

        assert tmp_db.find_by_title("The Batman") is None
        call_text = update.message.reply_text.call_args[0][0]
        assert "removed" in call_text.lower()

    @pytest.mark.asyncio
    async def test_remove_deletes_ratings(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update(), _make_context("The", "Batman"))
        await h.rate(_make_update(), _make_context("The", "Batman", "-", "4.5"))

        await h.remove(_make_update(), _make_context("the", "batman"))
        assert tmp_db.ratings_for_title("The Batman") == []

    @pytest.mark.asyncio
    async def test_remove_unknown_title(self, tmp_db):
        h = _make_handlers(tmp_db)
        update = _make_update()
        await h.remove(update, _make_context("Ghost", "Movie"))
        call_text = update.message.reply_text.call_args[0][0]
        assert "isn't on the dashboard" in call_text

    @pytest.mark.asyncio
    async def test_remove_no_args_shows_usage(self, tmp_db):
        h = _make_handlers(tmp_db)
        update = _make_update()
        await h.remove(update, _make_context())
        assert "Format" in update.message.reply_text.call_args[0][0]


class TestRateCommand:
    @pytest.mark.asyncio
    async def test_rate_existing_title(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update(), _make_context("The", "Batman"))
        update = _make_update()
        await h.rate(update, _make_context("The", "Batman", "-", "4.5"))
        ratings = tmp_db.ratings_for_title("The Batman")
        assert len(ratings) == 1
        assert ratings[0].score == 4.5

    @pytest.mark.asyncio
    async def test_rate_updates_existing_rating(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update("Alice"), _make_context("The", "Batman"))
        await h.rate(_make_update("Alice"), _make_context("The", "Batman", "-", "3.0"))
        await h.rate(_make_update("Alice"), _make_context("The", "Batman", "-", "4.5"))
        ratings = tmp_db.ratings_for_title("The Batman")
        alice_ratings = [r for r in ratings if r.user == "Alice"]
        assert len(alice_ratings) == 1
        assert alice_ratings[0].score == 4.5

    @pytest.mark.asyncio
    async def test_rate_nonexistent_title(self, tmp_db):
        h = _make_handlers(tmp_db)
        update = _make_update()
        await h.rate(update, _make_context("Unknown", "Movie", "-", "3"))
        call_text = update.message.reply_text.call_args[0][0]
        assert "watch" in call_text.lower()

    @pytest.mark.asyncio
    async def test_rate_no_args_shows_usage(self, tmp_db):
        h = _make_handlers(tmp_db)
        update = _make_update()
        await h.rate(update, _make_context())
        assert "Format" in update.message.reply_text.call_args[0][0]

    @pytest.mark.asyncio
    async def test_multiple_users_rate_same_title(self, tmp_db):
        h = _make_handlers(tmp_db)
        await h.watch(_make_update("Alice"), _make_context("The", "Batman"))
        await h.rate(_make_update("Alice"), _make_context("The", "Batman", "-", "4.5"))
        await h.rate(_make_update("Bob"),   _make_context("The", "Batman", "-", "3.0"))
        ratings = tmp_db.ratings_for_title("The Batman")
        assert len(ratings) == 2
