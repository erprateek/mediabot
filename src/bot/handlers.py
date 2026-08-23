"""
src/bot/handlers.py
Telegram command handlers.

Commands
--------
/watch [free-form text]   — log a title; Ollama parses title + optional rating
                            from whatever the user naturally types.
                            e.g. "just watched Dune, great 4.5/5"
                                 "The Batman"
                                 "Interstellar — 5 stars, mind-blowing"

/rate  [Title] - [0-5]    — explicitly add or update your rating for a title
                            that is already on the dashboard.
                            e.g. /rate The Batman - 4.5

/remove [Title]           — delete a title (and its ratings) from the
                            dashboard, e.g. when it was parsed incorrectly.

/merge [Keep] | [Remove]  — merge a duplicate title into the canonical
                            one, moving its ratings. e.g.
                            /merge Dune: Part Two | Dune Part Two

/show [Title]             — exact-match lookup: poster, year and one
                            rating per user.

/showall [Query]          — same info for every fuzzy match, sent
                            sequentially.
"""

import asyncio
import logging
import re
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.db.database import Database, Rating, WatchEntry
from src.services.errors import ExternalAPIError
from src.services.ollama import OllamaClient
from src.services.omdb import OmdbClient
from src.services.watchmode import WatchmodeClient

logger = logging.getLogger(__name__)


def _parse_rate_text(text: str) -> tuple[str, float | None]:
    """
    Parses a title plus score from any of these forms:
      'The Batman - 4.5'
      'Lanterns 8.5/10'
      'Dune - 9/10'
      'Movie 3/5'
    Returns (title, score) or (title, None) if no score found.
    Scores out of 10 are converted to the /5 scale and clamped to 0–5.
    """
    text = text.strip()

    slash = re.search(r"^(.+?)\s*(\d+(?:\.\d+)?)\s*/\s*(10|5)\s*$", text)
    if slash:
        value = float(slash.group(2))
        if slash.group(3) == "10":
            value /= 2.0
        title = slash.group(1).strip().rstrip("-").strip()
        return title, max(0.0, min(5.0, value))

    dash = re.search(r"^(.+?)\s*-\s*(\d+(?:\.\d+)?)\s*$", text)
    if dash:
        score = float(dash.group(2))
        return dash.group(1).strip(), max(0.0, min(5.0, score))

    return text, None


