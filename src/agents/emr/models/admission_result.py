"""Admission Result Model."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdmissionResult:
    """
    Result of admission control check.

    Determines whether a batch can proceed, needs to wait,
    or should be downgraded.
    """

    allowed: bool
    parallel: int = 0
    downgraded: bool = False
    original_parallel: Optional[int] = None
    wait_seconds: int = 0
    queue_position: int = 0
    reason: str = ""
    current_usage: int = 0
    available: int = 0

    def to_response(self) -> dict:
        """Convert to Lambda response format."""
        response = {
            "allowed": self.allowed,
            "current_usage": self.current_usage,
        }

        if self.allowed:
            response["parallel"] = self.parallel
            response["available"] = self.available

            if self.downgraded:
                response["downgraded"] = True
                response["original_parallel"] = self.original_parallel
                response["adjusted_parallel"] = self.parallel
                response["reason"] = self.reason or "partial_capacity_available"
        else:
            response["wait_seconds"] = self.wait_seconds
            response["queue_position"] = self.queue_position
            response["reason"] = self.reason or "connection_limit_exceeded"

        return response


@dataclass
class ReleaseResult:
    """Result of connection release."""

    released: bool
    released_connections: int = 0
    current_usage: int = 0
    error: Optional[str] = None

    def to_response(self) -> dict:
        """Convert to Lambda response format."""
        response = {
            "released": self.released,
            "released_connections": self.released_connections,
            "current_usage": self.current_usage,
        }
        if self.error:
            response["error"] = self.error
        return response
