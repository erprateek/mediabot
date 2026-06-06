import os
import re
import sqlite3
import asyncio
import requests
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# 1. Initialize FastAPI
app = FastAPI(title="Mac Mini Poster Media Lounge")

DB_FILE = "movies.db"
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "YOUR_OMDB_KEY_HERE") # Set your key here or via terminal

def init_db():
    """Creates/Updates table schema to include content type and poster URLs"""
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
            poster TEXT DEFAULT ''
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# 2. Setup Telegram Bot
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
tg_app = Application.builder().token(TOKEN).build()

def fetch_media_meta(title_query: str):
    """Hits OMDb API to get the correct type (movie/series) and poster art link"""
    url = f"http://www.omdbapi.com/?t={title_query}&apikey={OMDB_API_KEY}"
    try:
        res = requests.get(url).json()
        if res.get("Response") == "True":
            # Normalize content types
            c_type = "tv" if res.get("Type") == "series" else "movie"
            poster = res.get("Poster")
            # If no poster available, return placeholder string
            if poster == "N/A" or not poster:
                poster = ""
            return c_type, poster, res.get("Title", title_query)
    except Exception as e:
        print(f"OMDb Error: {e}")
    return "movie", "", title_query  # Default fallback if API fails or item not found

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes `/watch Title - 9/10` and fetches artwork live"""
    user = update.message.from_user.first_name
    text = " ".join(context.args)
    
    if not text:
        await update.message.reply_text("Format: /watch [Title] - [Rating/10]\nExample: /watch Stranger Things - 9/10")
        return

    # Parse Title and Rating
    match = re.search(r"(.+?)\s*-\s*(\d+/10)", text)
    if match:
        title_query, rating = match.group(1).strip(), match.group(2).strip()
    else:
        title_query, rating = text, "No Rating"

    # Fetch live posters and type from OMDb API
    content_type, poster_url, official_title = fetch_media_meta(title_query)

    # Save to SQLite Database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO watch_logs (user, title, rating, date, content_type, poster) VALUES (?, ?, ?, ?, ?, ?)",
        (user, official_title, rating, current_time, content_type, poster_url)
    )
    conn.commit()
    conn.close()

    type_emoji = "🎬" if content_type == "movie" else "📺"
    await update.message.reply_text(f"💾 Saved {type_emoji} *{official_title}* ({rating}) with artwork!")

tg_app.add_handler(CommandHandler("watch", watch_command))

# 3. Web Dashboard (Grouped Layout)
@app.get("/", response_class=HTMLResponse)
async def web_dashboard():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT date, user, title, rating, content_type, poster FROM watch_logs ORDER BY id DESC")
    rows_data = cursor.fetchall()
    conn.close()

    movie_cards = ""
    tv_cards = ""

    for row in rows_data:
        date, user, title, rating, content_type, poster = row
        initial = user.upper() if user else "?"
        
        # Use a fallback placeholder picture if OMDb didn't find artwork
        img_src = poster if poster else "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=300"

        card_html = f"""
        <div class="card">
            <div class="poster-container">
                <img src="{img_src}" alt="{title} poster" class="poster-img">
            </div>
            <div class="card-content">
                <div class="card-header">
                    <div class="avatar">{initial}</div>
                    <div>
                        <div class="username">{user}</div>
                        <div class="date">{date}</div>
                    </div>
                </div>
                <h3 class="movie-title">{title}</h3>
                <div class="card-footer">
                    <span class="badge">⭐ {rating}</span>
                </div>
            </div>
        </div>
        """
        
        if content_type == "tv":
            tv_cards += card_html
        else:
            movie_cards += card_html

    if not movie_cards:
        movie_cards = "<div class='no-data'>No movies logged yet!</div>"
    if not tv_cards:
        tv_cards = "<div class='no-data'>No TV shows logged yet!</div>"

    return f"""
    <html>
        <head>
            <title>🍿 Media Lounge Tracker</title>
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                :root {{
                    --bg-dark: #0f172a;
                    --card-bg: #1e293b;
                    --text-main: #f8fafc;
                    --text-muted: #94a3b8;
                    --accent: #38bdf8;
                }}
                body {{
                    font-family: system-ui, -apple-system, sans-serif;
                    background-color: var(--bg-dark);
                    color: var(--text-main);
                    max-width: 1400px;
                    margin: 0 auto;
                    padding: 40px 20px;
                }}
                header {{
                    text-align: center;
                    margin-bottom: 50px;
                }}
                header h1 {{
                    font-size: 2.8rem;
                    margin: 0;
                    background: linear-gradient(to right, #38bdf8, #818cf8);
                    -webkit-background-clip: text;
                    -webkit-text-fill-color: transparent;
                }}
                .section-title {{
                    font-size: 1.8rem;
                    border-left: 5px solid var(--accent);
                    padding-left: 15px;
                    margin: 40px 0 20px 0;
                    color: #e2e8f0;
                }}
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
                    gap: 25px;
                }}
                .card {{
                    background-color: var(--card-bg);
                    border-radius: 16px;
                    overflow: hidden;
                    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3);
                    border: 1px solid #334155;
                    display: flex;
                    flex-direction: column;
                    transition: transform 0.2s;
                }}
                .card:hover {{
                    transform: translateY(-5px);
                }}
                .poster-container {{
                    width: 100%;
                    height: 320px;
                    overflow: hidden;
                    background: #0b0f19;
                }}
                .poster-img {{
                    width: 100%;
                    height: 100%;
                    object-fit: cover;
                }}
                .card-content {{
                    padding: 16px;
                    display: flex;
                    flex-direction: column;
                    justify-content: space-between;
                    flex-grow: 1;
                }}
                .card-header {{
                    display: flex;
                    align-items: center;
                    gap: 10px;
                    margin-bottom: 12px;
                }}
                .avatar {{
                    width: 30px;
                    height: 30px;
                    background: linear-gradient(135deg, #6366f1, #06b6d4);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-weight: bold;
                    color: white;
                    font-size: 0.8rem;
                }}
                .username {{ font-weight: 600; font-size: 0.9rem; }}
                .date {{ font-size: 0.7rem; color: var(--text-muted); }}
                .movie-title {{ font-size: 1.1rem; margin: 0 0 12px 0; font-weight: 700; }}
                .badge {{
                    background-color: rgba(56, 189, 248, 0.15);
                    color: var(--accent);
                    padding: 4px 10px;
                    border-radius: 20px;
                    font-size: 0.8rem;
                    font-weight: 600;
                }}
                .no-data {{
                    text-align: center;
                    padding: 40px;
                    color: var(--text-muted);
                    background: #111827;
                    border-radius: 12px;
                    border: 1px dashed #334155;
                    grid-column: 1 / -1;
                }}
            </style>
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
    </html>
    """

# 5. Orchestration: Running Bot Polling & Web Server
@app.on_event("startup")
async def startup_event():
    await tg_app.initialize()
    await tg_app.start()
    asyncio.create_task(tg_app.updater.start_polling())

@app.on_event("shutdown")
async def shutdown_event():
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()