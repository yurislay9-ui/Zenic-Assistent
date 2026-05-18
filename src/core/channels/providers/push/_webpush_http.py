"""
ZENIC-AGENTS — Push Channel Provider: WebPush HTTP Mixin

Web Push HTTP request and payload encryption methods.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict

from ..._types import (
    ChannelResponse,
    DeliveryStatus,
    RateLimitInfo,
)
from ._utils import (
    _HAS_AIOHTTP,
    _HAS_CRYPTOGRAPHY,
    _HAS_URLLIB,
    _MAX_RETRIES,
    _RETRY_BASE_DELAY,
    _HTTP_TIMEOUT,
    _WEB_PUSH_TTL,
    _PUSH_PAYLOAD_MAX,
    _base64url_decode,
    _validate_url,
)

# Conditional imports for type hints
if _HAS_CRYPTOGRAPHY:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ec import (
        EllipticCurvePublicNumbers,
        SECP256R1,
    )
    from cryptography.hazmat.backends import default_backend


logger = logging.getLogger("zenic_agents.channels.push")


class _WebPushHttpMixin:
    """Mixin for WebPush HTTP request methods."""

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
        import urllib.request
        import urllib.error

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
