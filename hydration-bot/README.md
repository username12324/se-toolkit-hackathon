# 💧 Hydration & Event Broadcast Bot

A Telegram bot with a **web-based organizer dashboard** for event broadcast reminders,
plus **personal hydration reminders** for individual users.

Built with **python-telegram-bot v21**, **FastAPI**, **asyncpg**, **PostgreSQL**, and **Docker**.

---

## Overview

This system serves **two types of users**:

| Role | How they interact | What they do |
|------|-------------------|--------------|
| **Event Organizer** | Web dashboard (browser) | Create broadcast schedules, manage participants, view logs |
| **Event Participant** | Telegram bot | Receive broadcast messages, manage personal hydration reminders |

---

## Features

### 📢 Event Broadcasts (new)
- **Organizer web dashboard** – create, edit, pause, and delete broadcast schedules.
- **Time-of-day windows** – messages only sent within allowed hours (e.g. 09:00–19:00).
- **Overnight support** – correctly handles windows that cross midnight (e.g. 22:00–06:00).
- **Targeted audiences** – send to specific participant aliases or all participants.
- **Delivery logging** – every send attempt is recorded with status (sent/failed).
- **Auto-resume** – after a bot restart, broadcasts resume from the database state.

### 💧 Personal Hydration Reminders (original)
- **Start / Stop** reminders via inline buttons.
- **Settable frequency** – `/settime <minutes>` or quick-select buttons (15 min, 30 min, 1 hr, 2 hrs).
- **Persistent state** – user preferences stored in PostgreSQL.
- **Auto-restore** – active reminders re-scheduled after restart.

### General
- **Graceful shutdown** – handles SIGTERM/SIGINT cleanly.
- **Docker-ready** – three-service stack (db, bot, web) with healthchecks.

---

## Project Structure

```
hydration-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py          # Entry point, Telegram Application bootstrap
│   ├── handlers.py      # Command & callback handlers (water + /events)
│   ├── database.py      # asyncpg pool + CRUD (water + broadcast tables)
│   ├── scheduler.py     # JobQueue: water reminders + broadcast checker
│   └── config.py        # Settings from .env
├── web/
│   ├── app.py           # FastAPI web dashboard (organizer UI)
│   ├── templates/       # Jinja2 HTML templates
│   └── static/          # CSS styles
├── db/
│   └── init.sql         # Full schema (users + participants + broadcasts + delivery_log)
├── Dockerfile           # Bot container
├── Dockerfile.web       # Web dashboard container
├── docker-compose.yml   # Three services: db, bot, web
├── .env.example
├── requirements.txt
├── requirements-web.txt
└── README.md
```

---

## Quick Start (Docker Compose)

### 1. Create your `.env` file

```bash
cp .env.example .env
```

