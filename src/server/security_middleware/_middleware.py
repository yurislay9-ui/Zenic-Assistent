"""Security Middleware - Headers & Rate Limiting."""

import logging
import time
import threading
from typing import Any, Callable, Dict, List, Optional

from ._config import SecurityConfig

logger = logging.getLogger("zenic_agents.server.security_middleware")

class SecurityHeadersMiddleware:
    """Adds security headers to all responses.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy (if enabled)
    - Strict-Transport-Security (if enabled)
    - Permissions-Policy: restrictive defaults
    """

    def __init__(self, config: Optional[SecurityConfig] = None) -> None:
        self._config = config or SecurityConfig()

    def get_headers(self) -> Dict[str, str]:
        """Get all security headers as a dict.

        Returns:
            Dict of header name -> header value.
        """
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        }

        if self._config.enable_csp:
            headers["Content-Security-Policy"] = self._config.csp_policy

        if self._config.enable_hsts:
            headers["Strict-Transport-Security"] = (
                f"max-age={self._config.hsts_max_age}; includeSubDomains; preload"
            )

        return headers


# ============================================================
#  AUTH RATE LIMITER
# ============================================================

class AuthRateLimiter:
    """Rate limiter specifically for authentication endpoints.

    Prevents brute-force attacks on login, register, and token
    refresh endpoints. Uses per-IP token bucket with lower limits
    than the general rate limiter.

    This is separate from the main TenantRateLimiter because:
    1. Auth endpoints need much stricter limits
    2. Failed attempts should progressively increase delays
    3. Auth rate limiting happens before auth resolution
    """

    def __init__(
        self,
        rpm: int = 20,
        burst: int = 5,
        lockout_duration: float = 300.0,
        max_failures_before_lockout: int = 10,
    ) -> None:
        self._rpm = rpm
        self._burst = burst
        self._lockout_duration = lockout_duration
        self._max_failures = max_failures_before_lockout

        self._clients: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def is_allowed(self, client_ip: str) -> bool:
        """Check if an auth request from this IP is allowed.

        Args:
            client_ip: Client IP address.

        Returns:
            True if the request is allowed.
        """
        now = time.time()

        with self._lock:
            if client_ip not in self._clients:
                self._clients[client_ip] = {
                    "tokens": float(self._burst),
                    "last_refill": now,
                    "failures": 0,
                    "lockout_until": 0.0,
                }

            client = self._clients[client_ip]

            # Check lockout
            if now < client.get("lockout_until", 0):
                return False

            # Refill tokens
            elapsed = now - client["last_refill"]
            refill_rate = self._rpm / 60.0
            client["tokens"] = min(float(self._burst), client["tokens"] + elapsed * refill_rate)
            client["last_refill"] = now

            if client["tokens"] < 1.0:
                return False

            client["tokens"] -= 1.0
            return True

    def record_failure(self, client_ip: str) -> None:
        """Record a failed auth attempt (for progressive lockout).

        Args:
            client_ip: Client IP that failed authentication.
        """
        now = time.time()
        with self._lock:
            if client_ip in self._clients:
                self._clients[client_ip]["failures"] += 1
                if self._clients[client_ip]["failures"] >= self._max_failures:
                    self._clients[client_ip]["lockout_until"] = now + self._lockout_duration
                    logger.warning(
                        "AuthRateLimiter: IP %s locked out for %ds after %d failures",
                        client_ip, int(self._lockout_duration),
                        self._clients[client_ip]["failures"],
                    )

    def record_success(self, client_ip: str) -> None:
        """Record a successful auth attempt (resets failure counter).

        Args:
            client_ip: Client IP that succeeded authentication.
        """
        with self._lock:
            if client_ip in self._clients:
                self._clients[client_ip]["failures"] = 0

    def cleanup(self, max_age: float = 300.0) -> int:
        """Remove stale client entries.

        Args:
            max_age: Seconds of inactivity before removal.

        Returns:
            Number of entries removed.
        """
        now = time.time()
        with self._lock:
            stale = [
                ip for ip, c in self._clients.items()
                if c["last_refill"] < now - max_age
            ]
            for ip in stale:
                del self._clients[ip]
        return len(stale)


# ============================================================
#  TOKEN BLACKLIST
# ============================================================

