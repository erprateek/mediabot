"""
tests/unit/test_omdb.py
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.services.omdb import OmdbClient, MediaMeta


def _mock_session(json_data: dict, raise_exc=None) -> MagicMock:
    session = MagicMock(spec=requests.Session)
    if raise_exc:
        session.get.side_effect = raise_exc
    else:
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        session.get.return_value = resp
    return session


class TestOmdbClient:
    def _client(self, json_data=None, raise_exc=None) -> OmdbClient:
        return OmdbClient("fake_key", session=_mock_session(json_data or {}, raise_exc))

    def test_movie_returned_correctly(self):
        client = self._client({
            "Response": "True",
            "Type": "movie",
            "Title": "The Batman",
            "Poster": "https://example.com/poster.jpg",
            "imdbID": "tt1877830",
        })
        meta = client.fetch("batman")
        assert meta.content_type == "movie"
        assert meta.title == "The Batman"
        assert meta.imdb_id == "tt1877830"
        assert meta.poster == "https://example.com/poster.jpg"

    def test_series_mapped_to_tv(self):
        client = self._client({
            "Response": "True",
            "Type": "series",
            "Title": "Breaking Bad",
            "Poster": "",
            "imdbID": "tt0903747",
        })
        meta = client.fetch("breaking bad")
        assert meta.content_type == "tv"

    def test_na_poster_normalised_to_empty_string(self):
        client = self._client({
            "Response": "True",
            "Type": "movie",
            "Title": "Rare Film",
            "Poster": "N/A",
            "imdbID": "tt9999999",
        })
        meta = client.fetch("rare film")
        assert meta.poster == ""

    def test_api_response_false_returns_default(self):
        client = self._client({"Response": "False", "Error": "Movie not found!"})
        meta = client.fetch("xyzzy unknown title")
        assert meta.content_type == "movie"
        assert meta.title == "xyzzy unknown title"
        assert meta.imdb_id is None

    def test_network_exception_returns_default(self):
        client = self._client(raise_exc=requests.exceptions.ConnectionError("down"))
        meta = client.fetch("some title")
        assert meta.title == "some title"
        assert meta.imdb_id is None
