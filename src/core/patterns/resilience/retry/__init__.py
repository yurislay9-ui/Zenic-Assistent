"""
ZENIC-AGENTS - Retry Pattern v16

Comprehensive retry with exponential/linear/fixed backoff, jitter,
and on_retry callbacks. Designed for Android/Termux (500MB RAM) — stdlib only.

Backoff strategies:
    exponential : delay = base_delay * (exponential_base ** (attempt - 1))
    linear      : delay = base_delay * attempt
    fixed       : delay = base_delay

Jitter: random.uniform(0, jitter_max * current_delay) added when jitter=True.
"""

from ._config import RetryConfig
from ._programmatic import with_retry, with_retry_async, with_config_retry
from ._scope import retry, retry_async, RetryScope

__all__ = [
    "RetryConfig",
    "retry",
    "retry_async",
    "with_retry",
    "with_config_retry",
    "with_retry_async",
    "RetryScope",
]
