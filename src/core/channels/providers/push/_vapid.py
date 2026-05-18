"""
ZENIC-AGENTS — Push Channel Provider: VAPID Mixin

VAPID (Voluntary Application Server Identification) authentication
methods for Web Push.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any, Dict, Optional

from ._utils import (
    _HAS_CRYPTOGRAPHY,
    _HAS_PYJWT,
    _VAPID_JWT_EXPIRY,
    _base64url_encode,
    _base64url_decode,
    _pem_to_base64url,
)

# Conditional imports for type hints
if _HAS_CRYPTOGRAPHY:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.ec import (
        ECDSA,
        EllipticCurvePrivateKey,
        SECP256R1,
    )
    from cryptography.hazmat.backends import default_backend


logger = logging.getLogger("zenic_agents.channels.push")


class _VapidMixin:
    """Mixin for VAPID authentication methods."""

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
