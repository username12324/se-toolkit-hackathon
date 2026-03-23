#!/usr/bin/env python3
"""
Telegram bot entry point.

Supports two modes:
- Test mode: `uv run bot.py --test "/command"` prints response to stdout
- Telegram mode: `uv run bot.py` connects to Telegram and handles messages
"""

import argparse
import sys

from handlers import get_handler


def run_test_mode(command: str) -> None:
    """
    Run a command through the handler and print result to stdout.
    
    This allows testing handlers without connecting to Telegram.
    """
    # Parse command and extract arguments
    parts = command.strip().split(maxsplit=1)
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
    
    # Telegram mode would go here (Task 2+)
    print("Telegram mode not yet implemented. Use --test mode for now.")
    print("Example: uv run bot.py --test '/start'")


if __name__ == "__main__":
    main()
