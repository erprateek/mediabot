"""
src/services/ollama.py

Local Ollama integration — parses a free-form /watch message into structured
data using the Gemma model running on the same machine.

The model is asked to return ONLY a JSON object. We try to parse it cleanly;
if anything fails we fall back to treating the whole text as a title with no
rating so the rest of the pipeline always has something to work with.

Expected JSON schema:
  {
    "title":   "The Batman",       -- required, string
    "rating":  4.5,                -- optional, float 0-5 or null
    "comment": "loved the score"   -- optional, string (ignored for now, future use)
  }
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

import requests

from src.services.retry import call_with_retries

logger = logging.getLogger(__name__)


@dataclass
class ParsedWatch:
    title: str
    rating: Optional[float]     # 0.0 – 5.0, or None if user didn't mention one
    comment: Optional[str]


_SYSTEM_PROMPT = """\
You are a media-logging assistant embedded in a Telegram bot.
Your ONLY job is to parse a user's message into a JSON object.

Rules:
- Extract the movie or TV show title as precisely as possible.
- If the user mentioned a rating (out of 5, or out of 10 which you convert to /5), extract it as a float between 0 and 5.
- If no rating is mentioned, set "rating" to null.
- If the user included a short opinion or comment, put it in "comment", otherwise null.
- Return ONLY valid JSON. No explanation, no markdown, no code fences.

JSON schema:
{"title": "string", "rating": float_or_null, "comment": "string_or_null"}

Examples:
  Input:  "just watched Dune part 2, solid 4/5"
  Output: {"title": "Dune Part Two", "rating": 4.0, "comment": null}

  Input:  "The Bear season 3 was incredible, 9/10"
  Output: {"title": "The Bear", "rating": 4.5, "comment": "incredible"}

  Input:  "Interstellar"
  Output: {"title": "Interstellar", "rating": null, "comment": null}

  Input:  "finally watched Oppenheimer, i'd give it a 3.5 out of 5, a bit long"
  Output: {"title": "Oppenheimer", "rating": 3.5, "comment": "a bit long"}
"""


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "gemma3:12b-it-qat",
        session: Optional[requests.Session] = None,
        timeout: int = 30,
        retries: int = 3,
        backoff: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self._session = session or requests.Session()

    def _post_chat(self, raw_text: str) -> requests.Response:
        return self._session.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": raw_text},
                ],
            },
            timeout=self.timeout,
        )

    def _chat(self, raw_text: str) -> requests.Response:
        return call_with_retries(
            self._post_chat, raw_text,
            retries=self.retries, backoff=self.backoff,
        )

    def parse_watch_message(self, raw_text: str) -> ParsedWatch:
        """
        Send raw_text to the local Ollama model and return a ParsedWatch.
        Never raises — falls back to ParsedWatch(title=raw_text, rating=None)
        if the model is unavailable or returns unparseable output.
        """
        try:
            resp = self._chat(raw_text)
            resp.raise_for_status()
            content = resp.json()["message"]["content"].strip()
            return self._parse_response(content, raw_text)

        except requests.exceptions.ConnectionError:
            logger.warning("Ollama connection refused at %s — falling back to raw text", self.base_url)
        except requests.exceptions.Timeout:
            logger.warning("Ollama request timed out after %ss — falling back", self.timeout)
        except Exception as exc:
            logger.error("Ollama unexpected error: %s — falling back", exc)

        return ParsedWatch(title=raw_text.strip(), rating=None, comment=None)

    # ------------------------------------------------------------------ #
    # Private                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_response(content: str, fallback_title: str) -> ParsedWatch:
        """
        Extract JSON from the model output. Handles cases where the model
        wraps its answer in markdown code fences despite being told not to.
        """
        # Strip ```json ... ``` or ``` ... ``` fences if present
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if fenced:
            content = fenced.group(1)

        # Find the first {...} block in the response
        brace = re.search(r"\{.*\}", content, re.DOTALL)
        if not brace:
            logger.warning("No JSON object found in response: %r", content)
            return ParsedWatch(title=fallback_title.strip(), rating=None, comment=None)

        try:
            data = json.loads(brace.group())
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error: %s — raw: %r", exc, brace.group())
            return ParsedWatch(title=fallback_title.strip(), rating=None, comment=None)

        title = str(data.get("title") or fallback_title).strip()
        if not title:
            title = fallback_title.strip()

        raw_rating = data.get("rating")
        rating: Optional[float] = None
        if raw_rating is not None:
            try:
                rating = max(0.0, min(5.0, float(raw_rating)))
            except (TypeError, ValueError):
                rating = None

        comment = data.get("comment") or None
        if comment:
            comment = str(comment).strip() or None

        return ParsedWatch(title=title, rating=rating, comment=comment)
