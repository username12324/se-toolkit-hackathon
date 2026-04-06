"""
Broadcast scheduler using APScheduler.

Runs inside the bot process. Checks every minute for active broadcasts
that are due to be sent, respecting time windows and intervals.
"""

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from database_broadcast import (
    get_session_factory,
    list_broadcasts,
    get_participant_chat_ids,
    update_broadcast_last_sent,
    log_delivery,
    get_active_water_reminders,
    update_water_last_sent,
    is_within_time_window,
)

logger = logging.getLogger(__name__)


class BroadcastScheduler:
    """
    Manages scheduled broadcast messages and personal water reminders.

    The scheduler runs two periodic jobs:
    1. check_broadcasts – every minute, checks if any active broadcast is due
    2. check_water_reminders – every minute, checks if any personal water reminder is due
    """

    def __init__(self, bot):
        """
        Initialize the scheduler.

        Args:
            bot: aiogram Bot instance for sending messages
        """
        self.bot = bot
        self.scheduler = AsyncIOScheduler()
        self.session_factory = get_session_factory()

    def start(self):
        """Start the scheduler and load all active broadcasts from DB."""
        self.scheduler.add_job(
            self.check_broadcasts,
            trigger=IntervalTrigger(minutes=1),
            id="broadcast_checker",
            name="Check and send broadcast messages",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.check_water_reminders,
            trigger=IntervalTrigger(minutes=1),
            id="water_reminder_checker",
            name="Check and send personal water reminders",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("BroadcastScheduler started")

    def stop(self):
        """Shut down the scheduler gracefully."""
        self.scheduler.shutdown(wait=False)
        logger.info("BroadcastScheduler stopped")

    async def check_broadcasts(self):
        """
        Check all active broadcasts and send messages if due.

        For each active broadcast:
        1. Check if current time is within the allowed window
        2. Check if enough time has passed since last send (interval_minutes)
        3. If both conditions met, send message to all targets
        """
        now = datetime.now()
        current_time = now.time()

        async with self.session_factory() as session:
            broadcasts = await list_broadcasts(session)

            for bc in broadcasts:
                if not bc["is_active"]:
                    continue

                # Parse time window
                start_time = datetime.fromisoformat(bc["start_time"]).time()
                end_time = datetime.fromisoformat(bc["end_time"]).time()

                # Check if we're within the allowed time window
                if not is_within_time_window(start_time, end_time, current_time):
                    continue

                # Check if enough time has passed since last send
                last_sent = bc["last_sent_at"]
                if last_sent:
                    last_sent_dt = datetime.fromisoformat(last_sent)
                    elapsed = now - last_sent_dt
                    if elapsed < timedelta(minutes=bc["interval_minutes"]):
                        continue
                # If never sent (last_sent is None), send immediately

                # Get target chat IDs
                targets = bc["targets"]
                participants = await get_participant_chat_ids(session, targets)

                if not participants:
                    logger.warning(
                        "Broadcast %d has no valid targets", bc["id"]
                    )
                    continue

                # Send message to each target
                for alias, chat_id in participants:
                    try:
                        await self.bot.send_message(
                            chat_id=chat_id,
                            text=bc["message"],
                            parse_mode="Markdown",
                        )
                        await log_delivery(
                            session, bc["id"], alias, "sent"
                        )
                        logger.info(
                            "Broadcast %d sent to %s (chat_id: %d)",
                            bc["id"],
                            alias,
                            chat_id,
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to send broadcast %d to %s: %s",
                            bc["id"],
                            alias,
                            e,
                        )
                        await log_delivery(
                            session, bc["id"], alias, "failed"
                        )

                # Update last_sent_at for this broadcast
                await update_broadcast_last_sent(session, bc["id"])

    async def check_water_reminders(self):
        """
        Check all active personal water reminders and send if due.

        For each user with an active water reminder:
        1. Check if enough time has passed since last send
        2. If so, send a hydration reminder
        """
        now = datetime.now()

        async with self.session_factory() as session:
            reminders = await get_active_water_reminders(session)

            for reminder in reminders:
                chat_id = reminder["telegram_chat_id"]
                interval = reminder["interval_minutes"]
                last_sent = reminder["last_sent_at"]

                # Check interval
                if last_sent:
                    last_sent_dt = (
                        datetime.fromisoformat(last_sent)
                        if isinstance(last_sent, str)
                        else last_sent
                    )
                    elapsed = now - last_sent_dt
                    if elapsed < timedelta(minutes=interval):
                        continue

                # Send water reminder
                try:
                    await self.bot.send_message(
                        chat_id=chat_id,
                        text="💧 Time to drink some water! Stay hydrated!",
                    )
                    await update_water_last_sent(session, chat_id)
                    logger.info("Water reminder sent to chat_id: %d", chat_id)
                except Exception as e:
                    logger.error(
                        "Failed to send water reminder to chat_id %d: %s",
                        chat_id,
                        e,
                    )
