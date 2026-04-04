"""PostgreSQL database helpers using asyncpg.

Provides a simple connection-pool wrapper and typed CRUD functions
for the ``users`` table.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import asyncpg

from .config import settings

logger = logging.getLogger(__name__)

# Module-level pool reference – initialised by ``init_pool``.
_pool: asyncpg.Pool | None = None


# ---------------------------------------------------------------------------
# Pool lifecycle
# ---------------------------------------------------------------------------
async def init_pool() -> None:
    """Create the global asyncpg connection pool."""
    global _pool
    logger.info("Connecting to PostgreSQL at %s:%s …", settings.db_host, settings.db_port)
    _pool = await asyncpg.create_pool(
        dsn=settings.dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )
    logger.info("Database pool initialised (%d connections).", _pool.get_size())


async def close_pool() -> None:
    """Gracefully close the global connection pool."""
    global _pool
    if _pool is not None:
        logger.info("Closing database pool …")
        await _pool.close()
        _pool = None
        logger.info("Database pool closed.")


@asynccontextmanager
async def acquire():
    """Yield a connection from the pool with automatic release."""
    if _pool is None:
        raise RuntimeError("Database pool has not been initialised.")
    async with _pool.acquire() as conn:
        yield conn


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------
async def ensure_user(
    user_id: int,
    username: str | None = None,
) -> dict[str, Any]:
    """Insert a new user or return the existing row (UPSERT)."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (user_id, username, interval_minutes, reminder_active)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO UPDATE
                SET username = COALESCE(EXCLUDED.username, users.username)
            RETURNING *;
            """,
            user_id,
            username,
            settings.default_interval,
            False,
        )
    return dict(row) if row else {}


async def get_user(user_id: int) -> dict[str, Any] | None:
    """Fetch a single user row or return ``None``."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1;", user_id
        )
    return dict(row) if row else None


async def update_interval(user_id: int, minutes: int) -> None:
    """Set a user's reminder interval."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE users SET interval_minutes = $1 WHERE user_id = $2;",
            minutes,
            user_id,
        )


async def set_reminder_active(user_id: int, active: bool) -> None:
    """Toggle reminder_active and update last_reminder_time when activating."""
    async with acquire() as conn:
        if active:
            await conn.execute(
                """
                UPDATE users
                SET reminder_active = $1, last_reminder_time = NOW()
                WHERE user_id = $2;
                """,
                active,
                user_id,
            )
        else:
            await conn.execute(
                """
                UPDATE users
                SET reminder_active = $1, last_reminder_time = NULL
                WHERE user_id = $2;
                """,
                active,
                user_id,
            )


async def update_last_reminder(user_id: int) -> None:
    """Record the current timestamp as the last reminder time."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE users SET last_reminder_time = NOW() WHERE user_id = $1;",
            user_id,
        )


async def get_active_users() -> list[dict[str, Any]]:
    """Return every user whose reminders are currently active."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM users WHERE reminder_active = TRUE;"
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Schema bootstrap (called once at startup)
# ---------------------------------------------------------------------------
async def ensure_schema() -> None:
    """Create the users table if it doesn't already exist.

    This is a safety net so the bot can start even without the init.sql
    script having run (e.g. when connecting to a pre-existing database).
    """
    async with acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id         BIGINT PRIMARY KEY,
                username        TEXT,
                interval_minutes INT NOT NULL DEFAULT 60,
                reminder_active BOOLEAN NOT NULL DEFAULT FALSE,
                last_reminder_time TIMESTAMP WITH TIME ZONE
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_active_reminders
                ON users (reminder_active)
                WHERE reminder_active = TRUE;
        """)
    logger.info("Schema verified / created.")
