"""Web dashboard for the Event Broadcast Reminder System.

FastAPI application providing an organizer dashboard for managing
broadcast schedules, participants, and viewing delivery logs.

Runs on localhost:8000 by default.
"""

from __future__ import annotations

import os
import re
from datetime import time as dtime
from contextlib import asynccontextmanager
from typing import Annotated

import asyncpg
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape
from itsdangerous import URLSafeTimedSerializer
from passlib.context import CryptContext

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DSN = os.getenv(
    "DB_DSN",
    "postgresql://hydration_user:changeme@db:5432/hydration_bot",
)
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-production")
SESSION_MAX_AGE = 60 * 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
signer = URLSafeTimedSerializer(SESSION_SECRET)

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,50}$")

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=DSN, min_size=2, max_size=10)
    return _pool


# --- Auth helpers ---

async def get_user_by_id(user_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username FROM app_users WHERE id = $1;", user_id
        )
    if row is None:
        return None
    return {"id": row["id"], "username": row["username"]}


async def get_user_by_username(username: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, password_hash FROM app_users WHERE username = $1;",
            username,
        )
    if row is None:
        return None
    return {"id": row["id"], "username": row["username"], "password_hash": row["password_hash"]}


async def create_user(username: str, password: str) -> dict | None:
    password_hash = pwd_context.hash(password)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO app_users (username, password_hash) VALUES ($1, $2) "
            "ON CONFLICT (username) DO NOTHING RETURNING id, username;",
            username,
            password_hash,
        )
    if row is None:
        return None
    return {"id": row["id"], "username": row["username"]}


# --- Session helpers ---

def create_session_token(user_id: int) -> str:
    return signer.dumps(user_id)


def verify_session_token(token: str) -> int | None:
    try:
        user_id = signer.loads(token, max_age=SESSION_MAX_AGE)
        return int(user_id)
    except Exception:
        return None


async def require_user(request: Request) -> dict:
    """FastAPI dependency: return the logged-in user or redirect to login."""
    token = request.cookies.get("session")
    if not token:
        return RedirectResponse(url="/login", status_code=303)
    user_id = verify_session_token(token)
    if user_id is None:
        return RedirectResponse(url="/login", status_code=303)
    user = await get_user_by_id(user_id)
    if user is None:
        return RedirectResponse(url="/login", status_code=303)
    return user


CurrentUser = Annotated[dict, Depends(require_user)]

# ---------------------------------------------------------------------------
# Participants (scoped by owner_id)
# ---------------------------------------------------------------------------

