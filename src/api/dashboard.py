"""
src/api/dashboard.py
FastAPI routes for the web dashboard.
"""

import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.db.database import Database, RatedEntry


# ---------------------------------------------------------------------------
# Platform badge config
# ---------------------------------------------------------------------------
_PLATFORMS: dict[str, dict] = {
    "Netflix":     {"bg": "#E50914", "fg": "#fff",  "label": "N"},
    "Hulu":        {"bg": "#1CE783", "fg": "#000",  "label": "H"},
    "Max":         {"bg": "#002BE7", "fg": "#fff",  "label": "max"},
    "HBO Max":     {"bg": "#002BE7", "fg": "#fff",  "label": "max"},
    "Disney+":     {"bg": "#113CCF", "fg": "#fff",  "label": "D+"},
    "Apple TV+":   {"bg": "#1c1c1e", "fg": "#fff",  "label": "▶"},
    "Prime Video": {"bg": "#00A8E1", "fg": "#fff",  "label": "P"},
    "Paramount+":  {"bg": "#0064FF", "fg": "#fff",  "label": "P+"},
    "Peacock":     {"bg": "#333",    "fg": "#fff",  "label": "Pc"},
    "Tubi":        {"bg": "#FA2D27", "fg": "#fff",  "label": "T"},
    "Showtime":    {"bg": "#CC0000", "fg": "#fff",  "label": "SHO"},
    "Starz":       {"bg": "#111",    "fg": "#fff",  "label": "★"},
}


# ---------------------------------------------------------------------------
# Python-side helpers
# ---------------------------------------------------------------------------

def _parse_list(raw: str) -> list[str]:
    """'Netflix,Hulu' → ['Netflix', 'Hulu']. Strips legacy emoji prefixes."""
    if not raw:
        return []
    raw = raw.replace("📺 Stream on: ", "").replace("💰 Rent/Buy on: ", "")
    return [p.strip() for p in raw.split(",") if p.strip()]


_AVATAR_COLORS = ["#534AB7", "#0F6E56", "#993C1D", "#185FA5",
                  "#854F0B", "#993556", "#3B6D11"]


def _avatar_color(name: str) -> str:
    h = 0
    for c in name:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return _AVATAR_COLORS[abs(h) % len(_AVATAR_COLORS)]


def _picon_html(name: str, size: int = 18) -> str:
    p = _PLATFORMS.get(name, {"bg": "#888", "fg": "#fff", "label": name[:2].upper()})
    return (
        "<div class='picon' "
        "style='width:{s}px;height:{s}px;background:{bg};color:{fg}' "
        "title='{n}'>{lbl}</div>"
    ).format(s=size, bg=p["bg"], fg=p["fg"], n=name, lbl=p["label"])


def _pstrip_html(platforms: list[str]) -> str:
    if not platforms:
        return ""
    icons = "".join(_picon_html(p) for p in platforms[:3])
    extra = len(platforms) - 3
    more = "<span class='more-count'>+{}</span>".format(extra) if extra > 0 else ""
    return "<div class='pstrip'>{}{}</div>".format(icons, more)


def _pbadges_html(platforms: list[str]) -> str:
    if not platforms:
        return ""
    badges = "".join(
        "<div class='pbadge'>{}<span>{}</span></div>".format(_picon_html(p, 13), p)
        for p in platforms
    )
    return "<div class='platform-badges'>{}</div>".format(badges)


def _entry_to_dict(re: RatedEntry) -> dict:
    e = re.entry
    return {
        "title":        e.title,
        "poster":       e.poster,
        "content_type": e.content_type,
        "platforms":    _parse_list(e.platforms),
        "genres":       _parse_list(e.genres),
        "ratings":      [{"user": r.user, "score": r.score} for r in re.ratings],
        "added_by":     e.user,
        "date":         e.date,
    }


