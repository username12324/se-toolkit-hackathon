# 💧 Hydration & Event Broadcast Bot

A Telegram bot with a **web-based organizer dashboard** for event broadcast reminders,
plus **personal hydration reminders** for individual users.

Built with **python-telegram-bot v21**, **FastAPI**, **asyncpg**, **PostgreSQL**, and **Docker**.

---

## Overview

This system serves **two types of users**:

| Role | How they interact | What they do |
|------|-------------------|--------------|
| **Event Organizer** | Web dashboard (browser) | Create broadcast schedules, manage participants, view delivery logs |
| **Event Participant** | Telegram bot | Receive broadcasts, manage personal hydration reminders |

---

## Features

### 💧 Personal Hydration Reminders

| Command / Action | Description |
|---|---|
| `/start` | Welcome message + inline menu to start/stop reminders |
| `/settime <min>` | Set reminder interval (15–240 min) |
| `/status` | Show current hydration settings |
| **▶️ Start / ⏹️ Stop** | Inline buttons to toggle reminders on/off |
| **Quick-select** | 15 min · 30 min · 1 hr · 2 hrs buttons |

All settings persist across bot restarts and are automatically restored.

### 📢 Event Broadcasts

| Feature | Description |
|---|---|
| **Organizer dashboard** | Create, edit, pause, and delete broadcast schedules via web UI |
| **Time windows** | Messages only sent within allowed hours (e.g. 09:00–19:00), including overnight |
| **Targeted delivery** | Send to specific participant aliases registered by the organiser |
| **Subscribe / Unsubscribe** | Participants toggle per-broadcast subscriptions via inline buttons (`/events`) |
| **Delivery logging** | Every send attempt recorded with status (sent/failed) |
| **Auto-resume** | Broadcasts resume correctly after bot restart |

### 🔐 Multi-tenant Web Dashboard

Each organiser registers their own participants and broadcasts. Data is isolated by `owner_id` — organisers only see their own resources.

---

## Project Structure

```
hydration-bot/
├── bot/
│   ├── main.py          # Entry point, Telegram Application bootstrap
│   ├── handlers.py      # Command & callback handlers (water + broadcasts)
│   ├── database.py      # asyncpg pool + CRUD (users, participants, broadcasts, subscriptions)
│   ├── scheduler.py     # JobQueue: water reminders + broadcast checker
│   └── config.py        # Settings from .env
├── web/
│   ├── app.py           # FastAPI web dashboard (organizer UI)
│   ├── templates/       # Jinja2 HTML templates
│   └── static/          # CSS styles
├── db/
│   └── init.sql         # Full schema
├── Dockerfile           # Bot container
├── Dockerfile.web       # Web dashboard container
├── .env.example
├── requirements.txt
├── requirements-web.txt
└── README.md
```

---

## Database Schema

```
users                  – personal water reminder state (per Telegram user_id)
participants           – alias → telegram_chat_id mapping (per owner)
broadcasts             – schedule definition (message, interval, time window, active)
broadcast_targets      – many-to-many: broadcast ↔ participant aliases
broadcast_subscriptions– per-user subscribe/unsubscribe toggle per broadcast
delivery_log           – audit trail of every send attempt (sent/failed)
```

---

## Quick Start

### 1. Configure environment

```bash
cd hydration-bot
cp .env.example .env
```

Edit `.env` and set your **Telegram Bot Token** (obtain one from [@BotFather](https://t.me/BotFather)):

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
| `db`    | PostgreSQL with persistent volume | 5432 |
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

#### 1. Register

Open the dashboard → click **Register** → create an account.

#### 2. Add Participants

1. Go to **Participants** in the navbar.
2. Enter an **Alias** (e.g. `alice`, `team_lead_1`) and the participant's **Telegram Chat ID**.
3. Click **Add**.

> **How to find a participant's Chat ID:** Have them message
> [@userinfobot](https://t.me/userinfobot) on Telegram — it will reply with their numeric ID.

#### 3. Create a Broadcast

1. Go to **Dashboard** → click **+ New Broadcast**.
2. Fill in:
   - **Message** – the text to send (supports Markdown).
   - **Interval** – how often (minutes).
   - **Start / End time** – daily window when messages are allowed.
   - **Targets** – select specific participants.
   - **Active** – checked to start immediately, unchecked to create as paused.
3. Click **Create Broadcast**.

#### 4. Monitor Delivery

Go to **Logs** to see every send attempt with timestamp, target, and status.

### For Event Participants (Telegram)

| Command | Description |
|---|---|
| `/start` | Welcome message + hydration reminder menu |
| `/settime <min>` | Set personal hydration reminder interval (15–240 min) |
| `/status` | Show current hydration settings |
| `/events` | View broadcasts + subscribe/unsubscribe toggle buttons |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Bot token from @BotFather |
| `DB_NAME` | `hydration_bot` | PostgreSQL database name |
| `DB_USER` | `hydration_user` | PostgreSQL username |
| `DB_PASSWORD` | `changeme` | PostgreSQL password |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `WEB_PORT` | `8000` | Web dashboard port |
| `DEFAULT_INTERVAL` | `60` | Default water reminder interval (minutes) |
| `MIN_INTERVAL` | `15` | Minimum allowed interval |
| `MAX_INTERVAL` | `240` | Maximum allowed interval |

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
