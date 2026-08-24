"""
tests/unit/test_database.py
"""

import sqlite3
from datetime import datetime

from src.db.database import SCHEMA_VERSION, Database, Rating, WatchEntry


def _entry(**overrides) -> WatchEntry:
    base = dict(
        user="Alice", title="The Batman",
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        content_type="movie", poster="https://example.com/p.jpg",
        imdb_id="tt1877830", platforms="Netflix,Max", genres="Action,Drama",
    )
    base.update(overrides)
    return WatchEntry(**base)

def _rating(**overrides) -> Rating:
    base = dict(title="The Batman", user="Alice", score=4.5,
                date=datetime.now().strftime("%Y-%m-%d %H:%M"))
    base.update(overrides)
    return Rating(**base)


def _make_v1_db(path: str) -> None:
    """Create a pre-v2 database: old ratings table keyed by title."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE watch_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user          TEXT    NOT NULL,
            title         TEXT    NOT NULL UNIQUE,
            date          TEXT    NOT NULL,
            content_type  TEXT    NOT NULL DEFAULT 'movie',
            poster        TEXT             DEFAULT '',
            imdb_id       TEXT             DEFAULT '',
            platforms     TEXT             DEFAULT ''
        );
        CREATE TABLE ratings (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT    NOT NULL,
            user  TEXT    NOT NULL,
            score REAL    NOT NULL,
            date  TEXT    NOT NULL,
            UNIQUE(title, user)
        );
        INSERT INTO watch_logs (user, title, date)
        VALUES ('Alice', 'The Batman', '2024-01-01 10:00');
        INSERT INTO ratings (title, user, score, date)
        VALUES ('the batman', 'Alice', 4.5, '2024-01-01 10:05'),
               ('Orphan Movie', 'Bob', 3.0, '2024-01-02 09:00');
    """)
    conn.commit()
    conn.close()


class TestInsertAndFind:
    def test_insert_returns_id(self, tmp_db):
        assert tmp_db.insert_entry(_entry()) > 0

    def test_find_by_title_exact(self, tmp_db):
        tmp_db.insert_entry(_entry(title="Inception"))
        assert tmp_db.find_by_title("Inception") is not None

    def test_find_by_title_case_insensitive(self, tmp_db):
        tmp_db.insert_entry(_entry(title="The Batman"))
        assert tmp_db.find_by_title("the batman") is not None

    def test_find_by_title_not_found(self, tmp_db):
        assert tmp_db.find_by_title("Does Not Exist") is None

    def test_duplicate_insert_ignored(self, tmp_db):
        tmp_db.insert_entry(_entry(title="Dune"))
        tmp_db.insert_entry(_entry(title="Dune"))
        assert len(tmp_db.all_entries()) == 1

    def test_genres_stored_and_retrieved(self, tmp_db):
        tmp_db.insert_entry(_entry(title="Inception", genres="Sci-Fi,Thriller"))
        e = tmp_db.find_by_title("Inception")
        assert e.genres == "Sci-Fi,Thriller"


class TestAllEntries:
    def test_empty_db(self, tmp_db):
        assert tmp_db.all_entries() == []

    def test_returns_all_in_reverse_order(self, tmp_db):
        tmp_db.insert_entry(_entry(title="Movie A"))
        tmp_db.insert_entry(_entry(title="Movie B"))
        titles = [e.title for e in tmp_db.all_entries()]
        assert titles == ["Movie B", "Movie A"]


