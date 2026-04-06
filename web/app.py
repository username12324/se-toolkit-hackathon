"""
Web app for the Event Broadcast Reminder System.

FastAPI application providing an organizer dashboard for managing
broadcast schedules, participants, and viewing delivery logs.

Runs on localhost:8000 by default.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from database_broadcast import (
    get_session_factory,
    list_participants,
    add_participant,
    delete_participant,
    list_broadcasts,
    get_broadcast,
    create_broadcast,
    update_broadcast,
    delete_broadcast,
    get_delivery_logs,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    yield


app = FastAPI(
    title="Event Broadcast Dashboard",
    description="Organizer dashboard for managing broadcast reminders",
    version="1.0.0",
    lifespan=lifespan,
)

# Template and static file setup
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Session factory (lazy init to allow env vars to be set)
_session_factory = None


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory_from_module()
    return _session_factory


def get_session_factory_from_module():
    """Import and call the session factory from database_broadcast module."""
    import sys

    # Add bot directory to path
    bot_dir = os.path.join(os.path.dirname(BASE_DIR), "bot")
    if bot_dir not in sys.path:
        sys.path.insert(0, bot_dir)

    from database_broadcast import get_session_factory as _get_sf

    return _get_sf()


# ─── Pages ──────────────────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard – list all broadcast schedules."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        broadcasts = await list_broadcasts(session)
        participants = await list_participants(session)

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "broadcasts": broadcasts,
        "participants": participants,
    })


@app.get("/participants", response_class=HTMLResponse)
async def participants_page(request: Request):
    """Participants management page."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        participants = await list_participants(session)

    return templates.TemplateResponse("participants.html", {
        "request": request,
        "participants": participants,
    })


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request, limit: int = 100, offset: int = 0):
    """Delivery logs page."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        logs = await get_delivery_logs(session, limit=limit, offset=offset)

    return templates.TemplateResponse("logs.html", {
        "request": request,
        "logs": logs,
        "limit": limit,
        "offset": offset,
    })


@app.get("/broadcasts/new", response_class=HTMLResponse)
async def new_broadcast_page(request: Request):
    """Create new broadcast form."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        participants = await list_participants(session)

    return templates.TemplateResponse("broadcast_form.html", {
        "request": request,
        "broadcast": None,
        "participants": participants,
        "is_edit": False,
    })


@app.get("/broadcasts/{broadcast_id}/edit", response_class=HTMLResponse)
async def edit_broadcast_page(request: Request, broadcast_id: int):
    """Edit broadcast form."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        broadcast = await get_broadcast(session, broadcast_id)
        participants = await list_participants(session)

    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    return templates.TemplateResponse("broadcast_form.html", {
        "request": request,
        "broadcast": broadcast,
        "participants": participants,
        "is_edit": True,
    })


# ─── API Endpoints ──────────────────────────────────────────────────────────


@app.get("/api/broadcasts")
async def api_list_broadcasts():
    """GET /api/broadcasts – list all broadcast schedules."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        broadcasts = await list_broadcasts(session)
    return JSONResponse(content={"broadcasts": broadcasts})


@app.post("/api/broadcasts")
async def api_create_broadcast(
    message: str = Form(...),
    interval_minutes: int = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    targets: str = Form(...),  # Comma-separated aliases
):
    """POST /api/broadcasts – create a new broadcast schedule."""
    target_list = [t.strip() for t in targets.split(",") if t.strip()] if targets else []

    session_factory = get_session_factory()
    async with session_factory() as session:
        broadcast = await create_broadcast(
            session,
            message=message,
            interval_minutes=interval_minutes,
            start_time=start_time,
            end_time=end_time,
            targets=target_list,
        )

    return JSONResponse(content={"broadcast": broadcast})


