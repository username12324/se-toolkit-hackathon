"""
Services for the LMS Telegram bot.

Services handle external dependencies (APIs, databases, LLMs).
They are separate from handlers — this is *separation of concerns*.
"""

from .api_client import LMSClient
from . import api
from .llm import query_llm

__all__ = ["LMSClient", "api", "query_llm"]
