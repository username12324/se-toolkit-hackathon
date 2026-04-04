
<!--Stop-->
>**\[!COPYRIGHT CAUTION]**\
>This project is based on Lab 7 of se-toolkit-labs, all the rights for all the content besides *hydration-bot* belong to Nursultan and se-toolkit team
# 💧 Hydration Reminder Bot

# LMS Analytics & Telegram Bot

A full-stack learning management analytics platform with a conversational Telegram bot, designed for university instructors to monitor student progress across software engineering labs.

---

## Demo

### Dashboard

![Dashboard – Score Distribution and Pass Rates](docs/screenshots/dashboard-scores-passrates.png)

![Dashboard – Submissions Timeline and Group Performance](docs/screenshots/dashboard-timeline-groups.png)

### API (Swagger UI)

![Swagger UI – Analytics endpoints](docs/screenshots/swagger-analytics.png)

---

## Product Context

### End Users

- **University instructors and teaching assistants** who need to monitor student lab submissions, scores, and progress.
- **Course coordinators** who manage multiple groups and labs within a semester.

### Problem

Instructors lack a centralized, visual way to see how students are performing across labs and tasks. Raw grading data from auto-grading systems is hard to interpret at a glance, making it difficult to spot struggling students or problematic assignments early.

### Solution

LMS Analytics ingests grading data from an external autochecker service via an ETL pipeline, stores it in PostgreSQL, and exposes it through:

1. **A React dashboard** with interactive charts (score distributions, submission timelines, group performance, task pass rates).
2. **A FastAPI REST API** with analytics endpoints and Swagger UI for exploration.
3. **A Telegram bot** (in development) that lets instructors query analytics via natural language powered by an LLM.

---

## Features

### Implemented

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
| **Bot** | CLI Test Mode | Run slash commands and natural language queries locally via `--test` flag |
| **Bot** | LLM Intent Routing | Tool-calling logic mapping natural language to 9 backend API tools |
| **Infrastructure** | Docker Compose | Backend, PostgreSQL, pgAdmin, and Caddy reverse proxy |
| **Infrastructure** | Swagger UI | Interactive API docs at `/docs` |
| **Infrastructure** | pgAdmin | Database admin UI at `/utils/pgadmin` |

### Not Yet Implemented

| Area | Feature | Priority |
|---|---|---|
| **Bot** | Telegram polling / webhook mode | P0 |
| **Bot** | Bot Dockerfile & `docker-compose` service | P0 |
| **Bot** | Inline keyboard / reply keyboards | P1 |
| **Bot** | Periodic health checks & scheduled analytics reports | P1 |
| **Bot** | Rich response formatting (charts as images) | P2 |
| **Bot** | Multi-turn conversation context | P2 |
| **Bot** | Response caching | P2 |
| **Frontend** | Learner detail pages with individual history | — |
| **Frontend** | Export charts as images / PDF reports | — |

---

## Usage

### View the Dashboard

1. Open `http://<VM_IP>:42002` in a browser.
2. Enter your API key (the value of `LMS_API_KEY` from your `.env` file).
3. Select a lab from the dropdown to view its analytics.

### Query the API

Swagger UI is available at `http://<VM_IP>:42002/docs`. Use your API key as a Bearer token in the `Authorize` dialog.

Example — sync data from the autochecker:

```bash
curl -X POST http://<VM_IP>:42002/pipeline/sync \
  -H "Authorization: Bearer <LMS_API_KEY>"
```

Example — get task pass rates:

```bash
curl http://<VM_IP>:42002/analytics/pass-rates \
  -H "Authorization: Bearer <LMS_API_KEY>"
```

### Use the Telegram Bot (Test Mode)

```bash
# From the project root, with .env.bot.secret configured:
uv run poe bot-test -- "/start"
uv run poe bot-test -- "what labs are available?"
uv run poe bot-test -- "which task has the lowest pass rate?"
```

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

# Docker Compose is included with Docker Engine on modern installs
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
cp .env.docker.example .env.docker.secret
```

Edit `.env.docker.secret` and set the required values:

| Variable | Description |
|---|---|
| `LMS_API_KEY` | Secret key for API authentication |
| `AUTOCHECKER_API_URL` | URL of the external autochecker grading service |
| `AUTOCHECKER_API_LOGIN` | Login for the autochecker API |
| `AUTOCHECKER_API_PASSWORD` | Password for the autochecker API |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER` | PostgreSQL username |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `PGADMIN_EMAIL` | Email for pgAdmin login |
| `PGADMIN_PASSWORD` | Password for pgAdmin login |
| `BACKEND_HOST_ADDRESS` | Host IP to bind the backend (use `127.0.0.1`) |
| `BACKEND_HOST_PORT` | Host port for the backend (e.g. `8000`) |
| `BACKEND_CONTAINER_PORT` | Container port for the backend (e.g. `8000`) |
| `LMS_API_HOST_ADDRESS` | Host IP for the public API/dashboard (use `0.0.0.0`) |
| `LMS_API_HOST_PORT` | Public port for the dashboard (e.g. `42002`) |
| `CADDY_CONTAINER_PORT` | Caddy container port (e.g. `80`) |

Refer to `.env.docker.example` for all available variables and defaults.

**3. (Optional) Configure the Telegram bot**

```bash
cp .env.bot.example .env.bot.secret
```

Edit `.env.bot.secret` and set `BOT_TOKEN` (from BotFather) and `LLM_API_KEY` (for the LLM provider).

**4. Start the services**

```bash
docker compose --env-file .env.docker.secret up --build -d
```

This launches four containers:

| Service | Description |
|---|---|
| `backend` | FastAPI application |
| `postgres` | PostgreSQL 18 (with healthcheck and initial data seed) |
| `pgadmin` | pgAdmin web interface |
| `caddy` | Reverse proxy serving the React frontend |

**5. Verify the deployment**

```bash
docker compose ps
```

All services should show a `running` status. Check logs for any service:

```bash
docker compose logs backend
```

**6. Sync data from the autochecker**

```bash
curl -X POST http://localhost:42002/pipeline/sync \
  -H "Authorization: Bearer <LMS_API_KEY>"
```

**7. Access the application**

| Service | URL |
|---|---|
| Dashboard | `http://<VM_IP>:42002` |
| Swagger API Docs | `http://<VM_IP>:42002/docs` |
| pgAdmin | `http://<VM_IP>:<PGADMIN_HOST_PORT>/utils/pgadmin` |

**8. (Optional) Run the bot in test mode**

```bash
uv sync
uv run poe bot-test -- "/start"
```
