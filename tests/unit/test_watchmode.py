"""
tests/unit/test_watchmode.py
"""

from unittest.mock import MagicMock

import pytest
import requests

from src.services.errors import ExternalAPIError
from src.services.watchmode import WatchmodeClient


def _make_client(responses: list, retries: int = 1) -> WatchmodeClient:
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
    return WatchmodeClient("fake_key", session=session, retries=retries)


class TestFetchPlatforms:
    def test_stream_result(self):
        client = _make_client([
            {"title_results": [{"id": 123, "resultType": "movie"}]},
            [{"name": "Netflix", "type": "sub"}, {"name": "Hulu", "type": "sub"}],
        ])
        result = client.fetch_platforms("tt1234567")
        assert result == "Netflix,Hulu"

    def test_rent_result_when_no_subscription(self):
        client = _make_client([
            {"title_results": [{"id": 456}]},
            [{"name": "Amazon", "type": "rent"}, {"name": "Apple TV+", "type": "buy"}],
        ])
        result = client.fetch_platforms("tt9999999")
        assert result == "Amazon,Apple TV+"

    def test_fallback_to_name_search_when_imdb_misses(self):
        client = _make_client([
            {"title_results": []},
            {"title_results": [{"id": 789}]},
            [{"name": "Disney+", "type": "sub"}],
        ])
        result = client.fetch_platforms("tt0000000", "Encanto")
        assert "Disney+" in result

    def test_no_results_returns_empty_string(self):
        client = _make_client([
            {"title_results": []},
            {"title_results": []},
        ])
        result = client.fetch_platforms("tt0000001", "Unknown Movie")
        assert result == ""

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

    def test_network_error_raises_external_api_error(self):
        client = _make_client([requests.exceptions.ConnectionError("down")])
        with pytest.raises(ExternalAPIError):
            client.fetch_platforms("tt0000003")

    def test_transient_error_retries_then_succeeds(self):
        # First IMDb search call fails once (retries=2), then succeeds;
        # followed by the sources call.
        client = _make_client([
            requests.exceptions.ConnectionError("blip"),
            {"title_results": [{"id": 321}]},
            [{"name": "Netflix", "type": "sub"}],
        ], retries=2)
        assert client.fetch_platforms("tt0000123") == "Netflix"

    def test_invalid_json_raises_external_api_error(self):
        session = MagicMock(spec=requests.Session)
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.side_effect = ValueError("bad json")
        session.get.return_value = resp
        client = WatchmodeClient("fake_key", session=session, retries=1)
        with pytest.raises(ExternalAPIError):
            client.fetch_platforms("tt0000009")

    def test_no_platforms_found_returns_empty_string(self):
        client = _make_client([
            {"title_results": [{"id": 999}]},
            [],
        ])
        result = client.fetch_platforms("tt0000004")
        assert result == ""

    def test_caps_at_four_platforms(self):
        client = _make_client([
            {"title_results": [{"id": 111}]},
            [
                {"name": "Netflix",    "type": "sub"},
                {"name": "Hulu",       "type": "sub"},
                {"name": "Max",        "type": "sub"},
                {"name": "Disney+",    "type": "sub"},
                {"name": "Peacock",    "type": "sub"},
            ],
        ])
        result = client.fetch_platforms("tt0000005")
        assert result.count(",") == 3   # 4 platforms = 3 commas
        assert "Peacock" not in result

    def test_sub_preferred_over_rent(self):
        client = _make_client([
            {"title_results": [{"id": 222}]},
            [
                {"name": "Amazon",  "type": "rent"},
                {"name": "Netflix", "type": "sub"},
            ],
        ])
        result = client.fetch_platforms("tt0000006")
        assert result == "Netflix"
        assert "Amazon" not in result

    def test_addon_channels_filtered_out(self):
        # Real payload shape for HBO Max content: the primary service plus
        # channel add-ons riding inside Prime/Hulu.
        client = _make_client([
            {"title_results": [{"id": 3171309}]},
            [
                {"name": "MAX (Via Amazon Prime)", "type": "sub"},
                {"name": "HBO Max",                "type": "sub"},
                {"name": "HBO (Via Hulu)",         "type": "sub"},
            ],
        ])
        assert client.fetch_platforms("tt0000007") == "HBO Max"

    def test_addons_do_not_count_toward_four_cap(self):
        client = _make_client([
            {"title_results": [{"id": 444}]},
            [
                {"name": "Showtime (Via Prime Video)", "type": "sub"},
                {"name": "Paramount+ (Via Prime Video)", "type": "sub"},
                {"name": "Netflix",  "type": "sub"},
                {"name": "Hulu",     "type": "sub"},
                {"name": "Disney+",  "type": "sub"},
                {"name": "Peacock",  "type": "sub"},
            ],
        ])
        result = client.fetch_platforms("tt0000008")
        assert result == "Netflix,Hulu,Disney+,Peacock"
