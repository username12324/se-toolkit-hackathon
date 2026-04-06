"""Telegram command and callback handlers for the Hydration + Broadcast Bot.

Water reminder commands (original):
    /start   – welcome + main menu
    /settime – set reminder interval
    /status  – show current settings

Event broadcast commands (new, participant-facing):
    /events  – show status of broadcasts the user is subscribed to

All handler coroutines are registered by ``register_handlers(application)``.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import database as db
from .config import settings
from .scheduler import start_reminder, stop_reminder

logger = logging.getLogger(__name__)


async def _safe_edit(text: str, query, parse_mode: str = "HTML", reply_markup=None):
    """Edit message, silently ignoring 'not modified' errors."""
    try:
        return await query.edit_message_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
    except BadRequest as exc:
        if "not modified" in str(exc):
            logger.debug("Message already up-to-date; skipping edit.")
            return None
        raise


# ---------------------------------------------------------------------------
# Inline keyboard layouts
# ---------------------------------------------------------------------------
def _main_menu() -> InlineKeyboardMarkup:
    """Main menu with Start / Stop buttons."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("▶️ Start reminders", callback_data="start_reminders")],
            [InlineKeyboardButton("⏹️ Stop reminders", callback_data="stop_reminders")],
        ]
    )


def _time_buttons() -> InlineKeyboardMarkup:
    """Quick-select interval buttons (15 min, 30 min, 1 hr, 2 hrs)."""
    labels = {15: "15 min", 30: "30 min", 60: "1 hr", 120: "2 hrs"}
    row = [
        InlineKeyboardButton(label, callback_data=f"settime_{minutes}")
        for minutes, label in labels.items()
    ]
    return InlineKeyboardMarkup([row])


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message and show the main menu."""
    user = update.effective_user
    assert user is not None

    # Upsert the user into the database.
    await db.ensure_user(user.id, user.username)

    welcome = (
        f"👋 Hi {user.mention_html()}! I'm your Hydration & Event Reminder Bot.\n\n"
        "I can help you with two things:\n\n"
        "💧 <b>Personal Hydration Reminders</b> — get reminded to drink water.\n"
        "    Use the buttons below or try /settime and /status.\n\n"
        "📢 <b>Event Broadcasts</b> — receive scheduled messages from event organisers.\n"
        "    You'll be added by an organiser using your alias.\n"
        "    Use /events to see your broadcast subscriptions.\n\n"
        "Use the buttons below to manage your personal water reminders!"
    )

    await update.message.reply_text(
        welcome,
        parse_mode="HTML",
        reply_markup=_main_menu(),
    )
    logger.info("User %d (%s) tapped /start.", user.id, user.username)


# ---------------------------------------------------------------------------
# /settime
# ---------------------------------------------------------------------------
async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``/settime <minutes>`` – validate and persist the interval."""
    user = update.effective_user
    assert user is not None

    # Ensure user exists.
    await db.ensure_user(user.id, user.username)

    raw = " ".join(context.args) if context.args else ""
    if not raw:
        await update.message.reply_text(
            "⚠️ Please specify the interval in minutes.\n"
            "Example: <code>/settime 45</code>",
            parse_mode="HTML",
        )
        return

    try:
        minutes = int(raw)
    except ValueError:
        await update.message.reply_text(
            f'❌ "{raw}" is not a valid number. Please provide a positive integer.'
        )
        return

    valid, error = settings.validate_interval(minutes)
    if not valid:
        await update.message.reply_text(f"❌ {error}")
        return

    await db.update_interval(user.id, minutes)

    was_active = (await db.get_user(user.id))["reminder_active"]  # type: ignore[index]

    # If reminders are running, reschedule with the new interval.
    if was_active:
        start_reminder(context.application, user.id, minutes)  # type: ignore[arg-type]

    await update.message.reply_text(
        f"✅ Reminder interval set to <b>{minutes} minute(s)</b>.",
        parse_mode="HTML",
        reply_markup=_time_buttons(),
    )
    logger.info("User %d set interval to %d min.", user.id, minutes)


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user's current reminder settings."""
    user = update.effective_user
    assert user is not None

    row = await db.get_user(user.id)
    if row is None:
        await update.message.reply_text("I don't have your data yet. Please send /start first.")
        return

    active = "✅ Active" if row["reminder_active"] else "⏸️ Inactive"
    last = row["last_reminder_time"]
    last_str = last.strftime("%Y-%m-%d %H:%M UTC") if last else "Never"

    text = (
        f"📊 <b>Your Hydration Settings</b>\n\n"
        f"Interval: <b>{row['interval_minutes']}</b> minute(s)\n"
        f"Status: {active}\n"
        f"Last reminder: {last_str}"
    )
    await update.message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# /events  (new — participant-facing broadcast info)
