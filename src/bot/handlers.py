"""
src/bot/handlers.py
Telegram command handlers. Depends on injected DB / service clients
so they can be unit-tested without a live bot connection.
"""

import re
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from src.db.database import Database, WatchEntry
from src.services.omdb import OmdbClient
from src.services.watchmode import WatchmodeClient


def _parse_watch_text(text: str) -> tuple[str, str]:
    """
    Parses '/watch The Batman - 8.4/10' style input.
    Returns (title_query, rating).
    """
    match = re.search(r"(.+?)\s*-\s*(\d+(?:\.\d+)?/10)", text)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return text.strip(), "No Rating"


class BotHandlers:
    def __init__(
        self,
        db: Database,
        omdb: OmdbClient,
        watchmode: WatchmodeClient,
    ) -> None:
        self.db = db
        self.omdb = omdb
        self.watchmode = watchmode

    async def watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        user = update.message.from_user.first_name if update.message.from_user else "Unknown"
        text = " ".join(context.args or [])

        if not text:
            await update.message.reply_text(
                "Format: /watch [Title] - [Rating/10]\nExample: /watch The Batman - 8.4/10"
            )
            return

        title_query, rating = _parse_watch_text(text)

        meta = self.omdb.fetch(title_query)

        existing = self.db.find_by_title(meta.title)
        if existing:
            await update.message.reply_text(
                f"⚠️ *{meta.title}* is already on the dashboard! "
                f"Added by *{existing.user}* ({existing.rating}).",
                parse_mode="Markdown",
            )
            return

        platforms = self.watchmode.fetch_platforms(meta.imdb_id, meta.title)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        entry = WatchEntry(
            user=user,
            title=meta.title,
            rating=rating,
            date=now,
            content_type=meta.content_type,
            poster=meta.poster,
            imdb_id=meta.imdb_id or "",
            platforms=platforms,
        )
        self.db.insert_entry(entry)

        type_emoji = "🎬" if meta.content_type == "movie" else "📺"
        caption = f"💾 *Saved {type_emoji} {meta.title}* ({rating})!\n\n_{platforms}_"

        if meta.poster:
            try:
                await update.message.reply_photo(
                    photo=meta.poster, caption=caption, parse_mode="Markdown"
                )
                return
            except Exception:
                pass

        await update.message.reply_text(caption, parse_mode="Markdown")


def register_handlers(app: Application, handlers: BotHandlers) -> None:
    app.add_handler(CommandHandler("watch", handlers.watch))
