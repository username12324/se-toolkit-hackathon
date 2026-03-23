"""
Command handlers for the LMS Telegram bot.

Handlers are plain functions that take input and return text.
They don't know about Telegram - this makes them testable via --test mode,
unit tests, or any other entry point.

This is called *separation of concerns*: the business logic (handlers)
is separate from the transport layer (Telegram).
"""

from .command_handlers import (
    handle_start,
    handle_help,
    handle_health,
    handle_labs,
    handle_scores,
    get_handler,
)

__all__ = [
    "handle_start",
    "handle_help",
    "handle_health",
    "handle_labs",
    "handle_scores",
    "get_handler",
]
