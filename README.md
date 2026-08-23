# 🎬 MediaBot

A Telegram bot + FastAPI web dashboard for tracking movies and TV shows with your friends.
Logs what you've watched, fetches metadata from OMDb, and shows streaming availability via Watchmode.

## Project Structure

```
mediabot/
├── src/
│   ├── api/            # FastAPI app & routes
│   │   ├── __init__.py
│   │   └── dashboard.py
│   ├── bot/            # Telegram bot handlers
│   │   ├── __init__.py
│   │   └── handlers.py
│   ├── db/             # Database layer
│   │   ├── __init__.py
│   │   └── database.py
│   ├── services/       # External API integrations
│   │   ├── __init__.py
│   │   ├── omdb.py
│   │   └── watchmode.py
│   └── config.py       # Configuration / env vars
├── tests/
│   ├── unit/           # Fast, isolated unit tests
│   └── integration/    # Tests that touch DB or HTTP
├── scripts/
│   └── setup_launchd.sh   # macOS LaunchAgent installer
├── .github/
│   └── workflows/
│       └── ci.yml      # GitHub Actions CI (self-hosted runner)
├── main.py             # Entrypoint
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── pyproject.toml
```

## Setup

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your API keys
```

### 3. Run locally

```bash
python main.py
```

The FastAPI dashboard will be at `http://localhost:8000`

### 4. Run tests

```bash
pip install -r requirements-dev.txt
pytest
```

## CI / Self-Hosted Runner (Mac Mini)

This project uses GitHub Actions with a **self-hosted runner** on your Mac Mini.

```bash
# One-time setup — registers and installs the runner as a launchd service
./scripts/setup_launchd.sh
```

See [`scripts/setup_launchd.sh`](scripts/setup_launchd.sh) for full instructions.

## Environment Variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your BotFather token |
| `OMDB_API_KEY` | OMDb API key |
| `WATCHMODE_API_KEY` | Watchmode API key |
| `DB_FILE` | SQLite DB path (default: `movies.db`) |
| `REFRESH_INTERVAL_SECONDS` | Seconds between streaming refreshes (default: `604800` = weekly) |
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |
| `OLLAMA_MODEL` | Local model name (default: `gemma4:12b-it-qat`) |
| `HOST` / `PORT` | Dashboard bind address (defaults: `0.0.0.0` / `8000`) |
| `WATCHMODE_REGION` | Streaming sources region (default: `US`) |
