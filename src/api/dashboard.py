"""
src/api/dashboard.py
FastAPI routes for the web dashboard.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.db.database import Database, WatchEntry


# ---------------------------------------------------------------------------
# Platform logo map (Watchmode name → Wikimedia SVG URL)
# Add entries here as new platforms appear in your data.
# ---------------------------------------------------------------------------
_PLATFORM_LOGOS: dict[str, str] = {
    "Netflix":      "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/200px-Netflix_2015_logo.svg.png",
    "Hulu":         "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Hulu_Logo.svg/200px-Hulu_Logo.svg.png",
    "HBO Max":      "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/HBO_Max_Logo.svg/200px-HBO_Max_Logo.svg.png",
    "Max":          "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/HBO_Max_Logo.svg/200px-HBO_Max_Logo.svg.png",
    "Disney+":      "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Disney%2B_logo.svg/200px-Disney%2B_logo.svg.png",
    "Apple TV+":    "https://upload.wikimedia.org/wikipedia/commons/thumb/2/28/Apple_TV_Plus_Logo.svg/200px-Apple_TV_Plus_Logo.svg.png",
    "Prime Video":  "https://upload.wikimedia.org/wikipedia/commons/thumb/1/11/Amazon_Prime_Video_logo.svg/200px-Amazon_Prime_Video_logo.svg.png",
    "Paramount+":   "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Paramount_Plus_logo.svg/200px-Paramount_Plus_logo.svg.png",
    "Peacock":      "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/NBCUniversal_Peacock_Logo.svg/200px-NBCUniversal_Peacock_Logo.svg.png",
    "Tubi":         "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/Tubi_logo_2022.svg/200px-Tubi_logo_2022.svg.png",
    "Showtime":     "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Showtime.svg/200px-Showtime.svg.png",
    "Starz":        "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Starz_2016.svg/200px-Starz_2016.svg.png",
}

_LOGO_JS = "const PLATFORM_LOGOS = " + str(_PLATFORM_LOGOS).replace("'", '"') + ";"


def _parse_platforms(raw: str) -> list[str]:
    """Splits 'Netflix,Hulu' → ['Netflix', 'Hulu']. Handles empty / legacy strings."""
    if not raw:
        return []
    # Strip legacy emoji prefixes from older DB rows
    raw = raw.replace("📺 Stream on: ", "").replace("💰 Rent/Buy on: ", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


def _card_html(entry: WatchEntry, full: bool = False) -> str:
    initial = entry.user[0].upper() if entry.user else "?"
    img_src = entry.poster or "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300"
    platforms_json = str(_parse_platforms(entry.platforms)).replace("'", '"')
    return f"""
    <div class="card" data-platforms='{platforms_json}' data-full='{"1" if full else "0"}'>
        <div class="poster">
            <img src="{img_src}" loading="lazy"
                 onerror="this.src='https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300'">
            <div class="poster-overlay"></div>
            <div class="rating-chip">★ {entry.rating}</div>
        </div>
        <div class="card-body">
            <div class="card-title">{entry.title}</div>
            <div class="card-meta">
                <div class="avatar">{initial}</div>
                <span class="username">{entry.user}</span>
            </div>
            <div class="platform-area"></div>
        </div>
    </div>"""


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500&family=DM+Serif+Display&display=swap');
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#09090f;--surface:#111118;--card:#16161f;--border:#ffffff12;
  --text:#f0eff8;--muted:#6e6d84;--accent:#c084fc;--accent2:#38bdf8;--gold:#fbbf24;--green:#34d399;
}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;min-height:100vh}
.page{display:none;padding:1.5rem;max-width:960px;margin:0 auto}
.page.active{display:block}

/* header */
header{margin-bottom:1.75rem}
.header-top{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:.3rem}
.site-title{font-family:'DM Serif Display',serif;font-size:1.9rem;font-weight:400}
.site-title span{color:var(--accent)}
.subtitle{font-size:.72rem;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
.live-dot{display:flex;align-items:center;gap:5px;font-size:.72rem;color:var(--green)}
.dot{width:6px;height:6px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* stats */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:1.5rem}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:.6rem .9rem}
.stat-val{font-size:1.35rem;font-weight:600}
.stat-lbl{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-top:1px}

/* section header */
.section-hd{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:.75rem}
.section-hd h2{font-size:.8rem;font-weight:500;text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.view-all{font-size:.75rem;color:var(--accent);background:none;border:none;cursor:pointer;padding:0;font-family:inherit}
.view-all:hover{text-decoration:underline}

/* scroll rail */
.rail-wrap{overflow:hidden;margin:0 -1.5rem;padding:0 1.5rem 1rem}
.rail{display:flex;gap:10px;overflow-x:auto;padding-bottom:8px;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch}
.rail::-webkit-scrollbar{height:3px}
.rail::-webkit-scrollbar-thumb{background:var(--border);border-radius:10px}

/* card */
.card{
  flex-shrink:0;width:120px;background:var(--card);border:1px solid var(--border);
  border-radius:12px;overflow:visible;cursor:pointer;scroll-snap-align:start;
  position:relative;z-index:1;
  transition:transform .28s cubic-bezier(.34,1.56,.64,1);
}
.card:hover{transform:scale(1.38);z-index:100;border-color:#ffffff22}
.poster{position:relative;height:160px;background:#0d0d14;border-radius:12px;overflow:hidden}
.poster img{width:100%;height:100%;object-fit:cover;display:block}
.poster-overlay{position:absolute;bottom:0;left:0;right:0;height:55px;background:linear-gradient(transparent,var(--card))}
.rating-chip{
  position:absolute;top:6px;right:6px;background:rgba(0,0,0,.78);
  border:1px solid rgba(251,191,36,.25);border-radius:20px;
  padding:2px 6px;font-size:.62rem;font-weight:600;color:var(--gold)
}
.card-body{padding:6px 8px 8px}
.card-title{font-size:.72rem;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:5px}
.card-meta{display:flex;align-items:center;gap:4px;margin-bottom:5px}
.avatar{
  width:14px;height:14px;border-radius:50%;
  background:linear-gradient(135deg,var(--accent),var(--accent2));
  display:flex;align-items:center;justify-content:center;
  font-size:.5rem;font-weight:600;color:#fff;flex-shrink:0
}
.username{font-size:.65rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* platform icons — compact strip */
.platform-strip{display:flex;align-items:center;gap:4px;flex-wrap:nowrap;overflow:hidden}
.picon{width:18px;height:18px;border-radius:4px;flex-shrink:0;overflow:hidden;display:flex;align-items:center;justify-content:center}
.picon img{width:100%;height:100%;object-fit:cover}
.picon.fallback{background:var(--surface);border:1px solid var(--border);color:var(--muted);font-size:6px;font-weight:700}
.more-platforms{font-size:.6rem;color:var(--muted)}

/* platform badges — full grid */
.platform-row{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px}
.platform-badge{
  display:flex;align-items:center;gap:4px;
  background:var(--surface);border:1px solid var(--border);
  border-radius:6px;padding:3px 6px;font-size:.62rem;color:var(--muted)
}
.platform-badge .picon{width:14px;height:14px;border-radius:3px}

/* full-grid page */
.back-btn{display:flex;align-items:center;gap:6px;background:none;border:none;color:var(--muted);font-family:inherit;font-size:.8rem;cursor:pointer;margin-bottom:1.25rem;padding:0}
.back-btn:hover{color:var(--text)}
.page-title{font-family:'DM Serif Display',serif;font-size:1.6rem;font-weight:400;margin-bottom:1.25rem}
.page-title span{color:var(--accent)}
.full-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:14px}
.full-grid .card{width:auto;flex-shrink:unset}
.full-grid .card:hover{transform:scale(1.06)}
.no-data{text-align:center;padding:2.5rem;color:var(--muted);border:1px dashed var(--border);border-radius:12px;font-size:.82rem;grid-column:1/-1}
"""