async def web_list_participants(owner_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT alias, telegram_chat_id, created_at FROM participants "
            "WHERE owner_id = $1 ORDER BY alias;",
            owner_id,
        )
    return [
        {
            "alias": r["alias"],
            "telegram_chat_id": r["telegram_chat_id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


async def web_add_participant(owner_id: int, alias: str, telegram_chat_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO participants (alias, telegram_chat_id, owner_id) VALUES ($1, $2, $3) "
            "ON CONFLICT (alias, owner_id) DO NOTHING RETURNING alias, telegram_chat_id, created_at;",
            alias,
            telegram_chat_id,
            owner_id,
        )
    if row is None:
        raise ValueError(f"Participant '{alias}' already exists.")
    return {
        "alias": row["alias"],
        "telegram_chat_id": row["telegram_chat_id"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def web_delete_participant(owner_id: int, alias: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM participants WHERE alias = $1 AND owner_id = $2;",
            alias, owner_id,
        )
    return result.split()[-1] != "0"


# ---------------------------------------------------------------------------
# Broadcasts (scoped by owner_id)
# ---------------------------------------------------------------------------

async def web_list_broadcasts(owner_id: int) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT b.id, b.message, b.interval_minutes, b.start_time, b.end_time,
                   b.is_active, b.last_sent_at, b.created_at,
                   ARRAY_AGG(t.participant_alias) FILTER (WHERE t.participant_alias IS NOT NULL) AS targets
            FROM broadcasts b
            LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id AND t.owner_id = $1
            WHERE b.owner_id = $1
            GROUP BY b.id ORDER BY b.id
            """,
            owner_id,
        )
    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "message": r["message"],
            "interval_minutes": r["interval_minutes"],
            "start_time": str(r["start_time"]),
            "end_time": str(r["end_time"]),
            "is_active": r["is_active"],
            "last_sent_at": r["last_sent_at"].isoformat() if r["last_sent_at"] else None,
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "targets": list(r["targets"]) if r["targets"] else [],
        })
    return results


async def web_get_broadcast(owner_id: int, broadcast_id: int) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT b.id, b.message, b.interval_minutes, b.start_time, b.end_time,
                   b.is_active, b.last_sent_at, b.created_at,
                   ARRAY_AGG(t.participant_alias) FILTER (WHERE t.participant_alias IS NOT NULL) AS targets
            FROM broadcasts b
            LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id AND t.owner_id = $1
            WHERE b.id = $2 AND b.owner_id = $1
            GROUP BY b.id
            """,
            owner_id, broadcast_id,
        )
    if row is None:
        return None
    return {
        "id": row["id"],
        "message": row["message"],
        "interval_minutes": row["interval_minutes"],
        "start_time": str(row["start_time"]),
        "end_time": str(row["end_time"]),
        "is_active": row["is_active"],
        "last_sent_at": row["last_sent_at"].isoformat() if row["last_sent_at"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "targets": list(row["targets"]) if row["targets"] else [],
    }


async def web_create_broadcast(
    owner_id: int,
    message: str,
    interval_minutes: int,
    start_time: str,
    end_time: str,
    targets: list[str],
) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO broadcasts (message, interval_minutes, start_time, end_time, owner_id)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, message, interval_minutes, start_time, end_time, is_active, created_at;
                """,
                message,
                interval_minutes,
                dtime.fromisoformat(start_time),
                dtime.fromisoformat(end_time),
                owner_id,
            )
            bid = row["id"]
            for alias in targets:
                await conn.execute(
                    "INSERT INTO broadcast_targets (broadcast_id, participant_alias, owner_id) VALUES ($1, $2, $3);",
                    bid, alias, owner_id,
                )
    return {
        "id": row["id"],
        "message": row["message"],
        "interval_minutes": row["interval_minutes"],
        "start_time": str(row["start_time"]),
        "end_time": str(row["end_time"]),
        "is_active": row["is_active"],
        "targets": targets,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def web_update_broadcast(
    owner_id: int,
    broadcast_id: int,
    *,
    message: str | None = None,
    interval_minutes: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    is_active: bool | None = None,
    targets: list[str] | None = None,
) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Verify ownership
        existing = await conn.fetchval(
            "SELECT id FROM broadcasts WHERE id = $1 AND owner_id = $2;",
            broadcast_id, owner_id,
        )
        if existing is None:
            return None

        updates: dict = {}
        if message is not None:
            updates["message"] = message
        if interval_minutes is not None:
            updates["interval_minutes"] = interval_minutes
        if start_time is not None:
            updates["start_time"] = dtime.fromisoformat(start_time)
        if end_time is not None:
            updates["end_time"] = dtime.fromisoformat(end_time)
        if is_active is not None:
            updates["is_active"] = is_active

        if updates:
            set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(updates.keys())]
            values = list(updates.values()) + [broadcast_id, owner_id]
            await conn.execute(
                f"UPDATE broadcasts SET {', '.join(set_clauses)} WHERE id = ${len(values)-1} AND owner_id = ${len(values)};",
                *values,
            )

        if targets is not None:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM broadcast_targets WHERE broadcast_id = $1 AND owner_id = $2;",
                    broadcast_id, owner_id,
                )
                for alias in targets:
                    await conn.execute(
                        "INSERT INTO broadcast_targets (broadcast_id, participant_alias, owner_id) VALUES ($1, $2, $3);",
                        broadcast_id, alias, owner_id,
                    )

    return await web_get_broadcast(owner_id, broadcast_id)


async def web_delete_broadcast(owner_id: int, broadcast_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM broadcasts WHERE id = $1 AND owner_id = $2;",
            broadcast_id, owner_id,
        )
        # Reset the ID sequence so new broadcasts start from 1 when table is empty
        count = await conn.fetchval("SELECT COUNT(*) FROM broadcasts;")
        if int(count) == 0:
            await conn.execute("ALTER SEQUENCE broadcasts_id_seq RESTART WITH 1;")
    return result.split()[-1] != "0"


# ---------------------------------------------------------------------------
# Delivery log (scoped by owner_id)
# ---------------------------------------------------------------------------

async def web_get_delivery_logs(owner_id: int, *, limit: int = 100, offset: int = 0) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT dl.id, dl.broadcast_id, dl.participant_alias, dl.sent_at, dl.status,
                   b.message
            FROM delivery_log dl
            LEFT JOIN broadcasts b ON dl.broadcast_id = b.id AND b.owner_id = $1
            WHERE dl.owner_id = $1
            ORDER BY dl.sent_at DESC LIMIT $2 OFFSET $3;
            """,
            owner_id, limit, offset,
        )
    results = []
    for r in rows:
        msg = r["message"]
        preview = (msg[:100] + "...") if msg and len(msg) > 100 else msg
        results.append({
            "id": r["id"],
            "broadcast_id": r["broadcast_id"],
            "participant_alias": r["participant_alias"],
            "sent_at": r["sent_at"].isoformat() if r["sent_at"] else None,
            "status": r["status"],
            "message_preview": preview,
        })
    return results


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown: manage the asyncpg pool."""
    await get_pool()
    yield
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


app = FastAPI(title="Event Broadcast Dashboard", version="1.0.0", lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_jinja_env = Environment(
    loader=FileSystemLoader(os.path.join(BASE_DIR, "templates")),
    autoescape=select_autoescape(["html", "xml"]),
)

templates = Jinja2Templates(env=_jinja_env)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


# ===================================================================
# Auth Pages (no login required)
# ===================================================================

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show login form."""
    return templates.TemplateResponse(
        request, "login.html", {"request": request, "error": None},
    )


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    """Authenticate and set session cookie."""
    user = await get_user_by_username(username)
    if user is None or not pwd_context.verify(password, user["password_hash"]):
        return templates.TemplateResponse(
            request, "login.html", {"request": request, "error": "Invalid username or password"},
        )
    token = create_session_token(user["id"])
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", token, httponly=True, max_age=SESSION_MAX_AGE, samesite="lax")
    return resp


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Show registration form."""
    return templates.TemplateResponse(
        request, "register.html", {"request": request, "error": None},
    )


@app.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    """Create a new user account."""
    if password != confirm_password:
        return templates.TemplateResponse(
            request, "register.html",
            {"request": request, "error": "Passwords do not match"},
        )
    if not USERNAME_RE.match(username):
        return templates.TemplateResponse(
            request, "register.html",
            {"request": request, "error": "Username must be 3-50 chars, letters/numbers/underscores only"},
        )
    if len(password) < 6:
        return templates.TemplateResponse(
            request, "register.html",
            {"request": request, "error": "Password must be at least 6 characters"},
        )

    user = await create_user(username, password)
    if user is None:
        return templates.TemplateResponse(
            request, "register.html",
            {"request": request, "error": "Username already taken"},
        )

    token = create_session_token(user["id"])
    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie("session", token, httponly=True, max_age=SESSION_MAX_AGE, samesite="lax")
    return resp


@app.post("/logout")
async def logout():
    """Clear session cookie."""
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie("session")
    return resp


# ===================================================================
# Protected Pages
# ===================================================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, user: CurrentUser):
    if isinstance(user, RedirectResponse):
        return user
    broadcasts = await web_list_broadcasts(user["id"])
    participants = await web_list_participants(user["id"])
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"broadcasts": broadcasts, "participants": participants,
         "current_user": user["username"]},
    )


@app.get("/participants", response_class=HTMLResponse)
async def participants_page(request: Request, user: CurrentUser):
    if isinstance(user, RedirectResponse):
        return user
    participants = await web_list_participants(user["id"])
    return templates.TemplateResponse(
        request, "participants.html",
        {"participants": participants, "current_user": user["username"]},
    )


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, user: CurrentUser, limit: int = 100, offset: int = 0):
    if isinstance(user, RedirectResponse):
        return user
    logs = await web_get_delivery_logs(user["id"], limit=limit, offset=offset)
    return templates.TemplateResponse(
        request, "logs.html",
        {"logs": logs, "limit": limit, "offset": offset,
         "current_user": user["username"]},
    )


@app.get("/broadcasts/new", response_class=HTMLResponse)
async def new_broadcast_page(request: Request, user: CurrentUser):
    if isinstance(user, RedirectResponse):
        return user
    participants = await web_list_participants(user["id"])
    return templates.TemplateResponse(
        request, "broadcast_form.html",
        {"broadcast": None, "participants": participants, "is_edit": False,
         "current_user": user["username"]},
    )


@app.get("/broadcasts/{broadcast_id}/edit", response_class=HTMLResponse)
async def edit_broadcast_page(request: Request, broadcast_id: int, user: CurrentUser):
    if isinstance(user, RedirectResponse):
        return user
    broadcast = await web_get_broadcast(user["id"], broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    participants = await web_list_participants(user["id"])
    return templates.TemplateResponse(
        request, "broadcast_form.html",
        {"broadcast": broadcast, "participants": participants, "is_edit": True,
         "current_user": user["username"]},
    )


# ===================================================================
# Form POST handlers (redirect after POST)
# ===================================================================

@app.post("/broadcasts")
async def form_create_broadcast(
    user: CurrentUser,
    message: str = Form(...),
    interval_minutes: int = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    targets: str = Form(""),
):
    if isinstance(user, RedirectResponse):
        return user
    target_list = [t.strip() for t in targets.split(",") if t.strip()] if targets else []
    await web_create_broadcast(
        user["id"], message, interval_minutes, start_time, end_time, target_list,
    )
    return RedirectResponse(url="/", status_code=303)


@app.post("/broadcasts/{broadcast_id}/update")
async def form_update_broadcast(
    user: CurrentUser,
    broadcast_id: int,
    message: str = Form(...),
    interval_minutes: int = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    is_active: str = Form("off"),
    targets: str = Form(""),
):
    if isinstance(user, RedirectResponse):
        return user
    target_list = [t.strip() for t in targets.split(",") if t.strip()] if targets else []
    active_val = is_active.lower() in ("true", "1", "yes", "on")
    result = await web_update_broadcast(
        user["id"], broadcast_id,
        message=message, interval_minutes=interval_minutes,
        start_time=start_time, end_time=end_time,
        is_active=active_val, targets=target_list,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Broadcast not found or not yours")
    return RedirectResponse(url="/", status_code=303)


@app.post("/broadcasts/{broadcast_id}/delete")
async def form_delete_broadcast(user: CurrentUser, broadcast_id: int):
    if isinstance(user, RedirectResponse):
        return user
    await web_delete_broadcast(user["id"], broadcast_id)
    return RedirectResponse(url="/", status_code=303)


@app.post("/participants")
async def form_add_participant(
    request: Request,
    user: CurrentUser,
    alias: str = Form(...),
    telegram_chat_id: int = Form(...),
):
    if isinstance(user, RedirectResponse):
        return user
    try:
        await web_add_participant(user["id"], alias, telegram_chat_id)
    except ValueError as e:
        participants = await web_list_participants(user["id"])
        return templates.TemplateResponse(
            request, "participants.html",
            {"participants": participants, "current_user": user["username"],
             "error": str(e)},
        )
    return RedirectResponse(url="/participants", status_code=303)


@app.post("/participants/{alias}/delete")
async def form_delete_participant(user: CurrentUser, alias: str):
    if isinstance(user, RedirectResponse):
        return user
    await web_delete_participant(user["id"], alias)
    return RedirectResponse(url="/participants", status_code=303)


# ===================================================================
# JSON API endpoints (also protected by auth)
# ===================================================================

@app.get("/api/broadcasts")
async def api_list_broadcasts(user: CurrentUser):
    if isinstance(user, RedirectResponse):
        return user
    return {"broadcasts": await web_list_broadcasts(user["id"])}


@app.get("/api/participants")
async def api_list_participants(user: CurrentUser):
    if isinstance(user, RedirectResponse):
        return user
    return {"participants": await web_list_participants(user["id"])}


@app.get("/api/logs")
async def api_get_logs(user: CurrentUser, limit: int = 100, offset: int = 0):
    if isinstance(user, RedirectResponse):
        return user
    return {"logs": await web_get_delivery_logs(user["id"], limit=limit, offset=offset)}
