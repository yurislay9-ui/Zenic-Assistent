"""
Zenic-Agents Asistente - Defense in Depth Layers 5-6 (Phase 6.2)

Layer 5: ECDSA Licensing — see src/core/license/ for full implementation.
Layer 6: Server-side Secrets — remote verification for 20% of critical logic.

This module provides the server-side secrets verification layer.
It ensures that certain critical operations require validation against
a remote server, preventing full offline cracking.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def _validate_url(url: str, allowed_schemes: tuple = ("http", "https")) -> str:
    """Validate URL to prevent SSRF attacks."""
    parsed = urlparse(url)
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed. Use: {allowed_schemes}")
    if not parsed.hostname:
        raise ValueError("URL must have a hostname")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        pass  # hostname is not an IP, that's OK
    else:
        if ip.is_private or ip.is_loopback or ip.is_reserved:
            raise ValueError(f"Access to internal IPs is not allowed: {parsed.hostname}")
    return url


class SecretType(str, Enum):
    """Types of server-side secrets."""
    LICENSE_VALIDATION = "license_validation"
    FEATURE_UNLOCK = "feature_unlock"
    CONFIG_SIGNATURE = "config_signature"
    ADMIN_ACTION = "admin_action"
    EXPORT_AUTHORIZATION = "export_authorization"


@dataclass
class SecretVerification:
    """Result of a server-side secret verification."""
    secret_type: SecretType
    verified: bool
    server_url: str = ""
    response_time_ms: float = 0.0
    message: str = ""
    expires_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ServerSecretsLayer:
    """Defense in Depth Layer 6: Server-side secrets.

    Ensures that ~20% of the most critical logic requires
    validation against a remote server. This prevents full
    offline cracking of the licensing and security system.

    Critical operations that require server validation:
    - License activation/renewal
    - Feature unlocks for paid plans
    - Admin-level configuration changes
    - Data export authorization
    - Blueprint certification

    When the server is unreachable:
    - Grace period: Operations continue for a configurable time
    - After grace period: System enters Degraded Mode
    - Cache: Last valid verification is cached locally
    """

    def __init__(
        self,
        server_url: str = "",
        grace_period_hours: int = 72,
        cache_duration_hours: int = 24,
        offline_fallback: bool = True,
    ) -> None:
        self._server_url = server_url or os.environ.get("ZENIC_LICENSE_SERVER", "")
        self._grace_period_hours = grace_period_hours
        self._cache_duration_hours = cache_duration_hours
        self._offline_fallback = offline_fallback
        self._verification_cache: Dict[str, SecretVerification] = {}
        self._last_online_time: float = 0.0
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[SecretVerification], None]] = []

    def verify(
        self,
        secret_type: SecretType,
        payload: Dict[str, Any],
        force_online: bool = False,
    ) -> SecretVerification:
        """Verify a secret against the server.

        Args:
            secret_type: Type of secret to verify.
            payload: Verification payload (license_id, feature, etc.).
            force_online: Force online verification even if cache exists.

        Returns:
            SecretVerification with the result.
        """
        cache_key = self._cache_key(secret_type, payload)

        # Check cache first
        if not force_online:
            cached = self._verification_cache.get(cache_key)
            if cached and cached.expires_at and cached.expires_at > time.time():
                return cached

        # Attempt online verification
        if self._server_url:
            result = self._verify_online(secret_type, payload)
            if result.verified:
                with self._lock:
                    self._verification_cache[cache_key] = result
                    self._last_online_time = time.time()
                self._notify_callbacks(result)
                return result

        # Offline fallback
        if self._offline_fallback:
            return self._verify_offline_fallback(secret_type, payload)

        return SecretVerification(
            secret_type=secret_type,
            verified=False,
            message="Server unreachable and offline fallback disabled",
        )

    def _verify_online(
        self, secret_type: SecretType, payload: Dict[str, Any],
    ) -> SecretVerification:
        """Perform online verification against the license server.

        Makes an HTTP POST to the server with the verification payload.
        The server validates the request and returns a signed response.
        """
        start = time.time()
        try:
            import urllib.request
            import urllib.error

            url = _validate_url(f"{self._server_url}/api/v1/verify/{secret_type.value}")
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode())
                elapsed_ms = (time.time() - start) * 1000

                verified = body.get("verified", False)
                result = SecretVerification(
                    secret_type=secret_type,
                    verified=verified,
                    server_url=self._server_url,
                    response_time_ms=elapsed_ms,
                    message=body.get("message", "Verified" if verified else "Rejected"),
                    expires_at=time.time() + (self._cache_duration_hours * 3600),
                    metadata=body.get("metadata", {}),
                )
                return result

        except urllib.error.URLError as exc:
            elapsed_ms = (time.time() - start) * 1000
            logger.warning("ServerSecrets: Online verification failed: %s", exc)
            return SecretVerification(
                secret_type=secret_type,
                verified=False,
                server_url=self._server_url,
                response_time_ms=elapsed_ms,
                message=f"Server unreachable: {exc}",
            )
        except Exception as exc:
            return SecretVerification(
                secret_type=secret_type,
                verified=False,
                message=f"Verification error: {exc}",
            )

    def _verify_offline_fallback(
        self, secret_type: SecretType, payload: Dict[str, Any],
    ) -> SecretVerification:
        """Provide offline verification fallback.

        Uses cached verifications and grace period logic.
        If within grace period since last successful online check,
        operations continue with a warning.
        """
        hours_since_online = (time.time() - self._last_online_time) / 3600

        if hours_since_online <= self._grace_period_hours:
            # Within grace period — allow with warning
            return SecretVerification(
                secret_type=secret_type,
                verified=True,
                message=f"Offline fallback (within {self._grace_period_hours}h grace period)",
                expires_at=self._last_online_time + (self._grace_period_hours * 3600),
                metadata={"offline": True, "hours_since_online": round(hours_since_online, 1)},
            )

        # Grace period exceeded
        return SecretVerification(
            secret_type=secret_type,
            verified=False,
            message=f"Grace period exceeded ({hours_since_online:.1f}h > {self._grace_period_hours}h)",
            metadata={"offline": True, "hours_since_online": round(hours_since_online, 1)},
        )

    def is_within_grace_period(self) -> bool:
        """Check if we're within the grace period for offline operation."""
        if self._last_online_time == 0:
            return False  # Never connected
        hours_since = (time.time() - self._last_online_time) / 3600
        return hours_since <= self._grace_period_hours

    def get_last_online_time(self) -> Optional[float]:
        """Get the timestamp of the last successful online verification."""
        return self._last_online_time if self._last_online_time > 0 else None

    # ── Callbacks ──────────────────────────────────────────

    def on_verification(self, callback: Callable[[SecretVerification], None]) -> None:
        """Register a callback for verification events."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, result: SecretVerification) -> None:
        """Notify all registered callbacks."""
        for cb in self._callbacks:
            try:
                cb(result)
            except Exception as exc:
                logger.warning("ServerSecrets: Callback error: %s", exc)

    # ── Helpers ────────────────────────────────────────────

    @staticmethod
    def _cache_key(secret_type: SecretType, payload: Dict[str, Any]) -> str:
        """Generate a cache key for a verification request."""
        payload_str = json.dumps(payload, sort_keys=True)
        hash_val = hashlib.sha256(payload_str.encode()).hexdigest()[:12]
        return f"{secret_type.value}:{hash_val}"

    def get_status(self) -> Dict[str, Any]:
        """Get current server secrets status."""
        return {
            "server_url": self._server_url or "not configured",
            "grace_period_hours": self._grace_period_hours,
            "cache_duration_hours": self._cache_duration_hours,
            "offline_fallback": self._offline_fallback,
            "last_online": self._last_online_time,
            "within_grace_period": self.is_within_grace_period(),
            "cached_verifications": len(self._verification_cache),
        }


# ── Singleton ─────────────────────────────────────────────

_server_secrets: Optional[ServerSecretsLayer] = None
_lock = threading.Lock()


def get_server_secrets(**kwargs: Any) -> ServerSecretsLayer:
    """Get or create the global ServerSecretsLayer instance."""
    global _server_secrets
    with _lock:
        if _server_secrets is None:
            _server_secrets = ServerSecretsLayer(**kwargs)
        return _server_secrets


def reset_server_secrets() -> None:
    """Reset the global ServerSecretsLayer (for testing)."""
    global _server_secrets
    _server_secrets = None
