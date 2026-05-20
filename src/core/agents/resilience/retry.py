"""
Retry with Exponential Backoff for v18 agents.

delay = base_delay * (exponential_base ^ (attempt - 1))
capped at max_delay, with optional jitter (0-30%).
"""

from __future__ import annotations

import functools
import time
import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from src.core.shared.deterministic import ControllableJitter

T = TypeVar("T")

# Shared deterministic jitter instance for agent retry
_jitter_gen = ControllableJitter("agent_retry")


@dataclass
class AgentRetryConfig:
    """Retry configuration for an agent."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 0.3
    timeout_per_attempt: float = 5.0

    def compute_delay(self, attempt: int) -> float:
        """Compute delay for the given attempt number (1-based)."""
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay)
        if self.jitter:
            delay = _jitter_gen.apply(delay, self.jitter_max)
        return delay


# Default configs per agent group
RETRY_CONFIGS = {
    "understanding": AgentRetryConfig(max_attempts=3, base_delay=0.5, max_delay=5.0),
    "memory": AgentRetryConfig(max_attempts=3, base_delay=0.5, max_delay=5.0),
    "business": AgentRetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
    "code": AgentRetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
    "validation": AgentRetryConfig(max_attempts=2, base_delay=0.5, max_delay=5.0),
    "automation": AgentRetryConfig(max_attempts=3, base_delay=0.5, max_delay=5.0),
    "reasoning": AgentRetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
    "verdict": AgentRetryConfig(max_attempts=3, base_delay=1.0, max_delay=10.0),
    "infrastructure": AgentRetryConfig(max_attempts=2, base_delay=0.5, max_delay=5.0),
}


def with_agent_retry(
    func: Optional[Callable] = None,
    *,
    config: Optional[AgentRetryConfig] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
):
    """
    Decorator that adds retry with exponential backoff to an agent method.

    Usage:
        @with_agent_retry(config=AgentRetryConfig(max_attempts=3))
        def execute(self, input_data):
            ...

        # Or with defaults:
        @with_agent_retry
        def execute(self, input_data):
            ...
    """
    if config is None:
        config = AgentRetryConfig()

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < config.max_attempts:
                        delay = config.compute_delay(attempt)
                        if on_retry:
                            on_retry(attempt, e, delay)
                        time.sleep(delay)
            # All attempts exhausted — re-raise
            raise last_exception  # type: ignore[misc]

        wrapper._retry_config = config
        return wrapper

    if func is not None:
        return decorator(func)
    return decorator
