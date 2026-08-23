"""
src/services/watchmode.py
Watchmode API integration — resolves streaming platform availability.
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class WatchmodeClient:
    BASE_URL = "https://api.watchmode.com/v1"

    def __init__(self, api_key: str, session: Optional[requests.Session] = None) -> None:
        self.api_key = api_key
        self._session = session or requests.Session()

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def fetch_platforms(self, imdb_id: Optional[str], title_query: str = "") -> str:
        """
        Returns a raw comma-separated list of platform names, e.g.
          'Netflix,Hulu'
          'Amazon,Apple TV+'
          '' (empty string when nothing is found)
        Never raises.
        """
        results = self._search(imdb_id, title_query)
        watchmode_id = self._extract_id(results)

        if watchmode_id is None:
            return ""

        return self._resolve_sources(watchmode_id)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _search(self, imdb_id: Optional[str], title_query: str) -> list:
        """Runs IMDb-ID search first, falls back to name search."""
        if imdb_id:
            results = self._search_by_imdb_id(imdb_id)
            if results:
                return results

        if title_query:
            return self._search_by_name(title_query)

        return []

    def _search_by_imdb_id(self, imdb_id: str) -> list:
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/search/",
                params={
                    "apiKey": self.api_key,
                    "search_field": "imdb_id",
                    "search_value": imdb_id,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data.get("title_results") or data.get("results") or []
            if isinstance(data, list):
                return data
        except Exception as exc:
            logger.error("Watchmode IMDb search error: %s", exc)
        return []

    def _search_by_name(self, title_query: str) -> list:
        clean = title_query.replace("-", " ").strip()
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/search/",
                params={
                    "apiKey": self.api_key,
                    "search_field": "name",
                    "search_value": clean,
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                results = data.get("title_results", [])
                if not results:
                    results = data.get("results", data.get("autocomplete", []))
                return results
            if isinstance(data, list):
                return data
        except Exception as exc:
            logger.error("Watchmode name search error: %s", exc)
        return []

    @staticmethod
    def _extract_id(results: list) -> Optional[int]:
        for item in results:
            if not isinstance(item, dict):
                continue
            if item.get("resultType") == "person":
                continue
            wid = item.get("id") or item.get("title_id") or item.get("watchmode_id")
            if wid:
                return wid
        return None

    def _resolve_sources(self, watchmode_id: int) -> str:
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/title/{watchmode_id}/sources/",
                params={"apiKey": self.api_key, "regions": "US"},
                timeout=10,
            )
            resp.raise_for_status()
            sources = resp.json()

            if not isinstance(sources, list):
                return "Not available on subscription services"

            sub_platforms: list[str] = []
            rent_platforms: list[str] = []

            for source in sources:
                if not isinstance(source, dict):
                    continue
                name = source.get("name")
                s_type = source.get("type")
                if not name:
                    continue
                if s_type in ("sub", "free") and name not in sub_platforms:
                    sub_platforms.append(name)
                elif s_type in ("rent", "buy") and name not in rent_platforms:
                    rent_platforms.append(name)

            # Prefer subscription/free; fall back to rent/buy. Cap at 4 total.
            platforms = sub_platforms[:4] or rent_platforms[:4]
            return ",".join(platforms)

        except Exception as exc:
            logger.error("Watchmode source retrieval error: %s", exc)

        return ""
