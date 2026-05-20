"""ZENIC-AGENTS - Jira Executor: Auth Mixin"""

from __future__ import annotations

import base64
import os
from typing import Any, Dict

_ENV_BASE_URL = "JIRA_BASE_URL"
_ENV_EMAIL = "JIRA_EMAIL"
_ENV_API_TOKEN = "JIRA_API_TOKEN"
_ENV_BEARER_TOKEN = "JIRA_BEARER_TOKEN"


class _AuthMixin:
    """Mixin for Jira authentication methods."""

    def _get_base_url(self, config: Dict[str, Any]) -> str:
        """Resolve Jira base URL from config or environment."""
        url = config.get("base_url", "") or os.environ.get(_ENV_BASE_URL, "")
        return url.rstrip("/") if url else ""

    def _get_auth_headers(self, config: Dict[str, Any]) -> Dict[str, str]:
        """Build authentication headers from config or environment.

        Raises:
            ValueError: If required credentials are missing.
        """
        auth_type = config.get("auth_type", "api_token").lower()
        headers: Dict[str, str] = {"Content-Type": "application/json"}

        if auth_type == "bearer":
            token = (
                config.get("bearer_token", "")
                or os.environ.get(_ENV_BEARER_TOKEN, "")
            )
            if not token:
                raise ValueError(
                    "Bearer token required but not provided "
                    "(config.bearer_token or JIRA_BEARER_TOKEN)"
                )
            headers["Authorization"] = f"Bearer {token}"

        else:  # api_token (default)
            email = (
                config.get("email", "")
                or os.environ.get(_ENV_EMAIL, "")
            )
            api_token = (
                config.get("api_token", "")
                or os.environ.get(_ENV_API_TOKEN, "")
            )
            if not email or not api_token:
                raise ValueError(
                    "API token auth requires email and api_token "
                    "(config.email/api_token or JIRA_EMAIL/JIRA_API_TOKEN)"
                )
            credential = base64.b64encode(
                f"{email}:{api_token}".encode("utf-8")
            ).decode("utf-8")
            headers["Authorization"] = f"Basic {credential}"

        return headers

    # ── HTTP Request Layer ─────────────────────────────────────
