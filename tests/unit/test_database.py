"""
tests/unit/test_database.py
"""

from datetime import datetime

import pytest

from src.db.database import Database, WatchEntry


def _make_entry(**overrides) -> WatchEntry:
    base = dict(
        user="Alice",
        title="The Batman",
        rating="8.4/10",
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        content_type="movie",
        poster="https://example.com/poster.jpg",
        imdb_id="tt1877830",
        platforms="📺 Stream on: HBO Max",
    )
    base.update(overrides)
    return WatchEntry(**base)


class TestInsertAndFind:
    def test_insert_returns_id(self, tmp_db):
        entry_id = tmp_db.insert_entry(_make_entry())
        assert isinstance(entry_id, int)
        assert entry_id > 0

    def test_find_by_title_exact(self, tmp_db):
        tmp_db.insert_entry(_make_entry(title="Inception"))
        result = tmp_db.find_by_title("Inception")
        assert result is not None
        assert result.title == "Inception"

    def test_find_by_title_case_insensitive(self, tmp_db):
        tmp_db.insert_entry(_make_entry(title="The Batman"))
        result = tmp_db.find_by_title("the batman")
        assert result is not None

    def test_find_by_title_not_found(self, tmp_db):
        assert tmp_db.find_by_title("Does Not Exist") is None


class TestAllEntries:
    def test_empty_db(self, tmp_db):
        assert tmp_db.all_entries() == []

    def test_returns_all_in_reverse_order(self, tmp_db):
        tmp_db.insert_entry(_make_entry(title="Movie A"))
        tmp_db.insert_entry(_make_entry(title="Movie B"))
        titles = [e.title for e in tmp_db.all_entries()]
        assert titles == ["Movie B", "Movie A"]

    def test_tv_and_movie_mixed(self, tmp_db):
        tmp_db.insert_entry(_make_entry(title="Breaking Bad", content_type="tv"))
        tmp_db.insert_entry(_make_entry(title="Interstellar", content_type="movie"))
        entries = tmp_db.all_entries()
        assert len(entries) == 2


class TestUpdatePlatforms:
    def test_platforms_updated(self, tmp_db):
        entry_id = tmp_db.insert_entry(_make_entry(platforms="old"))
        tmp_db.update_platforms(entry_id, "📺 Stream on: Netflix")
        entries = tmp_db.all_entries()
        assert entries[0].platforms == "📺 Stream on: Netflix"


class TestAllEntriesForRefresh:
    def test_structure(self, tmp_db):
        tmp_db.insert_entry(_make_entry(title="Dune", imdb_id="tt1160419"))
        rows = tmp_db.all_entries_for_refresh()
        assert len(rows) == 1
        entry_id, title, imdb_id = rows[0]
        assert title == "Dune"
        assert imdb_id == "tt1160419"
        assert isinstance(entry_id, int)
