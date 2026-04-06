"""
Personal hydration reminder handlers for the Telegram bot.

These handlers allow individual participants to manage their own
water-drinking reminders, separate from event broadcasts.

Commands:
    /drinkwater  – Start personal hydration reminders
    /settime     – Set reminder frequency (in minutes)
    /stopwater   – Stop personal hydration reminders
    /waterstatus – Check current reminder status
"""

from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database_broadcast import (
    get_session_factory,
    get_water_reminder,
    upsert_water_reminder,
    toggle_water_reminder,
)

DEFAULT_INTERVAL = 60  # minutes

session_factory = get_session_factory()


async def handle_drinkwater(message: types.Message) -> None:
    """
    /drinkwater – Start or restart personal hydration reminders.
    Uses the user's previously set interval, or defaults to 60 minutes.
    """
    chat_id = message.from_user.id

    async with session_factory() as session:
        existing = await get_water_reminder(session, chat_id)
        interval = existing["interval_minutes"] if existing else DEFAULT_INTERVAL

        result = await upsert_water_reminder(
            session, chat_id, interval_minutes=interval, is_active=True
        )

    if result:
        await message.answer(
            f"💧 *Hydration reminders activated!*\n\n"
            f"You'll receive a reminder every *{result['interval_minutes']} minutes*.\n"
            f"Use /settime to change the frequency, or /stopwater to pause.",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "❌ Failed to activate hydration reminders. Please try again."
        )


async def handle_settime(message: types.Message) -> None:
    """
    /settime <minutes> – Set personal reminder frequency.
    Example: /settime 30  (every 30 minutes)
    """
    chat_id = message.from_user.id
    parts = message.text.split()

    if len(parts) < 2:
        await message.answer(
            "⏰ *Set reminder frequency*\n\n"
            "Usage: `/settime <minutes>`\n\n"
            "Examples:\n"
            "• `/settime 15` – every 15 minutes\n"
            "• `/settime 60` – every hour\n"
            "• `/settime 120` – every 2 hours",
            parse_mode="Markdown",
        )
        return

    try:
        minutes = int(parts[1])
        if minutes < 1 or minutes > 1440:
            raise ValueError
    except ValueError:
        await message.answer(
            "❌ Please provide a valid number of minutes (1–1440)."
        )
        return

    async with session_factory() as session:
        existing = await get_water_reminder(session, chat_id)
        was_active = existing["is_active"] if existing else False

        result = await upsert_water_reminder(
            session, chat_id, interval_minutes=minutes, is_active=was_active or True
        )

    if result:
        status = "active" if result["is_active"] else "paused"
        await message.answer(
            f"⏰ *Reminder frequency updated!*\n\n"
            f"You'll receive reminders every *{result['interval_minutes']} minutes*.\n"
            f"Current status: _{status}_",
            parse_mode="Markdown",
        )
    else:
        await message.answer("❌ Failed to update reminder settings.")


async def handle_stopwater(message: types.Message) -> None:
    """
    /stopwater – Pause personal hydration reminders.
    """
    chat_id = message.from_user.id

    async with session_factory() as session:
        result = await toggle_water_reminder(session, chat_id, is_active=False)

    if result:
        await message.answer(
            "⏸️ *Hydration reminders paused.*\n\n"
            "Use /drinkwater to resume.",
            parse_mode="Markdown",
        )
    else:
        await message.answer(
            "You don't have any active hydration reminders."
        )


async def handle_waterstatus(message: types.Message) -> None:
    """
    /waterstatus – Show current personal reminder settings.
    """
    chat_id = message.from_user.id

    async with session_factory() as session:
        reminder = await get_water_reminder(session, chat_id)

    if not reminder:
        await message.answer(
            "ℹ️ You don't have any hydration reminders set up.\n"
            "Use /drinkwater to start receiving reminders."
        )
        return

    status = "✅ Active" if reminder["is_active"] else "⏸️ Paused"
    last_sent = reminder["last_sent_at"] or "Never"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="▶️ Start" if not reminder["is_active"] else "⏸️ Pause",
                callback_data=f"toggle_water_{'true' if not reminder['is_active'] else 'false'}",
            )
        ]
    ])

    await message.answer(
        f"💧 *Your hydration reminder settings*\n\n"
        f"Status: {status}\n"
        f"Frequency: every *{reminder['interval_minutes']} minutes*\n"
        f"Last reminder: _{last_sent}_",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


def register_water_handlers(dp) -> None:
    """
    Register all water reminder command handlers with the dispatcher.

    Args:
        dp: aiogram Dispatcher instance
    """
    dp.message.register(handle_drinkwater, lambda m: m.text == "/drinkwater")
    dp.message.register(handle_settime, lambda m: m.text.startswith("/settime"))
    dp.message.register(handle_stopwater, lambda m: m.text == "/stopwater")
    dp.message.register(handle_waterstatus, lambda m: m.text == "/waterstatus")