# ---------------------------------------------------------------------------
async def events_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the user which broadcasts they are subscribed to."""
    user = update.effective_user
    assert user is not None

    chat_id = user.id

    # Find aliases that match this chat_id
    all_participants = await db.list_participants()
    user_aliases = [p["alias"] for p in all_participants if p["telegram_chat_id"] == chat_id]

    if not user_aliases:
        await update.message.reply_text(
            "📢 You are not currently subscribed to any event broadcasts.\n\n"
            "An event organiser needs to register you with an alias first.\n"
            "Meanwhile, you can still use /start for personal hydration reminders!"
        )
        return

    # Find active broadcasts that target this user
    broadcasts = await db.list_broadcasts()
    subs = []
    for bc in broadcasts:
        if any(a in bc["targets"] for a in user_aliases):
            status_word = "✅ Active" if bc["is_active"] else "⏸️ Paused"
            subs.append(
                f"• <b>Broadcast #{bc['id']}</b> — {status_word}\n"
                f"  Every {bc['interval_minutes']} min, {bc['start_time']}–{bc['end_time']}"
            )

    if not subs:
        await update.message.reply_text(
            f"📢 Your alias(es): <b>{', '.join(user_aliases)}</b>\n\n"
            "No active broadcasts target you right now.",
            parse_mode="HTML",
        )
        return

    text = "📢 <b>Your Event Broadcasts</b>\n\n" + "\n\n".join(subs)
    await update.message.reply_text(text, parse_mode="HTML")


# ---------------------------------------------------------------------------
# Inline button callback
# ---------------------------------------------------------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route inline keyboard callbacks to the correct action."""
    query = update.callback_query
    assert query is not None
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "start_reminders":
        await _handle_start_callback(query, user_id, context)
    elif data == "stop_reminders":
        await _handle_stop_callback(query, user_id, context)
    elif data.startswith("settime_"):
        await _handle_settime_callback(query, user_id, data.split("_")[1], context)
    else:
        logger.warning("Unknown callback data: %s", data)
        await query.edit_message_text("⚠️ Unknown action.")


async def _handle_start_callback(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed the 'Start reminders' inline button."""
    user = await db.get_user(user_id)
    if user is None:
        await db.ensure_user(user_id, query.from_user.username)
        user = await db.get_user(user_id)

    interval = user["interval_minutes"]
    await db.set_reminder_active(user_id, True)
    start_reminder(context.application, user_id, interval)

    await _safe_edit(
        f"✅ Reminders <b>started</b>! You'll receive a message every <b>{interval}</b> minute(s).\n\n"
        f"Press ⏹️ <b>Stop reminders</b> whenever you want to pause them.",
        query,
        reply_markup=_main_menu(),
    )
    logger.info("User %d activated reminders (interval=%d).", user_id, interval)


async def _handle_stop_callback(query, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User pressed the 'Stop reminders' inline button."""
    await db.set_reminder_active(user_id, False)
    stop_reminder(context.application, user_id)

    await _safe_edit(
        "⏹️ Reminders <b>stopped</b>. Press ▶️ <b>Start reminders</b> to resume.",
        query,
        reply_markup=_main_menu(),
    )
    logger.info("User %d deactivated reminders.", user_id)


async def _handle_settime_callback(
    query, user_id: int, raw_minutes: str, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """User pressed a quick-select time button (e.g. settime_30)."""
    try:
        minutes = int(raw_minutes)
    except ValueError:
        await query.edit_message_text("❌ Invalid time selection.")
        return

    valid, error = settings.validate_interval(minutes)
    if not valid:
        await query.edit_message_text(f"❌ {error}")
        return

    await db.ensure_user(user_id, query.from_user.username)
    await db.update_interval(user_id, minutes)

    # If reminders are active, reschedule with the new interval.
    user = await db.get_user(user_id)
    if user["reminder_active"]:
        start_reminder(context.application, user_id, minutes)

    label = {15: "15 min", 30: "30 min", 60: "1 hr", 120: "2 hrs"}.get(minutes, f"{minutes} min")
    status_word = "active" if user["reminder_active"] else "inactive"
    await _safe_edit(
        f"✅ Interval set to <b>{label}</b>. "
        f"Reminders are <b>{status_word}</b> – "
        f"use the buttons below to manage them.",
        query,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("▶️ Start", callback_data="start_reminders"),
                    InlineKeyboardButton("⏹️ Stop", callback_data="stop_reminders"),
                ]
            ]
        ),
    )
    logger.info("User %d selected quick interval: %d min.", user_id, minutes)


# ---------------------------------------------------------------------------
# Catch-all for unknown text messages – gently steer back to commands.
# ---------------------------------------------------------------------------
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply when a user sends a plain-text message that isn't a known command."""
    if update.message and update.message.text:
        await update.message.reply_text(
            "I only understand commands like <code>/start</code>, <code>/settime &lt;minutes&gt;</code>, "
            "<code>/status</code>, and <code>/events</code>. Try /start to see the menu!",
            parse_mode="HTML",
        )


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------
def register_handlers(application: Application) -> None:
    """Attach all handlers to the given ``Application``."""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("settime", set_time))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("events", events_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))
    logger.info("All handlers registered.")
