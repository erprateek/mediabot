import os
import re
import sqlite3
import asyncio
import requests
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- 1. CONFIGURATION & API KEYS ---
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_TOKEN_HERE")
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "YOUR_OMDB_KEY_HERE")
WATCHMODE_API_KEY = os.getenv("WATCHMODE_API_KEY", "YOUR_WATCHMODE_KEY_HERE")

DB_FILE = "movies.db"

# --- 2. DATABASE SYSTEM INITIALIZATION ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            title TEXT,
            rating TEXT,
            date TEXT,
            content_type TEXT DEFAULT 'movie',
            poster TEXT DEFAULT '',
            imdb_id TEXT DEFAULT '',
            platforms TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# --- 3. METADATA & STREAMING LOOKUPS ---
def fetch_media_meta(title_query: str):
    """Hits OMDb API to get type, poster art, official title, and unique IMDb ID"""
    url = f"http://www.omdbapi.com/?t={title_query}&apikey={OMDB_API_KEY}"
    try:
        res = requests.get(url).json()
        if res.get("Response") == "True":
            c_type = "tv" if res.get("Type") == "series" else "movie"
            poster = res.get("Poster")
            imdb_id = res.get("imdbID")
            if poster == "N/A" or not poster:
                poster = ""
            return c_type, poster, res.get("Title", title_query), imdb_id
    except Exception as e:
        print(f"OMDb Error: {e}")
    return "movie", "", title_query, None

def fetch_streaming_platforms(imdb_id: str, title_query: str = ""):
    """Queries Watchmode and intelligently extracts titles while completely filtering out people results"""
    results = []
    
    # --- STRATEGY 1: Rock-Solid IMDb ID Search ---
    if imdb_id:
        search_url = f"https://api.watchmode.com/v1/search/?apiKey={WATCHMODE_API_KEY}&search_field=imdb_id&search_value={imdb_id}"
        try:
            response = requests.get(search_url)
            search_res = response.json()
            if isinstance(search_res, dict):
                # Target the dedicated titles index explicitly
                results = search_res.get("title_results", []) or search_res.get("results", [])
            elif isinstance(search_res, list):
                results = search_res
        except Exception as e:
            print(f"Watchmode ID Search Error: {e}")

    # --- STRATEGY 2: Advanced Text Search Fallback ---
    if (not results or len(results) == 0) and title_query:
        clean_title = title_query.replace("-", " ").strip()
        print(f"⚠️ Watchmode ID missed. Trying direct title fallback for: {clean_title}")
        
        fallback_url = f"https://api.watchmode.com/v1/search/?apiKey={WATCHMODE_API_KEY}&search_field=name&search_value={clean_title}"
        try:
            fb_response = requests.get(fallback_url)
            fb_res = fb_response.json()
            
            if isinstance(fb_res, dict):
                # EXPLICIT FIX: Isolate 'title_results' directly to ignore 'people_results' arrays
                results = fb_res.get("title_results", [])
                if not results: # Fallback to generic results or autocomplete arrays if empty
                    results = fb_res.get("results", fb_res.get("autocomplete", []))
            elif isinstance(fb_res, list):
                results = fb_res
        except Exception as e:
            print(f"Watchmode Text Fallback Error: {e}")

    # --- PROCESS PARSED RESULTS VIA STRUCTURAL FILTERS ---
    if not results or not isinstance(results, list) or len(results) == 0:
        return "Streaming info unavailable"
        
    watchmode_id = None
    
    # Iterate through array to isolate an actual media item containing a clean ID
    for item in results:
        if isinstance(item, dict):
            # Verify it's a media object, skipping actor profiles that might share the name
            if item.get("resultType") == "person":
                continue
                
            # Safely grab the first available ID variant key
            watchmode_id = item.get("id") or item.get("title_id") or item.get("watchmode_id")
            if watchmode_id:
                break # Found a valid movie/show match!
                
    if not watchmode_id:
        return "Streaming platform reference missed"
    
    # 3. Fetch sources matching the extracted Watchmode ID
    try:
        sources_url = f"https://api.watchmode.com/v1/title/{watchmode_id}/sources/?apiKey={WATCHMODE_API_KEY}&regions=US"
        sources_res = requests.get(sources_url).json()
        
        if not isinstance(sources_res, list):
            return "Not available on subscription services"
        
        sub_platforms = []
        rent_platforms = []
        for source in sources_res:
            if not isinstance(source, dict):
                continue
            name = source.get("name")
            s_type = source.get("type")
            
            if s_type in ["sub", "free"]:
                if name and name not in sub_platforms:
                    sub_platforms.append(name)
            elif s_type in ["rent", "buy"]:
                if name and name not in rent_platforms:
                    rent_platforms.append(name)
        
        if sub_platforms:
            return "📺 Stream on: " + ", ".join(sub_platforms[:2])
        if rent_platforms:
            return "💰 Rent/Buy on: " + ", ".join(rent_platforms[:2])
            
    except Exception as e:
        print(f"Watchmode Source Retrieval Exception: {e}")
        
    return "Not currently streaming anywhere"


