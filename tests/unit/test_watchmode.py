"""
tests/unit/test_watchmode.py
"""

from unittest.mock import MagicMock, call

import pytest
import requests

from src.services.watchmode import WatchmodeClient


def _make_client(responses: list) -> WatchmodeClient:
    """
    responses: list of dicts (or exceptions) returned by successive session.get() calls.
    """
    session = MagicMock(spec=requests.Session)
    side_effects = []
    for r in responses:
        if isinstance(r, Exception):
            side_effects.append(r)
        else:
            resp = MagicMock()
            resp.raise_for_status.return_value = None
            resp.json.return_value = r
            side_effects.append(resp)
    session.get.side_effect = side_effects
    return WatchmodeClient("fake_key", session=session)


class TestFetchPlatforms:
    def test_stream_result(self):
        client = _make_client([
            # search by IMDb ID
            {"title_results": [{"id": 123, "resultType": "movie"}]},
            # sources
            [{"name": "Netflix", "type": "sub"}, {"name": "Hulu", "type": "sub"}],
        ])
        result = client.fetch_platforms("tt1234567")
        assert result == "📺 Stream on: Netflix, Hulu"

    def test_rent_result_when_no_subscription(self):
        client = _make_client([
            {"title_results": [{"id": 456}]},
            [{"name": "Amazon", "type": "rent"}, {"name": "Apple TV", "type": "buy"}],
        ])
        result = client.fetch_platforms("tt9999999")
        assert result == "💰 Rent/Buy on: Amazon, Apple TV"

    def test_fallback_to_name_search_when_imdb_misses(self):
        client = _make_client([
            # IMDb search returns empty
            {"title_results": []},
            # name fallback returns a match
            {"title_results": [{"id": 789}]},
            # sources
            [{"name": "Disney+", "type": "sub"}],
        ])
        result = client.fetch_platforms("tt0000000", "Encanto")
        assert "Disney+" in result

    def test_no_results_returns_fallback_message(self):
        client = _make_client([
            {"title_results": []},  # imdb search
            {"title_results": []},  # name search
        ])
        result = client.fetch_platforms("tt0000001", "Unknown Movie")
        assert result == "Streaming platform reference missed"

    def test_person_results_skipped(self):
        client = _make_client([
            {"title_results": [
                {"id": 1, "resultType": "person"},
                {"id": 2, "resultType": "movie"},
            ]},
            [{"name": "Peacock", "type": "sub"}],
        ])
        result = client.fetch_platforms("tt0000002")
        assert "Peacock" in result

    def test_network_error_returns_fallback(self):
        client = _make_client([requests.exceptions.ConnectionError("down")])
        result = client.fetch_platforms("tt0000003")
        assert result == "Streaming platform reference missed"

    def test_no_platforms_found(self):
        client = _make_client([
            {"title_results": [{"id": 999}]},
            [],  # empty sources
        ])
        result = client.fetch_platforms("tt0000004")
        assert result == "Not currently streaming anywhere"