_JS = """
const PLATFORM_LOGOS = {
  "Netflix":     "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/Netflix_2015_logo.svg/200px-Netflix_2015_logo.svg.png",
  "Hulu":        "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Hulu_Logo.svg/200px-Hulu_Logo.svg.png",
  "HBO Max":     "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/HBO_Max_Logo.svg/200px-HBO_Max_Logo.svg.png",
  "Max":         "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/HBO_Max_Logo.svg/200px-HBO_Max_Logo.svg.png",
  "Disney+":     "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Disney%2B_logo.svg/200px-Disney%2B_logo.svg.png",
  "Apple TV+":   "https://upload.wikimedia.org/wikipedia/commons/thumb/2/28/Apple_TV_Plus_Logo.svg/200px-Apple_TV_Plus_Logo.svg.png",
  "Prime Video": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/11/Amazon_Prime_Video_logo.svg/200px-Amazon_Prime_Video_logo.svg.png",
  "Paramount+":  "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Paramount_Plus_logo.svg/200px-Paramount_Plus_logo.svg.png",
  "Peacock":     "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d3/NBCUniversal_Peacock_Logo.svg/200px-NBCUniversal_Peacock_Logo.svg.png",
  "Tubi":        "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/Tubi_logo_2022.svg/200px-Tubi_logo_2022.svg.png",
  "Showtime":    "https://upload.wikimedia.org/wikipedia/commons/thumb/2/22/Showtime.svg/200px-Showtime.svg.png",
  "Starz":       "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Starz_2016.svg/200px-Starz_2016.svg.png"
};

function abbr(name){ return name.replace(/[^A-Za-z0-9+]/g,'').slice(0,2).toUpperCase() || '??'; }

function piconHTML(platform, size=18){
  const logo = PLATFORM_LOGOS[platform];
  const ab = abbr(platform);
  const s = `width:${size}px;height:${size}px`;
  if(logo) return `<div class="picon" style="${s}"><img src="${logo}" alt="${platform}"
    onerror="this.parentNode.classList.add('fallback');this.parentNode.textContent='${ab}'" loading="lazy"></div>`;
  return `<div class="picon fallback" style="${s}" title="${platform}">${ab}</div>`;
}

function renderPlatformAreas(){
  document.querySelectorAll('.card').forEach(card => {
    const platforms = JSON.parse(card.dataset.platforms || '[]');
    const full = card.dataset.full === '1';
    const area = card.querySelector('.platform-area');
    if(!area) return;
    if(!platforms.length){ area.innerHTML=''; return; }
    if(full){
      area.innerHTML = `<div class="platform-row">${
        platforms.map(p=>`<div class="platform-badge">${piconHTML(p,14)}<span>${p}</span></div>`).join('')
      }</div>`;
    } else {
      const shown = platforms.slice(0,3);
      const extra = platforms.length - shown.length;
      area.innerHTML = `<div class="platform-strip">
        ${shown.map(p=>piconHTML(p)).join('')}
        ${extra > 0 ? `<span class="more-platforms">+${extra}</span>` : ''}
      </div>`;
    }
  });
}

function showPage(id){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  window.scrollTo(0,0);
}

document.addEventListener('DOMContentLoaded', renderPlatformAreas);
"""


