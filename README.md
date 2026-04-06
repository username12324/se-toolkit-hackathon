# LMS Analytics & Hydration Bot

A full-stack project with two independent systems sharing a PostgreSQL database:

1. **LMS Analytics** – a learning management analytics platform for university instructors to monitor student progress across software engineering labs.
2. **Hydration Bot** – a Telegram bot + web dashboard for event broadcasts and personal hydration reminders.

---

## Part 1: LMS Analytics

### Dashboard

![Dashboard – Score Distribution and Pass Rates](docs/screenshots/dashboard-scores-passrates.png)

![Dashboard – Submissions Timeline and Group Performance](docs/screenshots/dashboard-timeline-groups.png)

### API (Swagger UI)

![Swagger UI – Analytics endpoints](docs/screenshots/swagger-analytics.png)

### Features

| Area | Feature | Description |
|---|---|---|
| **Backend** | Items CRUD | Tree-structured course items (course → labs → tasks → steps) with JSONB attributes |
| **Backend** | Learners | List (filterable by enrollment date) and create learners |
| **Backend** | Interactions | Log and query student attempts with scores |
| **Backend** | ETL Pipeline | Sync items and interaction logs from the autochecker API idempotently (`POST /pipeline/sync`) |
| **Backend** | Analytics | Score histogram, pass rates, submission timeline, group performance, completion rate, top learners |
| **Backend** | Auth | Bearer token (API key) authentication on all endpoints |
| **Backend** | CORS | Configurable cross-origin middleware |
| **Frontend** | API Key Login | Token persisted in `localStorage` |
| **Frontend** | Items Table | Lists all labs/tasks with ID, type, title, created date |
| **Frontend** | Dashboard | Lab selector + 4 chart cards (Submissions Timeline, Score Distribution, Group Performance, Task Pass Rates) and a pass rates table |
| **Infrastructure** | Docker Compose | Backend, PostgreSQL, pgAdmin, and Caddy reverse proxy |
| **Infrastructure** | Swagger UI | Interactive API docs at `/docs` |
| **Infrastructure** | pgAdmin | Database admin UI at `/utils/pgadmin` |

### Usage

**View the Dashboard**

1. Open `http://<VM_IP>:42002` in a browser.
2. Enter your API key (the value of `LMS_API_KEY` from your `.env` file).
3. Select a lab from the dropdown to view its analytics.

**Query the API**

Swagger UI is available at `http://<VM_IP>:42002/docs`. Use your API key as a Bearer token.

```bash
# Sync data from the autochecker
curl -X POST http://<VM_IP>:42002/pipeline/sync \
  -H "Authorization: Bearer <LMS_API_KEY>"

# Get task pass rates
curl http://<VM_IP>:42002/analytics/pass-rates \
  -H "Authorization: Bearer <LMS_API_KEY>"
```

---

## Part 2: Hydration Bot (`hydration-bot/`)

A Telegram bot with a **web-based organizer dashboard** for event broadcast reminders,
plus **personal hydration reminders** for individual users.

### Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Telegram Users  │     │  Event Organizers │     │  PostgreSQL  │
│  (participants)  │◄───►│  (web dashboard)  │◄───►│  (shared DB) │
│                  │     │   FastAPI + HTML  │     │              │
└──────────────────┘     └──────────────────┘     └──────────────┘
      python-telegram-bot        Jinja2              asyncpg
```

### Features

#### 💧 Personal Hydration Reminders

| Command / Action | Description |
|---|---|
| `/start` | Welcome message + inline menu to start/stop reminders |
| `/settime <min>` | Set reminder interval (15–240 min) |
| `/status` | Show current hydration settings |
| **▶️ Start / ⏹️ Stop** | Inline buttons to toggle reminders on/off |
| **Quick-select** | 15 min · 30 min · 1 hr · 2 hrs buttons |

All settings persist across bot restarts.

#### 📢 Event Broadcasts

| Feature | Description |
|---|---|
| **Organizer dashboard** | Create, edit, pause, delete broadcast schedules via web UI |
| **Time windows** | Messages only sent within allowed hours (e.g. 09:00–19:00), including overnight |
| **Targeted delivery** | Send to specific participant aliases registered by the organiser |
| **Subscribe / Unsubscribe** | Participants toggle per-broadcast subscriptions via inline buttons (`/events`) |
| **Delivery logging** | Every send attempt recorded with status (sent/failed) |
| **Auto-resume** | Broadcasts resume correctly after bot restart |

#### 🔐 Multi-tenant Web Dashboard

Each organiser registers their own participants and broadcasts. Data is isolated by `owner_id` — organisers only see their own resources.

### Project Structure

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
│   └── init.sql         # Full schema (users + participants + broadcasts + subscriptions + delivery_log)
├── Dockerfile           # Bot container
├── Dockerfile.web       # Web dashboard container
├── .env.example
├── requirements.txt
├── requirements-web.txt
└── README.md
```

