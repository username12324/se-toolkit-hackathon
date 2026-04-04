"""Reminder scheduling via python-telegram-bot's JobQueue.

Each user gets a uniquely named job so we can cancel / reschedule
individually without affecting other users.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from telegram.ext import Application, CallbackContext

from . import database as db
from .config import settings

logger = logging.getLogger(__name__)

# The reminder message sent to users.
REMINDER_TEXT = "💧 Time to drink water! Stay hydrated. 💧"


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
        logger.info("Sent reminder to user %d.", user_id)
    except Exception:  # pragma: no cover – network errors are logged
        logger.exception("Failed to send reminder to user %d.", user_id)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
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
        user_id: int = user["user_id"]
        interval: int = user["interval_minutes"]
        start_reminder(application, user_id, interval)
    logger.info("Restored %d active reminder(s) from database.", len(active_users))
    return len(active_users)
