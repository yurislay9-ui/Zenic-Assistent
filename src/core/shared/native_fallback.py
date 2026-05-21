"""
ZENIC-AGENTS — Native Fallback Registry.

When _zenic_native (Rust PyO3 module) is unavailable, this registry
provides Python fallbacks for critical functions. This prevents silent
capability loss when the Rust extension fails to load.

Usage:
    from src.core.shared.native_fallback import call_native

    result = call_native("blake3_hash", data)
    # Tries _zenic_native.blake3_hash first, falls back to Python implementation
"""

import logging
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)

__all__ = ["call_native", "register_fallback"]

# Registry of Python fallback implementations
_FALLBACKS: Dict[str, Callable] = {}


def register_fallback(name: str, fn: Callable) -> None:
    """Register a Python fallback for a Rust native function.

    Args:
        name: The function name as exposed by _zenic_native.
        fn: The Python fallback implementation.
    """
    _FALLBACKS[name] = fn
    logger.debug("Registered Python fallback for _zenic_native.%s", name)


def call_native(name: str, *args: Any, **kwargs: Any) -> Any:
    """Call a Rust native function with Python fallback.

    Tries _zenic_native.<name> first. If the module is unavailable
    or the function doesn't exist, falls back to a registered Python
    implementation.

    Args:
        name: The function name in _zenic_native.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The function result.

    Raises:
        RuntimeError: If native call fails and no fallback is registered.
    """
    try:
        import _zenic_native
        fn = getattr(_zenic_native, name)
        return fn(*args, **kwargs)
    except ImportError:
        logger.debug("_zenic_native not available, checking fallbacks")
    except AttributeError:
        logger.warning("_zenic_native.%s not found, checking fallbacks", name)
    except Exception as exc:
        logger.warning("_zenic_native.%s failed: %s, checking fallbacks", name, exc)

    # Try Python fallback
    if name in _FALLBACKS:
        logger.info("Using Python fallback for _zenic_native.%s", name)
        return _FALLBACKS[name](*args, **kwargs)

    raise RuntimeError(
        f"_zenic_native.{name} is unavailable and no Python fallback is registered. "
        f"Install the Rust extension or register a fallback with register_fallback()."
    )


# ── Built-in Python fallbacks ─────────────────────────────

def _sha256_hash(data: str) -> str:
    """Python fallback for blake3_hash (uses SHA-256 instead)."""
    import hashlib
    return hashlib.sha256(data.encode()).hexdigest()


def _hmac_sign(data: str, secret_key: str) -> str:
    """Python fallback for sign_data."""
    import hmac, hashlib
    return hmac.new(secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()


def _hmac_verify(data: str, signature: str, secret_key: str) -> bool:
    """Python fallback for verify_signature."""
    import hmac, hashlib
    expected = hmac.new(secret_key.encode(), data.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


# Register built-in fallbacks
register_fallback("blake3_hash", _sha256_hash)
register_fallback("sign_data", _hmac_sign)
register_fallback("verify_signature", _hmac_verify)