# --- 4. WEEKLY BACKGROUND REFRESH WORKER ---
async def weekly_streaming_refresh():
    """Wakes up every 7 days to clean and update cached streaming data"""
    while True:
        await asyncio.sleep(7 * 24 * 60 * 60) # Wait 7 days
        print("🔄 Background Job: Refreshing all movie streaming platforms...")
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Change SELECT to grab the title column too
        cursor.execute("SELECT id, title, imdb_id FROM watch_logs")
        movies = cursor.fetchall()
        
        for movie in movies:
            db_id, title, imdb_id = movie
            fresh_platforms = fetch_streaming_platforms(imdb_id, title)
            cursor.execute(
                "UPDATE watch_logs SET platforms = ? WHERE id = ?",
                (fresh_platforms, db_id)
            )
            conn.commit()
            await asyncio.sleep(0.5) # Rate limit padding
                
        conn.close()
        print("✅ Background Job: Streaming platforms update complete!")

# --- 5. TELEGRAM BOT OPERATIONS ---
tg_app = Application.builder().token(TOKEN).build()

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.first_name
    text = " ".join(context.args)
    
    if not text:
        await update.message.reply_text("Format: /watch [Title] - [Rating/10]\nExample: /watch The Batman - 8.4/10")
        return

    # Decimal and integer matching configuration regex
    match = re.search(r"(.+?)\s*-\s*(\d+(?:\.\d+)?/10)", text)
    if match:
        title_query, rating = match.group(1).strip(), match.group(2).strip()
    else:
        title_query, rating = text, "No Rating"

    content_type, poster_url, official_title, imdb_id = fetch_media_meta(title_query)

    # Duplicate Checker
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user, rating FROM watch_logs WHERE LOWER(title) = LOWER(?)", (official_title,))
    existing_entry = cursor.fetchone()

    if existing_entry:
        existing_user, existing_rating = existing_entry
        conn.close()
        await update.message.reply_text(f"⚠️ *{official_title}* is already on the dashboard! Added by *{existing_user}* ({existing_rating}).")
        return

    streaming_info = fetch_streaming_platforms(imdb_id, official_title)

    # Save details to DB
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        """INSERT INTO watch_logs (user, title, rating, date, content_type, poster, imdb_id, platforms) 
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user, official_title, rating, current_time, content_type, poster_url, imdb_id, streaming_info)
    )
    conn.commit()
    conn.close()

    type_emoji = "🎬" if content_type == "movie" else "📺"
    caption_text = f"💾 *Saved {type_emoji} {official_title}* ({rating})!\n\n_{streaming_info}_"

    if poster_url:
        try:
            await update.message.reply_photo(photo=poster_url, caption=caption_text, parse_mode="Markdown")
            return
        except Exception:
            pass
            
    await update.message.reply_text(caption_text, parse_mode="Markdown")

tg_app.add_handler(CommandHandler("watch", watch_command))

# --- 6. FASTAPI INTERFACE ROUTER ---
app = FastAPI(title="Mac Mini Poster Media Lounge")

@app.get("/", response_class=HTMLResponse)
async def web_dashboard():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT date, user, title, rating, content_type, poster, platforms FROM watch_logs ORDER BY id DESC")
    rows_data = cursor.fetchall()
    conn.close()

    movie_cards, tv_cards = "", ""

    for row in rows_data:
        date, user, title, rating, content_type, poster, platforms = row
        initial = user.upper() if user else "?"
        img_src = poster if poster else "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300"

        display_platforms = platforms.replace("📺 Stream on: ", "").replace("💰 Rent/Buy on: ", "") if platforms else "No data"

        card_html = f"""
        <div class="card">
            <div class="poster-container"><img src="{img_src}" class="poster-img"></div>
            <div class="card-content">
                <div class="card-header">
                    <div class="avatar">{initial}</div>
                    <div><div class="username">{user}</div><div class="date">{date}</div></div>
                </div>
                <h3 class="movie-title">{title}</h3>
                <div class="card-footer">
                    <span class="badge score-badge">⭐ {rating}</span>
                    <span class="badge platform-badge">🌐 {display_platforms}</span>
                </div>
            </div>
        </div>
        """
        if content_type == "tv": tv_cards += card_html
        else: movie_cards += card_html

    if not movie_cards: movie_cards = "<div class='no-data'>No movies logged yet!</div>"
    if not tv_cards: tv_cards = "<div class='no-data'>No TV shows logged yet!</div>"

    return f"""
    <html>
        <head>
            <title>🍿 Media Lounge Tracker</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {{ --bg-dark: #0f172a; --card-bg: #1e293b; --text-main: #f8fafc; --text-muted: #94a3b8; --accent: #38bdf8; }}
                body {{ font-family: system-ui, sans-serif; background-color: var(--bg-dark); color: var(--text-main); max-width: 1400px; margin: 0 auto; padding: 40px 20px; }}
                header {{ text-align: center; margin-bottom: 50px; }}
                header h1 {{ font-size: 2.8rem; margin: 0; background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
                .section-title {{ font-size: 1.8rem; border-left: 5px solid var(--accent); padding-left: 15px; margin: 40px 0 20px 0; color: #e2e8f0; }}
                
                /* --- INTERACTIVE ANIMATED GRID & CARDS --- */
                .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 25px; padding: 20px 0; }}
                .card {{ 
                    background-color: var(--card-bg); border-radius: 16px; overflow: hidden; 
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2); border: 1px solid #334155; 
                    display: flex; flex-direction: column; transform: scale(1);
                    transition: transform 0.3s cubic-bezier(0.25, 1, 0.5, 1), box-shadow 0.3s ease, border-color 0.3s ease;
                    will-change: transform, box-shadow;
                }}
                .card:hover {{ 
                    transform: scale(1.05); 
                    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.4); 
                    border-color: var(--accent); z-index: 10; 
                }}
                .poster-container {{ width: 100%; height: 280px; overflow: hidden; background: #0b0f19; }}
                .poster-img {{ width: 100%; height: 100%; object-fit: cover; transition: transform 0.5s ease; }}
                .card:hover .poster-img {{ transform: scale(1.03); }}
                
                .card-content {{ padding: 16px; display: flex; flex-direction: column; justify-content: space-between; flex-grow: 1; }}
                .card-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }}
                .avatar {{ width: 30px; height: 30px; background: linear-gradient(135deg, #6366f1, #06b6d4); border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; color: white; font-size: 0.8rem; }}
                .username {{ font-weight: 600; font-size: 0.9rem; }}
                .date {{ font-size: 0.7rem; color: var(--text-muted); }}
                .movie-title {{ font-size: 1.1rem; margin: 0 0 12px 0; font-weight: 700; min-height: 44px; }}
                .card-footer {{ display: flex; gap: 8px; flex-wrap: wrap; }}
                .badge {{ padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }}
                .score-badge {{ background-color: rgba(56, 189, 248, 0.15); color: var(--accent); }}
                .platform-badge {{ background-color: rgba(241, 245, 249, 0.1); color: #cbd5e1; border: 1px solid #475569; }}
                .no-data {{ text-align: center; padding: 40px; color: var(--text-muted); background: #111827; border-radius: 12px; border: 1px dashed #334155; grid-column: 1 / -1; }}
            </style>
        </head>
        <body>
            <header>
                <h1>🎬 The Friend Media Lounge</h1>
                <p>Synced live with our Telegram group chat</p>
            </header>
            <h2 class="section-title">🎬 Movies</h2><div class="grid">{movie_cards}</div>
            <h2 class="section-title">📺 TV Shows</h2><div class="grid">{tv_cards}</div>
        </body>
    </html>
    """

# --- 7. ORCHESTRATION LAYERS ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🤖 Starting Telegram Bot Polling...")
    await tg_app.initialize()
    await tg_app.start()
    polling_task = asyncio.create_task(tg_app.updater.start_polling())
    refresh_task = asyncio.create_task(weekly_streaming_refresh())
    yield
    print("🛑 Shutting down Telegram Bot...")
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()
    polling_task.cancel()
    refresh_task.cancel()

app.router.lifespan_context = lifespan