"""
main.py — Application entrypoint.

Wires together:
  - FastAPI dashboard
  - Telegram bot (polling)
  - Weekly streaming-data refresh background task
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from telegram.ext import Application

from src.api.dashboard import create_app
from src.bot.handlers import BotHandlers, register_handlers
from src.config import config
from src.db.database import Database
from src.services.errors import ExternalAPIError
from src.services.ollama import OllamaClient
from src.services.omdb import OmdbClient
from src.services.watchmode import WatchmodeClient

logger = logging.getLogger(__name__)


async def refresh_all_platforms(db: Database, watchmode: WatchmodeClient) -> None:
    """One pass: refresh streaming availability for every logged title."""
    logger.info("Refreshing streaming platforms for all entries...")
    for entry_id, title, imdb_id in db.all_entries_for_refresh():
        try:
            fresh = await asyncio.to_thread(
                watchmode.fetch_platforms, imdb_id or None, title
            )
        except ExternalAPIError:
            logger.warning("Skipping platform refresh for '%s': Watchmode unavailable", title)
            continue
        except Exception:
            logger.exception("Streaming refresh failed for entry %s (%s)", entry_id, title)
            continue
        await asyncio.to_thread(db.update_platforms, entry_id, fresh)
        await asyncio.sleep(0.5)
    logger.info("Streaming refresh complete.")


async def weekly_streaming_refresh(db: Database, watchmode: WatchmodeClient, interval: int) -> None:
    """Background task: periodically refreshes streaming availability."""
    while True:
        await asyncio.sleep(interval)
        await refresh_all_platforms(db, watchmode)


def build_telegram_app(
    db: Database,
    omdb: OmdbClient,
    watchmode: WatchmodeClient,
    ollama: OllamaClient,
) -> Application:
    tg_app = Application.builder().token(config.telegram_token).build()
    handlers = BotHandlers(db=db, omdb=omdb, watchmode=watchmode, ollama=ollama)
    register_handlers(tg_app, handlers)
    return tg_app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    config.validate()

    db       = Database(db_file=config.db_file)
    omdb     = OmdbClient(api_key=config.omdb_api_key)
    watchmode = WatchmodeClient(api_key=config.watchmode_api_key, region=config.watchmode_region)
    ollama   = OllamaClient(
        base_url=config.ollama_base_url,
        model=config.ollama_model,
        timeout=config.ollama_timeout,
        keep_alive=config.ollama_keep_alive,
    )

    tg_app = build_telegram_app(db, omdb, watchmode, ollama)

    @asynccontextmanager
    async def lifespan(_):
        logger.info("Starting Telegram bot (Ollama model: %s)...", config.ollama_model)
        await tg_app.initialize()
        await tg_app.start()
        if tg_app.updater is None:
            raise RuntimeError("Telegram Application was built without an Updater")
        polling_task = asyncio.create_task(tg_app.updater.start_polling())
        refresh_task = asyncio.create_task(
            weekly_streaming_refresh(db, watchmode, config.refresh_interval_seconds)
        )
        yield
        logger.info("Shutting down...")
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        polling_task.cancel()
        refresh_task.cancel()

    app = create_app(db)
    app.router.lifespan_context = lifespan

    uvicorn.run(app, host=config.host, port=config.port)


if __name__ == "__main__":
    main()