### Database Schema

```
users                  – personal water reminder state (per Telegram user_id)
participants           – alias → telegram_chat_id mapping (per owner)
broadcasts             – schedule definition (message, interval, time window, active)
broadcast_targets      – many-to-many: broadcast ↔ participant aliases
broadcast_subscriptions– per-user subscribe/unsubscribe toggle per broadcast
delivery_log           – audit trail of every send attempt (sent/failed)
```

### Quick Start

**1. Configure environment**

```bash
cd hydration-bot
cp .env.example .env
# Set TELEGRAM_BOT_TOKEN from @BotFather
```

**2. Start the stack**

```bash
docker compose up --build -d
```

This launches:

| Service | Description | Port |
|---------|-------------|------|
| `db`    | PostgreSQL with persistent volume | 5432 |
| `bot`   | Telegram bot + broadcast scheduler | — |
| `web`   | Organizer dashboard (FastAPI) | 8000 |

**3. Use the bot**

Find your bot on Telegram and send `/start`.

**4. Open the web dashboard**

Navigate to `http://localhost:8000` in your browser.

### Bot Commands

| Command | Audience | Description |
|---|---|---|
| `/start` | Participants | Welcome + hydration reminder menu |
| `/settime <min>` | Participants | Set personal reminder interval |
| `/status` | Participants | Show hydration settings |
| `/events` | Participants | View broadcasts + subscribe/unsubscribe toggle buttons |

### Web Dashboard (Organisers)

1. **Participants** — register participant aliases and their Telegram Chat IDs.
2. **Broadcasts** — create schedules with message, interval, time window, and targets.
3. **Logs** — view delivery history with timestamps and status.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Bot token from @BotFather |
| `DB_NAME` | `hydration_bot` | PostgreSQL database name |
| `DB_USER` | `hydration_user` | PostgreSQL username |
| `DB_PASSWORD` | `changeme` | PostgreSQL password |
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5432` | PostgreSQL port |
| `WEB_PORT` | `8000` | Web dashboard port |
| `DEFAULT_INTERVAL` | `60` | Default water reminder interval (min) |
| `MIN_INTERVAL` | `15` | Minimum allowed interval |
| `MAX_INTERVAL` | `240` | Maximum allowed interval |

---

## LMS Deployment

### Prerequisites

- Docker 24+
- Docker Compose 2.20+
- Ubuntu 24.04 LTS (or any Linux with Docker)

### Deploy

```bash
git clone https://github.com/username12324/se-toolkit-hackathon.git
cd se-toolkit-hackathon

cp .env.docker.example .env.docker.secret
# Edit .env.docker.secret with your values

docker compose --env-file .env.docker.secret up --build -d
```

| Service | URL |
|---|---|
| Dashboard | `http://<VM_IP>:42002` |
| Swagger API Docs | `http://<VM_IP>:42002/docs` |
| pgAdmin | `http://<VM_IP>:<PGADMIN_HOST_PORT>/utils/pgadmin` |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **LMS Backend** | FastAPI (Python 3.11), asyncpg, PostgreSQL 18 |
| **LMS Frontend** | React, Bootstrap, Chart.js |
| **Bot** | python-telegram-bot v21, APScheduler |
| **Bot Web Dashboard** | FastAPI, Jinja2, asyncpg |
| **Containerisation** | Docker + Docker Compose |
| **Reverse Proxy** | Caddy |