def _build_card_html(e: dict, full: bool = False) -> str:
    """Render a single card. Avoids f-strings with nested quotes."""
    avg_str = "+ rate"
    if e["ratings"]:
        avg = sum(r["score"] for r in e["ratings"]) / len(e["ratings"])
        avg_str = "★ {}".format(round(avg, 1))

    first_user = e["ratings"][0]["user"] if e["ratings"] else e["added_by"]
    bg = _avatar_color(first_user)
    meta_label = (
        "{} ratings".format(len(e["ratings"])) if len(e["ratings"]) > 1
        else first_user
    )

    max_genres = 3 if full else 2
    genres_html = "".join(
        "<span class='gtag'>{}</span>".format(g)
        for g in e["genres"][:max_genres]
    )
    platforms_html = _pbadges_html(e["platforms"]) if full else _pstrip_html(e["platforms"])

    poster = e["poster"] or ""
    fallback = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300"

    # Serialize data for JS — use double quotes inside, safe for HTML attribute
    genres_attr  = json.dumps(e["genres"])
    onclick_data = json.dumps(e)

    lines = [
        "<div class='card' data-genres='{}' onclick='openModal({})'>".format(
            genres_attr.replace("'", "&#39;"),
            onclick_data.replace("'", "&#39;"),
        ),
        "  <div class='poster'>",
        "    <img src='{}' loading='lazy' onerror=\"this.src='{}'\">".format(poster, fallback),
        "    <div class='poster-grad'></div>",
        "    <div class='rating-chip'>{}</div>".format(avg_str),
        "  </div>",
        "  <div class='card-body'>",
        "    <div class='card-title'>{}</div>".format(e["title"]),
        "    <div class='card-meta'>",
        "      <div class='avatar' style='background:{};color:#fff' title='{}'>{}</div>".format(
            bg, first_user, first_user[0].upper()
        ),
        "      <span class='username'>{}</span>".format(meta_label),
        "    </div>",
        platforms_html,
        "    <div class='genre-strip'>{}</div>".format(genres_html),
        "  </div>",
        "</div>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--color-background-tertiary);color:var(--color-text-primary);font-family:var(--font-sans);min-height:100vh}
.page{display:none;padding:1.25rem;max-width:960px;margin:0 auto}
.page.active{display:block}

.header-top{display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:.25rem}
.site-title{font-size:22px;font-weight:500;font-family:var(--font-serif)}
.site-title span{color:#7F77DD}
.subtitle{font-size:12px;color:var(--color-text-secondary);letter-spacing:.06em;text-transform:uppercase;margin-bottom:1rem}
.live-dot{display:flex;align-items:center;gap:5px;font-size:12px;color:#1D9E75}
.dot{width:6px;height:6px;border-radius:50%;background:#1D9E75;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:1.25rem}
.stat{background:var(--color-background-secondary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:.6rem .9rem}
.stat-val{font-size:22px;font-weight:500}
.stat-lbl{font-size:11px;color:var(--color-text-secondary);text-transform:uppercase;letter-spacing:.07em;margin-top:2px}

.section-hd{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:.6rem}
.section-hd h2{font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:.1em;color:var(--color-text-secondary)}
.view-all{font-size:12px;color:#7F77DD;background:none;border:none;cursor:pointer;padding:0;font-family:inherit}
.view-all:hover{text-decoration:underline}

/* rail — overflow-y visible so hover scale is never clipped */
.rail-outer{margin:0 -1.25rem;padding:0 1.25rem}
.rail{display:flex;gap:10px;overflow-x:auto;overflow-y:visible;padding:8px 0 56px;scroll-snap-type:x mandatory;-webkit-overflow-scrolling:touch}
.rail::-webkit-scrollbar{height:3px}
.rail::-webkit-scrollbar-thumb{background:var(--color-border-tertiary);border-radius:10px}

/* card */
.card{flex-shrink:0;width:110px;background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-lg);overflow:visible;cursor:pointer;scroll-snap-align:start;position:relative;z-index:1;transform-origin:bottom center;transition:transform .28s cubic-bezier(.34,1.56,.64,1),z-index 0s .28s,border-color .2s}
.card:hover{transform:scale(1.4);z-index:50;border-color:var(--color-border-primary);transition:transform .28s cubic-bezier(.34,1.56,.64,1),z-index 0s,border-color .2s}
.poster{position:relative;height:148px;background:var(--color-background-secondary);border-radius:var(--border-radius-lg);overflow:hidden}
.poster img{width:100%;height:100%;object-fit:cover;display:block}
.poster-grad{position:absolute;bottom:0;left:0;right:0;height:50px;background:linear-gradient(transparent,var(--color-background-primary))}
.rating-chip{position:absolute;top:6px;right:6px;background:rgba(0,0,0,.65);border:0.5px solid rgba(186,117,23,.4);border-radius:20px;padding:2px 6px;font-size:11px;font-weight:500;color:#FAC775}
.card-body{padding:5px 7px 7px}
.card-title{font-size:11px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-bottom:4px}
.card-meta{display:flex;align-items:center;gap:4px;margin-bottom:5px}

/* avatar with full-name tooltip on hover */
.avatar{width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:500;flex-shrink:0;position:relative;cursor:default}
.avatar::after{content:attr(title);position:absolute;bottom:calc(100% + 5px);left:50%;transform:translateX(-50%);background:rgba(0,0,0,.85);color:#fff;font-size:11px;white-space:nowrap;padding:3px 8px;border-radius:5px;pointer-events:none;z-index:200;opacity:0;transition:opacity .15s}
.avatar:hover::after{opacity:1}

.username{font-size:11px;color:var(--color-text-secondary);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* platform strip */
.pstrip{display:flex;align-items:center;gap:3px;overflow:hidden;flex-wrap:nowrap}
.picon{width:18px;height:18px;border-radius:4px;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:7px;font-weight:500;color:#fff;border:none}
.more-count{font-size:10px;color:var(--color-text-secondary)}

/* genre tags */
.genre-strip{display:flex;gap:3px;flex-wrap:wrap;margin-top:4px}
.gtag{font-size:10px;padding:1px 5px;border-radius:20px;background:var(--color-background-secondary);border:0.5px solid var(--color-border-tertiary);color:var(--color-text-secondary);white-space:nowrap}

/* full grid page */
.back-btn{display:flex;align-items:center;gap:5px;background:none;border:none;color:var(--color-text-secondary);font-family:inherit;font-size:13px;cursor:pointer;margin-bottom:1rem;padding:0}
.back-btn:hover{color:var(--color-text-primary)}
.page-title{font-size:22px;font-weight:500;font-family:var(--font-serif);margin-bottom:.75rem}
.page-title span{color:#7F77DD}
.genre-filter{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:1rem}
.gfbtn{font-size:11px;padding:3px 10px;border-radius:20px;border:0.5px solid var(--color-border-tertiary);background:var(--color-background-secondary);color:var(--color-text-secondary);cursor:pointer;font-family:inherit;transition:background .15s,color .15s}
.gfbtn.active{background:#534AB7;color:#EEEDFE;border-color:#534AB7}
.full-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:12px}
.full-grid .card{width:auto;flex-shrink:unset;transform-origin:center center}
.full-grid .card:hover{transform:scale(1.06)}
.platform-badges{display:flex;flex-wrap:wrap;gap:4px;margin-top:5px}
.pbadge{display:flex;align-items:center;gap:4px;background:var(--color-background-secondary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-md);padding:3px 6px;font-size:11px;color:var(--color-text-secondary)}
.pbadge .picon{width:13px;height:13px;border-radius:3px;font-size:6px}
.no-data{text-align:center;padding:2.5rem;color:var(--color-text-secondary);border:0.5px dashed var(--color-border-tertiary);border-radius:var(--border-radius-lg);font-size:13px;grid-column:1/-1}
.card.hidden{display:none}

/* modal */
#modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.55);z-index:1000;align-items:center;justify-content:center;padding:1rem}
#modal-overlay.open{display:flex}
#modal{background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:var(--border-radius-lg);width:100%;max-width:370px;padding:1.25rem;position:relative;max-height:90vh;overflow-y:auto}
.modal-close{position:absolute;top:10px;right:12px;background:none;border:none;cursor:pointer;color:var(--color-text-secondary);font-size:20px;line-height:1;font-family:inherit}
.modal-close:hover{color:var(--color-text-primary)}
.modal-header{display:flex;gap:12px;align-items:flex-start;margin-bottom:1rem}
.modal-poster{width:52px;height:72px;border-radius:6px;object-fit:cover;flex-shrink:0;background:var(--color-background-secondary)}
.modal-info{flex:1;min-width:0}
.modal-title{font-size:15px;font-weight:500;margin-bottom:4px}
.modal-genres{display:flex;gap:3px;flex-wrap:wrap;margin-bottom:6px}
.modal-platforms{display:flex;gap:4px;flex-wrap:wrap}
.score-block{display:flex;align-items:center;gap:14px;margin-bottom:1rem;padding-bottom:1rem;border-bottom:0.5px solid var(--color-border-tertiary)}
.big-score{font-size:44px;font-weight:500;line-height:1}
.stars-row{display:flex;gap:2px;margin-bottom:3px}
.star{font-size:16px;color:#FAC775}
.star.empty{color:var(--color-border-tertiary)}
.score-count{font-size:12px;color:var(--color-text-secondary)}
.bar-rows{display:flex;flex-direction:column;gap:8px}
.bar-row{display:flex;align-items:center;gap:8px}
.bar-label{font-size:11px;color:var(--color-text-secondary);width:12px;text-align:right;flex-shrink:0}
.bar-track{flex:1;height:8px;background:var(--color-background-secondary);border-radius:20px;overflow:hidden}
.bar-fill{height:100%;border-radius:20px;background:#7F77DD;transition:width .5s ease}
.bar-avatars{display:flex;gap:3px;flex-shrink:0;min-width:54px}

/* bar avatar with full-name tooltip */
.bar-avatar{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:500;flex-shrink:0;border:1.5px solid var(--color-background-primary);position:relative;cursor:default}
.bar-avatar::after{content:attr(title);position:absolute;bottom:calc(100% + 5px);left:50%;transform:translateX(-50%);background:rgba(0,0,0,.85);color:#fff;font-size:11px;white-space:nowrap;padding:3px 8px;border-radius:5px;pointer-events:none;z-index:300;opacity:0;transition:opacity .15s}
.bar-avatar:hover::after{opacity:1}

.no-ratings{font-size:13px;color:var(--color-text-secondary);padding:.5rem 0}
"""


# ---------------------------------------------------------------------------
# JS (injected into page)
# ---------------------------------------------------------------------------
_JS_PLATFORMS = "const PLATFORMS = {};".format(json.dumps(_PLATFORMS))

_JS = r"""
const AVATAR_COLORS = ["#534AB7","#0F6E56","#993C1D","#185FA5","#854F0B","#993556","#3B6D11"];
function avatarColor(name){
  let h=0; for(const c of name) h=(h*31+c.charCodeAt(0))&0xffffffff;
  return AVATAR_COLORS[Math.abs(h)%AVATAR_COLORS.length];
}

function piconHTML(name, size=18){
  const p = PLATFORMS[name] || {bg:"#888", fg:"#fff", label: name.slice(0,2).toUpperCase()};
  return `<div class="picon" style="width:${size}px;height:${size}px;background:${p.bg};color:${p.fg}" title="${name}">${p.label}</div>`;
}

function starsHTML(avg){
  let s = "";
  for(let i=1;i<=5;i++){
    if(avg >= i-0.25)      s += `<span class="star">★</span>`;
    else if(avg >= i-0.75) s += `<span class="star">½</span>`;
    else                   s += `<span class="star empty">★</span>`;
  }
  return s;
}

const FALLBACK_POSTER = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300";

function openModal(item){
  const avg = item.ratings.length
    ? item.ratings.reduce((a,r) => a+r.score, 0) / item.ratings.length
    : null;

  document.getElementById("modal-poster").src = item.poster || FALLBACK_POSTER;
  document.getElementById("modal-title").textContent = item.title;
  document.getElementById("modal-score").textContent = avg ? avg.toFixed(1) : "—";
  document.getElementById("modal-stars").innerHTML   = avg ? starsHTML(avg) : "";
  document.getElementById("modal-count").textContent = item.ratings.length
    ? `${item.ratings.length} rating${item.ratings.length !== 1 ? "s" : ""}`
    : "No ratings yet";
  document.getElementById("modal-genres").innerHTML =
    item.genres.map(g => `<span class="gtag">${g}</span>`).join("");
  document.getElementById("modal-platforms").innerHTML =
    item.platforms.map(p => piconHTML(p, 16)).join("");

  // Build 5→1 bar rows
  const byScore = {5:[],4:[],3:[],2:[],1:[]};
  for(const r of item.ratings){
    const b = Math.round(r.score);
    if(byScore[b]) byScore[b].push(r);
  }

  if(!item.ratings.length){
    document.getElementById("modal-bars").innerHTML =
      `<p class="no-ratings">No ratings yet — use /rate ${item.title} - 4.5</p>`;
  } else {
    let bars = "";
    for(let s=5; s>=1; s--){
      const reviewers = byScore[s] || [];
      const pct = Math.round((reviewers.length / item.ratings.length) * 100);
      const avatars = reviewers.map(r => {
        const bg  = avatarColor(r.user);
        const tip = `${r.user} — ${r.score}/5`;
        return `<div class="bar-avatar" style="background:${bg};color:#fff" title="${tip}">${r.user[0].toUpperCase()}</div>`;
      }).join("");
      bars += `<div class="bar-row">
        <div class="bar-label">${s}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <div class="bar-avatars">${avatars}</div>
      </div>`;
    }
    document.getElementById("modal-bars").innerHTML = bars;
  }

  document.getElementById("modal-overlay").classList.add("open");
}

function closeModal(e){
  if(!e || e.target === document.getElementById("modal-overlay")
        || e.currentTarget.classList.contains("modal-close")){
    document.getElementById("modal-overlay").classList.remove("open");
  }
}
document.addEventListener("keydown", e => {
  if(e.key === "Escape") document.getElementById("modal-overlay").classList.remove("open");
});

function showPage(id){
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  window.scrollTo(0, 0);
}

function filterGenre(btn, genre){
  // Scope filter to the grid inside the same page
  const page = btn.closest(".page");
  page.querySelectorAll(".gfbtn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  page.querySelectorAll(".full-grid .card").forEach(card => {
    if(genre === "all"){ card.classList.remove("hidden"); return; }
    const genres = JSON.parse(card.dataset.genres || "[]");
    card.classList.toggle("hidden", !genres.includes(genre));
  });
}
"""


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _genre_filter_html(genres: list[str]) -> str:
    if not genres:
        return ""
    btns = "<button class='gfbtn active' onclick=\"filterGenre(this,'all')\">All</button>"
    for g in genres:
        btns += "<button class='gfbtn' onclick=\"filterGenre(this,'{g}')\">{g}</button>".format(g=g)
    return "<div class='genre-filter'>{}</div>".format(btns)


def build_dashboard_html(rated_entries: list[RatedEntry]) -> str:
    movies = [re for re in rated_entries if re.entry.content_type != "tv"]
    tv     = [re for re in rated_entries if re.entry.content_type == "tv"]

    all_scores = [r.score for re in rated_entries for r in re.ratings]
    avg_rating = "{:.1f}".format(sum(all_scores) / len(all_scores)) if all_scores else "—"

    movie_dicts = [_entry_to_dict(re) for re in movies]
    tv_dicts    = [_entry_to_dict(re) for re in tv]

    def rail_html(entries: list[dict]) -> str:
        if not entries:
            return "<div class='no-data'>Nothing logged yet!</div>"
        return "\n".join(_build_card_html(e, full=False) for e in entries)

    def grid_html(entries: list[dict]) -> str:
        if not entries:
            return "<div class='no-data'>Nothing logged yet!</div>"
        return "\n".join(_build_card_html(e, full=True) for e in entries)

    # Collect unique genres per section
    def unique_genres(dicts: list[dict]) -> list[str]:
        seen: list[str] = []
        for d in dicts:
            for g in d["genres"]:
                if g not in seen:
                    seen.append(g)
        return seen

    movie_genres = unique_genres(movie_dicts)
    tv_genres    = unique_genres(tv_dicts)

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Media Lounge</title>
  <style>{css}</style>
</head>
<body>

<!-- HOME -->
<div class="page active" id="home">
  <div class="header-top">
    <h1 class="site-title">Media <span>Lounge</span></h1>
    <div class="live-dot"><div class="dot"></div> synced</div>
  </div>
  <p class="subtitle">Telegram Group · The Squad</p>
  <div class="stats">
    <div class="stat"><div class="stat-val">{n_movies}</div><div class="stat-lbl">Movies</div></div>
    <div class="stat"><div class="stat-val">{n_tv}</div><div class="stat-lbl">TV Shows</div></div>
    <div class="stat"><div class="stat-val">{avg}</div><div class="stat-lbl">Avg rating</div></div>
  </div>
  <div class="section-hd">
    <h2>Movies</h2>
    <button class="view-all" onclick="showPage('movies')">View all →</button>
  </div>
  <div class="rail-outer"><div class="rail">{movie_rail}</div></div>
  <div class="section-hd" style="margin-top:.5rem">
    <h2>TV Shows</h2>
    <button class="view-all" onclick="showPage('tv')">View all →</button>
  </div>
  <div class="rail-outer"><div class="rail">{tv_rail}</div></div>
</div>

<!-- MOVIES PAGE -->
<div class="page" id="movies">
  <button class="back-btn" onclick="showPage('home')">← Back</button>
  <h2 class="page-title">All <span>Movies</span></h2>
  {movie_filter}
  <div class="full-grid">{movie_grid}</div>
</div>

<!-- TV PAGE -->
<div class="page" id="tv">
  <button class="back-btn" onclick="showPage('home')">← Back</button>
  <h2 class="page-title">All <span>TV Shows</span></h2>
  {tv_filter}
  <div class="full-grid">{tv_grid}</div>
</div>

<!-- RATING MODAL -->
<div id="modal-overlay" role="dialog" aria-modal="true" onclick="closeModal(event)">
  <div id="modal">
    <button class="modal-close" onclick="closeModal()" aria-label="Close">×</button>
    <div class="modal-header">
      <img class="modal-poster" id="modal-poster" src="" alt="">
      <div class="modal-info">
        <div class="modal-title"  id="modal-title"></div>
        <div class="modal-genres" id="modal-genres"></div>
        <div class="modal-platforms" id="modal-platforms"></div>
      </div>
    </div>
    <div class="score-block">
      <div class="big-score" id="modal-score"></div>
      <div>
        <div class="stars-row"   id="modal-stars"></div>
        <div class="score-count" id="modal-count"></div>
      </div>
    </div>
    <div class="bar-rows" id="modal-bars"></div>
  </div>
</div>

<script>{platforms_js}{js}</script>
</body>
</html>""".format(
        css=_CSS,
        n_movies=len(movies),
        n_tv=len(tv),
        avg=avg_rating,
        movie_rail=rail_html(movie_dicts),
        tv_rail=rail_html(tv_dicts),
        movie_filter=_genre_filter_html(movie_genres),
        tv_filter=_genre_filter_html(tv_genres),
        movie_grid=grid_html(movie_dicts),
        tv_grid=grid_html(tv_dicts),
        platforms_js=_JS_PLATFORMS,
        js=_JS,
    )


def create_app(db: Database) -> FastAPI:
    app = FastAPI(title="Media Lounge")

    @app.get("/", response_class=HTMLResponse)
    async def web_dashboard() -> str:
        return build_dashboard_html(db.all_rated_entries())

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app