class TestRatings:
    def test_upsert_rating_insert(self, tmp_db):
        tmp_db.insert_entry(_entry())
        tmp_db.upsert_rating(_rating(score=4.0))
        ratings = tmp_db.ratings_for_title("The Batman")
        assert len(ratings) == 1
        assert ratings[0].score == 4.0

    def test_upsert_rating_update(self, tmp_db):
        tmp_db.insert_entry(_entry())
        tmp_db.upsert_rating(_rating(score=3.0))
        tmp_db.upsert_rating(_rating(score=5.0))   # same user, update
        ratings = tmp_db.ratings_for_title("The Batman")
        assert len(ratings) == 1
        assert ratings[0].score == 5.0

    def test_multiple_users(self, tmp_db):
        tmp_db.insert_entry(_entry())
        tmp_db.upsert_rating(_rating(user="Alice", score=4.5))
        tmp_db.upsert_rating(_rating(user="Bob",   score=3.0))
        ratings = tmp_db.ratings_for_title("The Batman")
        assert len(ratings) == 2

    def test_all_rated_entries_avg(self, tmp_db):
        tmp_db.insert_entry(_entry())
        tmp_db.upsert_rating(_rating(user="Alice", score=4.0))
        tmp_db.upsert_rating(_rating(user="Bob",   score=5.0))
        entries = tmp_db.all_rated_entries()
        assert len(entries) == 1
        assert entries[0].avg_score == 4.5

    def test_rated_entry_no_ratings(self, tmp_db):
        tmp_db.insert_entry(_entry())
        entries = tmp_db.all_rated_entries()
        assert entries[0].avg_score is None


class TestUpdatePlatforms:
    def test_platforms_updated(self, tmp_db):
        eid = tmp_db.insert_entry(_entry(platforms="old"))
        tmp_db.update_platforms(eid, "Netflix,Hulu")
        assert tmp_db.all_entries()[0].platforms == "Netflix,Hulu"


class TestAllEntriesForRefresh:
    def test_structure(self, tmp_db):
        tmp_db.insert_entry(_entry(title="Dune", imdb_id="tt1160419"))
        rows = tmp_db.all_entries_for_refresh()
        assert len(rows) == 1
        eid, title, imdb_id = rows[0]
        assert title == "Dune"
        assert imdb_id == "tt1160419"


class TestV3Migration:
    def test_v1_db_migrates_all_the_way_to_v3(self, tmp_path):
        db_file = str(tmp_path / "legacy.db")
        _make_v1_db(db_file)  # helper from TestV2Migration

        db = Database(db_file=db_file)

        conn = sqlite3.connect(db_file)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        cols = [r[1] for r in conn.execute("PRAGMA table_info(watch_logs)")]
        conn.close()
        assert version == SCHEMA_VERSION
        for col in ("plot", "actors", "director", "year"):
            assert col in cols
        # Data survived the whole chain
        assert db.find_by_title("The Batman") is not None
        assert len(db.ratings_for_title("THE BATMAN")) == 1

    def test_reopening_migrated_v3_db_is_noop(self, tmp_path):
        db_file = str(tmp_path / "fresh.db")
        Database(db_file=db_file)
        Database(db_file=db_file)  # must not raise or re-migrate
        conn = sqlite3.connect(db_file)
        assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        conn.close()


