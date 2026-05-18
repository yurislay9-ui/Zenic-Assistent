"""
ZENIC-AGENTS — Push Notifications Channel Provider

Outbound: Web Push (VAPID) and Firebase Cloud Messaging (FCM HTTP v1)

Supports:
  - Web Push API (VAPID): Browser push notifications
  - Firebase Cloud Messaging (FCM): Mobile push notifications via HTTP v1 API
  - In-memory subscription storage (extensible to SQLite)
  - VAPID JWT generation with ES256 (requires `cryptography` package)
  - FCM OAuth2 via self-signed JWT (requires `cryptography` package)
  - Rate limit tracking from response headers
  - Retry with exponential backoff
  - Dry-run mode when no backends configured

Configuration (env vars or constructor):
  - VAPID_PRIVATE_KEY:   ECDSA P-256 private key (PEM or base64)
  - VAPID_PUBLIC_KEY:    ECDSA P-256 public key (base64url)
  - VAPID_SUBJECT:       Contact URI (mailto: or https:)
  - FCM_PROJECT_ID:              Firebase project ID
  - FCM_SERVICE_ACCOUNT_KEY:     Path to service account JSON key file

Recipient routing:
  - recipient starts with 'fcm:'       -> Firebase Cloud Messaging
  - recipient starts with 'webpush:'   -> Web Push
  - Otherwise                          -> try both backends if configured

Design invariants:
  1. Never raises — always returns ChannelResponse.
  2. Uses aiohttp when available, falls back to urllib.
  3. Dry-run mode when unconfigured (logs messages).
  4. All HTTP errors are caught and wrapped.
  5. Thread-safe stats.
  6. VAPID/FCM signing requires `cryptography` package — dry-run otherwise.
"""

from __future__ import annotations

import base64
import ipaddress
import json
import logging
import os
import threading
import time
from typing import Any, Dict, FrozenSet, List, Optional, Set
from urllib.parse import urlparse

from .._formatter import MessageFormatter, truncate, sanitize_plain_text
from .._protocol import ChannelProvider
from .._types import (
    ChannelCapability,
    ChannelMessage,
    ChannelResponse,
    ConfirmationRequest,
    DeliveryStatus,
    RateLimitInfo,
)

logger = logging.getLogger("zenic_agents.channels.push")


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


