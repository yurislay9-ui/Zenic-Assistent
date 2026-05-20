"""
ZENIC-AGENTS - Retry Pattern v16: Configuration and Delay Calculation

RetryConfig dataclass and _compute_delay function.
"""

import random
from dataclasses import dataclass
from typing import Callable, Optional, Tuple, Type

import logging

from src.core.shared.deterministic import ControllableJitter

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    """
    Configuration for retry behaviour.

    Attributes:
        max_attempts: Maximum number of attempts (1 = no retry).
        base_delay: Base delay in seconds between retries.
        max_delay: Upper bound for the computed delay.
        exponential_base: Base for exponential backoff calculation.
        jitter: Whether to add random jitter to the delay.
        jitter_max: Jitter multiplier (0..1). Jitter ∈ [0, jitter_max * delay).
        retryable_exceptions: Exception types that trigger a retry.
        on_retry: Callback invoked on each retry: (attempt, exception, delay).
        backoff_strategy: One of ``"exponential"``, ``"linear"``, ``"fixed"``.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 0.5
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    on_retry: Optional[Callable[[int, Exception, float], None]] = None
    backoff_strategy: str = "exponential"

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if self.base_delay < 0:
            raise ValueError("base_delay must be >= 0")
        if self.max_delay < 0:
            raise ValueError("max_delay must be >= 0")
        if self.exponential_base <= 0:
            raise ValueError("exponential_base must be > 0")
        if not (0.0 <= self.jitter_max <= 1.0):
            raise ValueError("jitter_max must be in [0.0, 1.0]")
        if self.backoff_strategy not in ("exponential", "linear", "fixed"):
            raise ValueError(
                f"backoff_strategy must be 'exponential', 'linear', or 'fixed', "
                f"got {self.backoff_strategy!r}"
            )


# Shared deterministic jitter instance for retry configs
_jitter_gen = ControllableJitter("retry_config")


def _compute_delay(config: RetryConfig, attempt: int) -> float:
    """
    Compute the delay for the given attempt number (1-based).

    The delay is clamped to ``[0, max_delay]`` and optionally has jitter
    applied.
    """
    if config.backoff_strategy == "exponential":
        delay = config.base_delay * (config.exponential_base ** (attempt - 1))
    elif config.backoff_strategy == "linear":
        delay = config.base_delay * attempt
    else:  # fixed
        delay = config.base_delay

    delay = min(delay, config.max_delay)

    if config.jitter and delay > 0:
        delay = _jitter_gen.apply(delay, config.jitter_max)

    return delay
