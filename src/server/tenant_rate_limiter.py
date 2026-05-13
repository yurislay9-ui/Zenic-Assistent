"""
Tenant-aware rate limiter extending the base RateLimiter.

Adds per-user and per-tenant rate limiting with plan-based quotas.
Uses token bucket algorithm consistently with the base implementation.
Falls back to per-IP limiting for unauthenticated requests.
"""

import time
import threading
import logging
from typing import Any, Dict, Optional

from src.server.rate_limiter import RateLimiter, STALE_THRESHOLD_S
from src.core.auth_parts._tenant_mixin import PLAN_DEFINITIONS

logger = logging.getLogger(__name__)

__all__ = [
    "TenantRateLimiter",
]


class TenantRateLimiter(RateLimiter):
    """Extended rate limiter with per-user and per-tenant quotas.

    Inherits per-IP token bucket from RateLimiter and adds:
    - Per-user request tracking (token bucket per user_id)
    - Per-tenant daily quota enforcement
    - Plan-based limits from PLAN_DEFINITIONS
    - Automatic fallback to per-IP for unauthenticated requests

    Args:
        max_requests_per_minute: Per-IP RPM (fallback for anonymous).
        burst_size: Per-IP burst size.
        global_max_concurrent: Max concurrent requests system-wide.
        default_user_rpm: Default RPM per authenticated user.
        default_user_burst: Default burst per authenticated user.
    """

    def __init__(
        self,
        max_requests_per_minute: int = 30,
        burst_size: int = 10,
        global_max_concurrent: int = 20,
        default_user_rpm: int = 30,
        default_user_burst: int = 10,
        cleanup_interval_s: float = 60.0,
    ) -> None:
        super().__init__(
            max_requests_per_minute=max_requests_per_minute,
            burst_size=burst_size,
            global_max_concurrent=global_max_concurrent,
            cleanup_interval_s=cleanup_interval_s,
        )
        self.default_user_rpm: int = default_user_rpm
        self.default_user_burst: int = default_user_burst

        # Per-user token buckets: {user_id: {"tokens": float, "last_refill": float, "rpm": int, "burst": int}}
        self._users: Dict[int, Dict[str, Any]] = {}

        # Per-tenant minute counters: {tenant_id: {"count": int, "window_start": float}}
        self._tenants: Dict[str, Dict[str, Any]] = {}

    def acquire_user(self, user_id: int, tenant_id: Optional[str] = None) -> bool:
        """Try to acquire a request slot for an authenticated user.

        Checks: global concurrent → per-user token bucket → per-tenant quota.

        Args:
            user_id: Authenticated user ID.
            tenant_id: Optional tenant ID for quota enforcement.

        Returns:
            True if allowed, False if rate limited.
        """
        now = time.time()

        # Periodic cleanup
        if now - self._last_cleanup > self.cleanup_interval_s:
            self._cleanup(now)
            with self._lock:
                self._last_cleanup = now

        with self._lock:
            # 1. Global concurrent limit
            if self._active_requests >= self.global_max_concurrent:
                self._total_rejected += 1
                logger.warning(
                    "Rate limit: global concurrent limit (%d/%d)",
                    self._active_requests, self.global_max_concurrent,
                )
                return False

            # 2. Per-tenant quota (from plan)
            if tenant_id:
                if not self._check_tenant_quota_locked(tenant_id, now):
                    self._total_rejected += 1
                    return False

            # 3. Per-user token bucket
            if user_id not in self._users:
                self._users[user_id] = {
                    "tokens": float(self.default_user_burst),
                    "last_refill": now,
                    "rpm": self.default_user_rpm,
                    "burst": self.default_user_burst,
                }

            user = self._users[user_id]
            elapsed = now - user["last_refill"]
            refill_rate = user["rpm"] / 60.0
            user["tokens"] = min(float(user["burst"]), user["tokens"] + elapsed * refill_rate)
            user["last_refill"] = now

            if user["tokens"] < 1.0:
                self._total_rejected += 1
                logger.warning(
                    "Rate limit: user %d exceeded (%.1f tokens)",
                    user_id, user["tokens"],
                )
                return False

            user["tokens"] -= 1.0
            self._active_requests += 1
            self._total_accepted += 1

        return True

    def release_user(self):
        """Release a user-authenticated request slot. Alias for release()."""
        self.release()

    def acquire(
        self,
        client_ip: str,
        user_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> bool:
        """Unified acquire: uses per-user if authenticated, per-IP otherwise.

        Args:
            client_ip: Client IP address (always available).
            user_id: Authenticated user ID (None if anonymous).
            tenant_id: Tenant ID for quota enforcement.

        Returns:
            True if allowed, False if rate limited.
        """
        if user_id is not None:
            return self.acquire_user(user_id, tenant_id)
        return super().acquire(client_ip)

    def set_user_limits(self, user_id: int, rpm: int, burst: int) -> None:
        """Configure custom rate limits for a specific user.

        Called after auth when the user's plan has custom RPM.
        """
        with self._lock:
            if user_id in self._users:
                self._users[user_id]["rpm"] = rpm
                self._users[user_id]["burst"] = burst
                # Refill to new burst if current tokens exceed new burst
                self._users[user_id]["tokens"] = min(
                    self._users[user_id]["tokens"], float(burst)
                )
            else:
                self._users[user_id] = {
                    "tokens": float(burst),
                    "last_refill": time.time(),
                    "rpm": rpm,
                    "burst": burst,
                }

    def set_tenant_limits(self, tenant_id: str, rpm: int) -> None:
        """Set the per-minute request limit for a tenant.

        Called after auth based on the tenant's plan.
        """
        with self._lock:
            if tenant_id not in self._tenants:
                self._tenants[tenant_id] = {
                    "count": 0,
                    "window_start": time.time(),
                    "rpm": rpm,
                }
            else:
                self._tenants[tenant_id]["rpm"] = rpm

    def _check_tenant_quota_locked(self, tenant_id: str, now: float) -> bool:
        """Check tenant per-minute quota. Must hold self._lock."""
        if tenant_id not in self._tenants:
            return True  # No limits configured yet

        tenant = self._tenants[tenant_id]
        window_start = tenant.get("window_start", now)

        # Reset window if more than 60s elapsed
        if now - window_start >= 60.0:
            tenant["count"] = 0
            tenant["window_start"] = now

        rpm_limit = tenant.get("rpm", 200)
        if tenant["count"] >= rpm_limit:
            logger.warning(
                "Rate limit: tenant %s exceeded RPM (%d/%d)",
                tenant_id, tenant["count"], rpm_limit,
            )
            return False

        tenant["count"] += 1
        return True

    def get_stats(self) -> Dict[str, Any]:
        """Extended stats including user and tenant info."""
        base = super().get_stats()
        with self._lock:
            base["active_users"] = len(self._users)
            base["active_tenants"] = len(self._tenants)
        return base

    def _cleanup(self, now: float) -> None:
        """Clean up stale user and tenant entries, plus parent IP entries.

        The parent RateLimiter exposes ``_cleanup_locked()`` (not ``_cleanup()``),
        so we call that while holding the lock ourselves.
        """
        with self._lock:
            # Clean up parent's stale IP entries (method requires lock held)
            super()._cleanup_locked(now)

            # Stale users (5 min inactive)
            stale_threshold = now - STALE_THRESHOLD_S
            stale_users = [
                uid for uid, u in self._users.items()
                if u["last_refill"] < stale_threshold
            ]
            for uid in stale_users:
                del self._users[uid]

            # Stale tenant windows
            stale_tenants = [
                tid for tid, t in self._tenants.items()
                if t.get("window_start", 0) < now - STALE_THRESHOLD_S
            ]
            for tid in stale_tenants:
                del self._tenants[tid]

            if stale_users or stale_tenants:
                logger.debug(
                    "Cleaned up %d stale user + %d stale tenant rate limit entries",
                    len(stale_users), len(stale_tenants),
                )
