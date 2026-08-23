"""
src/db/database.py
All SQLite interactions in one place.

Schema (v2)
-----------
watch_logs  — one row per unique title
ratings     — one row per (entry, user) rating; FK to watch_logs.id

Migrations are versioned via PRAGMA user_version. v1 → v2 re-links the
ratings table to watch_logs by title match and backs up the DB file first.
"""

import logging
import os
import shutil
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 3


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
    plot: str = ""      # OMDb synopsis
    actors: str = ""    # comma-separated cast
    director: str = ""
    id: int | None = None


@dataclass
class Rating:
    title: str          # denormalized for display; source of truth is entry_id
    user: str
    score: float        # 0.0 – 5.0
    date: str
    id: int | None = None
    entry_id: int | None = None


@dataclass
class RatedEntry:
    """WatchEntry enriched with its ratings list — used by the dashboard."""
    entry: WatchEntry
    ratings: list[Rating] = field(default_factory=list)

    @property
    def avg_score(self) -> float | None:
        if not self.ratings:
            return None
        return round(sum(r.score for r in self.ratings) / len(self.ratings), 2)


class Database:
    def __init__(self, db_file: str = "movies.db") -> None:
        self.db_file = db_file
        self._init()

    # ------------------------------------------------------------------ #
    # Schema / migrations                                                  #
    # ------------------------------------------------------------------ #

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
                    genres        TEXT             DEFAULT '',
                    plot          TEXT             DEFAULT '',
                    actors        TEXT             DEFAULT '',
                    director      TEXT             DEFAULT ''
                )
            """)
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 2:
                self._migrate_to_v2(conn)
            if version < 3:
                self._migrate_to_v3(conn)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone() is not None

    def _migrate_to_v2(self, conn: sqlite3.Connection) -> None:
        """Bring a pre-v2 database up to the entry_id-linked ratings table."""
        # watch_logs: ensure genres column exists on very old schemas
        cols = [r[1] for r in conn.execute("PRAGMA table_info(watch_logs)")]
        if "genres" not in cols:
            conn.execute("ALTER TABLE watch_logs ADD COLUMN genres TEXT DEFAULT ''")

        if not self._table_exists(conn, "ratings"):
            conn.execute("""
                CREATE TABLE ratings (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id INTEGER NOT NULL REFERENCES watch_logs(id) ON DELETE CASCADE,
                    user     TEXT    NOT NULL,
                    score    REAL    NOT NULL,
                    date     TEXT    NOT NULL,
                    UNIQUE(entry_id, user)
                )
            """)
            return

        cols = [r[1] for r in conn.execute("PRAGMA table_info(ratings)")]
        if "entry_id" in cols:
            return  # already v2-shaped

        # Destructive rebuild — back up the file first.
        if os.path.exists(self.db_file) and os.path.getsize(self.db_file) > 0:
            backup_path = self.db_file + ".pre-v2.bak"
            shutil.copy2(self.db_file, backup_path)
            logger.info("Backed up database to %s before v2 migration", backup_path)

        old_rows = conn.execute(
            "SELECT title, user, score, date FROM ratings"
        ).fetchall()
        conn.execute("""
            CREATE TABLE ratings_v2 (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_id INTEGER NOT NULL REFERENCES watch_logs(id) ON DELETE CASCADE,
                user     TEXT    NOT NULL,
                score    REAL    NOT NULL,
                date     TEXT    NOT NULL,
                UNIQUE(entry_id, user)
            )
        """)
        migrated = 0
        for row in old_rows:
            match = conn.execute(
                "SELECT id FROM watch_logs WHERE LOWER(title) = LOWER(?)",
                (row["title"],),
            ).fetchone()
            if match is None:
                continue  # orphaned rating — no matching title
            conn.execute(
                "INSERT OR IGNORE INTO ratings_v2 (entry_id, user, score, date) "
                "VALUES (?, ?, ?, ?)",
                (match["id"], row["user"], row["score"], row["date"]),
            )
            migrated += 1
        conn.execute("DROP TABLE ratings")
        conn.execute("ALTER TABLE ratings_v2 RENAME TO ratings")
        logger.info(
            "Ratings migration v1→v2: %d/%d rows linked to watch_logs",
            migrated, len(old_rows),
        )

    # ------------------------------------------------------------------ #
    # Connection                                                           #
    # ------------------------------------------------------------------ #

    def _migrate_to_v3(self, conn: sqlite3.Connection) -> None:
        """v3: add OMDb enrichment columns (plot/actors/director)."""
        cols = [r[1] for r in conn.execute("PRAGMA table_info(watch_logs)")]
        for col in ("plot", "actors", "director"):
            if col not in cols:
                conn.execute(
                    f"ALTER TABLE watch_logs ADD COLUMN {col} TEXT DEFAULT ''"
                )

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ #
    # Writes                                                               #
    # ------------------------------------------------------------------ #

    def insert_entry(self, entry: WatchEntry) -> int | None:
        """Insert a new watch entry.

        Returns the new row id, or None if the title already existed
        (INSERT OR IGNORE skipped the row).
        """
        with self._conn() as conn:
            cursor = conn.execute("""
                INSERT OR IGNORE INTO watch_logs
                    (user, title, date, content_type, poster, imdb_id,
                     platforms, genres, plot, actors, director)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.user, entry.title, entry.date, entry.content_type,
                entry.poster, entry.imdb_id, entry.platforms, entry.genres,
                entry.plot, entry.actors, entry.director,
            ))
            if cursor.rowcount > 0:
                return cursor.lastrowid
            return None

    def upsert_rating(self, rating: Rating) -> bool:
        """
        Insert or update a (entry, user) rating. The entry is resolved from
        rating.title (case-insensitive).

        Returns True if stored, False when no matching watch_logs row exists.
        """
        with self._conn() as conn:
            match = conn.execute(
                "SELECT id FROM watch_logs WHERE LOWER(title) = LOWER(?)",
                (rating.title,),
            ).fetchone()
            if match is None:
                return False
            conn.execute("""
                INSERT INTO ratings (entry_id, user, score, date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(entry_id, user)
                DO UPDATE SET score=excluded.score, date=excluded.date
            """, (match["id"], rating.user, rating.score, rating.date))
            return True

    def update_platforms(self, entry_id: int, platforms: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE watch_logs SET platforms = ? WHERE id = ?",
                (platforms, entry_id),
            )

    def update_metadata(
        self, entry_id: int, *, plot: str = "", actors: str = "", director: str = ""
    ) -> None:
        """Fill OMDb enrichment columns for an existing entry (backfills)."""
        with self._conn() as conn:
            conn.execute(
                "UPDATE watch_logs SET plot = ?, actors = ?, director = ? WHERE id = ?",
                (plot, actors, director, entry_id),
            )

    def delete_entry(self, entry_id: int) -> bool:
        """Remove a title entirely. Ratings cascade via FK; also deleted
        explicitly so removal works even if foreign_keys is unavailable.

        Returns True when a row was deleted."""
        with self._conn() as conn:
            conn.execute("DELETE FROM ratings WHERE entry_id = ?", (entry_id,))
            cursor = conn.execute(
                "DELETE FROM watch_logs WHERE id = ?", (entry_id,)
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    # Reads                                                                #
    # ------------------------------------------------------------------ #

    def find_by_title(self, title: str) -> WatchEntry | None:
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
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT w.*, r.id AS rating_id, r.user AS rating_user,
                       r.score AS rating_score, r.date AS rating_date,
                       r.entry_id AS rating_entry_id
                FROM watch_logs w
                LEFT JOIN ratings r ON r.entry_id = w.id
                ORDER BY w.id DESC, r.date ASC
            """).fetchall()

        entries: dict[int, RatedEntry] = {}
        for row in rows:
            wid = row["id"]
            if wid not in entries:
                entries[wid] = RatedEntry(entry=self._row_to_entry(row))
            if row["rating_id"] is not None:
                entries[wid].ratings.append(Rating(
                    title=row["title"],
                    user=row["rating_user"],
                    score=row["rating_score"],
                    date=row["rating_date"],
                    id=row["rating_id"],
                    entry_id=row["rating_entry_id"],
                ))
        return list(entries.values())

    def ratings_for_title(self, title: str) -> list[Rating]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT r.*, w.title AS w_title
                FROM ratings r
                JOIN watch_logs w ON r.entry_id = w.id
                WHERE LOWER(w.title) = LOWER(?)
                ORDER BY r.date ASC
            """, (title,)).fetchall()
        return [Rating(title=r["w_title"], user=r["user"], score=r["score"],
                       date=r["date"], id=r["id"], entry_id=r["entry_id"])
                for r in rows]

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
            plot=row["plot"] if "plot" in keys else "",
            actors=row["actors"] if "actors" in keys else "",
            director=row["director"] if "director" in keys else "",
        )
