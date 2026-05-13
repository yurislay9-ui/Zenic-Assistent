"""
ZENIC-AGENTS v16 - Rate Limiter

Token bucket rate limiter for the HTTP server.
Protects against request flooding on resource-constrained ARM devices.

Features:
- Per-IP rate limiting with token bucket algorithm
- Global request cap across all clients
- Automatic cleanup of stale client entries
- Configurable burst and sustained rates
- Compatible with Termux/ARM (no external dependencies)
"""

import time
import threading
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Stale client threshold: entries with no activity for this many seconds are removed
STALE_THRESHOLD_S: float = 300.0  # 5 minutes

__all__ = [
    "RateLimiter",
    "STALE_THRESHOLD_S",
]


class RateLimiter:
    """
    Token bucket rate limiter for HTTP request protection.

    Args:
        max_requests_per_minute: Max sustained requests per IP per minute
        burst_size: Max burst requests per IP (token bucket capacity)
        global_max_concurrent: Max concurrent requests across all clients
        cleanup_interval_s: How often to clean up stale client entries
    """

    def __init__(
        self,
        max_requests_per_minute: int = 30,
        burst_size: int = 10,
        global_max_concurrent: int = 20,
        cleanup_interval_s: float = 60.0,
    ):
        self.max_rpm = max_requests_per_minute
        self.burst_size = burst_size
        self.global_max_concurrent = global_max_concurrent
        self.cleanup_interval_s = cleanup_interval_s

        # Token bucket state per client IP
        # {ip: {"tokens": float, "last_refill": float}}
        self._clients = {}

        # Global concurrent request counter
        self._active_requests = 0

        # Single lock for both global and per-IP checks to ensure atomicity
        self._lock = threading.Lock()

        # Last cleanup timestamp
        self._last_cleanup = time.time()

        # Stats
        self._total_rejected = 0
        self._total_accepted = 0

    def acquire(self, client_ip: str) -> bool:
        """
        Try to acquire a request slot for the given client IP.

        Returns:
            True if the request is allowed, False if rate limited
        """
        now = time.time()

        # Atomically check global concurrent limit AND per-IP rate limit
        # under a single lock to prevent race conditions between check and increment.
        with self._lock:
            # Periodic cleanup of stale entries (inside lock to prevent race)
            if now - self._last_cleanup > self.cleanup_interval_s:
                self._cleanup_locked(now)
                self._last_cleanup = now
            # Check global concurrent limit
            if self._active_requests >= self.global_max_concurrent:
                self._total_rejected += 1
                logger.warning(
                    "Rate limit: global concurrent limit reached (%d/%d)",
                    self._active_requests, self.global_max_concurrent
                )
                return False

            # Check per-IP rate limit (token bucket)
            if client_ip not in self._clients:
                self._clients[client_ip] = {
                    "tokens": float(self.burst_size),
                    "last_refill": now,
                }

            client = self._clients[client_ip]

            # Refill tokens based on elapsed time
            elapsed = now - client["last_refill"]
            refill_rate = self.max_rpm / 60.0  # tokens per second
            client["tokens"] = min(
                float(self.burst_size),
                client["tokens"] + elapsed * refill_rate
            )
            client["last_refill"] = now

            # Try to consume a token
            if client["tokens"] < 1.0:
                self._total_rejected += 1
                logger.warning(
                    "Rate limit: IP %s exceeded (%.1f tokens remaining)",
                    client_ip, client["tokens"]
                )
                return False

            client["tokens"] -= 1.0

            # Increment active request counter atomically with the checks above
            self._active_requests += 1
            self._total_accepted += 1

        return True

    def release(self):
        """Release a request slot after processing completes."""
        with self._lock:
            self._active_requests = max(0, self._active_requests - 1)

    def reset(self):
        """Emergency reset: clear all active request counters and client buckets.

        Useful after a crash or when slots have been leaked due to bugs.
        """
        with self._lock:
            leaked = self._active_requests
            self._active_requests = 0
            self._clients.clear()
            self._total_rejected = 0
            self._total_accepted = 0
            if leaked:
                logger.warning(
                    "Rate limiter reset: recovered %d leaked slots", leaked
                )

    def get_stats(self) -> Dict[str, Any]:
        """Return rate limiter statistics."""
        with self._lock:
            active_clients = len(self._clients)
            active_requests = self._active_requests

        return {
            "active_clients": active_clients,
            "active_requests": active_requests,
            "global_max_concurrent": self.global_max_concurrent,
            "max_rpm_per_ip": self.max_rpm,
            "burst_size": self.burst_size,
            "total_accepted": self._total_accepted,
            "total_rejected": self._total_rejected,
        }

    def _cleanup_locked(self, now: float):
        """Remove stale client entries (no activity for 5 minutes).

        Must be called while holding self._lock.
        """
        stale_threshold = now - STALE_THRESHOLD_S
        stale_ips = [
            ip for ip, client in self._clients.items()
            if client["last_refill"] < stale_threshold
        ]
        for ip in stale_ips:
            del self._clients[ip]

        if stale_ips:
            logger.debug("Cleaned up %d stale rate limit entries", len(stale_ips))