class TestMetadataAndDeletion:
    def test_metadata_roundtrip(self, tmp_db):
        tmp_db.insert_entry(_entry(plot="A dark knight story.",
                                   actors="Robert Pattinson,Zoë Kravitz",
                                   director="Matt Reeves"))
        entry = tmp_db.find_by_title("The Batman")
        assert entry.plot == "A dark knight story."
        assert entry.actors == "Robert Pattinson,Zoë Kravitz"
        assert entry.director == "Matt Reeves"

    def test_update_metadata_backfills_existing_row(self, tmp_db):
        eid = tmp_db.insert_entry(_entry())
        tmp_db.update_metadata(eid, plot="Synopsis", actors="A,B", director="C")
        entry = tmp_db.find_by_title("The Batman")
        assert (entry.plot, entry.actors, entry.director) == ("Synopsis", "A,B", "C")

    def test_delete_entry_removes_ratings_too(self, tmp_db):
        eid = tmp_db.insert_entry(_entry())
        tmp_db.upsert_rating(_rating(user="Alice", score=4.0))
        tmp_db.upsert_rating(_rating(user="Bob", score=3.0))

        assert tmp_db.delete_entry(eid) is True
        assert tmp_db.find_by_title("The Batman") is None
        assert tmp_db.ratings_for_title("The Batman") == []
        assert all(re.entry.id != eid for re in tmp_db.all_rated_entries())

    def test_delete_entry_unknown_id_returns_false(self, tmp_db):
        assert tmp_db.delete_entry(99999) is False

    def test_rename_entry(self, tmp_db):
        eid = tmp_db.insert_entry(_entry())
        assert tmp_db.rename_entry(eid, "The Batman: Revised") is True
        assert tmp_db.find_by_title("The Batman") is None
        assert tmp_db.find_by_title("The Batman: Revised") is not None

    def test_apply_omdb_fills_only_empty_fields_by_default(self, tmp_db):
        tmp_db.insert_entry(_entry(plot="Existing plot.", director=""))
        eid = tmp_db.find_by_title("The Batman").id
        tmp_db.apply_omdb(eid, plot="New plot.", director="Matt Reeves",
                          year="2022")
        entry = tmp_db.find_by_title("The Batman")
        assert entry.plot == "Existing plot."       # untouched
        assert entry.director == "Matt Reeves"      # filled
        assert entry.year == "2022"                 # filled

    def test_apply_omdb_overwrite_replaces_values(self, tmp_db):
        eid = tmp_db.insert_entry(_entry(plot="Old plot."))
        tmp_db.apply_omdb(eid, plot="New plot.", overwrite=True)
        assert tmp_db.find_by_title("The Batman").plot == "New plot."


class TestMerging:
    def _two_entries(self, db) -> tuple[int, int]:
        keep_id = db.insert_entry(_entry(title="Dune: Part Two", platforms="",
                                         genres="Sci-Fi"))
        dup_id = db.insert_entry(_entry(title="Dune Part Two", platforms="Netflix",
                                        genres="Drama,Sci-Fi"))
        return keep_id, dup_id

    def test_merge_moves_ratings_and_fills_empty_fields(self, tmp_db):
        keep_id, dup_id = self._two_entries(tmp_db)
        tmp_db.upsert_rating(_rating(title="Dune Part Two", user="Bob", score=5.0))
        tmp_db.upsert_rating(_rating(user="Alice", score=3.0,
                                     date="2026-01-01 10:00"))         # older on keep
        # Alice re-rated on the duplicate, newer → must win
        tmp_db.upsert_rating(_rating(title="Dune Part Two", user="Alice",
                                     score=4.5, date="2026-02-01 10:00"))

        result = tmp_db.merge_entries(keep_id, dup_id)

        assert result["kept_title"] == "Dune: Part Two"
        assert result["removed_title"] == "Dune Part Two"
        assert result["moved_ratings"] == 2  # Bob inserted + Alice updated

        entry = tmp_db.find_by_title("Dune: Part Two")
        assert entry.platforms == "Netflix"           # filled from duplicate
        assert entry.genres == "Sci-Fi,Drama"         # union, order preserved
        assert tmp_db.find_by_title("Dune Part Two") is None

        ratings = {r.user: r.score for r in tmp_db.ratings_for_title("Dune: Part Two")}
        assert ratings == {"Alice": 4.5, "Bob": 5.0}   # latest wins

    def test_merge_keeps_survivor_nonempty_values(self, tmp_db):
        keep_id = tmp_db.insert_entry(_entry(plot="Canonical plot."))
        dup_id = tmp_db.insert_entry(_entry(title="Dune Part Two", plot="Dup plot."))
        tmp_db.merge_entries(keep_id, dup_id)
        assert tmp_db.find_by_title("The Batman").plot == "Canonical plot."

    def test_merge_same_or_unknown_ids(self, tmp_db):
        eid = tmp_db.insert_entry(_entry())
        assert tmp_db.merge_entries(eid, eid) is None
        assert tmp_db.merge_entries(eid, 99999) is None
        assert tmp_db.merge_entries(99999, eid) is None


