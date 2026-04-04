
<!--Stop-->
>**\[!COPYRIGHT CAUTION]**\
>This project is based on Lab 7 of se-toolkit-labs, all the rights for all the content besides *hydration-bot* belong to Nursultan and se-toolkit team
# 💧 Hydration Reminder Bot

A Telegram bot that reminds users to drink water at configurable intervals.
Built with **python-telegram-bot v21**, **asyncpg**, **PostgreSQL**, and **Docker**.

---

## Features

- **Start / Stop** reminders via inline buttons.
- **Settable frequency** – `/settime <minutes>` or quick-select buttons (15 min, 30 min, 1 hr, 2 hrs).
- **Persistent state** – user preferences and active reminders stored in PostgreSQL.
- **Auto-restore** – after a bot restart, active reminders are re-scheduled from the database.
- **Graceful shutdown** – handles SIGTERM/SIGINT to cancel jobs and close DB connections.
- **Docker-ready** – one-command stack deployment with healthchecks.

---

## Project Structure

```
hydration-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py          # Entry point, signal handling, bootstrap
│   ├── handlers.py      # Command & callback handlers
│   ├── database.py      # asyncpg pool + CRUD helpers
│   ├── scheduler.py     # JobQueue reminder logic
│   └── config.py        # Settings from .env
├── db/
│   └── init.sql         # Schema bootstrap (runs on first DB startup)
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── requirements.txt
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

| Service | Description |
|---------|-------------|
| `db`    | PostgreSQL 15 with persistent volume |
| `bot`   | Python bot application |

### 3. Verify

```bash
docker compose logs -f bot
```

You should see:

```
Database ready.
Restored 0 reminder(s).
Starting bot polling …
```

### 4. Open Telegram

Find your bot and send `/start`.

---

## Local Development (no Docker)

### Prerequisites

- Python 3.11+
- PostgreSQL 15+ (running locally or remotely)

### 1. Set up a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
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
python -m bot.main
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message + main menu (Start/Stop buttons). |
| `/settime <min>` | Set reminder interval (15–240 minutes). |
| `/status` | Show current interval, active status, and last reminder time. |

### Inline Buttons

- **▶️ Start reminders** – begins periodic reminders at the user's interval.
- **⏹️ Stop reminders** – pauses reminders.
- **Quick-select** – 15 min · 30 min · 1 hr · 2 hrs.

---

## Database Schema

```sql
CREATE TABLE users (
    user_id          BIGINT PRIMARY KEY,
    username         TEXT,
    interval_minutes INT NOT NULL DEFAULT 60,
    reminder_active  BOOLEAN NOT NULL DEFAULT FALSE,
    last_reminder_time TIMESTAMP WITH TIME ZONE
);
```

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
| `DEFAULT_INTERVAL` | `60` | Default reminder interval (minutes). |
| `MIN_INTERVAL` | `15` | Minimum allowed interval. |
| `MAX_INTERVAL` | `240` | Maximum allowed interval. |

---

## Docker Compose Management

```bash
# Start
docker compose up --build -d

# View logs
docker compose logs -f bot

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

1. Cancels all scheduled reminder jobs.
2. Shuts down the Telegram Application.
3. Closes the asyncpg connection pool.

Docker sends `SIGTERM` automatically during `docker compose down`.

---

## Tech Stack

| Component | Library |
|-----------|---------|
| Telegram Bot | [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) v21 |
| PostgreSQL Driver | [asyncpg](https://github.com/MagicStack/asyncpg) 0.29 |
| Env vars | [python-dotenv](https://github.com/theskumar/python-dotenv) 1.0 |
| Containerisation | Docker + Docker Compose |
| Base image | `python:3.11-slim-bookworm` |
