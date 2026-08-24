"""
scripts/backfill_metadata.py

One-shot: fill plot/actors/director for titles logged before schema v3.
Safe to re-run — only entries with empty plot are fetched.

Usage:
    python scripts/backfill_metadata.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import config  # noqa: E402 (path setup must run first)
from src.db.database import Database  # noqa: E402
from src.services.omdb import OmdbClient  # noqa: E402


def main() -> None:
    if not config.omdb_api_key:
        sys.exit("OMDB_API_KEY is required (set it in .env)")

    db = Database(db_file=config.db_file)
    omdb = OmdbClient(api_key=config.omdb_api_key)

    pending = [e for e in db.all_entries() if not e.plot or not e.year]
    print(f"{len(pending)} title(s) missing metadata")

    updated = skipped = 0
    for entry in pending:
        meta = omdb.fetch(entry.title)
        # Only trust the result when OMDb actually matched the title
        if meta.imdb_id:
            # overwrite=False: fills only the empty columns, never clobbers
            db.apply_omdb(
                entry.id,
                plot=meta.plot,
                actors=",".join(meta.actors),
                director=meta.director,
                year=meta.year,
                genres=",".join(meta.genres),
                imdb_id=meta.imdb_id,
            )
            print(f"  + {entry.title}")
            updated += 1
        else:
            print(f"  . {entry.title}: nothing found")
            skipped += 1
        time.sleep(0.4)  # be polite to the free tier

    print(f"Done — {updated} updated, {skipped} without results")


if __name__ == "__main__":
    main()