class PushChannelProvider:
    """Push Notifications channel provider.

    Supports two backends:
      1. Web Push API (VAPID) — browser push notifications
      2. Firebase Cloud Messaging (FCM) — mobile push notifications

    Routing is based on recipient format:
      - 'fcm:<token>'           -> FCM to a specific device token
      - 'fcm:topic:<name>'     -> FCM to a topic
      - 'fcm:condition:<expr>' -> FCM to a condition
      - 'webpush:<user_id>'    -> Web Push to a registered subscription
      - Otherwise              -> try both if configured

    Dry-run mode when no backends are configured.
    """

    def __init__(
        self,
        vapid_private_key: Optional[str] = None,
        vapid_public_key: Optional[str] = None,
        vapid_subject: Optional[str] = None,
        fcm_project_id: Optional[str] = None,
        fcm_service_account_key_path: Optional[str] = None,
    ) -> None:
        # Web Push (VAPID) configuration
        self._vapid_private_key = vapid_private_key or os.environ.get("VAPID_PRIVATE_KEY", "")
        self._vapid_public_key = vapid_public_key or os.environ.get("VAPID_PUBLIC_KEY", "")
        self._vapid_subject = vapid_subject or os.environ.get("VAPID_SUBJECT", "")

        # FCM configuration
        self._fcm_project_id = fcm_project_id or os.environ.get("FCM_PROJECT_ID", "")
        self._fcm_service_account_key_path = (
            fcm_service_account_key_path
            or os.environ.get("FCM_SERVICE_ACCOUNT_KEY", "")
        )

        # Loaded FCM service account data (lazy)
        self._fcm_service_account_data: Optional[Dict[str, str]] = None
        self._fcm_access_token: str = ""
        self._fcm_token_expiry: float = 0.0

        # Web Push subscription storage (user_id -> subscription JSON)
        self._subscriptions: Dict[str, Dict[str, Any]] = {}
        self._sub_lock = threading.Lock()

        # VAPID private key object (lazy)
        self._vapid_private_key_obj: Optional[Any] = None

        # Stats
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._webpush_sent: int = 0
        self._fcm_sent: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()

        # HTTP session
        self._session: Optional[Any] = None  # aiohttp.ClientSession

    # ── ChannelProvider Protocol ────────────────────────────────

    @property
    def name(self) -> str:
        return "push"

    @property
    def capabilities(self) -> FrozenSet[ChannelCapability]:
        return frozenset({
            ChannelCapability.SEND_TEXT,
            ChannelCapability.SEND_RICH,
            ChannelCapability.SEND_PUSH,
            ChannelCapability.SEND_CONFIRMATION,
        })

    @property
    def is_available(self) -> bool:
        """Available if at least one backend is configured."""
        return self._has_web_push or self._has_fcm

    @property
    def _has_web_push(self) -> bool:
        """Whether Web Push (VAPID) is fully configured."""
        return bool(
            self._vapid_private_key
            and self._vapid_public_key
            and self._vapid_subject
        )

    @property
    def _has_fcm(self) -> bool:
        """Whether FCM is fully configured."""
        return bool(self._fcm_project_id and self._fcm_service_account_key_path)

    async def send(self, message: ChannelMessage) -> ChannelResponse:
        """Send a push notification.

        Routes to Web Push or FCM based on recipient format:
          - recipient starts with 'fcm:'       -> Firebase Cloud Messaging
          - recipient starts with 'webpush:'   -> Web Push
          - Otherwise                          -> try both if configured

        Args:
            message: Universal message envelope.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self.is_available:
            return self._dry_run_send(message)

        recipient = message.recipient or ""

        # Route based on recipient prefix
        if recipient.startswith("fcm:"):
            return await self._send_via_fcm(message, recipient[4:])
        elif recipient.startswith("webpush:"):
            user_id = recipient[8:]
            return await self._send_via_web_push(message, user_id)

        # No prefix — try both backends, return first success
        # Prefer FCM for mobile, then Web Push for browser
        responses: List[ChannelResponse] = []

        if self._has_fcm:
            fcm_resp = await self._send_via_fcm(message, recipient)
            if fcm_resp.success:
                return fcm_resp
            responses.append(fcm_resp)

        if self._has_web_push:
            wp_resp = await self._send_via_web_push(message, recipient)
            if wp_resp.success:
                return wp_resp
            responses.append(wp_resp)

        # Both failed or neither configured
        if responses:
            return responses[-1]

        return self._dry_run_send(message)

    async def send_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Send confirmation as push notification with action options.

        The confirmation is formatted as a push notification where the
        options are included in the data payload for the client to
        render as action buttons.

        Args:
            request: Confirmation request with options.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self.is_available:
            return self._dry_run_confirmation(request)

        # Build notification body with options
        option_labels = {
            "yes": "Confirm",
            "no": "Deny",
            "more_info": "More Info",
        }
        options_text = " | ".join(
            option_labels.get(o, o.replace("_", " ").title())
            for o in request.options
        )

        body = request.message
        if options_text:
            body = f"{body}\n\nActions: {options_text}" if body else f"Actions: {options_text}"

        # Build data payload with confirmation metadata
        data: Dict[str, Any] = {
            "type": "confirmation",
            "action_id": request.action_id,
            "action_type": request.action_type,
            "options": list(request.options),
            "timeout_seconds": request.timeout_seconds,
        }

        message = ChannelMessage(
            text=body,
            title=request.title or "Confirmation Required",
            recipient=request.recipient,
            metadata={
                **request.metadata,
                **data,
                "is_confirmation": True,
            },
        )

        response = await self.send(message)

        with self._lock:
            self._confirmation_count += 1

        return response

    async def start(self) -> None:
        """Initialize the provider (create HTTP session, load keys)."""
        if self._started:
            return

        if _HAS_AIOHTTP and not self._session:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=_HTTP_TIMEOUT),
            )

        # Pre-load VAPID private key
        if self._has_web_push and _HAS_CRYPTOGRAPHY:
            self._load_vapid_private_key()

        # Pre-load FCM service account data
        if self._has_fcm:
            self._load_fcm_service_account()

        self._started = True
        logger.info(
            "PushChannelProvider: started (webpush=%s, fcm=%s)",
            self._has_web_push,
            self._has_fcm,
        )

    async def stop(self) -> None:
        """Gracefully shut down the provider."""
        if self._session and _HAS_AIOHTTP:
            await self._session.close()
            self._session = None

        self._started = False
        logger.info("PushChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics."""
        with self._lock:
            return {
                "name": "push",
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "webpush_sent": self._webpush_sent,
                "fcm_sent": self._fcm_sent,
                "is_available": self.is_available,
                "has_web_push": self._has_web_push,
                "has_fcm": self._has_fcm,
                "subscription_count": len(self._subscriptions),
                "started": self._started,
            }

    @property
    def rate_limit_info(self) -> RateLimitInfo:
        """Current rate limit status."""
        return self._rate_limit_info

    # ── Web Push Subscription Management ────────────────────────

    def register_subscription(
        self, user_id: str, subscription: Dict[str, Any],
    ) -> None:
        """Register a Web Push subscription for a user.

        Args:
            user_id: Unique identifier for the user.
            subscription: PushSubscription JSON object with keys:
                          - endpoint: Push server URL
                          - keys.p256dh: ECDH public key (base64url)
                          - keys.auth: Authentication secret (base64url)
        """
        with self._sub_lock:
            self._subscriptions[user_id] = subscription

        logger.debug(
            "PushChannelProvider: registered subscription for user '%s' "
            "(endpoint=%s)",
            user_id,
            subscription.get("endpoint", "N/A")[:60],
        )

    def unregister_subscription(self, user_id: str) -> bool:
        """Remove a Web Push subscription.

        Args:
            user_id: User identifier to remove.

        Returns:
            True if a subscription was removed, False if not found.
        """
        with self._sub_lock:
            removed = user_id in self._subscriptions
            self._subscriptions.pop(user_id, None)

        if removed:
            logger.debug(
                "PushChannelProvider: unregistered subscription for user '%s'",
                user_id,
            )
        return removed

    def get_subscription(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a Web Push subscription for a user.

        Args:
            user_id: User identifier.

        Returns:
            Subscription dict or None if not found.
        """
        with self._sub_lock:
            return self._subscriptions.get(user_id)

    # ── FCM Public Methods ──────────────────────────────────────

    async def send_fcm(
        self,
        token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ChannelResponse:
        """Send an FCM push notification to a specific device token.

        Args:
            token: FCM device registration token.
            title: Notification title.
            body: Notification body text.
            data: Optional data payload.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self._has_fcm:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.DRY_RUN,
                error="FCM not configured",
                timestamp=time.time(),
            )

        message_payload: Dict[str, Any] = {"token": token}

        # Add notification
        notification: Dict[str, str] = {}
        if title:
            notification["title"] = title
        if body:
            notification["body"] = body
        if notification:
            message_payload["notification"] = notification

        # Add data
        if data:
            message_payload["data"] = {
                str(k): str(v) if not isinstance(v, str) else v
                for k, v in data.items()
            }

        return await self._post_fcm({"message": message_payload})

    async def send_fcm_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ChannelResponse:
        """Send an FCM push notification to a topic.

        Args:
            topic: FCM topic name.
            title: Notification title.
            body: Notification body text.
            data: Optional data payload.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self._has_fcm:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.DRY_RUN,
                error="FCM not configured",
                timestamp=time.time(),
            )

        message_payload: Dict[str, Any] = {"topic": topic}

        notification: Dict[str, str] = {}
        if title:
            notification["title"] = title
        if body:
            notification["body"] = body
        if notification:
            message_payload["notification"] = notification

        if data:
            message_payload["data"] = {
                str(k): str(v) if not isinstance(v, str) else v
                for k, v in data.items()
            }

        return await self._post_fcm({"message": message_payload})

    # ── Web Push Public Methods ─────────────────────────────────

    async def send_web_push(
        self,
        user_id: str,
        payload: Dict[str, Any],
    ) -> ChannelResponse:
        """Send a Web Push notification to a registered user.

        Args:
            user_id: User identifier with a registered subscription.
            payload: Push notification payload dict (will be JSON-serialized).

        Returns:
            ChannelResponse with delivery result.
        """
        if not self._has_web_push:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.DRY_RUN,
                error="Web Push not configured",
                timestamp=time.time(),
            )

        subscription = self.get_subscription(user_id)
        if not subscription:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.FAILED,
                error=f"No Web Push subscription found for user '{user_id}'",
                timestamp=time.time(),
            )

        return await self._post_web_push(subscription, payload)

    # ── VAPID ───────────────────────────────────────────────────

    def _generate_vapid_jwt(self, aud: str) -> Optional[str]:
        """Generate a VAPID JWT token for Web Push authentication.

        The JWT uses ES256 algorithm:
          Header: {"typ":"JWT","alg":"ES256"}
          Payload: {"aud":<audience>,"exp":<now+43200>,"sub":<subject>}

        Requires the `cryptography` package for ECDSA signing.
        Falls back to PyJWT if available.

        Args:
            aud: Audience (origin of the push service endpoint).

        Returns:
            Signed JWT string, or None if signing is unavailable.
        """
        if not self._vapid_private_key or not self._vapid_subject:
            logger.warning("PushChannelProvider: VAPID keys not configured")
            return None

        now = int(time.time())

        header = {"typ": "JWT", "alg": "ES256"}
        payload = {
            "aud": aud,
            "exp": now + _VAPID_JWT_EXPIRY,
            "sub": self._vapid_subject,
        }

        # Try PyJWT first (simplest path)
        if _HAS_PYJWT:
            try:
                import jwt as pyjwt_mod
                encoded = pyjwt_mod.encode(
                    payload,
                    self._vapid_private_key,
                    algorithm="ES256",
                    headers=header,
                )
                return encoded
            except Exception as e:
                logger.debug(
                    "PushChannelProvider: PyJWT encoding failed: %s", e,
                )

        # Manual JWT with cryptography package
        if _HAS_CRYPTOGRAPHY:
            try:
                return self._sign_vapid_jwt_manual(header, payload)
            except Exception as e:
                logger.warning(
                    "PushChannelProvider: manual VAPID JWT signing failed: %s",
                    e,
                )
                return None

        logger.warning(
            "PushChannelProvider: no crypto library available for VAPID JWT "
            "signing (install `cryptography` or `PyJWT`)"
        )
        return None

    def _sign_vapid_jwt_manual(
        self, header: Dict[str, Any], payload: Dict[str, Any],
    ) -> str:
        """Manually sign a VAPID JWT using the cryptography package.

        Args:
            header: JWT header dict.
            payload: JWT payload dict.

        Returns:
            Signed JWT string.
        """
        # Load private key if not cached
        if self._vapid_private_key_obj is None:
            self._load_vapid_private_key()

        if self._vapid_private_key_obj is None:
            raise RuntimeError("Failed to load VAPID private key")

        # Encode header and payload
        header_b64 = _base64url_encode(
            json.dumps(header, separators=(",", ":")).encode("utf-8"),
        )
        payload_b64 = _base64url_encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        )

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

        # Sign with ECDSA P-256 + SHA-256
        private_key: EllipticCurvePrivateKey = self._vapid_private_key_obj
        signature_bytes = private_key.sign(
            signing_input,
            ECDSA(hashes.SHA256()),
        )

        # DER-encoded signature -> raw (r || s) for JWT
        signature_raw = self._der_to_raw_signature(signature_bytes)
        signature_b64 = _base64url_encode(signature_raw)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    @staticmethod
    def _der_to_raw_signature(der_sig: bytes) -> bytes:
        """Convert a DER-encoded ECDSA signature to raw (r || s) format.

        Each of r and s is padded to 32 bytes for P-256.
        """
        # Parse DER: 0x30 <len> 0x02 <rlen> <r> 0x02 <slen> <s>
        idx = 2  # Skip 0x30 and length byte
        if der_sig[0] != 0x30:
            # Fallback: just return as-is
            return der_sig

        # Read r
        if der_sig[idx] != 0x02:
            return der_sig
        idx += 1
        r_len = der_sig[idx]
        idx += 1
        r_bytes = der_sig[idx : idx + r_len]
        idx += r_len

        # Read s
        if der_sig[idx] != 0x02:
            return der_sig
        idx += 1
        s_len = der_sig[idx]
        idx += 1
        s_bytes = der_sig[idx : idx + s_len]

        # Strip leading zero padding (DER adds 0x00 if high bit is set)
        if r_bytes[0] == 0 and len(r_bytes) > 32:
            r_bytes = r_bytes[1:]
        if s_bytes[0] == 0 and len(s_bytes) > 32:
            s_bytes = s_bytes[1:]

        # Pad to 32 bytes each
        r_padded = r_bytes.rjust(32, b"\x00")
        s_padded = s_bytes.rjust(32, b"\x00")

        return r_padded + s_padded

    def _load_vapid_private_key(self) -> None:
        """Load the VAPID ECDSA P-256 private key."""
        if not _HAS_CRYPTOGRAPHY:
            return

        try:
            key_str = self._vapid_private_key.strip()

            if key_str.startswith("-----"):
                # PEM format
                self._vapid_private_key_obj = serialization.load_pem_private_key(
                    key_str.encode("utf-8"),
                    password=None,
                    backend=default_backend(),
                )
            else:
                # Assume base64url-encoded raw private key
                # For P-256, raw key is 32 bytes
                try:
                    raw_bytes = _base64url_decode(key_str)
                    if len(raw_bytes) == 32:
                        # Convert raw private key to object
                        private_number = int.from_bytes(raw_bytes, "big")
                        self._vapid_private_key_obj = ec.derive_private_key(
                            private_number, SECP256R1(), default_backend(),
                        )
                    else:
                        logger.warning(
                            "PushChannelProvider: VAPID private key is %d "
                            "bytes (expected 32 for P-256)",
                            len(raw_bytes),
                        )
                except Exception:
                    # Try as DER
                    self._vapid_private_key_obj = serialization.load_der_private_key(
                        key_str.encode("utf-8") if not key_str.startswith("MII") else base64.b64decode(key_str),
                        password=None,
                        backend=default_backend(),
                    )
        except Exception as e:
            logger.warning(
                "PushChannelProvider: failed to load VAPID private key: %s", e,
            )
            self._vapid_private_key_obj = None

    def _get_vapid_headers(self, endpoint: str) -> Dict[str, str]:
        """Generate VAPID authentication headers for a push endpoint.

        Args:
            endpoint: The push subscription endpoint URL.

        Returns:
            Dict with Authorization and Crypto-Key headers.
        """
        # Extract origin from endpoint for audience
        try:
            if "://" in endpoint:
                parts = endpoint.split("://", 1)
                host = parts[1].split("/", 1)[0]
                aud = f"{parts[0]}://{host}"
            else:
                aud = endpoint
        except Exception:
            aud = endpoint

        jwt_token = self._generate_vapid_jwt(aud)
        if not jwt_token:
            return {}

        # Get the public key in base64url
        public_key_b64 = _pem_to_base64url(self._vapid_public_key)

        return {
            "Authorization": f"vapid t={jwt_token}, k={public_key_b64}",
            "Crypto-Key": f"p256ecdsa={public_key_b64}",
        }

    # ── FCM Authentication ──────────────────────────────────────

    def _load_fcm_service_account(self) -> None:
        """Load FCM service account key from JSON file."""
        if not self._fcm_service_account_key_path:
            return

        try:
            path = os.path.expanduser(self._fcm_service_account_key_path)
            with open(path, "r", encoding="utf-8") as f:
                self._fcm_service_account_data = json.load(f)

            logger.debug(
                "PushChannelProvider: loaded FCM service account "
                "(client_email=%s)",
                self._fcm_service_account_data.get("client_email", "N/A"),
            )
        except Exception as e:
            logger.warning(
                "PushChannelProvider: failed to load FCM service account "
                "key from '%s': %s",
                self._fcm_service_account_key_path,
                e,
            )
            self._fcm_service_account_data = None

    async def _get_fcm_access_token(self) -> Optional[str]:
        """Get a valid FCM OAuth2 access token.

        Uses self-signed JWT with RS256 if `cryptography` is available.
        Falls back to PyJWT if available.
        Caches the token until near expiry.

        Returns:
            Access token string, or None if unavailable.
        """
        # Return cached token if still valid (with 60s buffer)
        if self._fcm_access_token and time.time() < self._fcm_token_expiry - 60:
            return self._fcm_access_token

        if not self._fcm_service_account_data:
            self._load_fcm_service_account()

        if not self._fcm_service_account_data:
            logger.warning("PushChannelProvider: FCM service account not loaded")
            return None

        # Try to get access token via self-signed JWT
        try:
            return await self._fetch_fcm_access_token()
        except Exception as e:
            logger.warning(
                "PushChannelProvider: failed to get FCM access token: %s", e,
            )
            return None

    async def _fetch_fcm_access_token(self) -> Optional[str]:
        """Fetch a new FCM OAuth2 access token using self-signed JWT.

        Returns:
            Access token string, or None if unavailable.
        """
        sa_data = self._fcm_service_account_data
        if not sa_data:
            return None

        client_email = sa_data.get("client_email", "")
        private_key = sa_data.get("private_key", "")
        token_uri = sa_data.get("token_uri", _FCM_TOKEN_URL)

        if not client_email or not private_key:
            logger.warning(
                "PushChannelProvider: FCM service account missing "
                "client_email or private_key"
            )
            return None

        now = int(time.time())

        # Build the JWT claim
        claim = {
            "iss": client_email,
            "scope": _FCM_SCOPE,
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }

        # Sign the JWT
        jwt_token: Optional[str] = None

        # Try PyJWT first
        if _HAS_PYJWT:
            try:
                import jwt as pyjwt_mod
                jwt_token = pyjwt_mod.encode(
                    claim, private_key, algorithm="RS256",
                )
            except Exception as e:
                logger.debug(
                    "PushChannelProvider: PyJWT RS256 encoding failed: %s", e,
                )

        # Manual JWT with cryptography
        if jwt_token is None and _HAS_CRYPTOGRAPHY:
            try:
                jwt_token = self._sign_rs256_jwt(claim, private_key)
            except Exception as e:
                logger.debug(
                    "PushChannelProvider: manual RS256 JWT signing failed: %s",
                    e,
                )

        if jwt_token is None:
            logger.warning(
                "PushChannelProvider: no crypto library available for "
                "RS256 JWT signing"
            )
            return None

        # Exchange JWT for access token
        post_data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": jwt_token,
        }

        response = await self._http_post_form(token_uri, post_data)

        if response and response.get("success"):
            body = response.get("body", {})
            self._fcm_access_token = body.get("access_token", "")
            expires_in = body.get("expires_in", 3600)
            self._fcm_token_expiry = time.time() + expires_in
            return self._fcm_access_token

        logger.warning(
            "PushChannelProvider: FCM token exchange failed: %s",
            response,
        )
        return None

    def _sign_rs256_jwt(
        self, claim: Dict[str, Any], private_key_pem: str,
    ) -> str:
        """Sign a JWT with RS256 using the cryptography package.

        Args:
            claim: JWT payload dict.
            private_key_pem: PEM-encoded RSA private key.

        Returns:
            Signed JWT string.
        """
        from cryptography.hazmat.primitives.asymmetric import rsa

        header = {"alg": "RS256", "typ": "JWT"}
        header_b64 = _base64url_encode(
            json.dumps(header, separators=(",", ":")).encode("utf-8"),
        )
        payload_b64 = _base64url_encode(
            json.dumps(claim, separators=(",", ":")).encode("utf-8"),
        )

        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

        # Load private key
        key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"),
            password=None,
            backend=default_backend(),
        )

        # Sign with RSASSA-PKCS1-v1_5 + SHA-256
        if not isinstance(key, rsa.RSAPrivateKey):
            raise TypeError("Expected RSA private key for RS256 signing")

        signature = key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

        signature_b64 = _base64url_encode(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    # ── Internal: Routing ───────────────────────────────────────

    async def _send_via_fcm(
        self, message: ChannelMessage, target: str,
    ) -> ChannelResponse:
        """Send via FCM based on target format.

        Args:
            message: Universal message envelope.
            target: FCM target (token, 'topic:<name>', or 'condition:<expr>').

        Returns:
            ChannelResponse with delivery result.
        """
        if not self._has_fcm:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.DRY_RUN,
                error="FCM not configured",
                timestamp=time.time(),
            )

        # Build FCM message
        title = message.title or message.subject or ""
        body = sanitize_plain_text(message.text) if message.text else ""

        fcm_message: Dict[str, Any] = {}

        # Determine target type
        if target.startswith("topic:"):
            fcm_message["topic"] = target[6:]
        elif target.startswith("condition:"):
            fcm_message["condition"] = target[10:]
        else:
            fcm_message["token"] = target

        # Add notification
        notification: Dict[str, str] = {}
        if title:
            notification["title"] = truncate(title, 200)
        if body:
            notification["body"] = truncate(body, 4000)
        if message.image_url:
            notification["image"] = message.image_url
        if notification:
            fcm_message["notification"] = notification

        # Add FCM-specific options
        fcm_options: Dict[str, Any] = {}
        if message.metadata.get("fcm_android"):
            fcm_options["android"] = message.metadata["fcm_android"]
        if message.metadata.get("fcm_apns"):
            fcm_options["apns"] = message.metadata["fcm_apns"]
        if message.metadata.get("fcm_webpush"):
            fcm_options["webpush"] = message.metadata["fcm_webpush"]
        fcm_message.update(fcm_options)

        # Add data payload
        data: Dict[str, str] = {}
        if message.metadata:
            for k, v in message.metadata.items():
                if k.startswith("fcm_"):
                    continue  # Skip FCM-specific options already handled
                data[k] = str(v) if not isinstance(v, str) else v
        if message.fields:
            for field in message.fields:
                key = field.get("title", field.get("name", ""))
                val = field.get("value", "")
                if key:
                    data[key] = val
        if data:
            fcm_message["data"] = data

        payload = {"message": fcm_message}

        response = await self._post_fcm(payload)

        with self._lock:
            if response.success:
                self._sent_count += 1
                self._fcm_sent += 1
            else:
                self._failed_count += 1

        return response

    async def _send_via_web_push(
        self, message: ChannelMessage, user_id: str,
    ) -> ChannelResponse:
        """Send via Web Push.

        Args:
            message: Universal message envelope.
            user_id: User identifier or subscription lookup key.

        Returns:
            ChannelResponse with delivery result.
        """
        if not self._has_web_push:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.DRY_RUN,
                error="Web Push not configured",
                timestamp=time.time(),
            )

        # Look up subscription
        subscription = self.get_subscription(user_id)
        if not subscription:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.FAILED,
                error=f"No Web Push subscription found for user '{user_id}'",
                timestamp=time.time(),
            )

        # Build push payload
        title = message.title or message.subject or ""
        body = sanitize_plain_text(message.text) if message.text else ""

        push_payload: Dict[str, Any] = {
            "title": title,
            "body": body,
        }

        if message.image_url:
            push_payload["icon"] = message.image_url
        if message.metadata:
            push_payload["data"] = {
                k: v for k, v in message.metadata.items()
                if not k.startswith("fcm_")
            }
        if message.fields:
            push_payload["data"] = push_payload.get("data", {})
            push_payload["data"]["fields"] = [
                {k: v for k, v in f.items()} for f in message.fields
            ]

        # Check payload size
        payload_json = json.dumps(push_payload, separators=(",", ":"))
        if len(payload_json) > _PUSH_PAYLOAD_MAX:
            # Truncate body to fit
            max_body = _PUSH_PAYLOAD_MAX - len(json.dumps(
                {k: v for k, v in push_payload.items() if k != "body"},
                separators=(",", ":"),
            )) - 10  # overhead for "body":""
            push_payload["body"] = truncate(body, max_body)
            payload_json = json.dumps(push_payload, separators=(",", ":"))

        response = await self._post_web_push(subscription, push_payload)

        with self._lock:
            if response.success:
                self._sent_count += 1
                self._webpush_sent += 1
            else:
                self._failed_count += 1

        return response

    # ── Internal: HTTP ──────────────────────────────────────────

    async def _post_fcm(
        self, payload: Dict[str, Any],
    ) -> ChannelResponse:
        """POST a message to the FCM HTTP v1 API.

        Args:
            payload: FCM message payload.

        Returns:
            ChannelResponse with delivery result.
        """
        access_token = await self._get_fcm_access_token()
        if not access_token:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.FAILED,
                error="Failed to obtain FCM access token",
                timestamp=time.time(),
            )

        url = _FCM_BASE_URL.format(project_id=self._fcm_project_id)
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_fcm_aiohttp(url, data, headers)
                elif _HAS_URLLIB:
                    return await self._post_fcm_urllib(url, data, headers)
                else:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "PushChannelProvider: FCM attempt %d/%d failed: %s "
                        "— retrying in %.1fs",
                        attempt, _MAX_RETRIES, e, delay,
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "PushChannelProvider: FCM all %d attempts failed: %s",
                        _MAX_RETRIES, e,
                    )
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error=f"FCM HTTP error after {_MAX_RETRIES} attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.FAILED,
            error="Unexpected FCM retry loop exit",
            timestamp=time.time(),
        )

    async def _post_fcm_aiohttp(
        self, url: str, data: bytes, headers: Dict[str, str],
    ) -> ChannelResponse:
        """Send FCM message via aiohttp."""
        assert self._session is not None

        async with self._session.post(url, data=data, headers=headers) as resp:
            body = await resp.text()

            # Track rate limits
            self._update_rate_limit_from_headers(resp.headers)

            if resp.status == 200:
                try:
                    resp_data = json.loads(body)
                except json.JSONDecodeError:
                    resp_data = {}

                msg_name = resp_data.get("name", "")

                return ChannelResponse(
                    success=True,
                    channel="push",
                    message_id=msg_name,
                    status=DeliveryStatus.SENT,
                    metadata={
                        "backend": "fcm",
                        "http_status": resp.status,
                        "message_name": msg_name,
                    },
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                retry_after = float(
                    resp.headers.get("Retry-After", "5"),
                )
                self._rate_limit_info = RateLimitInfo(
                    remaining=0,
                    reset_at=time.time() + retry_after,
                )
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"FCM rate limited. Retry after {retry_after}s",
                    timestamp=time.time(),
                )
            else:
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"FCM HTTP {resp.status}: {body[:300]}",
                    metadata={"backend": "fcm", "http_status": resp.status},
                    timestamp=time.time(),
                )

    async def _post_fcm_urllib(
        self, url: str, data: bytes, headers: Dict[str, str],
    ) -> ChannelResponse:
        """Send FCM message via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio

        validated_url = _validate_url(url)

        def _sync_post() -> ChannelResponse:
            req = urllib.request.Request(
                validated_url, data=data, headers=headers, method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    try:
                        resp_data = json.loads(body)
                    except json.JSONDecodeError:
                        resp_data = {}

                    msg_name = resp_data.get("name", "")
                    return ChannelResponse(
                        success=True,
                        channel="push",
                        message_id=msg_name,
                        status=DeliveryStatus.SENT,
                        metadata={
                            "backend": "fcm",
                            "http_status": resp.status,
                            "message_name": msg_name,
                        },
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:300]
                if e.code == 429:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.RATE_LIMITED,
                        error="FCM rate limited",
                        timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"FCM HTTP {e.code}: {body}",
                    metadata={"backend": "fcm", "http_status": e.code},
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"FCM urllib error: {e}",
                    timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)

    async def _post_web_push(
        self,
        subscription: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> ChannelResponse:
        """POST an encrypted push message to a subscription endpoint.

        Args:
            subscription: PushSubscription object with endpoint and keys.
            payload: Notification payload dict.

        Returns:
            ChannelResponse with delivery result.
        """
        endpoint = subscription.get("endpoint", "")
        if not endpoint:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.FAILED,
                error="Web Push subscription missing endpoint",
                timestamp=time.time(),
            )

        # Get VAPID headers
        vapid_headers = self._get_vapid_headers(endpoint)
        if not vapid_headers:
            return ChannelResponse(
                success=False,
                channel="push",
                status=DeliveryStatus.FAILED,
                error="Failed to generate VAPID authentication headers",
                timestamp=time.time(),
            )

        # Serialize payload
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        # For full Web Push, we would need to encrypt the payload with
        # ECDH + AES-128-GCM using the subscription's p256dh and auth keys.
        # This requires the `cryptography` package for ECDH key agreement.
        # If not available, try sending unencrypted (some push services
        # accept empty payloads).
        content_encoding = ""
        encrypted_payload = b""
        crypto_headers: Dict[str, str] = {}

        if _HAS_CRYPTOGRAPHY:
            try:
                encrypted_payload, crypto_headers = self._encrypt_web_push_payload(
                    subscription, payload_bytes,
                )
                content_encoding = "aes128gcm"
            except Exception as e:
                logger.warning(
                    "PushChannelProvider: payload encryption failed: %s "
                    "(sending empty body)",
                    e,
                )
                encrypted_payload = b""
        else:
            logger.debug(
                "PushChannelProvider: cryptography package not available, "
                "sending push without payload encryption"
            )

        # Build headers
        request_headers: Dict[str, str] = {
            "TTL": str(_WEB_PUSH_TTL),
            "Content-Type": "application/octet-stream",
            **vapid_headers,
        }

        if content_encoding:
            request_headers["Content-Encoding"] = content_encoding

        if crypto_headers.get("Crypto-Key"):
            # Merge with VAPID Crypto-Key header
            existing_ck = request_headers.get("Crypto-Key", "")
            if existing_ck:
                request_headers["Crypto-Key"] = (
                    f"{existing_ck};{crypto_headers['Crypto-Key']}"
                )
            else:
                request_headers["Crypto-Key"] = crypto_headers["Crypto-Key"]

        if crypto_headers.get("Encryption"):
            request_headers["Encryption"] = crypto_headers["Encryption"]

        # Send the push message
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    return await self._post_web_push_aiohttp(
                        endpoint, encrypted_payload, request_headers,
                    )
                elif _HAS_URLLIB:
                    return await self._post_web_push_urllib(
                        endpoint, encrypted_payload, request_headers,
                    )
                else:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error="No HTTP library available",
                        timestamp=time.time(),
                    )
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "PushChannelProvider: Web Push attempt %d/%d failed: "
                        "%s — retrying in %.1fs",
                        attempt, _MAX_RETRIES, e, delay,
                    )
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "PushChannelProvider: Web Push all %d attempts "
                        "failed: %s",
                        _MAX_RETRIES, e,
                    )
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error=f"Web Push HTTP error after {_MAX_RETRIES} "
                        f"attempts: {e}",
                        timestamp=time.time(),
                    )

        return ChannelResponse(
            success=False,
            channel="push",
            status=DeliveryStatus.FAILED,
            error="Unexpected Web Push retry loop exit",
            timestamp=time.time(),
        )

    def _encrypt_web_push_payload(
        self,
        subscription: Dict[str, Any],
        payload: bytes,
    ) -> tuple[bytes, Dict[str, str]]:
        """Encrypt a Web Push payload using aes128gcm encoding.

        Implements RFC 8291 (Message Encryption for Web Push) with
        ECDH key agreement and AES-128-GCM.

        Requires the `cryptography` package.

        Args:
            subscription: PushSubscription with keys.p256dh and keys.auth.
            payload: Raw payload bytes to encrypt.

        Returns:
            Tuple of (encrypted_data, extra_headers).
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os as _os

        keys = subscription.get("keys", {})
        p256dh_b64 = keys.get("p256dh", "")
        auth_b64 = keys.get("auth", "")

        if not p256dh_b64 or not auth_b64:
            raise ValueError("Subscription missing p256dh or auth keys")

        # Decode subscription keys
        p256dh_bytes = _base64url_decode(p256dh_b64)
        auth_bytes = _base64url_decode(auth_b64)

        # Unmarshal the subscription's public key (x || y, 64 bytes for P-256)
        if len(p256dh_bytes) != 65 or p256dh_bytes[0] != 0x04:
            # Might be 64 bytes (raw x || y without 0x04 prefix)
            if len(p256dh_bytes) == 64:
                p256dh_bytes = b"\x04" + p256dh_bytes
            else:
                raise ValueError(
                    f"Invalid p256dh key length: {len(p256dh_bytes)}"
                )

        # Load subscription public key
        x = int.from_bytes(p256dh_bytes[1:33], "big")
        y = int.from_bytes(p256dh_bytes[33:65], "big")
        sub_public_numbers = EllipticCurvePublicNumbers(
            x, y, SECP256R1(),
        )
        sub_public_key = sub_public_numbers.public_key(default_backend())

        # Generate ephemeral ECDH key pair
        ephemeral_key = ec.generate_private_key(
            SECP256R1(), default_backend(),
        )
        ephemeral_public_key = ephemeral_key.public_key()

        # ECDH key agreement → shared secret
        shared_key = ephemeral_key.exchange(
            ec.ECDH(), sub_public_key,
        )

        # Derive PRK using HKDF-SHA-256
        #   PRK = HKDF-Extract(salt, ikm)
        #   key_info = "Content-Encoding: aes128gcm\0"
        #   CEK = HKDF-Expand(PRK, key_info, 16)
        #   nonce_info = "Content-Encoding: nonce\0"
        #   nonce = HKDF-Expand(PRK, nonce_info, 12)
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF

        salt = _os.urandom(16)

        # IKM = shared_key || auth_bytes (per RFC 8291 §3.3)
        ikm = shared_key + auth_bytes

        # PRK = HKDF-Extract(salt, ikm)
        hkdf_extract = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            info=b"",
            backend=default_backend(),
        )
        prk = hkdf_extract.derive(ikm)

        # CEK = HKDF-Expand(PRK, key_info, 16)
        key_info = b"Content-Encoding: aes128gcm\x00"
        hkdf_cek = HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=salt,
            info=key_info,
            backend=default_backend(),
        )
        cek = hkdf_cek.derive(ikm)

        # Nonce = HKDF-Expand(PRK, nonce_info, 12)
        nonce_info = b"Content-Encoding: nonce\x00"
        hkdf_nonce = HKDF(
            algorithm=hashes.SHA256(),
            length=12,
            salt=salt,
            info=nonce_info,
            backend=default_backend(),
        )
        nonce = hkdf_nonce.derive(ikm)

        # Encrypt with AES-128-GCM
        # Padding: 0x02 byte after payload, then zeros to fill
        # RFC 8291: content = payload || 0x02 || padding
        padding_len = max(0, 1 - len(payload))  # At least 0x02 delimiter
        padded_payload = payload + b"\x02" + b"\x00" * padding_len

        aesgcm = AESGCM(cek)
        ciphertext = aesgcm.encrypt(nonce, padded_payload, None)

        # Build the aes128gcm encoding:
        # salt (16) || rs (4, big-endian, 4096) || key_id_len (1) || key_id || ciphertext
        # where key_id is the ephemeral public key (raw 65 bytes)
        ephemeral_raw = ephemeral_public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )

        rs = 4096  # Record size
        header = salt + rs.to_bytes(4, "big") + len(ephemeral_raw).to_bytes(1, "big") + ephemeral_raw

        encrypted_data = header + ciphertext

        # For aes128gcm encoding, Crypto-Key and Encryption headers
        # are NOT needed (they're in the binary header)
        extra_headers: Dict[str, str] = {}

        return encrypted_data, extra_headers

    async def _post_web_push_aiohttp(
        self,
        endpoint: str,
        data: bytes,
        headers: Dict[str, str],
    ) -> ChannelResponse:
        """Send Web Push via aiohttp."""
        assert self._session is not None

        async with self._session.post(
            endpoint, data=data, headers=headers,
        ) as resp:
            body = await resp.text()

            # Track rate limits
            self._update_rate_limit_from_headers(resp.headers)

            if resp.status in (200, 201, 202, 204):
                return ChannelResponse(
                    success=True,
                    channel="push",
                    status=DeliveryStatus.SENT,
                    metadata={
                        "backend": "webpush",
                        "http_status": resp.status,
                        "endpoint": endpoint[:80],
                    },
                    timestamp=time.time(),
                )
            elif resp.status == 429:
                retry_after = float(
                    resp.headers.get("Retry-After", "5"),
                )
                self._rate_limit_info = RateLimitInfo(
                    remaining=0,
                    reset_at=time.time() + retry_after,
                )
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.RATE_LIMITED,
                    error=f"Web Push rate limited. Retry after {retry_after}s",
                    timestamp=time.time(),
                )
            elif resp.status == 410:
                # Subscription has expired or been unsubscribed
                logger.info(
                    "PushChannelProvider: subscription expired (410) for "
                    "endpoint %s",
                    endpoint[:60],
                )
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error="Web Push subscription expired (410 Gone)",
                    metadata={
                        "backend": "webpush",
                        "http_status": 410,
                        "subscription_expired": True,
                    },
                    timestamp=time.time(),
                )
            elif resp.status == 413:
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error="Web Push payload too large (413)",
                    metadata={"backend": "webpush", "http_status": 413},
                    timestamp=time.time(),
                )
            else:
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"Web Push HTTP {resp.status}: {body[:300]}",
                    metadata={
                        "backend": "webpush",
                        "http_status": resp.status,
                    },
                    timestamp=time.time(),
                )

    async def _post_web_push_urllib(
        self,
        endpoint: str,
        data: bytes,
        headers: Dict[str, str],
    ) -> ChannelResponse:
        """Send Web Push via urllib (sync, wrapped in asyncio.to_thread)."""
        import asyncio

        validated_endpoint = _validate_url(endpoint)

        def _sync_post() -> ChannelResponse:
            req = urllib.request.Request(
                validated_endpoint, data=data, headers=headers, method="POST",
            )
            try:
                with urllib.request.urlopen(
                    req, timeout=_HTTP_TIMEOUT,
                ) as resp:
                    return ChannelResponse(
                        success=True,
                        channel="push",
                        status=DeliveryStatus.SENT,
                        metadata={
                            "backend": "webpush",
                            "http_status": resp.status,
                            "endpoint": endpoint[:80],
                        },
                        timestamp=time.time(),
                    )
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")[:300]
                if e.code == 410:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error="Subscription expired (410 Gone)",
                        metadata={
                            "backend": "webpush",
                            "subscription_expired": True,
                        },
                        timestamp=time.time(),
                    )
                elif e.code == 429:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.RATE_LIMITED,
                        error="Web Push rate limited",
                        timestamp=time.time(),
                    )
                elif e.code == 413:
                    return ChannelResponse(
                        success=False,
                        channel="push",
                        status=DeliveryStatus.FAILED,
                        error="Payload too large (413)",
                        timestamp=time.time(),
                    )
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"Web Push HTTP {e.code}: {body}",
                    metadata={"backend": "webpush", "http_status": e.code},
                    timestamp=time.time(),
                )
            except Exception as e:
                return ChannelResponse(
                    success=False,
                    channel="push",
                    status=DeliveryStatus.FAILED,
                    error=f"Web Push urllib error: {e}",
                    timestamp=time.time(),
                )

        return await asyncio.to_thread(_sync_post)

    async def _http_post_form(
        self, url: str, data: Dict[str, str],
    ) -> Optional[Dict[str, Any]]:
        """POST form-encoded data and return parsed JSON response.

        Used for OAuth2 token exchange.

        Args:
            url: Target URL.
            data: Form-encoded POST data.

        Returns:
            Dict with 'success', 'body', 'status' or None on failure.
        """
        encoded = urllib.parse.urlencode(data).encode("utf-8") if _HAS_URLLIB else b""
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP and self._session:
                    async with self._session.post(
                        url, data=encoded, headers=headers,
                    ) as resp:
                        body = await resp.text()
                        try:
                            body_json = json.loads(body)
                        except json.JSONDecodeError:
                            body_json = {}

                        if resp.status == 200:
                            return {"success": True, "body": body_json}
                        else:
                            return {
                                "success": False,
                                "status": resp.status,
                                "error": body[:200],
                            }
                elif _HAS_URLLIB:
                    import asyncio

                    validated_url = _validate_url(url)

                    def _sync_post() -> Dict[str, Any]:
                        req = urllib.request.Request(
                            validated_url, data=encoded, headers=headers, method="POST",
                        )
                        with urllib.request.urlopen(
                            req, timeout=_HTTP_TIMEOUT,
                        ) as resp:
                            body = resp.read().decode("utf-8")
                            try:
                                body_json = json.loads(body)
                            except json.JSONDecodeError:
                                body_json = {}
                            return {"success": True, "body": body_json}

                    return await asyncio.to_thread(_sync_post)
                else:
                    return None
            except Exception as e:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    import asyncio
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "PushChannelProvider: HTTP POST form failed after "
                        "%d attempts: %s",
                        _MAX_RETRIES, e,
                    )
                    return None

        return None

    def _update_rate_limit_from_headers(
        self, headers: Any,
    ) -> None:
        """Update rate limit info from response headers.

        Args:
            headers: HTTP response headers (Mapping or dict-like).
        """
        try:
            remaining = headers.get("X-RateLimit-Remaining")
            if remaining is not None:
                reset_at = headers.get("X-RateLimit-Reset", "0")
                limit = headers.get("X-RateLimit-Limit", "-1")
                self._rate_limit_info = RateLimitInfo(
                    remaining=int(remaining),
                    reset_at=float(reset_at) if reset_at else 0.0,
                    limit=int(limit) if limit else -1,
                )
        except (ValueError, TypeError, AttributeError):
            pass

    # ── Internal: Dry Run ───────────────────────────────────────

    def _dry_run_send(self, message: ChannelMessage) -> ChannelResponse:
        """Log message without sending (dry-run mode)."""
        with self._lock:
            self._sent_count += 1

        text_preview = sanitize_plain_text(message.text or message.html or "")[:200]
        logger.info(
            "[PUSH DRY-RUN] To: %s | Title: %s | Text: %s",
            message.recipient or "default",
            message.title or message.subject or "(none)",
            text_preview,
        )

        return ChannelResponse(
            success=True,
            channel="push",
            status=DeliveryStatus.DRY_RUN,
            metadata={
                "mode": "dry_run",
                "backend": "none",
                "has_web_push": self._has_web_push,
                "has_fcm": self._has_fcm,
            },
            timestamp=time.time(),
        )

    def _dry_run_confirmation(
        self, request: ConfirmationRequest,
    ) -> ChannelResponse:
        """Log confirmation without sending (dry-run mode)."""
        with self._lock:
            self._confirmation_count += 1

        logger.info(
            "[PUSH DRY-RUN] Confirmation: %s | Options: %s | Recipient: %s",
            request.title,
            list(request.options),
            request.recipient or "default",
        )

        return ChannelResponse(
            success=True,
            channel="push",
            status=DeliveryStatus.DRY_RUN,
            metadata={
                "mode": "dry_run",
                "action_id": request.action_id,
            },
            timestamp=time.time(),
        )


__all__ = ["PushChannelProvider"]
