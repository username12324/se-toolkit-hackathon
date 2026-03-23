"""
Services for the LMS Telegram bot.

Services handle external dependencies (APIs, databases, LLMs).
They are separate from handlers — this is *separation of concerns*.
"""

from .api_client import LMSClient

__all__ = ["LMSClient"]
