"""
ZENIC-AGENTS — Push Channel Provider: FCM Authentication Mixin

Firebase Cloud Messaging OAuth2 authentication methods.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, Optional

from ._utils import (
    _HAS_AIOHTTP,
    _HAS_CRYPTOGRAPHY,
    _HAS_PYJWT,
    _HAS_URLLIB,
    _FCM_SCOPE,
    _FCM_TOKEN_URL,
    _MAX_RETRIES,
    _RETRY_BASE_DELAY,
    _HTTP_TIMEOUT,
    _base64url_encode,
    _validate_url,
)

# Conditional imports for type hints
if _HAS_CRYPTOGRAPHY:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend


logger = logging.getLogger("zenic_agents.channels.push")


class _FcmAuthMixin:
    """Mixin for FCM authentication methods."""

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
