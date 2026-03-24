"""
LLM client for intent-based routing.

Handles communication with the LLM API for tool calling.
The LLM decides which backend tool to call based on tool descriptions.
"""

import json
import sys
from typing import Any

import httpx
from config import load_config


# Tool definitions for all 9 backend endpoints
# The LLM reads these descriptions to decide which tool to call
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_items",
            "description": "Get list of all labs and tasks. Use this to discover what labs are available or to get lab IDs.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_learners",
            "description": "Get list of enrolled learners and their group assignments. Use this to find student information.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scores",
            "description": "Get score distribution (4 buckets) for a specific lab. Shows how many students scored in each range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {"type": "string", "description": "Lab identifier, e.g. 'lab-01', 'lab-04'"}
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pass_rates",
            "description": "Get per-task average scores and attempt counts for a specific lab. Use this to see which tasks are hardest.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {"type": "string", "description": "Lab identifier, e.g. 'lab-01', 'lab-04'"}
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timeline",
            "description": "Get submission timeline showing submissions per day for a lab. Use this to see activity patterns.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {"type": "string", "description": "Lab identifier, e.g. 'lab-01', 'lab-04'"}
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_groups",
            "description": "Get per-group performance metrics for a lab. Shows average scores and student counts per group.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {"type": "string", "description": "Lab identifier, e.g. 'lab-01', 'lab-04'"}
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_learners",
            "description": "Get top N learners by score for a lab. Use this to find the best performing students.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {"type": "string", "description": "Lab identifier, e.g. 'lab-01', 'lab-04'"},
                    "limit": {"type": "integer", "description": "Number of top learners to return, e.g. 5"}
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_completion_rate",
            "description": "Get completion rate percentage for a lab. Shows what fraction of students completed the lab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {"type": "string", "description": "Lab identifier, e.g. 'lab-01', 'lab-04'"}
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_sync",
            "description": "Trigger ETL sync to refresh data from the autochecker. Use this when data seems stale.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# System prompt that encourages tool use
SYSTEM_PROMPT = """You are an LMS (Learning Management System) assistant that helps users understand lab performance and student progress.

You have access to tools that query the LMS backend. When a user asks a question:
1. Think about what data you need to answer
2. Call the appropriate tool(s) to get that data
3. Use the tool results to formulate your answer

For questions comparing labs or finding extremes (e.g., "which lab has the lowest pass rate"), you should:
1. First get the list of all labs using get_items
2. Then call the relevant analytics tool for each lab
3. Compare the results and provide a specific answer

If the user's message is a greeting or unclear, respond helpfully without using tools. Suggest what you can help with.

Always provide specific, data-driven answers when you have the data. Include numbers and percentages."""


