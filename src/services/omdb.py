"""
src/services/omdb.py
OMDb API integration — fetches media metadata including genres.
"""

import logging
from dataclasses import dataclass, field

import requests

from src.services.retry import retryable

logger = logging.getLogger(__name__)


@dataclass
class MediaMeta:
    content_type: str       # 'movie' | 'tv'
    poster: str
    title: str
    imdb_id: str | None
    genres: list[str] = field(default_factory=list)  # e.g. ['Action', 'Drama']


class OmdbClient:
    BASE_URL = "http://www.omdbapi.com/"

    def __init__(self, api_key: str, session: requests.Session | None = None) -> None:
        self.api_key = api_key
        self._session = session or requests.Session()

    @retryable()
    def _request(self, title_query: str) -> dict:
        resp = self._session.get(
            self.BASE_URL,
            params={"t": title_query, "apikey": self.api_key},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def fetch(self, title_query: str) -> MediaMeta:
        """
        Query OMDb by title. Returns a MediaMeta with best-effort values —
        never raises; on any failure returns a safe default.
        """
        try:
            data = self._request(title_query)

            if data.get("Response") == "True":
                content_type = "tv" if data.get("Type") == "series" else "movie"
                poster = data.get("Poster", "")
                if poster == "N/A":
                    poster = ""
                raw_genres = data.get("Genre", "")
                genres = (
                    [g.strip() for g in raw_genres.split(",") if g.strip()]
                    if raw_genres and raw_genres != "N/A"
                    else []
                )
                return MediaMeta(
                    content_type=content_type,
                    poster=poster,
                    title=data.get("Title", title_query),
                    imdb_id=data.get("imdbID"),
                    genres=genres,
                )
        except Exception as exc:  # pragma: no cover
            logger.error("OMDb error for '%s': %s", title_query, exc)

        return MediaMeta(
            content_type="movie",
            poster="",
            title=title_query,
            imdb_id=None,
            genres=[],
        )
