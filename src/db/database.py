"""
src/db/database.py
All SQLite interactions in one place.

Schema
------
watch_logs  — one row per unique title
ratings     — one row per (user, title) rating; supports multiple raters per title
"""

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Generator, Optional


@dataclass
class WatchEntry:
    user: str           # first user to log the title
    title: str
    date: str
    content_type: str
    poster: str
    imdb_id: str
    platforms: str      # comma-separated, e.g. "Netflix,Hulu"
    genres: str         # comma-separated, e.g. "Action,Drama"
    id: Optional[int] = None


@dataclass
class Rating:
    title: str
    user: str
    score: float        # 0.0 – 5.0
    date: str
    id: Optional[int] = None


@dataclass
class RatedEntry:
    """WatchEntry enriched with its ratings list — used by the dashboard."""
    entry: WatchEntry
    ratings: list[Rating] = field(default_factory=list)

    @property
    def avg_score(self) -> Optional[float]:
        if not self.ratings:
            return None
        return round(sum(r.score for r in self.ratings) / len(self.ratings), 2)


class Database:
    def __init__(self, db_file: str = "movies.db") -> None:
        self.db_file = db_file
        self._init()

    def _init(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watch_logs (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user          TEXT    NOT NULL,
                    title         TEXT    NOT NULL UNIQUE,
                    date          TEXT    NOT NULL,
                    content_type  TEXT    NOT NULL DEFAULT 'movie',
                    poster        TEXT             DEFAULT '',
                    imdb_id       TEXT             DEFAULT '',
                    platforms     TEXT             DEFAULT '',
                    genres        TEXT             DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    id    INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT    NOT NULL,
                    user  TEXT    NOT NULL,
                    score REAL    NOT NULL,
                    date  TEXT    NOT NULL,
                    UNIQUE(title, user)
                )
            """)
            # Migrate: add genres column if upgrading from older schema
            try:
                conn.execute("ALTER TABLE watch_logs ADD COLUMN genres TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass  # column already exists

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

    # ... (lines 1-172 unchanged)
    
    # ------------------------------------------------------------------ #
    # Writes                                                               #
    # ------------------------------------------------------------------ #
    
    def insert_entry(self, entry: WatchEntry) -> Optional[int]:
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO watch_logs
                    (user, title, date, content_type, poster, imdb_id, platforms, genres)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.user, entry.title, entry.date, entry.content_type,
                entry.poster, entry.imdb_id, entry.platforms, entry.genres,
            ))
            # Check if the row was actually inserted (not ignored)
            if cursor.rowcount > 0:
                return cursor.lastrowid
            return None
                return None

    def upsert_rating(self, rating: Rating) -> None:
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO ratings (title, user, score, date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(title, user) DO UPDATE SET score=excluded.score, date=excluded.date
            """, (rating.title, rating.user, rating.score, rating.date))

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
                "SELECT * FROM watch_logs WHERE LOWER(title) = LOWER(?)", (title,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def all_entries(self) -> list[WatchEntry]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM watch_logs ORDER BY id DESC"
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def all_rated_entries(self) -> list[RatedEntry]:
        """Returns every title with its ratings list attached."""
        entries = {e.title: RatedEntry(entry=e) for e in self.all_entries()}
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM ratings ORDER BY date ASC").fetchall()
        for row in rows:
            title = row["title"]
            if title in entries:
                entries[title].ratings.append(Rating(
                    title=row["title"],
                    user=row["user"],
                    score=row["score"],
                    date=row["date"],
                    id=row["id"],
                ))
        return list(entries.values())

    def ratings_for_title(self, title: str) -> list[Rating]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM ratings WHERE LOWER(title) = LOWER(?) ORDER BY date ASC",
                (title,)
            ).fetchall()
        return [Rating(title=r["title"], user=r["user"], score=r["score"],
                       date=r["date"], id=r["id"]) for r in rows]

    def all_entries_for_refresh(self) -> list[tuple[int, str, str]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT id, title, imdb_id FROM watch_logs"
            ).fetchall()
        return [(row["id"], row["title"], row["imdb_id"]) for row in rows]

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> WatchEntry:
        keys = row.keys()
        return WatchEntry(
            id=row["id"],
            user=row["user"],
            title=row["title"],
            date=row["date"],
            content_type=row["content_type"],
            poster=row["poster"],
            imdb_id=row["imdb_id"],
            platforms=row["platforms"],
            genres=row["genres"] if "genres" in keys else "",
        )
