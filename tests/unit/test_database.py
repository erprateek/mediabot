"""
tests/unit/test_database.py
"""

from datetime import datetime
import pytest
from src.db.database import Database, WatchEntry, Rating


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
