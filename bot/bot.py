#!/usr/bin/env python3
"""
Telegram bot entry point.

Supports three modes:
- Test mode: `uv run bot.py --test "message"` prints response to stdout
- Telegram mode: `uv run bot.py` connects to Telegram, handles messages, runs scheduler
- Broadcast-only mode: `uv run bot.py --broadcast-only` runs scheduler without LMS features
"""

import argparse
import asyncio
import logging
import sys

import aiogram
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from config import load_config
from handlers import get_handler, register_water_handlers
from handlers.keyboard import get_help_text
from services.llm_client import route
from scheduler_broadcast import BroadcastScheduler

logger = logging.getLogger(__name__)


def run_test_mode(message: str) -> None:
    """
    Run a message through the bot and print result to stdout.

    Supports both slash commands and natural language queries.
    - Slash commands (e.g., /start, /help) are handled by command handlers
    - Natural language queries are routed through the LLM
    """
    message = message.strip()

    # Check if it's a slash command
    if message.startswith("/"):
        parts = message.split(maxsplit=1)
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        handler = get_handler(cmd)
        if handler is None:
            print(f"Unknown command: {cmd}. Use /help to see available commands.")
            sys.exit(0)

        # Call handler - some take arguments, some don't
        if cmd == "/scores":
            response = handler(arg)
        else:
            response = handler()

        print(response)
        sys.exit(0)
    else:
        # Natural language query - route through LLM
        response = route(message)
        print(response)
        sys.exit(0)


async def cmd_start(message: types.Message) -> None:
    """Handle /start – welcome message with options."""
    welcome = (
        "👋 *Welcome to the Event Broadcast & Hydration Reminder Bot!*\n\n"
        "I can help you with two things:\n\n"
        "📢 *Event Broadcasts* – Receive scheduled messages from event organizers.\n"
        "   (You'll be added by an organizer with your alias.)\n\n"
        "💧 *Personal Hydration Reminders* – Get reminders to drink water.\n"
        "   Use the commands below to manage your personal reminders.\n\n"
        "*Available commands:*\n"
        "/drinkwater – Start hydration reminders\n"
        "/settime – Set reminder frequency (e.g., /settime 30)\n"
        "/stopwater – Pause hydration reminders\n"
        "/waterstatus – Check your reminder settings\n"
        "/help – Show this help message"
    )
    await message.answer(welcome, parse_mode="Markdown")


async def cmd_help(message: types.Message) -> None:
    """Handle /help – show available commands."""
    help_text = get_help_text()
    help_text += (
        "\n\n💧 *Hydration Reminders*\n"
        "/drinkwater – Start personal water reminders\n"
        "/settime <min> – Set frequency (e.g., /settime 30)\n"
        "/stopwater – Pause reminders\n"
        "/waterstatus – View your settings"
    )
    await message.answer(help_text, parse_mode="Markdown")


async def handle_water_callback(callback: CallbackQuery) -> None:
    """Handle inline keyboard callbacks for water reminders."""
    from database_broadcast import get_session_factory, toggle_water_reminder

    data = callback.data  # e.g., "toggle_water_true" or "toggle_water_false"
    if not data.startswith("toggle_water_"):
        return

    should_activate = data.split("_")[-1] == "true"
    chat_id = callback.from_user.id

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await toggle_water_reminder(session, chat_id, is_active=should_activate)

    if result:
        status = "✅ Activated" if result["is_active"] else "⏸️ Paused"
        await callback.message.edit_text(
            f"💧 *Hydration reminders {status}*\n\n"
            f"Frequency: every *{result['interval_minutes']} minutes*",
            parse_mode="Markdown",
        )
    else:
        await callback.answer("❌ Failed to update settings.")


def setup_dispatcher(dp: Dispatcher) -> None:
    """
    Register all handlers with the dispatcher.

    Args:
        dp: aiogram Dispatcher instance
    """
    # LMS analytics commands (existing)
    dp.message.register(
        lambda m: m.answer(handle_start()),
        CommandStart(),
    )
    dp.message.register(
        lambda m: m.answer(handle_help(), parse_mode="Markdown"),
        Command("help"),
    )
    dp.message.register(
        lambda m: m.answer(handle_health()),
        Command("health"),
    )
    dp.message.register(
        lambda m: m.answer(handle_labs()),
        Command("labs"),
    )
    dp.message.register(
        lambda m: m.answer(handle_scores(m.text.split(maxsplit=1)[1] if len(m.text.split()) > 1 else "")),
        Command("scores"),
    )

    # Water reminder commands
    register_water_handlers(dp)

    # Water reminder callback
    dp.callback_query.register(handle_water_callback, lambda c: c.data.startswith("toggle_water_"))


async def main() -> None:
    """Main entry point for Telegram bot mode."""
    config = load_config()
    bot_token = config.get("BOT_TOKEN", "")

    if not bot_token:
        print("❌ Error: BOT_TOKEN is not set.")
        print("   Configure .env.bot.secret with your Telegram bot token.")
        sys.exit(1)

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Initialize bot and dispatcher
    bot = Bot(token=bot_token)
    dp = Dispatcher()

    # Register handlers
    setup_dispatcher(dp)

    # Initialize and start broadcast scheduler
    scheduler = BroadcastScheduler(bot=bot)
    scheduler.start()
    logger.info("Broadcast scheduler started")

    # Startup message
    logger.info("Bot is starting in Telegram polling mode...")

    try:
        # Start polling
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        scheduler.stop()
        await bot.session.close()


def main_cli() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="LMS Telegram Bot + Event Broadcast System")
    parser.add_argument(
        "--test",
        type=str,
        metavar="COMMAND",
        help="Test mode: run a command and print response to stdout",
    )

    args = parser.parse_args()

    if args.test:
        run_test_mode(args.test)
        return

    # Run Telegram bot mode with scheduler
    asyncio.run(main())


if __name__ == "__main__":
    main_cli()
