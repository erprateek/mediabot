"""
src/db/database.py
All SQLite interactions in one place.
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Generator, Optional


@dataclass
class WatchEntry:
    user: str
    title: str
    rating: str
    date: str
    content_type: str
    poster: str
    imdb_id: str
    platforms: str
    id: Optional[int] = None


class Database:
    def __init__(self, db_file: str = "movies.db") -> None:
        self.db_file = db_file
        self._init()

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watch_logs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user          TEXT    NOT NULL,
                    title         TEXT    NOT NULL,
                    rating        TEXT    NOT NULL DEFAULT 'No Rating',
                    date          TEXT    NOT NULL,
                    content_type  TEXT    NOT NULL DEFAULT 'movie',
                    poster        TEXT             DEFAULT '',
                    imdb_id       TEXT             DEFAULT '',
                    platforms     TEXT             DEFAULT ''
                )
                """
            )

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Writes                                                               #
    # ------------------------------------------------------------------ #

    def insert_entry(self, entry: WatchEntry) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO watch_logs
                    (user, title, rating, date, content_type, poster, imdb_id, platforms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.user,
                    entry.title,
                    entry.rating,
                    entry.date,
                    entry.content_type,
                    entry.poster,
                    entry.imdb_id,
                    entry.platforms,
                ),
            )
            return cursor.lastrowid

    def update_platforms(self, entry_id: int, platforms: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE watch_logs SET platforms = ? WHERE id = ?",
                (platforms, entry_id),
            )

    # ------------------------------------------------------------------ #
    # Reads                                                                #
    # ------------------------------------------------------------------ #

    def find_by_title(self, title: str) -> Optional[WatchEntry]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM watch_logs WHERE LOWER(title) = LOWER(?)",
                (title,),
            ).fetchone()
        if row is None:
            return None
        return WatchEntry(**{k: row[k] for k in row.keys()})

    def all_entries(self) -> list[WatchEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM watch_logs ORDER BY id DESC"
            ).fetchall()
        return [WatchEntry(**{k: row[k] for k in row.keys()}) for row in rows]

    def all_entries_for_refresh(self) -> list[tuple[int, str, str]]:
        """Returns (id, title, imdb_id) tuples for the background refresh job."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, imdb_id FROM watch_logs"
            ).fetchall()
        return [(row["id"], row["title"], row["imdb_id"]) for row in rows]
