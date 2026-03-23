"""
Command handler implementations.

Each handler is a pure function: it takes input and returns text.
No Telegram dependencies here - this makes handlers testable.
"""

from services.api_client import LMSClient


def handle_start() -> str:
    """Handle /start command - returns welcome message."""
    return "Welcome! I'm your LMS assistant bot. Use /help to see available commands."


def handle_help() -> str:
    """Handle /help command - lists available commands."""
    return """Available commands:
/start - Welcome message
/help - Show this help message
/health - Check backend status
/labs - List available labs
/scores <lab> - Show pass rates for a lab (e.g., /scores lab-04)"""


def handle_health() -> str:
    """Handle /health command - checks backend status."""
    client = LMSClient()
    try:
        items = client.get_items()
        return f"Backend is healthy. {len(items)} items available."
    except ConnectionError as e:
        return str(e)


def handle_labs() -> str:
    """Handle /labs command - lists available labs."""
    client = LMSClient()
    try:
        items = client.get_items()
        labs = [item for item in items if item.get("type") == "lab"]
        if not labs:
            return "No labs found."
        result = "Available labs:\n"
        for lab in labs:
            result += f"- {lab.get('title', 'Unknown')}\n"
        return result.strip()
    except ConnectionError as e:
        return str(e)


def handle_scores(query: str = "") -> str:
    """Handle /scores command - shows per-task pass rates."""
    if not query:
        return "Usage: /scores <lab-name>. Example: /scores lab-04"

    client = LMSClient()
    try:
        pass_rates = client.get_pass_rates(query)
        if not pass_rates:
            return f"No pass rate data found for '{query}'. Check the lab name."

        result = f"Pass rates for {query}:\n"
        for rate in pass_rates:
            task_name = rate.get("task_title", rate.get("task", "Unknown"))
            avg_score = rate.get("avg_score", rate.get("pass_rate", 0))
            attempts = rate.get("attempts", 0)
            result += f"- {task_name}: {avg_score:.1f}% ({attempts} attempts)\n"
        return result.strip()
    except ConnectionError as e:
        return str(e)


def get_handler(command: str):
    """
    Route command to appropriate handler.
    
    Returns the handler function for a given command string,
    or None if the command is not recognized.
    """
    handlers = {
        "/start": handle_start,
        "/help": handle_help,
        "/health": handle_health,
        "/labs": handle_labs,
        "/scores": handle_scores,
    }
    return handlers.get(command)
