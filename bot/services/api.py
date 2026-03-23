"""
LMS API wrapper functions for LLM tool use.

Each function returns JSON (dict or list) or a dict with "error" key on failure.
These are designed to be called by the LLM router.
"""

import httpx
from config import load_config


def _get_client() -> tuple[str, dict]:
    """Get base URL and headers for API requests."""
    config = load_config()
    base_url = config["LMS_API_BASE_URL"]
    headers = {"Authorization": f"Bearer {config['LMS_API_KEY']}"}
    return base_url, headers


def _make_request(method: str, endpoint: str, **kwargs) -> dict | list:
    """Make an HTTP request and return JSON or error dict."""
    base_url, headers = _get_client()
    url = f"{base_url}{endpoint}"
    try:
        with httpx.Client() as client:
            response = client.request(method, url, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
    except httpx.ConnectError as e:
        return {"error": f"Connection refused ({base_url}). Check services are running."}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} {e.response.reason_phrase}"}
    except httpx.HTTPError as e:
        return {"error": str(e)}


def get_items() -> list:
    """Get all items (labs and tasks)."""
    result = _make_request("GET", "/items/")
    return result if isinstance(result, list) else []


def get_pass_rates(lab: str) -> list:
    """Get pass rates for a specific lab."""
    result = _make_request("GET", f"/analytics/pass-rates?lab={lab}")
    return result if isinstance(result, list) else []


def get_learners() -> list:
    """Get all enrolled learners."""
    result = _make_request("GET", "/learners/")
    return result if isinstance(result, list) else []


def get_scores(lab: str) -> list:
    """Get score distribution for a lab."""
    result = _make_request("GET", f"/analytics/scores?lab={lab}")
    return result if isinstance(result, list) else []


def get_timeline(lab: str) -> list:
    """Get submission timeline for a lab."""
    result = _make_request("GET", f"/analytics/timeline?lab={lab}")
    return result if isinstance(result, list) else []


def get_groups(lab: str) -> list:
    """Get per-group performance for a lab."""
    result = _make_request("GET", f"/analytics/groups?lab={lab}")
    return result if isinstance(result, list) else []


def get_top_learners(lab: str, limit: int = 5) -> list:
    """Get top N learners for a lab."""
    result = _make_request("GET", f"/analytics/top-learners?lab={lab}&limit={limit}")
    return result if isinstance(result, list) else []


def get_completion_rate(lab: str) -> dict:
    """Get completion percentage for a lab."""
    result = _make_request("GET", f"/analytics/completion-rate?lab={lab}")
    return result if isinstance(result, dict) else {"error": "No data returned"}


def trigger_sync() -> dict:
    """Trigger ETL sync."""
    result = _make_request("POST", "/pipeline/sync", json={})
    return result if isinstance(result, dict) else {"error": "Sync failed"}
