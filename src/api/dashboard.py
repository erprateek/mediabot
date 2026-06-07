"""
src/api/dashboard.py
FastAPI routes for the web dashboard.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.db.database import Database, WatchEntry


def _card_html(entry: WatchEntry) -> str:
    initial = (entry.user[0].upper()) if entry.user else "?"
    img_src = entry.poster or "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300"
    display_platforms = (
        entry.platforms
        .replace("📺 Stream on: ", "")
        .replace("💰 Rent/Buy on: ", "")
    ) if entry.platforms else "No data"

    return f"""
    <div class="card">
        <div class="poster-container"><img src="{img_src}" class="poster-img" loading="lazy"></div>
        <div class="card-content">
            <div class="card-header">
                <div class="avatar">{initial}</div>
                <div><div class="username">{entry.user}</div><div class="date">{entry.date}</div></div>
            </div>
            <h3 class="movie-title">{entry.title}</h3>
            <div class="card-footer">
                <span class="badge score-badge">⭐ {entry.rating}</span>
                <span class="badge platform-badge">🌐 {display_platforms}</span>
            </div>
        </div>
    </div>
    """


_CSS = """
:root {
    --bg: #0f172a; --card-bg: #1e293b; --text: #f8fafc;
    --muted: #94a3b8; --accent: #38bdf8;
}
* { box-sizing: border-box; }
body {
    font-family: system-ui, sans-serif; background: var(--bg);
    color: var(--text); max-width: 1400px; margin: 0 auto; padding: 40px 20px;
}
header { text-align: center; margin-bottom: 50px; }
header h1 {
    font-size: 2.8rem; margin: 0;
    background: linear-gradient(to right, #38bdf8, #818cf8);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.section-title {
    font-size: 1.8rem; border-left: 5px solid var(--accent);
    padding-left: 15px; margin: 40px 0 20px; color: #e2e8f0;
}
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 25px; }
.card {
    background: var(--card-bg); border-radius: 16px; overflow: hidden;
    border: 1px solid #334155; display: flex; flex-direction: column;
    transition: transform .3s cubic-bezier(.25,1,.5,1), box-shadow .3s, border-color .3s;
}
.card:hover {
    transform: scale(1.05);
    box-shadow: 0 20px 25px -5px rgba(0,0,0,.5);
    border-color: var(--accent); z-index: 10;
}
.poster-container { height: 280px; overflow: hidden; background: #0b0f19; }
.poster-img { width: 100%; height: 100%; object-fit: cover; transition: transform .5s; }
.card:hover .poster-img { transform: scale(1.03); }
.card-content { padding: 16px; display: flex; flex-direction: column; flex-grow: 1; }
.card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.avatar {
    width: 30px; height: 30px; border-radius: 50%;
    background: linear-gradient(135deg, #6366f1, #06b6d4);
    display: flex; align-items: center; justify-content: center;
    font-weight: bold; color: #fff; font-size: .8rem;
}
.username { font-weight: 600; font-size: .9rem; }
.date { font-size: .7rem; color: var(--muted); }
.movie-title { font-size: 1.1rem; margin: 0 0 12px; font-weight: 700; min-height: 44px; }
.card-footer { display: flex; gap: 8px; flex-wrap: wrap; }
.badge { padding: 4px 10px; border-radius: 20px; font-size: .75rem; font-weight: 600; }
.score-badge { background: rgba(56,189,248,.15); color: var(--accent); }
.platform-badge { background: rgba(241,245,249,.1); color: #cbd5e1; border: 1px solid #475569; }
.no-data {
    text-align: center; padding: 40px; color: var(--muted);
    background: #111827; border-radius: 12px;
    border: 1px dashed #334155; grid-column: 1/-1;
}
"""


def build_dashboard_html(entries: list[WatchEntry]) -> str:
    movie_cards = "".join(_card_html(e) for e in entries if e.content_type != "tv")
    tv_cards = "".join(_card_html(e) for e in entries if e.content_type == "tv")
    if not movie_cards:
        movie_cards = "<div class='no-data'>No movies logged yet!</div>"
    if not tv_cards:
        tv_cards = "<div class='no-data'>No TV shows logged yet!</div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🍿 Media Lounge</title>
    <style>{_CSS}</style>
</head>
<body>
    <header>
        <h1>🎬 The Friend Media Lounge</h1>
        <p>Synced live with our Telegram group chat</p>
    </header>
    <h2 class="section-title">🎬 Movies</h2>
    <div class="grid">{movie_cards}</div>
    <h2 class="section-title">📺 TV Shows</h2>
    <div class="grid">{tv_cards}</div>
</body>
</html>"""


def create_app(db: Database) -> FastAPI:
    app = FastAPI(title="Mac Mini Poster Media Lounge")

    @app.get("/", response_class=HTMLResponse)
    async def web_dashboard() -> str:
        entries = db.all_entries()
        return build_dashboard_html(entries)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app
