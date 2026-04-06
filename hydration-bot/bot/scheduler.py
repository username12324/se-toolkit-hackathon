"""Reminder and broadcast scheduling via python-telegram-bot's JobQueue.

Water reminders (original):
    Each user gets a uniquely named job so we can cancel / reschedule
    individually without affecting other users.

Event broadcasts (new):
    A single repeating job checks every minute for active broadcasts
    that are due to be sent, respecting time-of-day windows and intervals.
"""

from __future__ import annotations

import logging
from datetime import timedelta, datetime, time as dtime

from telegram.ext import Application, CallbackContext

from . import database as db
from .config import settings

logger = logging.getLogger(__name__)

# The reminder message sent to users for personal water reminders.
REMINDER_TEXT = "💧 Time to drink water! Stay hydrated. 💧"


# ===================================================================
# Water reminder jobs (original)
# ===================================================================

def _job_name(user_id: int) -> str:
    """Deterministic job name for a given user."""
    return f"hydration_{user_id}"


async def remind_user(context: CallbackContext) -> None:
    """Callback executed by the JobQueue for each reminder tick.

    Sends the reminder message and updates the user's last_reminder_time.
    """
    user_id: int = context.job.user_id  # type: ignore[attr-defined]
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=REMINDER_TEXT,
        )
        await db.update_last_reminder(user_id)
        logger.info("Sent water reminder to user %d.", user_id)
    except Exception:  # pragma: no cover – network errors are logged
        logger.exception("Failed to send water reminder to user %d.", user_id)


def start_reminder(application: Application, user_id: int, interval_minutes: int) -> None:
    """Schedule (or reschedule) a periodic reminder job for *user_id*."""
    job_queue = application.job_queue
    if job_queue is None:
        logger.error("JobQueue is not available – cannot schedule reminder for %d.", user_id)
        return

    name = _job_name(user_id)

    # Cancel any existing job for this user first to prevent duplicates.
    _cancel_if_exists(application, name)

    job_queue.run_repeating(
        remind_user,
        interval=timedelta(minutes=interval_minutes),
        first=timedelta(minutes=interval_minutes),  # first reminder after full interval
        name=name,
        user_id=user_id,
    )
    logger.info(
        "Scheduled repeating reminder for user %d every %d min.",
        user_id,
        interval_minutes,
    )


def stop_reminder(application: Application, user_id: int) -> None:
    """Cancel the reminder job for *user_id*."""
    _cancel_if_exists(application, _job_name(user_id))
    logger.info("Cancelled reminder for user %d.", user_id)


def _cancel_if_exists(application: Application, name: str) -> None:
    """Remove a job from the JobQueue if it exists."""
    if application.job_queue is None:
        return
    current_jobs = application.job_queue.jobs()
    for job in current_jobs:
        if job.name == name:
            job.schedule_removal()
            logger.debug("Removed existing job '%s'.", name)
            break


async def restore_active_reminders(application: Application) -> int:
    """Re-schedule jobs for all users who had active reminders before restart.

    Returns the number of restored reminders (useful for logging).
    """
    active_users = await db.get_active_users()
    for user in active_users:
        uid: int = user["user_id"]
        interval: int = user["interval_minutes"]
        start_reminder(application, uid, interval)
    logger.info("Restored %d water reminder(s) from database.", len(active_users))
    return len(active_users)


# ===================================================================
# Event broadcast scheduler (new)
# ===================================================================

async def check_broadcasts(context: CallbackContext) -> None:
    """JobQueue callback that runs every minute to check for due broadcasts.

    For each active broadcast:
    1. Check if current time is within the allowed window [start_time, end_time].
    2. Check if enough time has passed since last send (interval_minutes).
    3. If both conditions met, send message to all target participants.
    4. Log each delivery attempt.
    """
    application: Application = context.application
    bot = application.bot
    now = datetime.now()
    current_time = now.time()

    broadcasts = await db.list_broadcasts()

    for bc in broadcasts:
        if not bc["is_active"]:
            continue

        # Parse time window (e.g. "08:00:00" → time object)
        start_t = dtime.fromisoformat(bc["start_time"])
        end_t = dtime.fromisoformat(bc["end_time"])

        # Check if we're within the allowed time window
        if not db.is_within_time_window(start_t, end_t, current_time):
            continue

        # Check if enough time has passed since last send
        last_sent = bc["last_sent_at"]
        if last_sent:
            # Handle both timezone-aware and naive datetimes
            last_sent_dt = datetime.fromisoformat(last_sent)
            if last_sent_dt.tzinfo is not None:
                last_sent_dt = last_sent_dt.replace(tzinfo=None)
            elapsed = now - last_sent_dt
            # Use a 2-second tolerance to account for job scheduling drift
            if elapsed < timedelta(minutes=bc["interval_minutes"]) - timedelta(seconds=2):
                continue
        # If never sent (last_sent is None), send immediately

        # Get subscribed chat IDs (only users who haven't unsubscribed)
        chat_ids = await db.get_subscribed_chat_ids(bc["id"])

        if not chat_ids:
            logger.warning("Broadcast %d has no subscribed targets.", bc["id"])
            continue

        # Update last_sent_at BEFORE sending so the timestamp reflects the
        # decision time, not the completion time (avoids a ~1s drift that
        # causes every-other-minute delivery).
        await db.update_broadcast_last_sent(bc["id"])

        # Send message to each subscribed user
        for chat_id in chat_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=bc["message"],
                    parse_mode="Markdown",
                )
                await db.log_delivery(bc["id"], f"chat_{chat_id}", "sent")
                logger.info("Broadcast %d sent to chat_id %d", bc["id"], chat_id)
            except Exception as exc:
                logger.error("Failed to send broadcast %d to chat_id %d: %s", bc["id"], chat_id, exc)
                await db.log_delivery(bc["id"], f"chat_{chat_id}", "failed")


def start_broadcast_checker(application: Application) -> None:
    """Schedule the broadcast checker to run every minute."""
    job_queue = application.job_queue
    if job_queue is None:
        logger.error("JobQueue is not available – broadcast checker cannot start.")
        return

    job_queue.run_repeating(
        check_broadcasts,
        interval=timedelta(minutes=1),
        first=timedelta(seconds=10),  # first check 10s after start
        name="broadcast_checker",
    )
    logger.info("Broadcast checker scheduled (every 1 minute).")


async def restore_broadcast_info(application: Application) -> int:
    """Log how many active broadcasts exist on startup.

    The actual re-scheduling is handled by the checker job which
    reads from DB each time — no state to restore beyond starting the job.
    """
    broadcasts = await db.list_broadcasts()
    active_count = sum(1 for b in broadcasts if b["is_active"])
    logger.info(
        "Found %d active broadcast(s) in database on startup.",
        active_count,
    )
    return active_count
