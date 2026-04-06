"""PostgreSQL database helpers using asyncpg.

Provides a simple connection-pool wrapper and typed CRUD functions
for the ``users`` table (water reminders) and broadcast tables
(participants, broadcasts, targets, delivery_log).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, time
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


# ===================================================================
# Water reminder CRUD (original functionality)
# ===================================================================

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


# ===================================================================
# Broadcast system CRUD
# ===================================================================

# --- Participants ---

async def list_participants() -> list[dict[str, Any]]:
    """Return all participant aliases with their Telegram chat IDs."""
    async with acquire() as conn:
        rows = await conn.fetch(
            "SELECT alias, telegram_chat_id, created_at FROM participants ORDER BY alias"
        )
    return [
        {
            "alias": r["alias"],
            "telegram_chat_id": r["telegram_chat_id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


async def add_participant(alias: str, telegram_chat_id: int) -> dict[str, Any]:
    """Add a new participant. Returns the created record."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO participants (alias, telegram_chat_id)
            VALUES ($1, $2)
            ON CONFLICT (alias) DO NOTHING
            RETURNING alias, telegram_chat_id, created_at;
            """,
            alias,
            telegram_chat_id,
        )
    if row is None:
        raise ValueError(f"Participant '{alias}' already exists.")
    return {
        "alias": row["alias"],
        "telegram_chat_id": row["telegram_chat_id"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


async def delete_participant(alias: str) -> bool:
    """Delete a participant. Returns True if a row was removed."""
    async with acquire() as conn:
        result = await conn.execute(
            "DELETE FROM participants WHERE alias = $1;", alias
        )
    # result is like 'DELETE 1'
    return result.split()[-1] != "0"


async def get_chat_id_by_alias(alias: str) -> int | None:
    """Look up a participant's Telegram chat ID by alias."""
    async with acquire() as conn:
        row = await conn.fetchval(
            "SELECT telegram_chat_id FROM participants WHERE alias = $1;", alias
        )
    return row


async def get_participant_chat_ids(
    aliases: list[str] | None = None,
) -> list[tuple[str, int]]:
    """
    Get (alias, chat_id) pairs.
    If *aliases* is None, return all participants.
    If empty list, return empty list.
    Deduplicates by telegram_chat_id so the same user isn't messaged twice.
    """
    async with acquire() as conn:
        if aliases is None:
            rows = await conn.fetch(
                "SELECT DISTINCT ON (telegram_chat_id) alias, telegram_chat_id "
                "FROM participants ORDER BY telegram_chat_id, alias"
            )
        elif len(aliases) == 0:
            return []
        else:
            rows = await conn.fetch(
                "SELECT DISTINCT ON (telegram_chat_id) alias, telegram_chat_id "
                "FROM participants WHERE alias = ANY($1) ORDER BY telegram_chat_id, alias",
                aliases,
            )
    return [(r["alias"], r["telegram_chat_id"]) for r in rows]


# --- Broadcasts ---

async def list_broadcasts() -> list[dict[str, Any]]:
    """Return all broadcast schedules with their target aliases."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT b.id, b.message, b.interval_minutes, b.start_time, b.end_time,
                   b.is_active, b.last_sent_at, b.created_at,
                   ARRAY_AGG(t.participant_alias) FILTER (WHERE t.participant_alias IS NOT NULL) AS targets
            FROM broadcasts b
            LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id
            GROUP BY b.id
            ORDER BY b.id
            """
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