class BotHandlers:
    def __init__(
        self,
        db: Database,
        omdb: OmdbClient,
        watchmode: WatchmodeClient,
        ollama: OllamaClient,
    ) -> None:
        self.db = db
        self.omdb = omdb
        self.watchmode = watchmode
        self.ollama = ollama

    # ------------------------------------------------------------------ #
    # /watch — Ollama parses the free-form message                        #
    # ------------------------------------------------------------------ #

    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        user = update.message.from_user.first_name if update.message.from_user else "Unknown"
        raw_text = " ".join(context.args or [])

        if not raw_text:
            await update.message.reply_text(
                "Just tell me what you watched — naturally!\n\n"
                "Examples:\n"
                "  `/watch The Batman`\n"
                "  `/watch just finished Dune, solid 4/5`\n"
                "  `/watch Interstellar — 5 stars, mind-blowing`\n\n"
                "To update a rating later: `/rate The Batman - 4.5`",
                parse_mode="Markdown",
            )
            return

        # ── Step 1: Let Ollama parse the free-form text ──────────────────
        await update.message.reply_text("🤔 Parsing…")
        parsed = await asyncio.to_thread(self.ollama.parse_watch_message, raw_text)

        # ── Step 2: Fetch metadata from OMDb ─────────────────────────────
        meta = await asyncio.to_thread(self.omdb.fetch, parsed.title)

        # ── Step 3: Check if title already exists ────────────────────────
        existing = await asyncio.to_thread(self.db.find_by_title, meta.title)

        if existing:
            # Title is already logged — if the user included a rating, just upsert it
            if parsed.rating is not None:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                await asyncio.to_thread(
                    self.db.upsert_rating,
                    Rating(
                        title=existing.title,
                        user=user,
                        score=parsed.rating,
                        date=now,
                    ),
                )
                stars = "⭐" * round(parsed.rating)
                await update.message.reply_text(
                    f"{stars} Updated your rating for *{existing.title}*: {parsed.rating}/5",
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text(
                    f"*{meta.title}* is already on the dashboard!\n"
                    f"To rate it: `/rate {meta.title} - 4.5`",
                    parse_mode="Markdown",
                )
            return

        # ── Step 4: Fetch streaming platforms ────────────────────────────
        try:
            platforms = await asyncio.to_thread(
                self.watchmode.fetch_platforms, meta.imdb_id, meta.title
            )
        except ExternalAPIError:
            logger.warning("Platform lookup failed for '%s' — leaving blank", meta.title)
            platforms = ""
        genres_str = ",".join(meta.genres)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── Step 5: Insert the title ──────────────────────────────────────
        entry = WatchEntry(
            user=user,
            title=meta.title,
            date=now,
            content_type=meta.content_type,
            poster=meta.poster,
            imdb_id=meta.imdb_id or "",
            platforms=platforms,
            genres=genres_str,
            year=meta.year,
            plot=meta.plot,
            actors=",".join(meta.actors),
            director=meta.director,
        )
        entry_id = await asyncio.to_thread(self.db.insert_entry, entry)
        if entry_id is None:
            # Lost an insert race — another user logged this title first.
            await update.message.reply_text(
                f"*{meta.title}* is already on the dashboard!\n"
                f"To rate it: `/rate {meta.title} - 4.5`",
                parse_mode="Markdown",
            )
            return

        # ── Step 6: Upsert rating if one was extracted ────────────────────
        if parsed.rating is not None:
            await asyncio.to_thread(
                self.db.upsert_rating,
                Rating(
                    title=meta.title,
                    user=user,
                    score=parsed.rating,
                    date=now,
                ),
            )

        # ── Step 7: Reply ─────────────────────────────────────────────────
        type_emoji = "🎬" if meta.content_type == "movie" else "📺"
        genre_display = " · ".join(meta.genres[:3]) if meta.genres else "Unknown"
        platform_display = (
            "📺 " + ", ".join(platforms.split(",")) if platforms
            else "Not currently streaming"
        )

        rating_line = (
            f"⭐ Logged your rating: *{parsed.rating}/5*\n"
            if parsed.rating is not None
            else f"Rate it with: `/rate {meta.title} - 4.5`\n"
        )

        caption = (
            f"💾 *Saved {type_emoji} {meta.title}*\n"
            f"_{genre_display}_\n\n"
            f"{platform_display}\n\n"
            f"{rating_line}"
        )

        if meta.poster:
            try:
                await update.message.reply_photo(
                    photo=meta.poster, caption=caption, parse_mode="Markdown"
                )
                return
            except Exception:
                pass

        await update.message.reply_text(caption, parse_mode="Markdown")

    # ------------------------------------------------------------------ #
    # /rate — explicit re-rating for an existing title                    #
    # ------------------------------------------------------------------ #

    async def rate(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        user = update.message.from_user.first_name if update.message.from_user else "Unknown"
        text = " ".join(context.args or [])

        if not text:
            await update.message.reply_text(
                "Format: `/rate [Title] - [0-5]`\nExample: `/rate The Batman - 4.5`",
                parse_mode="Markdown",
            )
            return

        title_query, score = _parse_rate_text(text)

        if score is None:
            await update.message.reply_text(
                "Couldn't parse a score.\nFormat: `/rate The Batman - 4.5` or `/rate Dune 9/10`",
                parse_mode="Markdown",
            )
            return

        existing = await asyncio.to_thread(self.db.find_by_title, title_query)
        if not existing:
            await update.message.reply_text(
                f"*{title_query}* isn't on the dashboard yet.\n"
                f"Add it with: `/watch {title_query}`",
                parse_mode="Markdown",
            )
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        await asyncio.to_thread(
            self.db.upsert_rating,
            Rating(
                title=existing.title,
                user=user,
                score=score,
                date=now,
            ),
        )

        stars = "⭐" * round(score)
        await update.message.reply_text(
            f"{stars} *{user}* rated *{existing.title}* {score}/5",
            parse_mode="Markdown",
        )


    # ------------------------------------------------------------------ #
    # /remove — delete a title (e.g. it was parsed incorrectly)            #
    # ------------------------------------------------------------------ #

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        user = update.message.from_user.first_name if update.message.from_user else "Unknown"
        text = " ".join(context.args or [])

        if not text:
            await update.message.reply_text(
                "Format: `/remove [Title]`\nExample: `/remove The Batman`",
                parse_mode="Markdown",
            )
            return

        existing = await asyncio.to_thread(self.db.find_by_title, text)
        if not existing or existing.id is None:
            await update.message.reply_text(
                f"*{text}* isn't on the dashboard.",
                parse_mode="Markdown",
            )
            return

        deleted = await asyncio.to_thread(self.db.delete_entry, existing.id)
        if deleted:
            logger.info("'%s' removed by %s", existing.title, user)
            await update.message.reply_text(
                f"🗑 Removed *{existing.title}* from the dashboard.",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"Couldn't remove *{existing.title}* — try again.",
                parse_mode="Markdown",
            )


    # ------------------------------------------------------------------ #
    # /show, /showall — look up logged titles                              #
    # ------------------------------------------------------------------ #

    async def _send_title_card(self, update: Update, entry: WatchEntry) -> None:
        """Poster + title (year) + one rating line per user."""
        if update.message is None:
            return
        ratings = await asyncio.to_thread(self.db.ratings_for_title, entry.title)

        header = f"🎬 *{entry.title}*"
        if entry.year:
            header += f" ({entry.year})"
        if ratings:
            rating_lines = "\n".join(
                f"⭐ {r.user} — {r.score:g}/5" for r in ratings
            )
        else:
            rating_lines = "_No ratings yet._"

        caption = f"{header}\n\n{rating_lines}"

        if entry.poster:
            try:
                await update.message.reply_photo(
                    photo=entry.poster, caption=caption, parse_mode="Markdown"
                )
                return
            except Exception:
                logger.warning("Poster fetch failed for '%s'", entry.title)
        await update.message.reply_text(caption, parse_mode="Markdown")

    async def show(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        query = " ".join(context.args or [])
        if not query:
            await update.message.reply_text(
                "Format: `/show [Title]`\nExample: `/show The Batman`\n\n"
                "Fuzzy search instead: `/showall dune`",
                parse_mode="Markdown",
            )
            return

        entry = await asyncio.to_thread(self.db.find_by_title, query)
        if entry is None:
            await update.message.reply_text(
                f"*{query}* isn't on the dashboard.\n"
                f"Fuzzy search: `/showall {query}`",
                parse_mode="Markdown",
            )
            return

        await self._send_title_card(update, entry)

    async def showall(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        query = " ".join(context.args or [])
        if not query:
            await update.message.reply_text(
                "Format: `/showall [Query]`\nExample: `/showall dune`",
                parse_mode="Markdown",
            )
            return

        candidates = await asyncio.to_thread(
            self.db.find_candidates, query,
            min_ratio=0.6, limit=10,
        )
        if not candidates:
            await update.message.reply_text(
                f"Nothing matches *{query}*.",
                parse_mode="Markdown",
            )
            return

        for entry, _ratio in candidates:
            await self._send_title_card(update, entry)

    # ------------------------------------------------------------------ #
    # /merge — fold a duplicate title into the canonical one               #
    # ------------------------------------------------------------------ #

    async def _resolve_or_suggest(self, update: Update, query: str) -> WatchEntry | None:
        """Find a logged title, or reply with fuzzy suggestions."""
        if update.message is None:
            return None
        entry = await asyncio.to_thread(self.db.find_by_title, query)
        if entry is not None:
            return entry

        candidates = await asyncio.to_thread(self.db.find_candidates, query)
        if candidates:
            listing = "\n".join(f"  • {e.title}" for e, _ in candidates)
            await update.message.reply_text(
                f"*{query}* doesn't match a logged title.\nDid you mean:\n{listing}",
                parse_mode="Markdown",
            )
        else:
            await update.message.reply_text(
                f"*{query}* isn't on the dashboard.",
                parse_mode="Markdown",
            )
        return None

    async def merge(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        text = " ".join(context.args or [])

        if "|" not in text:
            await update.message.reply_text(
                "Merge a duplicate into the real title:\n"
                "`/merge [Keep] | [Remove]`\n\n"
                "Example: `/merge Dune: Part Two | Dune Part Two`",
                parse_mode="Markdown",
            )
            return

        keep_q, dup_q = (part.strip() for part in text.split("|", 1))
        if not keep_q or not dup_q:
            await update.message.reply_text(
                "Both sides are needed:\n`/merge [Keep] | [Remove]`",
                parse_mode="Markdown",
            )
            return

        keep = await self._resolve_or_suggest(update, keep_q)
        if keep is None:
            return
        dup = await self._resolve_or_suggest(update, dup_q)
        if dup is None:
            return

        if keep.id is None or dup.id is None or keep.id == dup.id:
            await update.message.reply_text(
                "Pick two *different* titles.", parse_mode="Markdown"
            )
            return

        result = await asyncio.to_thread(
            self.db.merge_entries, keep.id, dup.id
        )
        if result is None:
            await update.message.reply_text("Merge failed — try again.")
            return

        logger.info(
            "Merged '%s' into '%s' (%s ratings moved)",
            result["removed_title"], result["kept_title"], result["moved_ratings"],
        )
        await update.message.reply_text(
            f"🔗 Merged *{result['removed_title']}* into "
            f"*{result['kept_title']}*\n"
            f"{result['moved_ratings']} rating(s) moved.",
            parse_mode="Markdown",
        )


def register_handlers(app: Application, handlers: BotHandlers) -> None:
    app.add_handler(CommandHandler("watch", handlers.watch))
    app.add_handler(CommandHandler("rate",  handlers.rate))
    app.add_handler(CommandHandler("remove", handlers.remove))
    app.add_handler(CommandHandler("merge", handlers.merge))
    app.add_handler(CommandHandler("show", handlers.show))
    app.add_handler(CommandHandler("showall", handlers.showall))
