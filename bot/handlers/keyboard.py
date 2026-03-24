"""
Inline keyboard definitions for the Telegram bot.

Provides keyboard buttons for common actions so users can discover
capabilities without typing.
"""


def get_main_keyboard() -> list:
    """
    Return the main inline keyboard layout.

    This keyboard provides quick access to common analytics queries.
    When Telegram mode is implemented, these buttons will send
    callback queries or pre-filled messages.

    Returns a list of button rows (each row is a list of button dicts).
    """
    return [
        [
            {"text": "📊 All Labs", "callback_data": "labs"},
            {"text": "💚 Health Check", "callback_data": "health"},
        ],
        [
            {"text": "📈 Lab Scores", "callback_data": "scores_lab"},
            {"text": "🏆 Top Students", "callback_data": "top_students"},
        ],
        [
            {"text": "👥 Group Performance", "callback_data": "groups"},
            {"text": "📅 Timeline", "callback_data": "timeline"},
        ],
        [
            {"text": "❓ Help", "callback_data": "help"},
        ],
    ]


def get_lab_selection_keyboard(labs: list) -> list:
    """
    Return a keyboard with buttons for each lab.

    Args:
        labs: List of lab dicts with 'id' and 'title' keys

    Returns a list of button rows.
    """
    buttons = []
    row = []
    for lab in labs:
        lab_id = lab.get("id", "")
        # Convert lab ID to lab-XX format
        if isinstance(lab_id, int):
            lab_key = f"lab-{lab_id:02d}"
        else:
            lab_key = str(lab_id)
        row.append({
            "text": f"Lab {lab_id}",
            "callback_data": f"select_lab_{lab_key}"
        })
        if len(row) >= 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([{"text": "« Back", "callback_data": "main_menu"}])
    return buttons


def get_help_text() -> str:
    """Return help text describing bot capabilities."""
    return """I'm your LMS Analytics Assistant! I can help you understand lab performance and student progress.

**What I can do:**

📊 **View Labs** - See all available labs and tasks
💚 **Health Check** - Verify backend connection
📈 **Lab Scores** - Get score distributions for any lab
🏆 **Top Students** - Find the best performers
👥 **Group Performance** - Compare group results
📅 **Timeline** - See submission patterns

**How to use:**

You can either:
1. Click the buttons below to explore
2. Ask me questions in plain English, like:
   • "Which lab has the lowest pass rate?"
   • "Show me scores for lab 4"
   • "Who are the top 5 students?"
   • "How are groups doing in lab 3?"

Try asking me anything about lab analytics!"""
