"""
Distributed Circuit Breaker — Shared State Model.

Contains the SharedCircuitState class that represents a snapshot
of circuit breaker state shared across distributed nodes.
"""

from typing import Any, Dict, Optional


class SharedCircuitState:
    """
    Snapshot of circuit breaker state shared across nodes.

    Attributes:
        name: Circuit breaker name.
        state: Current state (CLOSED/OPEN/HALF_OPEN).
        failure_count: Consecutive failures in CLOSED state.
        success_count: Consecutive successes in HALF_OPEN state.
        half_open_call_count: Calls made in HALF_OPEN state.
        opened_at: Timestamp when circuit was opened.
        version: Optimistic concurrency version number.
    """
    __slots__ = (
        "name", "state", "failure_count", "success_count",
        "half_open_call_count", "opened_at", "version",
    )

    def __init__(
        self,
        name: str,
        state: str = "closed",
        failure_count: int = 0,
        success_count: int = 0,
        half_open_call_count: int = 0,
        opened_at: Optional[float] = None,
        version: int = 0,
    ) -> None:
        self.name = name
        self.state = state
        self.failure_count = failure_count
        self.success_count = success_count
        self.half_open_call_count = half_open_call_count
        self.opened_at = opened_at
        self.version = version

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for backend storage."""
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "half_open_call_count": self.half_open_call_count,
            "opened_at": self.opened_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], version: int = 0) -> "SharedCircuitState":
        """Deserialize from backend dict."""
        return cls(
            name=data.get("name", ""),
            state=data.get("state", "closed"),
            failure_count=data.get("failure_count", 0),
            success_count=data.get("success_count", 0),
            half_open_call_count=data.get("half_open_call_count", 0),
            opened_at=data.get("opened_at"),
            version=version,
        )
