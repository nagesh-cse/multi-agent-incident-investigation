from __future__ import annotations
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class ToolException(Exception):
    """Base exception for investigation tools."""
    def __init__(self, message: str, tool_name: str, recoverable: bool = True):
        super().__init__(message)
        self.message = message
        self.tool_name = tool_name
        self.recoverable = recoverable


class ToolTimeoutError(ToolException):
    """Raised when a simulated tool times out."""
    pass


class ToolRateLimitError(ToolException):
    """Raised when a simulated tool hits a rate limit (429)."""
    pass


class ToolServiceUnavailableError(ToolException):
    """Raised when a data source is temporarily offline (503)."""
    pass


class ToolExecutionContext(BaseModel):
    """Execution context holding current incident scenario data and metrics."""
    scenario_data: Dict[str, Any] = Field(default_factory=dict)
    total_calls: int = 0
    failure_log: list[str] = Field(default_factory=list)

    def record_call(self, tool_name: str):
        self.total_calls += 1

    def record_failure(self, failure_msg: str):
        self.failure_log.append(failure_msg)