@app.put("/api/broadcasts/{broadcast_id}")
async def api_update_broadcast(
    broadcast_id: int,
    message: Optional[str] = Form(None),
    interval_minutes: Optional[int] = Form(None),
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
    is_active: Optional[str] = Form(None),
    targets: Optional[str] = Form(None),
):
    """PUT /api/broadcasts/{id} – update a broadcast schedule."""
    target_list = (
        [t.strip() for t in targets.split(",") if t.strip()] if targets else None
    )

    # Parse is_active from form string
    active_val = None
    if is_active is not None:
        active_val = is_active.lower() in ("true", "1", "yes", "on")

    session_factory = get_session_factory()
    async with session_factory() as session:
        broadcast = await update_broadcast(
            session,
            broadcast_id=broadcast_id,
            message=message,
            interval_minutes=interval_minutes,
            start_time=start_time,
            end_time=end_time,
            is_active=active_val,
            targets=target_list,
        )

    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    return JSONResponse(content={"broadcast": broadcast})


@app.delete("/api/broadcasts/{broadcast_id}")
async def api_delete_broadcast(broadcast_id: int):
    """DELETE /api/broadcasts/{id} – delete a broadcast schedule."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        deleted = await delete_broadcast(session, broadcast_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    return JSONResponse(content={"success": True})


@app.get("/api/participants")
async def api_list_participants():
    """GET /api/participants – list all participants."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        participants = await list_participants(session)
    return JSONResponse(content={"participants": participants})


@app.post("/api/participants")
async def api_add_participant(
    alias: str = Form(...),
    telegram_chat_id: int = Form(...),
):
    """POST /api/participants – add a participant."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        participant = await add_participant(session, alias, telegram_chat_id)
    return JSONResponse(content={"participant": participant})


@app.delete("/api/participants/{alias}")
async def api_delete_participant(alias: str):
    """DELETE /api/participants/{alias} – remove a participant."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        deleted = await delete_participant(session, alias)

    if not deleted:
        raise HTTPException(status_code=404, detail="Participant not found")

    return JSONResponse(content={"success": True})


@app.get("/api/logs")
async def api_get_logs(limit: int = 100, offset: int = 0):
    """GET /api/logs – get delivery log entries."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        logs = await get_delivery_logs(session, limit=limit, offset=offset)
    return JSONResponse(content={"logs": logs, "limit": limit, "offset": offset})


# ─── Form handlers (POST redirects) ─────────────────────────────────────────


@app.post("/broadcasts")
async def form_create_broadcast(
    message: str = Form(...),
    interval_minutes: int = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    targets: str = Form(""),
):
    """Form handler: create broadcast and redirect to dashboard."""
    target_list = [t.strip() for t in targets.split(",") if t.strip()] if targets else []

    session_factory = get_session_factory()
    async with session_factory() as session:
        await create_broadcast(
            session,
            message=message,
            interval_minutes=interval_minutes,
            start_time=start_time,
            end_time=end_time,
            targets=target_list,
        )

    return RedirectResponse(url="/", status_code=303)


@app.post("/broadcasts/{broadcast_id}/update")
async def form_update_broadcast(
    broadcast_id: int,
    message: str = Form(...),
    interval_minutes: int = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(...),
    is_active: str = Form("off"),
    targets: str = Form(""),
):
    """Form handler: update broadcast and redirect to dashboard."""
    target_list = [t.strip() for t in targets.split(",") if t.strip()] if targets else []
    active_val = is_active.lower() in ("true", "1", "yes", "on")

    session_factory = get_session_factory()
    async with session_factory() as session:
        await update_broadcast(
            session,
            broadcast_id=broadcast_id,
            message=message,
            interval_minutes=interval_minutes,
            start_time=start_time,
            end_time=end_time,
            is_active=active_val,
            targets=target_list,
        )

    return RedirectResponse(url="/", status_code=303)


@app.post("/broadcasts/{broadcast_id}/delete")
async def form_delete_broadcast(broadcast_id: int):
    """Form handler: delete broadcast and redirect to dashboard."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        await delete_broadcast(session, broadcast_id)

    return RedirectResponse(url="/", status_code=303)


@app.post("/participants")
async def form_add_participant(
    alias: str = Form(...),
    telegram_chat_id: int = Form(...),
):
    """Form handler: add participant and redirect to participants page."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        await add_participant(session, alias, telegram_chat_id)

    return RedirectResponse(url="/participants", status_code=303)


@app.post("/participants/{alias}/delete")
async def form_delete_participant(alias: str):
    """Form handler: delete participant and redirect."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        await delete_participant(session, alias)

    return RedirectResponse(url="/participants", status_code=303)
