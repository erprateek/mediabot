"""
src/api/dashboard.py
FastAPI routes for the web dashboard.

HTML is rendered with Jinja2 (autoescaping on) from templates/dashboard.html.j2.
Static CSS/JS live in static/. Card/modal data is exposed via GET /api/entries;
the client fetches it instead of receiving inline JSON blobs in attributes.
"""

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.db.database import Database, RatedEntry

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

FALLBACK_POSTER = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300"


# ---------------------------------------------------------------------------
# Platform badge config
# ---------------------------------------------------------------------------
_LOGOS = "/static/logos"

_PLATFORMS: dict[str, dict] = {
    "Netflix":     {"bg": "#E50914", "fg": "#fff",  "label": "N",
                    "logo": f"{_LOGOS}/netflix.svg"},
    "Hulu":        {"bg": "#1CE783", "fg": "#000",  "label": "H",
                    "logo": f"{_LOGOS}/hulu.svg"},
    "Max":         {"bg": "#002BE7", "fg": "#fff",  "label": "max",
                    "logo": f"{_LOGOS}/max.svg"},
    "HBO Max":     {"bg": "#002BE7", "fg": "#fff",  "label": "max",
                    "logo": f"{_LOGOS}/max.svg"},
    "HBO":         {"bg": "#9E7DFF", "fg": "#fff",  "label": "HBO",
                    "logo": f"{_LOGOS}/hbo.svg"},
    "Disney+":     {"bg": "#113CCF", "fg": "#fff",  "label": "D+"},
    "Apple TV+":   {"bg": "#F5F5F7", "fg": "#000",  "label": "tv",
                    "logo": f"{_LOGOS}/appletv.svg"},
    "Prime Video": {"bg": "#00A8E1", "fg": "#fff",  "label": "P",
                    "logo": f"{_LOGOS}/primevideo.svg"},
    "Paramount+":  {"bg": "#0064FF", "fg": "#fff",  "label": "P+",
                    "logo": f"{_LOGOS}/paramountplus.svg"},
    "Peacock":     {"bg": "#FDB813", "fg": "#fff",  "label": "Pc"},
    "Tubi":        {"bg": "#FA2D27", "fg": "#fff",  "label": "T",
                    "logo": f"{_LOGOS}/tubi.svg"},
    "Showtime":    {"bg": "#CC0000", "fg": "#fff",  "label": "SHO",
                    "logo": f"{_LOGOS}/showtime.svg"},
    "Starz":       {"bg": "#FFFFFF", "fg": "#000",  "label": "★",
                    "logo": f"{_LOGOS}/starz.svg"},
}

_AVATAR_COLORS = ["#534AB7", "#0F6E56", "#993C1D", "#185FA5",
                  "#854F0B", "#993556", "#3B6D11"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_list(raw: str) -> list[str]:
    """'Netflix,Hulu' → ['Netflix', 'Hulu']. Strips legacy emoji prefixes."""
    if not raw:
        return []
    raw = raw.replace("📺 Stream on: ", "").replace("💰 Rent/Buy on: ", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _avatar_color(name: str) -> str:
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return _AVATAR_COLORS[abs(h) % len(_AVATAR_COLORS)]


def _picon(name: str) -> dict:
    p = _PLATFORMS.get(name, {"bg": "#888", "fg": "#fff", "label": name[:2].upper()})
    return {
        "name": name, "bg": p["bg"], "fg": p["fg"],
        "label": p["label"], "logo": p.get("logo", ""),
    }


def _entry_to_dict(re: RatedEntry) -> dict:
    e = re.entry
    scores = [r.score for r in re.ratings]
    users = [r.user for r in re.ratings]
    ratings_payload = [
        {"user": u, "score": s} for u, s in zip(users, scores, strict=True)
    ]
    avg = round(sum(scores) / len(scores), 1) if scores else None
    first_user = users[0] if users else e.user
    platforms = _parse_list(e.platforms)
    icons = [_picon(p) for p in platforms]
    return {
        "title":        e.title,
        "poster":       e.poster,
        "content_type": e.content_type,
        "platforms":    platforms,
        "genres":       _parse_list(e.genres),
        "year":         e.year,
        "ratings":      ratings_payload,
        "added_by":     e.user,
        "date":         e.date,
        # OMDb enrichment
        "plot":         e.plot,
        "actors":       _parse_list(e.actors),
        "director":     e.director,
        # Render-only fields
        "avg":          avg,
        "first_user":   first_user,
        "avatar_bg":    _avatar_color(first_user),
        "pstrip": {
            "icons": icons[:3],
            "more": max(0, len(icons) - 3),
        },
        "pbadges": icons,
    }


_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "j2"]),
)
_template = _env.get_template("dashboard.html.j2")


def build_dashboard_html(rated_entries: list[RatedEntry]) -> str:
    movies = [re for re in rated_entries if re.entry.content_type != "tv"]
    tv     = [re for re in rated_entries if re.entry.content_type == "tv"]

    movie_dicts = [_entry_to_dict(re) for re in movies]
    tv_dicts    = [_entry_to_dict(re) for re in tv]

    def unique_genres(dicts: list[dict]) -> list[str]:
        seen: list[str] = []
        for d in dicts:
            for g in d["genres"]:
                if g not in seen:
                    seen.append(g)
        return seen

    movie_genres = unique_genres(movie_dicts)
    tv_genres    = unique_genres(tv_dicts)
    all_genres   = unique_genres(movie_dicts + tv_dicts)

    return _template.render(
        n_movies=len(movies),
        n_tv=len(tv),
        movies=movie_dicts,
        tv=tv_dicts,
        all_genres=all_genres,
        movie_genres=movie_genres,
        tv_genres=tv_genres,
        platforms_json=json.dumps(_PLATFORMS),
        fallback_poster=FALLBACK_POSTER,
    )


def create_app(db: Database) -> FastAPI:
    app = FastAPI(title="Media Lounge")
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def web_dashboard() -> str:
        rated_entries = await asyncio.to_thread(db.all_rated_entries)
        return build_dashboard_html(rated_entries)

    @app.get("/api/entries")
    async def api_entries() -> list[dict]:
        rated_entries = await asyncio.to_thread(db.all_rated_entries)
        return [_entry_to_dict(re) for re in rated_entries]

    @app.get("/api/duplicates")
    async def api_duplicates() -> list[dict]:
        """Likely duplicate titles (fuzzy-matched pairs) for cleanup."""
        return await asyncio.to_thread(db.duplicate_candidates)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app
