"""
src/services/watchmode.py
Watchmode API integration — resolves streaming platform availability.
"""

import logging
import re

import requests

from src.services.errors import ExternalAPIError
from src.services.retry import call_with_retries

logger = logging.getLogger(__name__)

# Channel add-ons ride along inside other services ("HBO (Via Hulu)",
# "MAX (Via Amazon Prime)"). Only primary services interest us.
_ADDON_NAME_RE = re.compile(r"\(via", re.IGNORECASE)


class WatchmodeClient:
    BASE_URL = "https://api.watchmode.com/v1"

    def __init__(
        self,
        api_key: str,
        session: requests.Session | None = None,
        retries: int = 3,
        backoff: float = 0.5,
        region: str = "US",
    ) -> None:
        self.api_key = api_key
        self._session = session or requests.Session()
        self.retries = retries
        self.backoff = backoff
        self.region = region

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def fetch_platforms(self, imdb_id: str | None, title_query: str = "") -> str:
        """
        Returns a raw comma-separated list of platform names, e.g.
          'Netflix,Hulu'
          'Amazon,Apple TV+'
          '' (empty string when the title has no listed sources)

        Raises ExternalAPIError when the API is unreachable or failing —
        callers can then skip the update instead of persisting empty data.
        """
        results = self._search(imdb_id, title_query)
        watchmode_id = self._extract_id(results)

        if watchmode_id is None:
            return ""

        return self._resolve_sources(watchmode_id)

    # ------------------------------------------------------------------ #
    # HTTP helper                                                          #
    # ------------------------------------------------------------------ #

    def _get_json(self, path: str, params: dict):
        """GET with retries; raises ExternalAPIError on final failure."""
        try:
            resp = call_with_retries(
                self._session.get,
                f"{self.BASE_URL}{path}",
                params=params,
                timeout=10,
                retries=self.retries,
                backoff=self.backoff,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as exc:
            raise ExternalAPIError(f"Watchmode request failed: {path}") from exc
        except ValueError as exc:  # includes json.JSONDecodeError
            raise ExternalAPIError(f"Watchmode returned invalid JSON: {path}") from exc

    @staticmethod
    def _results_from(data) -> list:
        """Normalize the various search response shapes."""
        if isinstance(data, dict):
            return (
                data.get("title_results")
                or data.get("results")
                or data.get("autocomplete")
                or []
            )
        if isinstance(data, list):
            return data
        return []

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _search(self, imdb_id: str | None, title_query: str) -> list:
        """Runs IMDb-ID search first, falls back to name search."""
        if imdb_id:
            results = self._search_by_imdb_id(imdb_id)
            if results:
                return results

        if title_query:
            return self._search_by_name(title_query)

        return []

    def _search_by_imdb_id(self, imdb_id: str) -> list:
        data = self._get_json("/search/", {
            "apiKey": self.api_key,
            "search_field": "imdb_id",
            "search_value": imdb_id,
        })
        return self._results_from(data)

    def _search_by_name(self, title_query: str) -> list:
        clean = title_query.replace("-", " ").strip()
        data = self._get_json("/search/", {
            "apiKey": self.api_key,
            "search_field": "name",
            "search_value": clean,
        })
        return self._results_from(data)

    @staticmethod
    def _extract_id(results: list) -> int | None:
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
        data = self._get_json(
            f"/title/{watchmode_id}/sources/",
            {"apiKey": self.api_key, "regions": self.region},
        )

        if not isinstance(data, list):
            raise ExternalAPIError(
                f"Unexpected sources payload for watchmode id {watchmode_id}"
            )

        sub_platforms: list[str] = []
        rent_platforms: list[str] = []

        for source in data:
            if not isinstance(source, dict):
                continue
            name = source.get("name")
            s_type = source.get("type")
            if not name or _ADDON_NAME_RE.search(name):
                continue  # skip add-on channels
            if s_type in ("sub", "free") and name not in sub_platforms:
                sub_platforms.append(name)
            elif s_type in ("rent", "buy") and name not in rent_platforms:
                rent_platforms.append(name)

        # Prefer subscription/free; fall back to rent/buy. Cap at 4 total.
        platforms = sub_platforms[:4] or rent_platforms[:4]
        return ",".join(platforms)
