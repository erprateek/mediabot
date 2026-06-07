"""
tests/integration/test_dashboard.py
Uses FastAPI's TestClient — no live server needed.
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from src.api.dashboard import create_app, build_dashboard_html
from src.db.database import Database, WatchEntry


def _entry(title: str, content_type: str = "movie") -> WatchEntry:
    return WatchEntry(
        user="Alice",
        title=title,
        rating="8/10",
        date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        content_type=content_type,
        poster="",
        imdb_id="tt0000001",
        platforms="📺 Stream on: Netflix",
    )


@pytest.fixture
def client(tmp_db):
    app = create_app(tmp_db)
    return TestClient(app), tmp_db


class TestHealthEndpoint:
    def test_health_ok(self, client):
        tc, _ = client
        resp = tc.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestDashboard:
    def test_empty_db_renders_placeholders(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert resp.status_code == 200
        assert "No movies logged yet" in resp.text
        assert "No TV shows logged yet" in resp.text

    def test_movie_appears_in_movies_grid(self, client):
        tc, db = client
        db.insert_entry(_entry("Inception", "movie"))
        resp = tc.get("/")
        assert "Inception" in resp.text

    def test_tv_show_appears_in_tv_grid(self, client):
        tc, db = client
        db.insert_entry(_entry("The Wire", "tv"))
        resp = tc.get("/")
        assert "The Wire" in resp.text

    def test_html_content_type(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert "text/html" in resp.headers["content-type"]


class TestBuildDashboardHtml:
    def test_no_entries_shows_no_data(self):
        html = build_dashboard_html([])
        assert "No movies logged yet" in html
        assert "No TV shows logged yet" in html

    def test_avatar_is_first_letter_of_user(self):
        html = build_dashboard_html([_entry("Dune")])
        assert "<div class=\"avatar\">A</div>" in html
