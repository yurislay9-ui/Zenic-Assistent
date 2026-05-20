"""ZENIC-AGENTS - ServiceNow Executor: Auth Mixin"""

from __future__ import annotations

import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from ..base import _validate_url_ssrf

logger = logging.getLogger(__name__)

_ENV_INSTANCE_URL = "SERVICENOW_INSTANCE_URL"
_ENV_USERNAME = "SERVICENOW_USERNAME"
_ENV_PASSWORD = "SERVICENOW_PASSWORD"
_ENV_CLIENT_ID = "SERVICENOW_CLIENT_ID"
_ENV_CLIENT_SECRET = "SERVICENOW_CLIENT_SECRET"
_ENV_TOKEN_URL = "SERVICENOW_TOKEN_URL"

_STATE_CLOSED = 7
_STATE_IN_PROGRESS = 2


class _AuthMixin:
    """Mixin for ServiceNow authentication methods."""

    def _get_instance_url(self, config: Dict[str, Any]) -> str:
        """Resolve the ServiceNow instance URL from config or env."""
        url = config.get("instance_url", "") or os.environ.get(_ENV_INSTANCE_URL, "")
        # Strip trailing slash for consistent URL building
        if url and url.endswith("/"):
            url = url.rstrip("/")
        return url

    def _get_auth_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        """Build authentication headers based on auth_type.

        Args:
            config: Configuration dict containing ``auth_type`` and
                either basic-auth or OAuth2 credentials.

        Returns:
            Dict with ``Authorization`` and ``Content-Type`` headers.

        Raises:
            ValueError: If required credentials are missing.
        """
        auth_type = config.get("auth_type", "basic").lower()

        if auth_type == "oauth2":
            token = self._get_oauth_token(config)
            if not token:
                raise ValueError(
                    "OAuth2 token acquisition failed — check client_id, "
                    "client_secret, and token_url configuration"
                )
            return {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

        # Default: Basic Auth
        username = config.get("username", "") or os.environ.get(_ENV_USERNAME, "")
        password = config.get("password", "") or os.environ.get(_ENV_PASSWORD, "")

        if not username or not password:
            raise ValueError(
                "Basic auth requires username and password "
                "(config keys or SERVICENOW_USERNAME / SERVICENOW_PASSWORD env-vars)"
            )

        return self._get_basic_auth(username, password)

    @staticmethod

    @staticmethod
    def _get_basic_auth(username: str, password: str) -> Dict[str, str]:
        """Build Basic Authentication headers.

        Args:
            username: ServiceNow username.
            password: ServiceNow password.

        Returns:
            Dict with ``Authorization`` (Basic) and ``Content-Type`` headers.
        """
        credentials = base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get_oauth_token(self, config: Dict[str, Any]) -> Optional[str]:
        """Obtain an OAuth2 Bearer token via client-credentials flow.

        Caches the token per instance_url until expiry.

        Args:
            config: Configuration dict with ``client_id``,
                ``client_secret``, and ``oauth_token_url``.

        Returns:
            Bearer token string, or ``None`` on failure.
        """
        instance_url = self._get_instance_url(config)

        # ── Check cache ───────────────────────────────────────
        with self._lock:
            cached = self._oauth_cache.get(instance_url)
            if cached and cached.get("expires_at", 0) > time.time():
                return cached["token"]

        client_id = (
            config.get("client_id", "")
            or os.environ.get(_ENV_CLIENT_ID, "")
        )
        client_secret = (
            config.get("client_secret", "")
            or os.environ.get(_ENV_CLIENT_SECRET, "")
        )
        token_url = (
            config.get("oauth_token_url", "")
            or os.environ.get(_ENV_TOKEN_URL, "")
        )

        if not all([client_id, client_secret, token_url]):
            logger.warning(
                "ServiceNowExecutor: OAuth2 requires client_id, "
                "client_secret, and token_url"
            )
            return None

        # ── Token request (synchronous — fallback urllib) ─────
        try:
            token_data = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
            }).encode("utf-8")

            validated_token_url = _validate_url_ssrf(token_url)
            req = urllib.request.Request(
                validated_token_url,
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                body = json.loads(resp.read().decode("utf-8"))

            token = body.get("access_token", "")
            expires_in = body.get("expires_in", 3600)

            if not token:
                logger.warning("ServiceNowExecutor: OAuth2 response missing access_token")
                return None

            # ── Cache ─────────────────────────────────────────
            with self._lock:
                self._oauth_cache[instance_url] = {
                    "token": token,
                    "expires_at": time.time() + expires_in - 60,  # 60 s margin
                }

            logger.debug(
                "ServiceNowExecutor: OAuth2 token acquired for %s (expires in %ds)",
                instance_url, expires_in,
            )
            return token

        except Exception as exc:
            logger.error(
                "ServiceNowExecutor: OAuth2 token request failed: %s", exc,
            )
            return None

    # ──────────────────────────────────────────────────────────
    #  URL BUILDER
    # ──────────────────────────────────────────────────────────

    @staticmethod

    @staticmethod
    def _build_url(
        instance_url: str,
        table: str,
        sys_id: Optional[str] = None,
    ) -> str:
        """Build a ServiceNow Table API URL.

        Args:
            instance_url: Base instance URL (e.g. ``https://dev123.service-now.com``).
            table: Table name (e.g. ``incident``, ``change_request``).
            sys_id: Optional record sys_id for specific record operations.

        Returns:
            Fully-qualified Table API URL.
        """
        url = f"{instance_url}/api/now/table/{table}"
        if sys_id:
            url = f"{url}/{sys_id}"
        return url

    # ──────────────────────────────────────────────────────────
    #  HTTP REQUEST LAYER
    # ──────────────────────────────────────────────────────────