Edit `.env` and set your **Telegram Bot Token** (obtain one from
[@BotFather](https://t.me/BotFather)):

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

You can leave the other defaults as-is.

### 2. Start the stack

```bash
docker compose up --build -d
```

This launches:

| Service | Description | Port |
|---------|-------------|------|
| `db`    | PostgreSQL 15 with persistent volume | 5432 |
| `bot`   | Telegram bot + broadcast scheduler | — |
| `web`   | Organizer dashboard (FastAPI) | 8000 |

### 3. Verify

```bash
docker compose logs -f bot
```

You should see:

```
Database pool initialised …
Restored 0 water reminder(s).
Broadcast checker scheduled (every 1 minute).
Broadcast system ready (0 active broadcast(s)).
Starting bot polling …
```

### 4. Open Telegram

Find your bot and send `/start`.

### 5. Open the Web Dashboard

Navigate to **`http://localhost:8000`** in your browser.

---

## Using the System

### For Event Organizers (Web Dashboard)

#### 1. Add Participants

1. Go to **Participants** in the navbar.
2. Enter an **Alias** (e.g. `alice`, `team_lead_1`) and the participant's **Telegram Chat ID**.
3. Click **Add**.

> **How to find a participant's Chat ID:** Have them message
> [@userinfobot](https://t.me/userinfobot) on Telegram — it will reply with their numeric ID.

#### 2. Create a Broadcast Schedule

1. Go to **Dashboard** → click **+ New Broadcast**.
2. Fill in:
   - **Message** – the text to send (supports MarkdownV2: `*bold*`, `_italic_`).
   - **Interval** – how often (15 min, 30 min, 1 hr, 2 hrs, or custom).
   - **Start / End time** – daily window when messages are allowed.
   - **Targets** – select specific participants or leave unchecked for none.
   - **Active** – checked to start immediately, unchecked to create as paused.
3. Click **Create Broadcast**.

#### 3. Monitor Delivery

1. Go to **Logs** to see every send attempt with timestamp, target, and status.

### For Event Participants (Telegram)

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + hydration reminder menu. |
| `/settime <min>` | Set personal hydration reminder interval (15–240 min). |
| `/status` | Show current hydration settings. |
| `/events` | See which event broadcasts you're subscribed to. |

### Inline Buttons

- **▶️ Start reminders** – begin personal water reminders.
- **⏹️ Stop reminders** – pause personal water reminders.
- **Quick-select** – 15 min · 30 min · 1 hr · 2 hrs.

---

## Database Schema

```
users               – personal water reminder state (per Telegram user_id)
participants        – alias → telegram_chat_id mapping (for broadcasts)
broadcasts          – schedule definition (message, interval, time window, active)
broadcast_targets   – many-to-many: broadcast ↔ participant aliases
delivery_log        – audit trail of every send attempt (sent/failed)
```

See [`db/init.sql`](db/init.sql) for the full schema.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Bot token from @BotFather. |
| `DB_NAME` | `hydration_bot` | PostgreSQL database name. |
| `DB_USER` | `hydration_user` | PostgreSQL username. |
| `DB_PASSWORD` | `changeme` | PostgreSQL password. |
| `DB_HOST` | `localhost` | PostgreSQL host. |
| `DB_PORT` | `5432` | PostgreSQL port. |
| `WEB_PORT` | `8000` | Web dashboard port. |
| `DEFAULT_INTERVAL` | `60` | Default water reminder interval (minutes). |
| `MIN_INTERVAL` | `15` | Minimum allowed interval. |
| `MAX_INTERVAL` | `240` | Maximum allowed interval. |

---

## Docker Compose Management

```bash
# Start all services
docker compose up --build -d

# View bot logs
docker compose logs -f bot

# View web logs
docker compose logs -f web

# Stop (keeps DB data)
docker compose down

# Stop and delete DB data
docker compose down -v

# Rebuild only the bot
docker compose up -d --build bot
```

---

## Graceful Shutdown

The bot handles `SIGTERM` and `SIGINT`:

1. Cancels all scheduled JobQueue jobs (water reminders + broadcast checker).
2. Shuts down the Telegram Application.
3. Closes the asyncpg connection pool.

Docker sends `SIGTERM` automatically during `docker compose down`.

---

## Local Development (no Docker)

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (running locally or remotely)

### 1. Set up virtual environments

```bash
# Bot
python3.11 -m venv .venv-bot
source .venv-bot/bin/activate
pip install -r requirements.txt
deactivate

# Web
python3.11 -m venv .venv-web
source .venv-web/bin/activate
pip install -r requirements-web.txt
deactivate
```

### 2. Configure `.env`

```bash
cp .env.example .env
# Edit DB_HOST, DB_USER, DB_PASSWORD, DB_NAME as needed.
```

### 3. Create the database schema

```bash
psql -h localhost -U hydration_user -d hydration_bot -f db/init.sql
```

### 4. Run the bot

```bash
source .venv-bot/bin/activate
python -m bot.main
```

### 5. Run the web dashboard (separate terminal)

```bash
source .venv-web/bin/activate
export DB_DSN="postgresql://hydration_user:changeme@localhost:5432/hydration_bot"
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

---

## Tech Stack

| Component | Library |
|-----------|---------|
| Telegram Bot | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21 |
| Web Framework | [FastAPI](https://fastapi.tiangolo.com/) |
| PostgreSQL Driver | [asyncpg](https://github.com/MagicStack/asyncpg) 0.29 |
| Env vars | [python-dotenv](https://github.com/theskumar/python-dotenv) 1.0 |
| Templates | [Jinja2](https://jinja.palletsprojects.com/) |
| Containerisation | Docker + Docker Compose |
| Base image | `python:3.11-slim-bookworm` |
