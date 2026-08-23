"""
tests/unit/test_ollama.py
"""

from unittest.mock import MagicMock

import requests

from src.services.ollama import OllamaClient


def _make_client(response_text: str = "", raise_exc=None) -> OllamaClient:
    session = MagicMock(spec=requests.Session)
    if raise_exc:
        session.post.side_effect = raise_exc
    else:
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        resp.json.return_value = {"message": {"content": response_text}}
        session.post.return_value = resp
    return OllamaClient(session=session, retries=1)


class TestParseWatchMessage:
    def test_title_and_rating_parsed(self):
        client = _make_client('{"title": "The Batman", "rating": 4.0, "comment": null}')
        result = client.parse_watch_message("just watched the batman, 4/5")
        assert result.title == "The Batman"
        assert result.rating == 4.0
        assert result.comment is None

    def test_title_only(self):
        client = _make_client('{"title": "Interstellar", "rating": null, "comment": null}')
        result = client.parse_watch_message("Interstellar")
        assert result.title == "Interstellar"
        assert result.rating is None

    def test_rating_with_comment(self):
        client = _make_client('{"title": "Dune", "rating": 4.5, "comment": "loved it"}')
        result = client.parse_watch_message("Dune, loved it, 4.5/5")
        assert result.rating == 4.5
        assert result.comment == "loved it"

    def test_rating_clamped_to_5(self):
        client = _make_client('{"title": "Movie", "rating": 9.0, "comment": null}')
        result = client.parse_watch_message("Movie 9/10")
        assert result.rating == 5.0

    def test_rating_clamped_to_0(self):
        client = _make_client('{"title": "Movie", "rating": -1.0, "comment": null}')
        result = client.parse_watch_message("Movie was terrible")
        assert result.rating == 0.0

    def test_markdown_fences_stripped(self):
        client = _make_client('```json\n{"title": "Dune", "rating": 4.0, "comment": null}\n```')
        result = client.parse_watch_message("Dune 4/5")
        assert result.title == "Dune"
        assert result.rating == 4.0

    def test_connection_error_fallback(self):
        client = _make_client(raise_exc=requests.exceptions.ConnectionError("refused"))
        result = client.parse_watch_message("The Batman")
        assert result.title == "The Batman"
        assert result.rating is None
        assert result.comment is None

    def test_timeout_fallback(self):
        client = _make_client(raise_exc=requests.exceptions.Timeout())
        result = client.parse_watch_message("Dune")
        assert result.title == "Dune"
        assert result.rating is None

    def test_malformed_json_fallback(self):
        client = _make_client("not json at all")
        result = client.parse_watch_message("Interstellar")
        assert result.title == "Interstellar"
        assert result.rating is None

    def test_missing_title_uses_raw_text(self):
        client = _make_client('{"title": "", "rating": null, "comment": null}')
        result = client.parse_watch_message("Oppenheimer")
        assert result.title == "Oppenheimer"
