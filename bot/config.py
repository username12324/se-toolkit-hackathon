"""
Configuration loader for the bot.

Loads environment variables from .env.bot.secret file.
This pattern keeps secrets out of source code and in environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv


def load_config() -> dict[str, str]:
    """
    Load configuration from .env.bot.secret file.
    
    Returns a dict with keys:
    - BOT_TOKEN: Telegram bot token
    - LMS_API_BASE_URL: Backend API URL
    - LMS_API_KEY: Backend API key for Bearer auth
    - LLM_API_KEY: LLM API key
    - LLM_API_MODEL: LLM model name
    - LLM_API_BASE_URL: LLM API URL
    """
    # Find .env.bot.secret in the bot directory
    bot_dir = Path(__file__).parent
    env_file = bot_dir / ".env.bot.secret"
    
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # Try parent directory (for when bot is run from repo root)
        env_file = bot_dir.parent / ".env.bot.secret"
        if env_file.exists():
            load_dotenv(env_file)
    
    return {
        "BOT_TOKEN": os.getenv("BOT_TOKEN", ""),
        "LMS_API_BASE_URL": os.getenv("LMS_API_BASE_URL", ""),
        "LMS_API_KEY": os.getenv("LMS_API_KEY", ""),
        "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
        "LLM_API_MODEL": os.getenv("LLM_API_MODEL", "coder-model"),
        "LLM_API_BASE_URL": os.getenv("LLM_API_BASE_URL", ""),
        # Database (for broadcast system)
        "DB_HOST": os.getenv("DB_HOST", "localhost"),
        "DB_PORT": os.getenv("DB_PORT", "5432"),
        "DB_NAME": os.getenv("DB_NAME", "lms"),
        "DB_USER": os.getenv("DB_USER", "postgres"),
        "DB_PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
    }
