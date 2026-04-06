# 💧 Hydration & Event Broadcast Bot

A Telegram bot with a web-based organizer dashboard for event broadcast reminders and personal hydration reminders.

---

## Demo

### Organizer Web Dashboard

![Organizer Dashboard – Participants and Broadcasts](docs/screenshots/dashboard-participants-broadcasts.png)

![Broadcast Form – Create and Target Participants](docs/screenshots/broadcast-form.png)

### Telegram Bot

![Bot /start – Welcome Menu with Hydration Buttons](docs/screenshots/bot-start-menu.png)

![Bot /events – Broadcast Subscription Toggle Buttons](docs/screenshots/bot-events-subscribe.png)

---

## Product Context

### End Users

- **Event organisers** (team leads, teachers, community managers) who need to send recurring reminder messages to a group of people at specific times.
- **Event participants** who receive broadcast messages and can also set up personal hydration reminders to stay healthy during long sessions.

### Problem

Sending recurring reminders to a group of people is tedious. Organisers must remember who to message, what to say, and when. Participants have no easy way to opt out of broadcasts they no longer care about. Meanwhile, people working long hours forget to drink water.

### Solution

1. **Organisers** use a web dashboard to define broadcast schedules (message, interval, daily time window, target audience). The bot automatically delivers messages to subscribed participants.
2. **Participants** use the Telegram bot to receive broadcasts and can subscribe/unsubscribe per broadcast with a single button press. They can also set up personal hydration reminders with configurable intervals.

---

## Features

### Implemented

| Area | Feature | Description |
|---|---|---|
| **Bot** | Hydration Reminders | Start/stop personal water reminders via inline buttons |
| **Bot** | Custom Intervals | `/settime <min>` or quick-select buttons (15 min, 30 min, 1 hr, 2 hrs) |
| **Bot** | Broadcast Receipt | Receive scheduled event broadcasts from organisers |
| **Bot** | Subscribe / Unsubscribe | Inline toggle buttons per broadcast via `/events` |
| **Bot** | Auto-restore | Active reminders and broadcasts resume after restart |
| **Web** | Organizer Dashboard | FastAPI + Jinja2 HTML dashboard with session-based auth |
| **Web** | Participant Management | Register participants with alias + Telegram Chat ID |
| **Web** | Broadcast Management | Create, edit, pause, delete broadcast schedules |
| **Web** | Time Windows | Messages only sent within configured hours (incl. overnight) |
| **Web** | Delivery Logs | View every send attempt with timestamp and status |
| **Web** | Multi-tenant | Each organiser sees only their own participants and broadcasts |
| **Database** | Persistent State | PostgreSQL stores all users, broadcasts, participants, subscriptions |
| **Infrastructure** | Docker Compose | Three services: PostgreSQL, bot, web dashboard |

### Not Yet Implemented

| Area | Feature | Priority |
|---|---|---|
| **Bot** | Rich message formatting (images, charts) | P1 |
| **Bot** | Multi-language support (i18n) | P2 |
| **Bot** | Notification for broadcast changes | P2 |
| **Web** | Participant import/export (CSV) | P1 |
| **Web** | Real-time delivery status dashboard (WebSocket) | P2 |
| **Web** | Broadcast analytics (open rate, delivery rate) | P2 |
| **Infrastructure** | HTTPS / Let's Encrypt for dashboard | P1 |
| **Infrastructure** | Health-check endpoint for the bot | P1 |

---

## Usage

### For Event Organisers

1. Open `http://<VM_IP>:8000` in a browser.
2. **Register** an account (username + password).
3. Go to **Participants** → add participant aliases and their Telegram Chat IDs.
   > Participants can find their Chat ID by messaging [@userinfobot](https://t.me/userinfobot).
4. Go to **Dashboard** → click **+ New Broadcast** → fill in message, interval, time window, and targets.
5. Check **Logs** to monitor delivery status.

### For Event Participants

1. Find the bot on Telegram and send `/start`.
2. Use the inline buttons to **start** or **stop** personal hydration reminders.
3. Set a custom interval with `/settime <minutes>`.
4. Send `/events` to see broadcasts you're registered for — tap the toggle buttons to **subscribe** or **unsubscribe**.

---

## Deployment

### Target OS

Ubuntu 24.04 LTS (or any Linux distribution with Docker and Docker Compose support).

### Prerequisites

The VM must have the following installed:

| Tool | Version | Purpose |
|---|---|---|
| **Docker** | 24+ | Container runtime |
| **Docker Compose** | 2.20+ | Multi-container orchestration |
| **Git** | — | Clone the repository |

On a fresh Ubuntu 24.04 VM, install prerequisites with:

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in for group changes to take effect

# Verify:
docker compose version
```

### Step-by-Step Deployment

**1. Clone the repository**

```bash
git clone https://github.com/username12324/se-toolkit-hackathon.git
cd se-toolkit-hackathon
```

**2. Configure environment variables**

```bash
cd hydration-bot
cp .env.example .env
```

Edit `.env` and set the required values:

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `DB_NAME` | PostgreSQL database name (default: `hydration_bot`) |
| `DB_USER` | PostgreSQL username (default: `hydration_user`) |
| `DB_PASSWORD` | PostgreSQL password (change from default `changeme`) |
| `DB_HOST` | PostgreSQL host — set to `db` for Docker Compose |
| `DB_PORT` | PostgreSQL port (default: `5432`) |
| `WEB_PORT` | Web dashboard port (default: `8000`) |
| `DEFAULT_INTERVAL` | Default hydration reminder interval in minutes (default: `60`) |
| `MIN_INTERVAL` | Minimum allowed interval (default: `15`) |
| `MAX_INTERVAL` | Maximum allowed interval (default: `240`) |

**3. Start the services**

```bash
docker compose up --build -d
```

This launches three containers:

| Service | Description |
|---|---|
| `db` | PostgreSQL 15 with persistent volume and schema seeding |
| `bot` | Telegram bot + broadcast scheduler |
| `web` | Organizer web dashboard (FastAPI + Jinja2) |

**4. Verify the deployment**

```bash
docker compose ps
```

All services should show `running` status. Check bot logs:

```bash
docker compose logs -f bot
```

You should see:

```
Database pool initialised …
Restored 0 water reminder(s).
Broadcast checker scheduled (every 1 minute).
Broadcast system ready.
Starting bot polling …
```

**5. Access the application**

| Service | URL |
|---|---|
| Web Dashboard | `http://<VM_IP>:8000` |
| Telegram Bot | Search for your bot username on Telegram |

**6. Register as an organiser**

1. Open the dashboard → click **Register**.
2. Create a username and password.
3. You'll be redirected to the dashboard where you can add participants and create broadcasts.

### Docker Compose Management

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
