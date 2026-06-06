import os
import re
import asyncio
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# 1. Initialize FastAPI
app = FastAPI(title="Mac Mini Watch Log")

# Local data storage (wipes on restart—we can add a database file later)
watch_logs = [
    {"user": "System", "title": "Mac Mini Server Active!", "rating": "10/10", "date": "System Start"}
]

# 2. Setup Telegram Bot
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
tg_app = Application.builder().token(TOKEN).build()

async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes `/watch Movie Name - 9/10` in the group chat"""
    user = update.message.from_user.first_name
    text = " ".join(context.args)
    
    if not text:
        await update.message.reply_text("Format: /watch [Title] - [Rating/10]\nExample: /watch Interstellar - 9/10")
        return

    # Parse Title and Rating
    match = re.search(r"(.+?)\s*-\s*(\d+/10)", text)
    if match:
        title, rating = match.group(1).strip(), match.group(2).strip()
    else:
        title, rating = text, "No Rating"

    # Save to our list
    watch_logs.append({
        "user": user,
        "title": title,
        "rating": rating,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    })

    await update.message.reply_text(f"🍿 Logged: *{title}* ({rating})")

tg_app.add_handler(CommandHandler("watch", watch_command))

# 3. Web Dashboard Interface
@app.get("/", response_class=HTMLResponse)
async def web_dashboard():
    rows = "".join([
        f"<tr><td>{log['date']}</td><td><b>{log['user']}</b></td><td>{log['title']}</td><td>⭐ {log['rating']}</td></tr>"
        for log in reversed(watch_logs)
    ])
    
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
            <h2>🎬 Group Watch History (Hosted on Mac Mini)</h2>
            <table>
                <tr><th>Date</th><th>User</th><th>Title</th><th>Rating</th></tr>
                {rows}
            </table>
        </body>
    </html>
    """

# 4. Orchestration: Running both Bot Polling & Web Server together
@app.on_event("startup")
async def startup_event():
    # Start Telegram polling in the background when FastAPI starts
    await tg_app.initialize()
    await tg_app.start()
    # Create an asynchronous background task so it runs non-stop
    asyncio.create_task(tg_app.updater.start_polling())

@app.on_event("shutdown")
async def shutdown_event():
    # Clean up gracefully when shutting down
    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()
