"""
LLM router for natural language intent routing.

Uses the OpenAI-compatible API to interpret user messages and call appropriate tools.
"""

import json
import sys
from openai import OpenAI
from config import load_config
from services import api as api_funcs


# Tool definitions for the LLM
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_items",
            "description": "Get all labs and tasks from the LMS. Use this to list available labs or explore the catalog.",
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
            "name": "get_pass_rates",
            "description": "Get pass rates for tasks within a specific lab. Use this when user asks about scores, pass rates, or how students are performing on a lab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {
                        "type": "string",
                        "description": "Lab identifier (e.g., 'lab-04', 'lab-01')",
                    },
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_learners",
            "description": "Get all enrolled learners/students in the system.",
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
            "description": "Get score distribution (buckets) for a specific lab. Use when user asks about score distribution or grade breakdown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {
                        "type": "string",
                        "description": "Lab identifier (e.g., 'lab-04', 'lab-01')",
                    },
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_timeline",
            "description": "Get submission timeline showing submissions per day for a lab. Use when user asks about submission patterns or activity over time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {
                        "type": "string",
                        "description": "Lab identifier (e.g., 'lab-04', 'lab-01')",
                    },
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_groups",
            "description": "Get per-group performance for a lab. Use when user asks about group comparisons or which group is performing better.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {
                        "type": "string",
                        "description": "Lab identifier (e.g., 'lab-04', 'lab-01')",
                    },
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_learners",
            "description": "Get top performing learners for a lab. Use when user asks about best students, leaderboard, or top performers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {
                        "type": "string",
                        "description": "Lab identifier (e.g., 'lab-04', 'lab-01')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of top learners to return (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_completion_rate",
            "description": "Get completion percentage for a lab. Use when user asks about completion rate or how many students finished a lab.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lab": {
                        "type": "string",
                        "description": "Lab identifier (e.g., 'lab-04', 'lab-01')",
                    },
                },
                "required": ["lab"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_sync",
            "description": "Trigger ETL pipeline sync to update data from the autochecker. Use when user asks to refresh data or sync latest submissions.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]

# Map function names to actual Python functions
TOOL_MAP = {
    "get_items": api_funcs.get_items,
    "get_pass_rates": api_funcs.get_pass_rates,
    "get_learners": api_funcs.get_learners,
    "get_scores": api_funcs.get_scores,
    "get_timeline": api_funcs.get_timeline,
    "get_groups": api_funcs.get_groups,
    "get_top_learners": api_funcs.get_top_learners,
    "get_completion_rate": api_funcs.get_completion_rate,
    "trigger_sync": api_funcs.trigger_sync,
}

SYSTEM_PROMPT = """You are an assistant for a Learning Management System (LMS). 
You have access to tools that fetch data about labs, students, scores, and analytics.
When a user asks a question, use the appropriate tool(s) to get the data and then provide a helpful, natural language response.

Guidelines:
- Always call tools when you need data - don't make up information
- If a tool returns an error, explain the issue to the user
- Format responses clearly (use bullet points, numbered lists when appropriate)
- If the user doesn't specify a lab when needed, ask them to clarify
- Lab identifiers look like: lab-01, lab-02, lab-03, lab-04, lab-05, lab-06, lab-07
"""


def query_llm(user_message: str) -> str:
    """
    Query the LLM with a user message and return the response.
    
    Handles tool calls in a loop until the LLM returns a final answer.
    """
    config = load_config()
    
    # Check if LLM is configured
    if not config["LLM_API_KEY"] or config["LLM_API_KEY"] == "placeholder":
        return "LLM is not configured. Please set LLM_API_KEY in .env.bot.secret"
    
    if not config["LLM_API_BASE_URL"] or config["LLM_API_BASE_URL"] == "placeholder":
        return "LLM is not configured. Please set LLM_API_BASE_URL in .env.bot.secret"
    
    try:
        client = OpenAI(
            api_key=config["LLM_API_KEY"],
            base_url=config["LLM_API_BASE_URL"],
        )
    except Exception as e:
        return f"LLM client initialization error: {e}"
    
    # Build conversation history
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
    
    max_iterations = 5  # Prevent infinite loops
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        try:
            # Call the LLM
            response = client.chat.completions.create(
                model=config["LLM_API_MODEL"],
                messages=messages,
                tools=TOOLS,
            )
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "authentication" in error_msg.lower():
                return "LLM authentication failed. Please check LLM_API_KEY in .env.bot.secret"
            elif "connection" in error_msg.lower():
                return f"Cannot connect to LLM service ({config['LLM_API_BASE_URL']}). Check that it's running."
            else:
                return f"LLM error: {error_msg}"
        
        assistant_message = response.choices[0].message
        
        # Check if LLM wants to call tools
        if assistant_message.tool_calls:
            # Add assistant's message to history
            messages.append({
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": assistant_message.tool_calls,
            })
            
            # Execute each tool call
            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)
                
                print(f"[tool] LLM called: {tool_name} with args: {tool_args}", file=sys.stderr)
                
                # Get the function from TOOL_MAP and call it
                if tool_name in TOOL_MAP:
                    func = TOOL_MAP[tool_name]
                    try:
                        result = func(**tool_args)
                    except TypeError as e:
                        # Handle case where function doesn't accept the arguments
                        result = {"error": f"Invalid arguments: {e}"}
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}
                
                # Add tool result to conversation
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result, default=str),
                })
                
                print(f"[tool] Result: {result}", file=sys.stderr)
        else:
            # No tool calls - LLM has final answer
            return assistant_message.content or ""
    
    return "Error: LLM took too many iterations. Please try rephrasing your question."