def build_dashboard_html(entries: list[WatchEntry]) -> str:
    movies = [e for e in entries if e.content_type != "tv"]
    tv     = [e for e in entries if e.content_type == "tv"]

    movie_count = len(movies)
    tv_count    = len(tv)
    ratings     = [float(e.rating.replace("/10","")) for e in entries if "/10" in e.rating]
    avg_rating  = f"{sum(ratings)/len(ratings):.1f}" if ratings else "—"

    movie_rail  = "".join(_card_html(e) for e in movies) or "<div class='no-data'>No movies logged yet!</div>"
    tv_rail     = "".join(_card_html(e) for e in tv)    or "<div class='no-data'>No TV shows logged yet!</div>"
    movie_grid  = "".join(_card_html(e, full=True) for e in movies) or "<div class='no-data'>No movies logged yet!</div>"
    tv_grid     = "".join(_card_html(e, full=True) for e in tv)    or "<div class='no-data'>No TV shows logged yet!</div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Lounge</title>
    <style>{_CSS}</style>
</head>
<body>

<!-- HOME -->
<div class="page active" id="home">
  <header>
    <div class="header-top">
      <h1 class="site-title">Media <span>Lounge</span></h1>
      <div class="live-dot"><div class="dot"></div> synced</div>
    </div>
    <p class="subtitle">Telegram Group · The Squad</p>
  </header>
  <div class="stats">
    <div class="stat"><div class="stat-val">{movie_count}</div><div class="stat-lbl">Movies</div></div>
    <div class="stat"><div class="stat-val">{tv_count}</div><div class="stat-lbl">TV Shows</div></div>
    <div class="stat"><div class="stat-val">{avg_rating}</div><div class="stat-lbl">Avg rating</div></div>
  </div>
  <div class="section-hd">
    <h2>Movies</h2>
    <button class="view-all" onclick="showPage('movies')">View all →</button>
  </div>
  <div class="rail-wrap"><div class="rail">{movie_rail}</div></div>
  <div class="section-hd" style="margin-top:.75rem">
    <h2>TV Shows</h2>
    <button class="view-all" onclick="showPage('tv')">View all →</button>
  </div>
  <div class="rail-wrap"><div class="rail">{tv_rail}</div></div>
</div>

<!-- MOVIES PAGE -->
<div class="page" id="movies">
  <button class="back-btn" onclick="showPage('home')">← Back</button>
  <h2 class="page-title">All <span>Movies</span></h2>
  <div class="full-grid">{movie_grid}</div>
</div>

<!-- TV PAGE -->
<div class="page" id="tv">
  <button class="back-btn" onclick="showPage('home')">← Back</button>
  <h2 class="page-title">All <span>TV Shows</span></h2>
  <div class="full-grid">{tv_grid}</div>
</div>

<script>{_JS}</script>
</body>
</html>"""


def create_app(db: Database) -> FastAPI:
    app = FastAPI(title="Media Lounge")

    @app.get("/", response_class=HTMLResponse)
    async def web_dashboard() -> str:
        return build_dashboard_html(db.all_entries())

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app
