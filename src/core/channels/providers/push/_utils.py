"""
ZENIC-AGENTS — Push Channel Provider: Utility Functions & Constants

Standalone functions, optional-dependency flags, and constants shared
across push provider mixins.
"""

from __future__ import annotations

import base64
import ipaddress
from urllib.parse import urlparse


# ── Optional Dependencies ─────────────────────────────────────

try:
    import aiohttp
    _HAS_AIOHTTP = True
except ImportError:
    _HAS_AIOHTTP = False

try:
    import urllib.request
    import urllib.error
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec, padding, utils
    from cryptography.hazmat.primitives.asymmetric.ec import (
        ECDSA,
        EllipticCurvePrivateKey,
        EllipticCurvePublicNumbers,
        SECP256R1,
    )
    from cryptography.hazmat.backends import default_backend
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False

try:
    import jwt as pyjwt
    _HAS_PYJWT = True
except ImportError:
    _HAS_PYJWT = False


# ── Constants ─────────────────────────────────────────────────

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5  # seconds
_HTTP_TIMEOUT = 30       # seconds
_WEB_PUSH_TTL = 241920   # 28 days in seconds (max TTL for push)
_VAPID_JWT_EXPIRY = 43200  # 12 hours

# FCM HTTP v1 API
_FCM_BASE_URL = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
_FCM_TOKEN_URL = "https://oauth2.googleapis.com/token"
_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# Push notification size limits
_PUSH_PAYLOAD_MAX = 4096  # 4KB max for Web Push
_FCM_PAYLOAD_MAX = 4096   # 4KB max for FCM data message


# ── Utility ───────────────────────────────────────────────────

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


def _base64url_encode(data: bytes) -> str:
    """Encode bytes to base64url without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(s: str) -> bytes:
    """Decode base64url with padding restoration."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def _pem_to_base64url(pem_key: str) -> str:
    """Convert a PEM-encoded EC public key to raw base64url (x || y)."""
    if not _HAS_CRYPTOGRAPHY:
        return pem_key

    try:
        # If it's already base64url, return as-is
        if not pem_key.startswith("-----"):
            return pem_key

        public_key = serialization.load_pem_public_key(
            pem_key.encode("utf-8"), backend=default_backend(),
        )
        numbers = public_key.public_numbers()
        # x and y are 32 bytes each for P-256
        raw = numbers.x.to_bytes(32, "big") + numbers.y.to_bytes(32, "big")
        return _base64url_encode(raw)
    except Exception:
        return pem_key