class LLMClient:
    """Client for LLM API with tool calling support."""

    def __init__(self):
        config = load_config()
        self.base_url = config["LLM_API_BASE_URL"].rstrip("/")
        self.api_key = config["LLM_API_KEY"]
        self.model = config["LLM_API_MODEL"]
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """
        Send a chat request to the LLM with optional tool definitions.

        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool definitions

        Returns:
            The LLM response as a dict
        """
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        try:
            with httpx.Client() as client:
                response = client.post(url, headers=self._headers, json=payload, timeout=60.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise ConnectionError(
                    "LLM error: HTTP 401 Unauthorized. The API token may be expired. "
                    "Restart the Qwen proxy: cd ~/qwen-code-oai-proxy && docker compose restart"
                ) from e
            raise ConnectionError(
                f"LLM error: HTTP {e.response.status_code} {e.response.reason_phrase}"
            ) from e
        except httpx.ConnectError as e:
            raise ConnectionError(
                f"LLM error: connection refused ({self.base_url}). Check that the LLM service is running."
            ) from e
        except httpx.HTTPError as e:
            raise ConnectionError(f"LLM error: {str(e)}") from e

    def extract_tool_calls(self, response: dict) -> list[dict] | None:
        """
        Extract tool calls from an LLM response.

        Returns a list of tool call dicts, or None if no tool calls.
        """
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls")
        return tool_calls

    def get_assistant_content(self, response: dict) -> str:
        """Extract the assistant's text content from a response."""
        choice = response.get("choices", [{}])[0]
        message = choice.get("message", {})
        return message.get("content", "")


def route(user_message: str, lms_client: Any = None) -> str:
    """
    Route a user message through the LLM to get a response.

    This is the main entry point for intent-based routing.
    It sends the message to the LLM, executes any tool calls,
    feeds results back, and returns the final answer.

    Args:
        user_message: The user's natural language query
        lms_client: Optional LMSClient instance (created if not provided)

    Returns:
        The bot's response as a string
    """
    from services.api_client import LMSClient

    if lms_client is None:
        lms_client = LMSClient()

    llm_client = LLMClient()

    # Build the conversation history
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # Tool execution loop
    max_iterations = 5  # Prevent infinite loops
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Call the LLM
        try:
            response = llm_client.chat(messages, tools=TOOL_DEFINITIONS)
        except ConnectionError as e:
            return f"LLM error: {str(e)}"

        # Check if the LLM wants to call tools
        tool_calls = llm_client.extract_tool_calls(response)

        if not tool_calls:
            # No tool calls - the LLM has a final answer
            return llm_client.get_assistant_content(response) or "I'm not sure how to help with that. Try asking about labs, scores, or students."

        # Execute tool calls and collect results
        tool_results = []
        for tool_call in tool_calls:
            function = tool_call.get("function", {})
            tool_name = function.get("name", "")
            tool_args_str = function.get("arguments", "{}")

            try:
                tool_args = json.loads(tool_args_str) if tool_args_str else {}
            except json.JSONDecodeError:
                tool_args = {}

            # Execute the tool
            print(f"[tool] LLM called: {tool_name}({tool_args})", file=sys.stderr)
            result = _execute_tool(tool_name, tool_args, lms_client)
            print(f"[tool] Result: {str(result)[:200]}", file=sys.stderr)

            tool_results.append({
                "tool_call_id": tool_call.get("id"),
                "role": "tool",
                "name": tool_name,
                "content": json.dumps(result) if not isinstance(result, str) else result,
            })

        # Add assistant's message and tool results to conversation
        assistant_message = {
            "role": "assistant",
            "content": None,
            "tool_calls": tool_calls,
        }
        messages.append(assistant_message)
        messages.extend(tool_results)

        print(f"[summary] Feeding {len(tool_results)} tool result(s) back to LLM", file=sys.stderr)

    # If we exit the loop without a final answer
    return "I'm having trouble answering this question. Please try rephrasing or use a slash command like /help."


def _execute_tool(tool_name: str, args: dict, lms_client: LMSClient) -> Any:
    """Execute a tool by calling the appropriate LMS API method."""
    # Ensure limit is an integer if present (LLM may pass it as string)
    if "limit" in args and isinstance(args["limit"], str):
        try:
            args["limit"] = int(args["limit"])
        except ValueError:
            pass

    # Map tool names to API endpoints (tool names use underscores, endpoints use hyphens)
    tool_methods = {
        "get_items": lambda: lms_client.get_items(),
        "get_learners": lambda: lms_client.get_learners(),
        "get_scores": lambda: lms_client.get_analytics("scores", **args),
        "get_pass_rates": lambda: lms_client.get_pass_rates(args.get("lab", "")),
        "get_timeline": lambda: lms_client.get_analytics("timeline", **args),
        "get_groups": lambda: lms_client.get_analytics("groups", **args),
        "get_top_learners": lambda: lms_client.get_analytics("top-learners", **args),
        "get_completion_rate": lambda: lms_client.get_analytics("completion-rate", **args),
        "trigger_sync": lambda: lms_client.sync_pipeline(),
    }

    method = tool_methods.get(tool_name)
    if method is None:
        return {"error": f"Unknown tool: {tool_name}"}

    try:
        return method()
    except ConnectionError as e:
        return {"error": str(e)}
