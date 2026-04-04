"""Hydration Reminder Bot – main entry point.

Initialises the ``python-telegram-bot`` Application, connects to
PostgreSQL, restores active reminders from the database, and starts
polling for Telegram updates.

Graceful shutdown is handled internally by ``run_polling()`` which
catches SIGTERM / SIGINT, cancels all jobs and closes the application
cleanly.
"""

from __future__ import annotations

import logging
import sys

from telegram.ext import ApplicationBuilder

from . import database as db
from .config import settings
from .handlers import register_handlers
from .scheduler import restore_active_reminders

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Logging configuration (stdout, Docker-friendly)
# ---------------------------------------------------------------------------
def _setup_logging() -> None:
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )


# ---------------------------------------------------------------------------
# Lifecycle hooks – all run inside the SAME event loop that run_polling()
# creates, so asyncpg connections are never orphaned across loops.
# ---------------------------------------------------------------------------
async def post_init(application) -> None:
    """Initialise the DB, verify schema, and restore active reminders."""
    await db.init_pool()
    await db.ensure_schema()
    restored = await restore_active_reminders(application)
    logger.info("Restored %d reminder(s).", restored)


async def post_shutdown(application) -> None:
    """Close the DB pool before the application tears down."""
    await db.close_pool()


# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------
def main() -> None:
    """Entry point – builds the app and runs polling (blocking)."""
    _setup_logging()

    if not settings.bot_token:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Please create a .env file from .env.example."
        )
        sys.exit(1)

    # Build the Telegram Application.
    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .connect_timeout(10)
        .read_timeout(10)
        .write_timeout(10)
        .get_updates_connect_timeout(10)
        .get_updates_read_timeout(10)
        .get_updates_write_timeout(10)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register command / callback handlers.
    register_handlers(application)

    # Block here – run_polling() handles init, start, signal handling,
    # and cleanup automatically.
    logger.info("Starting bot polling …")
    try:
        application.run_polling(drop_pending_updates=True)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")


if __name__ == "__main__":
    main()