class TestTitleMatching:
    def test_normalize_strips_articles_and_punctuation(self, tmp_db):
        norm = tmp_db._normalize_title
        assert norm("The Batman") == norm("batman")
        assert norm("Dune: Part Two") == norm("dune part two")

    def test_find_candidates_ranks_near_titles(self, tmp_db):
        tmp_db.insert_entry(_entry(title="Dune: Part Two"))
        tmp_db.insert_entry(_entry(title="Interstellar"))
        matches = tmp_db.find_candidates("dune part two")
        assert matches and matches[0][0].title == "Dune: Part Two"

    def test_find_candidates_excludes_unrelated(self, tmp_db):
        tmp_db.insert_entry(_entry(title="Interstellar"))
        assert tmp_db.find_candidates("The Godfather") == []

    def test_duplicate_candidates_pairs_similar_titles(self, tmp_db):
        tmp_db.insert_entry(_entry(title="The Batman"))       # older (keep)
        tmp_db.insert_entry(_entry(title="Batman The"))       # newer (dup)
        pairs = tmp_db.duplicate_candidates()
        assert len(pairs) == 1
        assert pairs[0]["keep"]["title"] == "The Batman"
        assert pairs[0]["duplicate"]["title"] == "Batman The"


class TestRatingIntegrity:
    def test_upsert_rating_unknown_title_returns_false(self, tmp_db):
        assert tmp_db.upsert_rating(_rating(title="Ghost Title")) is False

    def test_ratings_carry_entry_id(self, tmp_db):
        tmp_db.insert_entry(_entry())
        tmp_db.upsert_rating(_rating())
        ratings = tmp_db.ratings_for_title("The Batman")
        entry = tmp_db.find_by_title("The Batman")
        assert ratings[0].entry_id == entry.id


class TestV2Migration:
    def test_migration_links_and_preserves_ratings(self, tmp_path):
        db_file = str(tmp_path / "legacy.db")
        _make_v1_db(db_file)

        db = Database(db_file=db_file)

        # Schema upgraded
        conn = sqlite3.connect(db_file)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        cols = [r[1] for r in conn.execute("PRAGMA table_info(ratings)")]
        conn.close()
        assert version >= 2
        assert "entry_id" in cols

        # Matching rating survived and is linked (case-insensitive match)
        ratings = db.ratings_for_title("THE BATMAN")
        assert len(ratings) == 1
        assert ratings[0].score == 4.5
        entry = db.find_by_title("The Batman")
        assert ratings[0].entry_id == entry.id

        # Orphaned rating (no matching title) was dropped, not crashed on
        assert db.all_rated_entries()[0].entry.title == "The Batman"

    def test_migration_creates_backup(self, tmp_path):
        db_file = str(tmp_path / "legacy.db")
        _make_v1_db(db_file)
        Database(db_file=db_file)
        import os
        assert os.path.exists(db_file + ".pre-v2.bak")

    def test_fresh_db_is_at_v2_without_backup(self, tmp_path):
        db_file = str(tmp_path / "fresh.db")
        Database(db_file=db_file)
        import os
        assert not os.path.exists(db_file + ".pre-v2.bak")
        conn = sqlite3.connect(db_file)
        assert conn.execute("PRAGMA user_version").fetchone()[0] >= 2
        conn.close()

    def test_reopening_migrated_db_does_not_remigrate(self, tmp_path):
        db_file = str(tmp_path / "legacy.db")
        _make_v1_db(db_file)
        first = Database(db_file=db_file)
        first.upsert_rating(_rating(title="The Batman", user="New", score=2.0))
        second = Database(db_file=db_file)
        ratings = second.ratings_for_title("The Batman")
        assert {r.user for r in ratings} == {"Alice", "New"}
