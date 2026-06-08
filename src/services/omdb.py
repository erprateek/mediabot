"""
src/services/omdb.py
OMDb API integration — fetches media metadata.
"""

from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class MediaMeta:
    content_type: str   # 'movie' | 'tv'
    poster: str
    title: str
    imdb_id: Optional[str]


class OmdbClient:
    BASE_URL = "http://www.omdbapi.com/"

    def __init__(self, api_key: str, session: Optional[requests.Session] = None) -> None:
        self.api_key = api_key
        self._session = session or requests.Session()

    def fetch(self, title_query: str) -> MediaMeta:
        """
        Query OMDb by title. Returns a MediaMeta with best-effort values —
        never raises; on any failure returns a safe default.
        """
        try:
            resp = self._session.get(
                self.BASE_URL,
                params={"t": title_query, "apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("Response") == "True":
                content_type = "tv" if data.get("Type") == "series" else "movie"
                poster = data.get("Poster", "")
                if poster == "N/A":
                    poster = ""
                return MediaMeta(
                    content_type=content_type,
                    poster=poster,
                    title=data.get("Title", title_query),
                    imdb_id=data.get("imdbID"),
                )
        except Exception as exc:  # pragma: no cover
            print(f"OMDb error for '{title_query}': {exc}")

        return MediaMeta(
            content_type="movie",
            poster="",
            title=title_query,
            imdb_id=None,
        )
