"""Configuration management for the Hydration Bot.

Loads environment variables using python-dotenv and exposes them
through a single ``Settings`` instance.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _find_env_file() -> Path | None:
    """Search common locations for an .env file.

    Priority order:
    1. ``.env`` in the project root (cwd or script parent).
    2. ``.env.secret`` – the project convention for real secrets.
    """
    candidates: list[Path] = [
        Path(__file__).resolve().parent.parent / ".env",
        Path(__file__).resolve().parent.parent / ".env.secret",
        Path.cwd() / ".env",
        Path.cwd() / ".env.secret",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Load .env file before anything else
# ---------------------------------------------------------------------------
_env_file = _find_env_file()
if _env_file:
    load_dotenv(_env_file, override=True)


@dataclass(frozen=True)
class Settings:
    """Immutable configuration bag populated from environment variables."""

    # Telegram
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))

    # PostgreSQL
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", "hydration_bot"))
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", "hydration_user"))
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: int = field(default_factory=lambda: int(os.getenv("DB_PORT", "5432")))

    # Web dashboard
    web_host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("WEB_PORT", "8000")))

    # Reminder defaults
    default_interval: int = field(
        default_factory=lambda: int(os.getenv("DEFAULT_INTERVAL", "60"))
    )
    min_interval: int = field(
        default_factory=lambda: int(os.getenv("MIN_INTERVAL", "15"))
    )
    max_interval: int = field(
        default_factory=lambda: int(os.getenv("MAX_INTERVAL", "240"))
    )

    # Quick-select intervals (minutes) shown as inline buttons
    quick_intervals: list[int] = field(
        default_factory=lambda: [15, 30, 60, 120]
    )

    @property
    def dsn(self) -> str:
        """Build a PostgreSQL DSN string for asyncpg."""
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def validate_interval(self, minutes: int) -> tuple[bool, str]:
        """Return ``(is_valid, error_message)`` for a candidate interval."""
        if minutes < self.min_interval:
            return False, f"Interval must be at least {self.min_interval} minutes."
        if minutes > self.max_interval:
            return False, f"Interval must be at most {self.max_interval} minutes."
        return True, ""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
settings = Settings()
