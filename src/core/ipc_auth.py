"""
ZENIC-AGENTS - IPC Bridge Authentication

Provides authentication and authorization for inter-process communication
between the Python core and the Next.js gateway (TypeScript).

Security measure: Prevents unauthorized processes from calling Python
bridge endpoints by requiring a shared secret token.

Usage::

    from src.core.ipc_auth import require_ipc_auth, verify_ipc_token

    @require_ipc_auth
    def sensitive_operation(token: str, **kwargs):
        ...

    # Or manual verification:
    if verify_ipc_token(token):
        ...
"""

from __future__ import annotations

import functools
import logging
import os
import secrets
import time
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger("zenic_agents.ipc_auth")

# ──────────────────────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────────────────────

# Token expiry in seconds (default: 5 minutes)
_IPC_TOKEN_TTL: int = int(os.environ.get("ZENIC_IPC_TOKEN_TTL", "300"))

# Maximum clock skew tolerance in seconds
_MAX_CLOCK_SKEW: int = 30

# ──────────────────────────────────────────────────────────────
#  Token Verification
# ──────────────────────────────────────────────────────────────

def _get_expected_token() -> str:
    """Get the expected IPC token from environment.

    In production, ZENIC_IPC_TOKEN MUST be set.
    In development, a random token is generated per-process
    (only same-process IPC works).
    """
    token = os.environ.get("ZENIC_IPC_TOKEN", "")
    if token:
        return token

    if os.environ.get("NODE_ENV") == "production" or os.environ.get("ZENIC_ENV") == "production":
        raise RuntimeError(
            "ZENIC_IPC_TOKEN is required in production. "
            "Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    # Development: generate a random token per process
    if not hasattr(_get_expected_token, "_dev_token"):
        _get_expected_token._dev_token = secrets.token_hex(32)  # type: ignore[attr-defined]
        logger.warning(
            "ipc_auth: ZENIC_IPC_TOKEN not set — using ephemeral dev token. "
            "Only same-process IPC will work."
        )

    return _get_expected_token._dev_token  # type: ignore[attr-defined]


def verify_ipc_token(token: str) -> bool:
    """Verify an IPC authentication token using constant-time comparison.

    Args:
        token: The token to verify.

    Returns:
        True if the token matches the expected value, False otherwise.
    """
    if not token:
        logger.warning("ipc_auth: Empty token provided")
        return False

    expected = _get_expected_token()
    if not expected:
        logger.error("ipc_auth: No expected token configured")
        return False

    # Constant-time comparison to prevent timing attacks
    try:
        return secrets.compare_digest(token, expected)
    except Exception as exc:
        logger.error("ipc_auth: Token comparison failed: %s", exc)
        return False


def verify_ipc_token_with_timestamp(token: str, timestamp: str) -> bool:
    """Verify an IPC token with timestamp-based expiry.

    The timestamp is the Unix epoch time when the token was generated.
    The token is valid if:
    1. The token itself matches the expected value (via compare_digest)
    2. The timestamp is within IPC_TOKEN_TTL seconds of the current time

    Args:
        token: The authentication token.
        timestamp: Unix epoch timestamp string when the token was generated.

    Returns:
        True if both token and timestamp are valid.
    """
    if not verify_ipc_token(token):
        return False

    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        logger.warning("ipc_auth: Invalid timestamp format: %s", timestamp)
        return False

    now = int(time.time())
    age = abs(now - ts)

    if age > _IPC_TOKEN_TTL + _MAX_CLOCK_SKEW:
        logger.warning(
            "ipc_auth: Token expired (age=%ds, ttl=%ds)",
            age, _IPC_TOKEN_TTL,
        )
        return False

    return True


# ──────────────────────────────────────────────────────────────
#  Decorator
# ──────────────────────────────────────────────────────────────

F = TypeVar("F", bound=Callable[..., Any])


def require_ipc_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that requires IPC authentication for a function.

    The decorated function MUST accept a `token` keyword argument.
    If the token is invalid, the function raises PermissionError.

    Usage::

        @require_ipc_auth
        def execute_action(token: str, action: str, **kwargs):
            # token is already verified at this point
            ...

    Raises:
        PermissionError: If the IPC token is invalid or missing.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = kwargs.pop("token", None) or kwargs.pop("ipc_token", None)

        if not token:
            logger.warning(
                "ipc_auth: Missing token for %s.%s",
                getattr(func, "__module__", "?"),
                func.__qualname__,
            )
            raise PermissionError(
                f"IPC authentication required for {func.__qualname__}. "
                "Provide 'token' keyword argument."
            )

        if not verify_ipc_token(token):
            logger.warning(
                "ipc_auth: Invalid token for %s.%s",
                getattr(func, "__module__", "?"),
                func.__qualname__,
            )
            raise PermissionError(
                f"Invalid IPC token for {func.__qualname__}."
            )

        return func(*args, **kwargs)

    return wrapper


def require_ipc_auth_with_timestamp(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that requires IPC authentication with timestamp validation.

    The decorated function MUST accept `token` and `timestamp` keyword arguments.

    Raises:
        PermissionError: If the IPC token is invalid, missing, or expired.
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        token = kwargs.pop("token", None) or kwargs.pop("ipc_token", None)
        timestamp = kwargs.pop("timestamp", None)

        if not token or not timestamp:
            raise PermissionError(
                f"IPC authentication with timestamp required for {func.__qualname__}. "
                "Provide 'token' and 'timestamp' keyword arguments."
            )

        if not verify_ipc_token_with_timestamp(token, str(timestamp)):
            raise PermissionError(
                f"Invalid or expired IPC token for {func.__qualname__}."
            )

        return func(*args, **kwargs)

    return wrapper


# ──────────────────────────────────────────────────────────────
#  Convenience: Generate Token
# ──────────────────────────────────────────────────────────────

def generate_ipc_token() -> str:
    """Generate a new random IPC token (for setup scripts).

    Returns:
        A 64-character hex string (256 bits of entropy).
    """
    return secrets.token_hex(32)


__all__ = [
    "verify_ipc_token",
    "verify_ipc_token_with_timestamp",
    "require_ipc_auth",
    "require_ipc_auth_with_timestamp",
    "generate_ipc_token",
]
