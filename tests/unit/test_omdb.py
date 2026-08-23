"""
tests/unit/test_omdb.py
"""

from unittest.mock import MagicMock

import requests

from src.services.omdb import OmdbClient


def _mock_session(json_data, raise_exc=None):
    session = MagicMock(spec=requests.Session)
    if raise_exc:
        session.get.side_effect = raise_exc
    else:
        resp = MagicMock()
        resp.json.return_value = json_data
        resp.raise_for_status.return_value = None
        session.get.return_value = resp
    return session

def _client(json_data=None, raise_exc=None):
    return OmdbClient("fake_key", session=_mock_session(json_data or {}, raise_exc))


class TestOmdbClient:
    def test_movie_returned_correctly(self):
        meta = _client({"Response":"True","Type":"movie","Title":"The Batman",
                         "Poster":"https://example.com/p.jpg","imdbID":"tt1877830",
                         "Genre":"Action, Crime", "Year": "2022"}).fetch("batman")
        assert meta.content_type == "movie"
        assert meta.title == "The Batman"
        assert meta.imdb_id == "tt1877830"
        assert meta.genres == ["Action", "Crime"]
        assert meta.year == "2022"

    def test_na_year_normalised(self):
        meta = _client({"Response":"True","Type":"movie","Title":"Old Film",
                         "Poster":"","imdbID":"tt0000003","Year":"N/A"}).fetch("old film")
        assert meta.year == ""

    def test_series_mapped_to_tv(self):
        meta = _client({
            "Response": "True", "Type": "series", "Title": "Breaking Bad",
            "Poster": "", "imdbID": "tt0903747", "Genre": "Crime, Drama",
        }).fetch("breaking bad")
        assert meta.content_type == "tv"
        assert meta.genres == ["Crime", "Drama"]

    def test_na_poster_normalised(self):
        meta = _client({"Response":"True","Type":"movie","Title":"Rare Film",
                         "Poster":"N/A","imdbID":"tt9999999","Genre":"Drama"}).fetch("rare film")
        assert meta.poster == ""

    def test_na_genre_returns_empty_list(self):
        meta = _client({"Response":"True","Type":"movie","Title":"Silent Film",
                         "Poster":"","imdbID":"tt0000001","Genre":"N/A"}).fetch("silent film")
        assert meta.genres == []

    def test_plot_actors_director_extracted(self):
        meta = _client({
            "Response": "True", "Type": "movie", "Title": "The Batman",
            "Poster": "", "imdbID": "tt1877830", "Genre": "Action",
            "Plot": "When a sadistic serial killer leaves behind a cryptic trail...",
            "Actors": "Robert Pattinson, Zoë Kravitz, Colin Farrell",
            "Director": "Matt Reeves",
        }).fetch("batman")
        assert meta.plot.startswith("When a sadistic serial killer")
        assert meta.actors == ["Robert Pattinson", "Zoë Kravitz", "Colin Farrell"]
        assert meta.director == "Matt Reeves"

    def test_na_plot_actors_director_normalised(self):
        meta = _client({
            "Response": "True", "Type": "movie", "Title": "Obscure Film",
            "Poster": "", "imdbID": "tt0000009",
            "Plot": "N/A", "Actors": "N/A", "Director": "N/A",
        }).fetch("obscure film")
        assert meta.plot == ""
        assert meta.actors == []
        assert meta.director == ""

    def test_missing_genre_returns_empty_list(self):
        meta = _client({"Response":"True","Type":"movie","Title":"No Genre",
                         "Poster":"","imdbID":"tt0000002"}).fetch("no genre")
        assert meta.genres == []

    def test_api_false_returns_default(self):
        meta = _client({"Response":"False","Error":"Movie not found!"}).fetch("xyzzy")
        assert meta.content_type == "movie"
        assert meta.imdb_id is None
        assert meta.genres == []

    def test_network_exception_returns_default(self):
        meta = _client(raise_exc=requests.exceptions.ConnectionError("down")).fetch("title")
        assert meta.imdb_id is None
        assert meta.genres == []