async def get_broadcast(broadcast_id: int) -> dict[str, Any] | None:
    """Get a single broadcast by ID with its targets."""
    async with acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT b.id, b.message, b.interval_minutes, b.start_time, b.end_time,
                   b.is_active, b.last_sent_at, b.created_at,
                   ARRAY_AGG(t.participant_alias) FILTER (WHERE t.participant_alias IS NOT NULL) AS targets
            FROM broadcasts b
            LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id
            WHERE b.id = $1
            GROUP BY b.id
            """,
            broadcast_id,
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


async def create_broadcast(
    message: str,
    interval_minutes: int,
    start_time: str,
    end_time: str,
    targets: list[str],
) -> dict[str, Any]:
    """Create a new broadcast schedule with target aliases."""
    async with acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO broadcasts (message, interval_minutes, start_time, end_time)
                VALUES ($1, $2, $3::time, $4::time)
                RETURNING id, message, interval_minutes, start_time, end_time, is_active, created_at;
                """,
                message,
                interval_minutes,
                start_time,
                end_time,
            )
            broadcast_id = row["id"]

            # Insert targets
            for alias in targets:
                await conn.execute(
                    "INSERT INTO broadcast_targets (broadcast_id, participant_alias) VALUES ($1, $2);",
                    broadcast_id,
                    alias,
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


async def update_broadcast(
    broadcast_id: int,
    *,
    message: str | None = None,
    interval_minutes: int | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    is_active: bool | None = None,
    targets: list[str] | None = None,
) -> dict[str, Any] | None:
    """Update an existing broadcast. Returns the updated record or None."""
    async with acquire() as conn:
        # Fetch current data first
        current = await conn.fetchrow(
            "SELECT * FROM broadcasts WHERE id = $1;", broadcast_id
        )
        if current is None:
            return None

        # Build update fields
        updates: dict[str, Any] = {}
        if message is not None:
            updates["message"] = message
        if interval_minutes is not None:
            updates["interval_minutes"] = interval_minutes
        if start_time is not None:
            updates["start_time"] = start_time
        if end_time is not None:
            updates["end_time"] = end_time
        if is_active is not None:
            updates["is_active"] = is_active

        if updates:
            set_clauses = [f"{k} = ${i+1}" for i, k in enumerate(updates.keys())]
            values = list(updates.values()) + [broadcast_id]
            await conn.execute(
                f"UPDATE broadcasts SET {', '.join(set_clauses)} WHERE id = ${len(values)};",
                *values,
            )

        # Replace targets if provided
        if targets is not None:
            async with conn.transaction():
                await conn.execute(
                    "DELETE FROM broadcast_targets WHERE broadcast_id = $1;",
                    broadcast_id,
                )
                for alias in targets:
                    await conn.execute(
                        "INSERT INTO broadcast_targets (broadcast_id, participant_alias) VALUES ($1, $2);",
                        broadcast_id,
                        alias,
                    )

    return await get_broadcast(broadcast_id)


async def delete_broadcast(broadcast_id: int) -> bool:
    """Delete a broadcast and its targets (CASCADE). Returns True if deleted."""
    async with acquire() as conn:
        result = await conn.execute(
            "DELETE FROM broadcasts WHERE id = $1;", broadcast_id
        )
        # Reset the ID sequence so new broadcasts start from 1 when table is empty
        await conn.execute("ALTER SEQUENCE broadcasts_id_seq RESTART WITH 1;")
    return result.split()[-1] != "0"


async def update_broadcast_last_sent(broadcast_id: int) -> None:
    """Set last_sent_at to NOW() for a broadcast."""
    async with acquire() as conn:
        await conn.execute(
            "UPDATE broadcasts SET last_sent_at = NOW() WHERE id = $1;",
            broadcast_id,
        )


# --- Delivery log ---

async def log_delivery(
    broadcast_id: int,
    participant_alias: str,
    status: str,
) -> None:
    """Record a delivery attempt."""
    async with acquire() as conn:
        await conn.execute(
            """
            INSERT INTO delivery_log (broadcast_id, participant_alias, status)
            VALUES ($1, $2, $3);
            """,
            broadcast_id,
            participant_alias,
            status,
        )


async def get_delivery_logs(
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Get recent delivery log entries."""
    async with acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT dl.id, dl.broadcast_id, dl.participant_alias, dl.sent_at, dl.status,
                   b.message
            FROM delivery_log dl
            LEFT JOIN broadcasts b ON dl.broadcast_id = b.id
            ORDER BY dl.sent_at DESC
            LIMIT $1 OFFSET $2;
            """,
            limit,
            offset,
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


# ===================================================================
# Time-window helper
# ===================================================================

def is_within_time_window(
    start_time: time,
    end_time: time,
    current_time: time | None = None,
) -> bool:
    """Check if *current_time* falls within [start_time, end_time].

    Correctly handles windows that cross midnight (e.g. 22:00–06:00).
    """
    if current_time is None:
        current_time = datetime.now().time()

    if start_time <= end_time:
        # Normal window: 09:00–19:00
        return start_time <= current_time <= end_time
    else:
        # Crosses midnight: 22:00–06:00
        return current_time >= start_time or current_time <= end_time


# ---------------------------------------------------------------------------
# Schema bootstrap (called once at startup)
# ---------------------------------------------------------------------------
async def ensure_schema() -> None:
    """Create all tables if they don't already exist.

    This is a safety net so the bot can start even without the init.sql
    script having run (e.g. when connecting to a pre-existing database).
    """
    async with acquire() as conn:
        # --- Migration: add owner_id columns if missing (for existing tables) ---
        await conn.execute("ALTER TABLE participants ADD COLUMN IF NOT EXISTS owner_id INT;")
        await conn.execute("ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS owner_id INT;")
        await conn.execute("ALTER TABLE broadcast_targets ADD COLUMN IF NOT EXISTS owner_id INT;")
        await conn.execute("ALTER TABLE delivery_log ADD COLUMN IF NOT EXISTS owner_id INT;")

        # --- Migration: change participants PK from (alias) to (id, alias+owner_id unique) ---
        await conn.execute("""
            DO $$ 
            DECLARE
                has_serial_id BOOLEAN;
            BEGIN
                -- Check if participants table still has alias as PK (old schema)
                SELECT EXISTS(
                    SELECT 1 FROM information_schema.table_constraints
                    WHERE table_name = 'participants' AND constraint_type = 'PRIMARY KEY'
                ) INTO has_serial_id;
                
                IF has_serial_id THEN
                    -- Check if we need to add the serial id column
                    IF NOT EXISTS(
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'participants' AND column_name = 'id'
                    ) THEN
                        -- Add serial id column
                        ALTER TABLE participants ADD COLUMN id SERIAL;
                        
                        -- Drop old FK constraints that reference alias as PK
                        IF EXISTS(SELECT 1 FROM pg_constraint WHERE conname = 'broadcast_targets_participant_alias_fkey') THEN
                            ALTER TABLE broadcast_targets DROP CONSTRAINT broadcast_targets_participant_alias_fkey;
                        END IF;
                        
                        -- Drop old unique constraint on telegram_chat_id (we may want to keep it optional)
                        -- Drop the old PK constraint (on alias)
                        ALTER TABLE participants DROP CONSTRAINT participants_pkey;
                        
                        -- Set the new PK on id
                        ALTER TABLE participants ADD PRIMARY KEY (id);
                        
                        -- Add unique constraint on (alias, owner_id)
                        ALTER TABLE participants ADD CONSTRAINT uq_participants_alias_owner UNIQUE (alias, owner_id);
                        
                        -- Re-add FK from broadcast_targets to participants.alias (now just a unique key, not PK)
                        ALTER TABLE broadcast_targets ADD CONSTRAINT fk_bt_participant
                            FOREIGN KEY (participant_alias) REFERENCES participants(alias);
                    END IF;
                END IF;
            END $$;
        """)
        # Add FK constraints if missing
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_p_owner'
                ) THEN
                    ALTER TABLE participants ADD CONSTRAINT fk_p_owner
                        FOREIGN KEY (owner_id) REFERENCES app_users(id);
                END IF;
            END $$;
        """)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_b_owner'
                ) THEN
                    ALTER TABLE broadcasts ADD CONSTRAINT fk_b_owner
                        FOREIGN KEY (owner_id) REFERENCES app_users(id);
                END IF;
            END $$;
        """)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_bt_owner'
                ) THEN
                    ALTER TABLE broadcast_targets ADD CONSTRAINT fk_bt_owner
                        FOREIGN KEY (owner_id) REFERENCES app_users(id);
                END IF;
            END $$;
        """)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'fk_dl_owner'
                ) THEN
                    ALTER TABLE delivery_log ADD CONSTRAINT fk_dl_owner
                        FOREIGN KEY (owner_id) REFERENCES app_users(id);
                END IF;
            END $$;
        """)

        # --- users (water reminders) ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id          BIGINT PRIMARY KEY,
                username         TEXT,
                interval_minutes INT NOT NULL DEFAULT 60,
                reminder_active  BOOLEAN NOT NULL DEFAULT FALSE,
                last_reminder_time TIMESTAMP WITH TIME ZONE
            );
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_active_reminders
                ON users (reminder_active)
                WHERE reminder_active = TRUE;
        """)

        # --- participants ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id SERIAL PRIMARY KEY,
                alias VARCHAR(100) NOT NULL,
                telegram_chat_id BIGINT NOT NULL,
                owner_id INT REFERENCES app_users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (alias, owner_id)
            );
        """)

        # --- broadcasts ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcasts (
                id SERIAL PRIMARY KEY,
                message TEXT NOT NULL,
                interval_minutes INT NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                last_sent_at TIMESTAMP WITH TIME ZONE DEFAULT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                owner_id INT REFERENCES app_users(id)
            );
        """)

        # --- broadcast_targets ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broadcast_targets (
                broadcast_id INT REFERENCES broadcasts(id) ON DELETE CASCADE,
                participant_alias VARCHAR(100) REFERENCES participants(alias) ON DELETE CASCADE,
                owner_id INT REFERENCES app_users(id),
                PRIMARY KEY (broadcast_id, participant_alias)
            );
        """)

        # --- delivery_log ---
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS delivery_log (
                id SERIAL PRIMARY KEY,
                broadcast_id INT REFERENCES broadcasts(id),
                participant_alias VARCHAR(100),
                owner_id INT REFERENCES app_users(id),
                sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                status VARCHAR(20) CHECK (status IN ('sent', 'failed'))
            );
        """)

        # --- Indexes ---
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broadcasts_is_active ON broadcasts(is_active);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broadcasts_owner ON broadcasts(owner_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broadcast_targets_broadcast ON broadcast_targets(broadcast_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broadcast_targets_owner ON broadcast_targets(owner_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_delivery_log_broadcast ON delivery_log(broadcast_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_delivery_log_sent_at ON delivery_log(sent_at);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_delivery_log_owner ON delivery_log(owner_id);
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_participants_owner ON participants(owner_id);
        """)

        # --- View ---
        await conn.execute("""
            CREATE OR REPLACE VIEW v_broadcast_schedule AS
            SELECT
                b.id, b.message, b.interval_minutes, b.start_time, b.end_time,
                b.is_active, b.last_sent_at, b.created_at,
                ARRAY_AGG(t.participant_alias) FILTER (WHERE t.participant_alias IS NOT NULL) AS targets
            FROM broadcasts b
            LEFT JOIN broadcast_targets t ON b.id = t.broadcast_id
            GROUP BY b.id;
        """)

    logger.info("Schema verified / created (users + broadcast tables).")
