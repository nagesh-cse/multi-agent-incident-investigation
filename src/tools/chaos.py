from __future__ import annotations
from typing import Dict, Any, Optional
from src.tools.base import (
    ToolTimeoutError,
    ToolRateLimitError,
    ToolServiceUnavailableError,
    ToolExecutionContext,
)


def apply_chaos(tool_name: str, context: Optional[ToolExecutionContext]) -> Optional[Dict[str, Any]]:
    """
    Checks if the active scenario defines a simulated failure for the given tool.
    Returns override directives (like truncation) or raises a ToolException.
    """
    if not context or not context.scenario_data:
        return None

    chaos_config = context.scenario_data.get("chaos_rules", {}).get(tool_name)
    if not chaos_config:
        return None

    action = chaos_config.get("action")
    message = chaos_config.get("message", f"Simulated failure in {tool_name}")

    if action == "timeout":
        context.record_failure(f"{tool_name}: Timeout ({message})")
        raise ToolTimeoutError(message=message, tool_name=tool_name, recoverable=True)

    elif action == "rate_limit":
        context.record_failure(f"{tool_name}: Rate Limit 429 ({message})")
        raise ToolRateLimitError(message=message, tool_name=tool_name, recoverable=True)

    elif action == "service_unavailable":
        context.record_failure(f"{tool_name}: 503 Unavailable ({message})")
        raise ToolServiceUnavailableError(message=message, tool_name=tool_name, recoverable=False)

    elif action == "truncate":
        context.record_failure(f"{tool_name}: Truncated results ({message})")
        return {"truncate": True, "limit": chaos_config.get("limit", 3), "notice": message}

    return None
