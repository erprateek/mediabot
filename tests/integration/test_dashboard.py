"""
tests/integration/test_dashboard.py
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.api.dashboard import build_dashboard_html, create_app
from src.db.database import Rating, WatchEntry


def _entry(title: str, content_type: str = "movie", genres: str = "Action") -> WatchEntry:
    return WatchEntry(
        user="Alice", title=title,
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        content_type=content_type, poster="",
        imdb_id="tt0000001", platforms="Netflix",
        genres=genres,
    )

def _rating(title: str, user: str = "Alice", score: float = 4.0) -> Rating:
    return Rating(title=title, user=user, score=score,
                  date=datetime.now().strftime("%Y-%m-%d %H:%M"))


@pytest.fixture
def client(tmp_db):
    return TestClient(create_app(tmp_db)), tmp_db


class TestHealthEndpoint:
    def test_health_ok(self, client):
        tc, _ = client
        assert tc.get("/health").json() == {"status": "ok"}


class TestDashboard:
    def test_empty_db_renders_placeholders(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert resp.status_code == 200
        assert "Nothing logged yet" in resp.text

    def test_movie_appears_in_page(self, client):
        tc, db = client
        db.insert_entry(_entry("Inception", "movie"))
        assert "Inception" in tc.get("/").text

    def test_tv_appears_in_page(self, client):
        tc, db = client
        db.insert_entry(_entry("The Wire", "tv"))
        assert "The Wire" in tc.get("/").text

    def test_genre_filter_buttons_rendered(self, client):
        tc, db = client
        db.insert_entry(_entry("Dune", "movie", genres="Sci-Fi,Action"))
        resp = tc.get("/")
        assert "Sci-Fi" in resp.text
        assert "Action" in resp.text

    def test_avg_rating_shown_when_rated(self, client):
        tc, db = client
        db.insert_entry(_entry("Dune"))
        db.upsert_rating(_rating("Dune", "Alice", 4.0))
        db.upsert_rating(_rating("Dune", "Bob",   5.0))
        resp = tc.get("/")
        assert "4.5" in resp.text

    def test_html_content_type(self, client):
        tc, _ = client
        assert "text/html" in tc.get("/").headers["content-type"]

    def test_xss_title_is_escaped(self, client):
        tc, db = client
        db.insert_entry(_entry('<script>alert(1)</script>', genres="Action"))
        resp = tc.get("/")
        assert "<script>alert(1)</script>" not in resp.text
        assert "&lt;script&gt;" in resp.text

    def test_xss_user_is_escaped(self, client):
        tc, db = client
        db.insert_entry(_entry("Dune"))
        db.upsert_rating(_rating("Dune", user="<b>Bob</b>", score=4.0))
        resp = tc.get("/")
        assert "<b>Bob</b>" not in resp.text
        assert "&lt;b&gt;Bob&lt;/b&gt;" in resp.text

    def test_no_inline_event_handlers(self, client):
        tc, db = client
        db.insert_entry(_entry("Inception"))
        html = tc.get("/").text
        assert "onclick=" not in html


class TestApiEntries:
    def test_returns_json_list(self, client):
        tc, db = client
        db.insert_entry(_entry("Inception", genres="Sci-Fi,Action"))
        data = tc.get("/api/entries").json()
        assert isinstance(data, list)
        assert len(data) == 1
        entry = data[0]
        assert entry["title"] == "Inception"
        assert entry["genres"] == ["Sci-Fi", "Action"]
        assert entry["platforms"] == ["Netflix"]

    def test_includes_ratings_and_avg(self, client):
        tc, db = client
        db.insert_entry(_entry("Dune"))
        db.upsert_rating(_rating("Dune", "Alice", 4.0))
        db.upsert_rating(_rating("Dune", "Bob", 5.0))
        entry = tc.get("/api/entries").json()[0]
        assert len(entry["ratings"]) == 2
        assert entry["avg"] == 4.5


class TestBuildDashboardHtml:
    def test_no_entries_shows_no_data(self, tmp_db):
        html = build_dashboard_html(tmp_db.all_rated_entries())
        assert "Nothing logged yet" in html

    def test_unrated_chip_shows_plus_rate(self, tmp_db):
        tmp_db.insert_entry(_entry("Oppenheimer"))
        html = build_dashboard_html(tmp_db.all_rated_entries())
        assert "+ rate" in html

    def test_rated_chip_shows_score(self, tmp_db):
        tmp_db.insert_entry(_entry("Oppenheimer"))
        tmp_db.upsert_rating(_rating("Oppenheimer", score=4.5))
        html = build_dashboard_html(tmp_db.all_rated_entries())
        assert "4.5" in html
