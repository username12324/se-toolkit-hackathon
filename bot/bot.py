#!/usr/bin/env python3
"""
Telegram bot entry point.

Supports two modes:
- Test mode: `uv run bot.py --test "/command"` prints response to stdout
- Telegram mode: `uv run bot.py` connects to Telegram and handles messages
"""

import argparse
import sys
import logging

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers import get_handler, handle_message
from config import load_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_test_mode(command: str) -> None:
    """
    Run a command through the handler and print result to stdout.

    This allows testing handlers without connecting to Telegram.
    """
    # Parse command and extract arguments
    parts = command.strip().split(maxsplit=1)
    cmd = parts[0]
    arg = parts[1] if len(parts) > 1 else ""

    # For test mode, handle plain text messages (no leading /)
    if not cmd.startswith("/"):
        response = handle_message(command)
        print(response)
        sys.exit(0)

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


def get_main_keyboard() -> InlineKeyboardMarkup:
    """Create the main inline keyboard for /start."""
    keyboard = [
        [
            InlineKeyboardButton(text="📚 Available Labs", callback_data="labs"),
            InlineKeyboardButton(text="🏆 Top Learners", callback_data="top_learners"),
        ],
        [
            InlineKeyboardButton(text="💊 Health Check", callback_data="health"),
            InlineKeyboardButton(text="❓ Help", callback_data="help"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


async def handle_start_command(message: types.Message, bot: Bot) -> None:
    """Handle /start command with inline keyboard."""
    text = handle_start()
    keyboard = get_main_keyboard()
    await message.answer(text, reply_markup=keyboard)


async def handle_help_command(message: types.Message) -> None:
    """Handle /help command."""
    text = handle_help()
    await message.answer(text)


async def handle_health_command(message: types.Message) -> None:
    """Handle /health command."""
    text = handle_health()
    await message.answer(text)


async def handle_labs_command(message: types.Message) -> None:
    """Handle /labs command."""
    text = handle_labs()
    await message.answer(text)


async def handle_scores_command(message: types.Message) -> None:
    """Handle /scores command with optional lab argument."""
    args = message.text.split(maxsplit=1)
    lab = args[1] if len(args) > 1 else ""
    text = handle_scores(lab)
    await message.answer(text)


async def handle_text_message(message: types.Message) -> None:
    """Handle plain text messages via LLM router."""
    text = message.text or ""
    
    # Check if it's a command we should handle directly
    if text.startswith("/"):
        # Let the command handlers deal with it
        return
    
    # Route through LLM
    logger.info(f"Processing message via LLM: {text[:50]}...")
    response = handle_message(text)
    await message.answer(response)


async def handle_callback_query(callback_query: types.CallbackQuery) -> None:
    """Handle inline keyboard button clicks."""
    data = callback_query.data
    logger.info(f"Callback query: {data}")
    
    if data == "labs":
        response = handle_labs()
    elif data == "health":
        response = handle_health()
    elif data == "help":
        response = handle_help()
    elif data == "top_learners":
        # Use LLM to get top learners
        response = handle_message("Show me the top learners across all labs")
    else:
        response = "Unknown action."
    
    await callback_query.message.answer(response)
    await callback_query.answer()


async def run_telegram_mode() -> None:
    """Run the bot in Telegram mode."""
    config = load_config()
    bot_token = config["BOT_TOKEN"]
    
    if not bot_token or bot_token == "placeholder":
        logger.error("BOT_TOKEN not configured. Set it in .env.bot.secret")
        logger.error("Telegram mode cannot start without a valid bot token.")
        return
    
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    
    # Register handlers
    dp.message.register(handle_start_command, CommandStart())
    dp.message.register(handle_help_command, Command("help"))
    dp.message.register(handle_health_command, Command("health"))
    dp.message.register(handle_labs_command, Command("labs"))
    dp.message.register(handle_scores_command, Command("scores"))
    dp.message.register(handle_text_message)  # Plain text messages
    
    # Register callback query handler for inline buttons
    dp.callback_query.register(handle_callback_query)
    
    logger.info("Bot started in Telegram mode")
    await dp.start_polling(bot)


def main():
    parser = argparse.ArgumentParser(description="LMS Telegram Bot")
    parser.add_argument(
        "--test",
        type=str,
        metavar="COMMAND",
        help="Test mode: run a command and print response to stdout"
    )

    args = parser.parse_args()

    if args.test:
        run_test_mode(args.test)
        return

    # Telegram mode
    import asyncio
    asyncio.run(run_telegram_mode())


if __name__ == "__main__":
    main()
