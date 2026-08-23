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
    Parses 'The Batman - 4.5' or 'The Batman - 4'.
    Returns (title, score) or (title, None) if no score found.
    """
    match = re.search(r"^(.+?)\s*-\s*(\d+(?:\.\d+)?)\s*$", text.strip())
    if match:
        score = float(match.group(2))
        score = max(0.0, min(5.0, score))
        return match.group(1).strip(), score
    return text.strip(), None


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
                "Couldn't parse a score.\nFormat: `/rate The Batman - 4.5`",
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


def register_handlers(app: Application, handlers: BotHandlers) -> None:
    app.add_handler(CommandHandler("watch", handlers.watch))
    app.add_handler(CommandHandler("rate",  handlers.rate))
