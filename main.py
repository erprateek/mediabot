import os
import re
import sqlite3
import asyncio
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# 1. Initialize FastAPI
app = FastAPI(title="Mac Mini Persistent Watch Log")

# 2. Database Initialization Helper
DB_FILE = "movies.db"

def init_db():
    """Creates the database file and table if it doesn't exist yet"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS watch_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user TEXT,
            title TEXT,
            rating TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the database immediately on script load
init_db()

# 3. Setup Telegram Bot
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
tg_app = Application.builder().token(TOKEN).build()

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes `/watch Movie Name - 9/10` and saves it to SQLite"""
    user = update.message.from_user.first_name
    text = " ".join(context.args)
    
    if not text:
        await update.message.reply_text("Format: /watch [Title] - [Rating/10]\nExample: /watch Breaking Bad - 10/10")
        return

    # Parse Title and Rating
    match = re.search(r"(.+?)\s*-\s*(\d+/10)", text)
    if match:
        title, rating = match.group(1).strip(), match.group(2).strip()
    else:
        title, rating = text, "No Rating"

    # Save to SQLite Database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute(
        "INSERT INTO watch_logs (user, title, rating, date) VALUES (?, ?, ?, ?)",
        (user, title, rating, current_time)
    )
    conn.commit()
    conn.close()

    await update.message.reply_text(f"💾 Permanently Saved: *{title}* ({rating})")

tg_app.add_handler(CommandHandler("watch", watch_command))

# 4. Web Dashboard Interface (Reads from SQLite)
@app.get("/", response_class=HTMLResponse)
async def web_dashboard():
    # Fetch all logs from the database, newest first
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT date, user, title, rating FROM watch_logs ORDER BY id DESC")
    rows_data = cursor.fetchall()
    conn.close()

    # Generate HTML rows dynamically
    rows = ""
    for row in rows_data:
        date, user, title, rating = row
        rows += f"<tr><td>{date}</td><td><b>{user}</b></td><td>{title}</td><td>⭐ {rating}</td></tr>"
    
    # If database is empty, show a friendly placeholder
    if not rows:
        rows = "<tr><td colspan='4' style='text-align:center;'>No movies logged yet! Type /watch in the chat.</td></tr>"

    return f"""
    <html>
        <head>
            <title>Mac Mini Movie Tracker</title>
            <style>
                body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; max-width: 800px; margin: 40px auto; padding: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: #1e293b; border-radius: 8px; overflow: hidden; }}
                th, td {{ padding: 14px; text-align: left; }}
                th {{ background-color: #334155; color: #38bdf8; }}
                tr {{ border-bottom: 1px solid #334155; }}
                tr:last-child {{ border: none; }}
            </style>
        </head>
        <body>
            <h2>🎬 Group Watch History (Saved to Mac Mini Disk)</h2>
            <table>
                <tr><th>Date</th><th>User</th><th>Title</th><th>Rating</th></tr>
                {rows}
            </table>
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
