"""
Database functions for the broadcast reminder system.

Provides async CRUD operations for participants, broadcasts, delivery logs,
and personal water reminders. Shared between the web app and the bot.
"""

import os
from datetime import time, datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


def get_engine():
    """Create async engine from environment variables."""
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "lms")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")

    dsn = f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    return create_async_engine(dsn, echo=False)


def get_session_factory():
    """Create async session factory."""
    engine = get_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ─── Participants ───────────────────────────────────────────────────────────

async def list_participants(session: AsyncSession) -> list[dict]:
    """Return all participants as list of dicts."""
    result = await session.execute(
        text("SELECT alias, telegram_chat_id, created_at FROM participants ORDER BY alias")
    )
    rows = result.fetchall()
    return [
        {
            "alias": r.alias,
            "telegram_chat_id": r.telegram_chat_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


async def add_participant(
    session: AsyncSession, alias: str, telegram_chat_id: int
) -> dict:
    """Add a new participant. Returns the created participant dict."""
    await session.execute(
        text(
            "INSERT INTO participants (alias, telegram_chat_id) VALUES (:alias, :chat_id)"
        ),
        {"alias": alias, "chat_id": telegram_chat_id},
    )
    await session.commit()

    result = await session.execute(
        text("SELECT alias, telegram_chat_id, created_at FROM participants WHERE alias = :alias"),
        {"alias": alias},
    )
    row = result.fetchone()
    return {
        "alias": row.alias,
        "telegram_chat_id": row.telegram_chat_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def delete_participant(session: AsyncSession, alias: str) -> bool:
    """Delete a participant. Returns True if deleted, False if not found."""
    result = await session.execute(
        text("DELETE FROM participants WHERE alias = :alias"),
        {"alias": alias},
    )
    await session.commit()
    return result.rowcount > 0


async def get_chat_id_by_alias(session: AsyncSession, alias: str) -> Optional[int]:
    """Look up a participant's Telegram chat ID by alias."""
    result = await session.execute(
        text("SELECT telegram_chat_id FROM participants WHERE alias = :alias"),
        {"alias": alias},
    )
    row = result.fetchone()
    return row.telegram_chat_id if row else None


# ─── Broadcasts ─────────────────────────────────────────────────────────────

async def list_broadcasts(session: AsyncSession) -> list[dict]:
    """Return all broadcast schedules with their targets."""
    result = await session.execute(text(
        """
        SELECT b.id, b.message, b.interval_minutes, b.start_time, b.end_time,
               b.is_active, b.last_sent_at, b.created_at,
               ARRAY_AGG(t.participant_alias) FILTER (WHERE t.participant_alias IS NOT NULL) AS targets
        FROM broadcasts b
        LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id
        GROUP BY b.id
        ORDER BY b.id
        """
    ))
    rows = result.fetchall()
    broadcasts = []
    for r in rows:
        broadcasts.append({
            "id": r.id,
            "message": r.message,
            "interval_minutes": r.interval_minutes,
            "start_time": r.start_time.isoformat() if r.start_time else None,
            "end_time": r.end_time.isoformat() if r.end_time else None,
            "is_active": r.is_active,
            "last_sent_at": r.last_sent_at.isoformat() if r.last_sent_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "targets": r.targets or [],
        })
    return broadcasts


async def get_broadcast(session: AsyncSession, broadcast_id: int) -> Optional[dict]:
    """Get a single broadcast by ID with targets."""
    result = await session.execute(text(
        """
        SELECT b.id, b.message, b.interval_minutes, b.start_time, b.end_time,
               b.is_active, b.last_sent_at, b.created_at,
               ARRAY_AGG(t.participant_alias) FILTER (WHERE t.participant_alias IS NOT NULL) AS targets
        FROM broadcasts b
        LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id
        WHERE b.id = :id
        GROUP BY b.id
        """
    ), {"id": broadcast_id})
    row = result.fetchone()
    if not row:
        return None
    return {
        "id": row.id,
        "message": row.message,
        "interval_minutes": row.interval_minutes,
        "start_time": row.start_time.isoformat() if row.start_time else None,
        "end_time": row.end_time.isoformat() if row.end_time else None,
        "is_active": row.is_active,
        "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "targets": row.targets or [],
    }


async def create_broadcast(
    session: AsyncSession,
    message: str,
    interval_minutes: int,
    start_time: str,
    end_time: str,
    targets: list[str],
) -> dict:
    """Create a new broadcast schedule with target aliases."""
    result = await session.execute(
        text(
            """
            INSERT INTO broadcasts (message, interval_minutes, start_time, end_time)
            VALUES (:message, :interval, :start_time, :end_time)
            RETURNING id, message, interval_minutes, start_time, end_time, is_active, created_at
            """
        ),
        {
            "message": message,
            "interval": interval_minutes,
            "start_time": start_time,
            "end_time": end_time,
        },
    )
    row = result.fetchone()
    broadcast_id = row.id

    # Insert targets
    for alias in targets:
        await session.execute(
            text(
                "INSERT INTO broadcast_targets (broadcast_id, participant_alias) VALUES (:bid, :alias)"
            ),
            {"bid": broadcast_id, "alias": alias},
        )

    await session.commit()

    return {
        "id": broadcast_id,
        "message": row.message,
        "interval_minutes": row.interval_minutes,
        "start_time": row.start_time.isoformat() if row.start_time else None,
        "end_time": row.end_time.isoformat() if row.end_time else None,
        "is_active": row.is_active,
        "targets": targets,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def update_broadcast(
    session: AsyncSession,
    broadcast_id: int,
    message: Optional[str] = None,
    interval_minutes: Optional[int] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    is_active: Optional[bool] = None,
    targets: Optional[list[str]] = None,
) -> Optional[dict]:
    """Update an existing broadcast. Returns updated broadcast or None."""
    # Build dynamic update
    fields = []
    params: dict = {"id": broadcast_id}

    if message is not None:
        fields.append("message = :message")
        params["message"] = message
    if interval_minutes is not None:
        fields.append("interval_minutes = :interval")
        params["interval"] = interval_minutes
    if start_time is not None:
        fields.append("start_time = :start_time")
        params["start_time"] = start_time
    if end_time is not None:
        fields.append("end_time = :end_time")
        params["end_time"] = end_time
    if is_active is not None:
        fields.append("is_active = :is_active")
        params["is_active"] = is_active

    if fields:
        await session.execute(
            text(f"UPDATE broadcasts SET {', '.join(fields)} WHERE id = :id"),
            params,
        )

    # Update targets if provided (replace all)
    if targets is not None:
        await session.execute(
            text("DELETE FROM broadcast_targets WHERE broadcast_id = :id"),
            {"id": broadcast_id},
        )
        for alias in targets:
            await session.execute(
                text(
                    "INSERT INTO broadcast_targets (broadcast_id, participant_alias) VALUES (:bid, :alias)"
                ),
                {"bid": broadcast_id, "alias": alias},
            )

    await session.commit()
    return await get_broadcast(session, broadcast_id)


async def delete_broadcast(session: AsyncSession, broadcast_id: int) -> bool:
    """Delete a broadcast and its targets. Returns True if deleted."""
    result = await session.execute(
        text("DELETE FROM broadcasts WHERE id = :id"),
        {"id": broadcast_id},
    )
    await session.commit()

    # Reset the ID sequence so new broadcasts start from 1 when table is empty
    await session.execute(text("ALTER SEQUENCE broadcasts_id_seq RESTART WITH 1"))
    await session.commit()

    return result.rowcount > 0


async def update_broadcast_last_sent(session: AsyncSession, broadcast_id: int) -> None:
    """Update the last_sent_at timestamp for a broadcast."""
    await session.execute(
        text("UPDATE broadcasts SET last_sent_at = NOW() WHERE id = :id"),
        {"id": broadcast_id},
    )
    await session.commit()


# ─── Broadcast targets helpers ──────────────────────────────────────────────

async def get_broadcast_targets(session: AsyncSession, broadcast_id: int) -> list[str]:
    """Get target aliases for a broadcast."""
    result = await session.execute(
        text("SELECT participant_alias FROM broadcast_targets WHERE broadcast_id = :id"),
        {"id": broadcast_id},
    )
    return [row.participant_alias for row in result.fetchall()]


async def get_participant_chat_ids(
    session: AsyncSession, aliases: Optional[list[str]] = None
) -> list[tuple[str, int]]:
    """
    Get (alias, telegram_chat_id) pairs.
    If aliases is None, return all participants.
    If aliases is empty list, return empty list.
    """
    if aliases is not None and len(aliases) == 0:
        return []

    if aliases is None:
        result = await session.execute(
            text("SELECT alias, telegram_chat_id FROM participants ORDER BY alias")
        )
    else:
        result = await session.execute(
            text(
                "SELECT alias, telegram_chat_id FROM participants WHERE alias = ANY(:aliases) ORDER BY alias"
            ),
            {"aliases": aliases},
        )
    return [(row.alias, row.telegram_chat_id) for row in result.fetchall()]


# ─── Delivery log ───────────────────────────────────────────────────────────

async def log_delivery(
    session: AsyncSession,
    broadcast_id: int,
    participant_alias: str,
    status: str,
) -> None:
    """Record a delivery attempt in the log."""
    await session.execute(
        text(
            """
            INSERT INTO delivery_log (broadcast_id, participant_alias, status)
            VALUES (:bid, :alias, :status)
            """
        ),
        {"bid": broadcast_id, "alias": participant_alias, "status": status},
    )
    await session.commit()


async def get_delivery_logs(
    session: AsyncSession, limit: int = 100, offset: int = 0
) -> list[dict]:
    """Get recent delivery log entries."""
    result = await session.execute(
        text(
            """
            SELECT dl.id, dl.broadcast_id, dl.participant_alias, dl.sent_at, dl.status,
                   b.message
            FROM delivery_log dl
            LEFT JOIN broadcasts b ON dl.broadcast_id = b.id
            ORDER BY dl.sent_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {"limit": limit, "offset": offset},
    )
    return [
        {
            "id": r.id,
            "broadcast_id": r.broadcast_id,
            "participant_alias": r.participant_alias,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "status": r.status,
            "message_preview": (r.message[:100] + "...") if r.message and len(r.message) > 100 else r.message,
        }
        for r in result.fetchall()
    ]


# ─── Water reminders (personal hydration) ────────────────────────────────────

async def get_water_reminder(session: AsyncSession, telegram_chat_id: int) -> Optional[dict]:
    """Get a user's water reminder settings."""
    result = await session.execute(
        text(
            "SELECT telegram_chat_id, interval_minutes, is_active, last_sent_at FROM water_reminders WHERE telegram_chat_id = :cid"
        ),
        {"cid": telegram_chat_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return {
        "telegram_chat_id": row.telegram_chat_id,
        "interval_minutes": row.interval_minutes,
        "is_active": row.is_active,
        "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
    }


async def upsert_water_reminder(
    session: AsyncSession,
    telegram_chat_id: int,
    interval_minutes: int = 60,
    is_active: bool = True,
) -> dict:
    """Create or update a user's water reminder settings."""
    await session.execute(
        text(
            """
            INSERT INTO water_reminders (telegram_chat_id, interval_minutes, is_active)
            VALUES (:cid, :interval, :active)
            ON CONFLICT (telegram_chat_id)
            DO UPDATE SET interval_minutes = :interval, is_active = :active
            """
        ),
        {"cid": telegram_chat_id, "interval": interval_minutes, "active": is_active},
    )
    await session.commit()
    return await get_water_reminder(session, telegram_chat_id)


async def toggle_water_reminder(
    session: AsyncSession, telegram_chat_id: int, is_active: bool
) -> Optional[dict]:
    """Toggle a user's water reminder on/off."""
    result = await session.execute(
        text(
            "UPDATE water_reminders SET is_active = :active WHERE telegram_chat_id = :cid RETURNING telegram_chat_id, interval_minutes, is_active, last_sent_at"
        ),
        {"active": is_active, "cid": telegram_chat_id},
    )
    await session.commit()
    row = result.fetchone()
    if not row:
        return None
    return {
        "telegram_chat_id": row.telegram_chat_id,
        "interval_minutes": row.interval_minutes,
        "is_active": row.is_active,
        "last_sent_at": row.last_sent_at.isoformat() if row.last_sent_at else None,
    }


async def get_active_water_reminders(session: AsyncSession) -> list[dict]:
    """Get all users with active water reminders for scheduled sending."""
    result = await session.execute(
        text(
            "SELECT telegram_chat_id, interval_minutes, last_sent_at FROM water_reminders WHERE is_active = TRUE"
        )
    )
    return [
        {
            "telegram_chat_id": row.telegram_chat_id,
            "interval_minutes": row.interval_minutes,
            "last_sent_at": row.last_sent_at,
        }
        for row in result.fetchall()
    ]


async def update_water_last_sent(
    session: AsyncSession, telegram_chat_id: int
) -> None:
    """Update last_sent_at for a water reminder."""
    await session.execute(
        text("UPDATE water_reminders SET last_sent_at = NOW() WHERE telegram_chat_id = :cid"),
        {"cid": telegram_chat_id},
    )
    await session.commit()


# ─── Time window helper ─────────────────────────────────────────────────────

def is_within_time_window(
    start_time: time, end_time: time, current_time: Optional[time] = None
) -> bool:
    """
    Check if current_time falls within [start_time, end_time].
    Correctly handles windows that cross midnight (e.g., 22:00–06:00).
    """
    if current_time is None:
        current_time = datetime.now().time()

    if start_time <= end_time:
        # Normal window: e.g., 09:00–19:00
        return start_time <= current_time <= end_time
    else:
        # Crosses midnight: e.g., 22:00–06:00
        return current_time >= start_time or current_time <= end_time
