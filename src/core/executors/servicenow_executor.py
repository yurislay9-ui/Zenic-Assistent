"""
ZENIC-AGENTS - ServiceNowExecutor (Phase 2: Channel Integration)

ServiceNow REST API executor for ticket management.  Supports incident CRUD,
search, comments, and change-request creation via the ServiceNow Table API.

Features:
  - OAuth2 or Basic Auth
  - Per-instance rate-limit tracking (from X-RateLimit-Remaining headers)
  - Exponential backoff retry (3 attempts)
  - Dry-run mode when instance_url is not configured
  - Thread-safe statistics
  - Never raises — always returns ActionResult
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from .base import ActionExecutor, ActionResult, _HAS_AIOHTTP, _validate_url

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  OPTIONAL aiohttp IMPORT
# ──────────────────────────────────────────────────────────────

try:
    import aiohttp  # type: ignore[import-untyped]
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

# ──────────────────────────────────────────────────────────────
#  CONSTANTS
# ──────────────────────────────────────────────────────────────

_VALID_OPERATIONS: frozenset[str] = frozenset({
    "create_incident",
    "update_incident",
    "close_incident",
    "get_incident",
    "search_incidents",
    "add_comment",
    "create_change_request",
})

_MAX_RETRIES: int = 3
_RETRY_BASE_DELAY: float = 0.5  # seconds — 0.5, 1.0, 2.0

# ServiceNow incident state codes
_STATE_CLOSED: int = 7
_STATE_IN_PROGRESS: int = 2

# Environment variable names
_ENV_INSTANCE_URL = "SERVICENOW_INSTANCE_URL"
_ENV_USERNAME = "SERVICENOW_USERNAME"
_ENV_PASSWORD = "SERVICENOW_PASSWORD"
_ENV_CLIENT_ID = "SERVICENOW_CLIENT_ID"
_ENV_CLIENT_SECRET = "SERVICENOW_CLIENT_SECRET"
_ENV_TOKEN_URL = "SERVICENOW_TOKEN_URL"


class ServiceNowExecutor(ActionExecutor):
    """ServiceNow REST API executor for ticket management.

    Supports incident CRUD operations, search, comments, and change-request
    creation via the ServiceNow Table API.

    Authentication modes:
      - **Basic Auth** (``auth_type="basic"``): Username + password encoded
        as a Base64 ``Authorization`` header.
      - **OAuth2** (``auth_type="oauth2"``): Client-credentials flow; the
        executor obtains a Bearer token from the token endpoint before
        each request.

    Rate limiting:
      Per-instance rate-limit counters are tracked from the
      ``X-RateLimit-Remaining`` response header when present.

    Retry:
      Failed HTTP calls are retried up to ``_MAX_RETRIES`` times with
      exponential back-off (0.5 s, 1.0 s, 2.0 s).

    Dry-run:
      When ``instance_url`` is not provided (and the
      ``SERVICENOW_INSTANCE_URL`` env-var is absent), the executor enters
      dry-run mode: operations are logged but no HTTP requests are made.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rate_limits: Dict[str, Dict[str, Any]] = {}
        # OAuth token cache: key = instance_url -> {"token": ..., "expires_at": ...}
        self._oauth_cache: Dict[str, Dict[str, Any]] = {}
        self._stats: Dict[str, int] = {
            "requests_total": 0,
            "requests_success": 0,
            "requests_failed": 0,
            "retries_total": 0,
            "dry_run_ops": 0,
        }

    # ──────────────────────────────────────────────────────────
    #  ActionExecutor INTERFACE
    # ──────────────────────────────────────────────────────────

    async def execute(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ActionResult:
        """Execute a ServiceNow operation.

        Args:
            config: Operation configuration (see module docstring).
            context: Execution context (may include ``alert_id``,
                ``monitor_id``, ``sna_source``).

        Returns:
            ActionResult with operation outcome.  Never raises.
        """
        start = self._measure()
        operation = config.get("operation", "").lower()

        # ── Validate operation ────────────────────────────────
        if operation not in _VALID_OPERATIONS:
            return ActionResult(
                success=False,
                data={"operation": operation},
                error=(
                    f"Invalid ServiceNow operation: '{operation}'. "
                    f"Must be one of {sorted(_VALID_OPERATIONS)}"
                ),
                duration_ms=self._elapsed_ms(start),
            )

        # ── Resolve instance URL ──────────────────────────────
        instance_url = self._get_instance_url(config)

        # ── Dry-run when no instance configured ───────────────
        if not instance_url:
            logger.info(
                "ServiceNowExecutor: dry-run mode — no instance_url configured "
                "for operation '%s'",
                operation,
            )
            with self._lock:
                self._stats["dry_run_ops"] += 1
            result = self._dry_run(config)
            # Enrich dry-run result with context metadata
            if context.get("alert_id"):
                result.data["alert_id"] = context["alert_id"]
            if context.get("monitor_id"):
                result.data["monitor_id"] = context["monitor_id"]
            if context.get("sna_source"):
                result.data["sna_source"] = context["sna_source"]
            return result

        # ── Validate instance URL ─────────────────────────────
        if not _validate_url(instance_url):
            return ActionResult(
                success=False,
                data={"instance_url": instance_url},
                error=f"Invalid ServiceNow instance URL: '{instance_url}'",
                duration_ms=self._elapsed_ms(start),
            )

        # ── Build auth headers ────────────────────────────────
        try:
            headers = self._get_auth_headers(config)
        except Exception as exc:
            return ActionResult(
                success=False,
                data={"auth_type": config.get("auth_type", "basic")},
                error=f"Failed to build auth headers: {exc}",
                duration_ms=self._elapsed_ms(start),
            )

        # ── Dispatch operation ────────────────────────────────
        try:
            handler = {
                "create_incident": self._create_incident,
                "update_incident": self._update_incident,
                "close_incident": self._close_incident,
                "get_incident": self._get_incident,
                "search_incidents": self._search_incidents,
                "add_comment": self._add_comment,
                "create_change_request": self._create_change_request,
            }[operation]

            result = await handler(config, headers, instance_url)

            # ── Enrich result with context metadata ───────────
            if context.get("alert_id"):
                result.data["alert_id"] = context["alert_id"]
            if context.get("monitor_id"):
                result.data["monitor_id"] = context["monitor_id"]
            if context.get("sna_source"):
                result.data["sna_source"] = context["sna_source"]

            return result

        except Exception as exc:
            elapsed = self._elapsed_ms(start)
            logger.error(
                "ServiceNowExecutor: unhandled error in '%s': %s",
                operation, exc,
            )
            return ActionResult(
                success=False,
                data={"operation": operation, "instance_url": instance_url},
                error=f"Unhandled executor error: {exc}",
                duration_ms=elapsed,
            )

    # ──────────────────────────────────────────────────────────
    #  CONFIG RESOLVERS
    # ──────────────────────────────────────────────────────────

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

            req = urllib.request.Request(
                token_url,
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

    async def _snow_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request against the ServiceNow API with retry.

        Uses aiohttp when available; falls back to urllib otherwise.

        Args:
            method: HTTP method (GET, POST, PATCH, PUT, DELETE).
            url: Full API URL.
            headers: Request headers (including auth).
            json_data: Optional JSON body.

        Returns:
            Dict with ``status``, ``body``, ``headers`` keys.
            On failure, includes ``error`` key.
        """
        with self._lock:
            self._stats["requests_total"] += 1

        last_error: Optional[str] = None

        for attempt in range(_MAX_RETRIES):
            try:
                if _AIOHTTP_AVAILABLE:
                    result = await self._snow_request_aiohttp(
                        method, url, headers, json_data,
                    )
                else:
                    result = await self._snow_request_urllib(
                        method, url, headers, json_data,
                    )

                # ── Track rate limits from response ───────────
                resp_headers = result.get("headers", {})
                remaining = resp_headers.get("X-RateLimit-Remaining") or resp_headers.get("x-ratelimit-remaining")
                if remaining is not None:
                    try:
                        self._update_rate_limit(url, int(remaining))
                    except (ValueError, TypeError):
                        pass

                # ── Success ───────────────────────────────────
                with self._lock:
                    self._stats["requests_success"] += 1

                return result

            except Exception as exc:
                last_error = str(exc)
                with self._lock:
                    self._stats["retries_total"] += 1

                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "ServiceNowExecutor: request failed (attempt %d/%d), "
                        "retrying in %.1fs — %s",
                        attempt + 1, _MAX_RETRIES, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "ServiceNowExecutor: request failed after %d attempts — %s",
                        _MAX_RETRIES, exc,
                    )

        with self._lock:
            self._stats["requests_failed"] += 1

        return {
            "status": 0,
            "body": {},
            "headers": {},
            "error": last_error or "Max retries exceeded",
        }

    async def _snow_request_aiohttp(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute request using aiohttp (async-native)."""
        import aiohttp  # type: ignore[import-untyped]

        async with aiohttp.ClientSession() as session:
            kwargs: Dict[str, Any] = {
                "headers": headers,
                "timeout": aiohttp.ClientTimeout(total=30),
            }
            if json_data is not None:
                kwargs["json"] = json_data

            async with session.request(method, url, **kwargs) as resp:
                body = await resp.text()
                resp_headers = dict(resp.headers)

                try:
                    parsed_body = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    parsed_body = {"raw": body}

                return {
                    "status": resp.status,
                    "body": parsed_body,
                    "headers": resp_headers,
                }

    async def _snow_request_urllib(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute request using urllib (sync, wrapped in to_thread)."""

        def _do() -> Dict[str, Any]:
            data = None
            if json_data is not None:
                data = json.dumps(json_data).encode("utf-8")

            req = urllib.request.Request(url, data=data, headers=headers, method=method)

            try:
                with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                    body_text = resp.read().decode("utf-8")
                    resp_headers = dict(resp.headers)

                    try:
                        parsed = json.loads(body_text) if body_text else {}
                    except json.JSONDecodeError:
                        parsed = {"raw": body_text}

                    return {
                        "status": resp.status,
                        "body": parsed,
                        "headers": resp_headers,
                    }
            except urllib.error.HTTPError as exc:
                body_text = ""
                try:
                    body_text = exc.read().decode("utf-8", errors="replace")
                except Exception:
                    pass

                try:
                    parsed = json.loads(body_text) if body_text else {}
                except json.JSONDecodeError:
                    parsed = {"raw": body_text} if body_text else {}

                return {
                    "status": exc.code,
                    "body": parsed,
                    "headers": dict(exc.headers) if exc.headers else {},
                    "error": str(exc),
                }

        return await asyncio.to_thread(_do)

    # ──────────────────────────────────────────────────────────
    #  RATE-LIMIT TRACKING
    # ──────────────────────────────────────────────────────────

    def _update_rate_limit(self, url: str, remaining: int) -> None:
        """Update per-instance rate-limit counter from response headers."""
        # Extract instance hostname for per-instance tracking
        parsed = urllib.parse.urlparse(url)
        instance_key = parsed.netloc

        with self._lock:
            self._rate_limits[instance_key] = {
                "remaining": remaining,
                "updated_at": time.time(),
            }

        if remaining < 10:
            logger.warning(
                "ServiceNowExecutor: rate limit low for %s — %d remaining",
                instance_key, remaining,
            )

    # ──────────────────────────────────────────────────────────
    #  OPERATION IMPLEMENTATIONS
    # ──────────────────────────────────────────────────────────

    async def _create_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Create a new ServiceNow incident.

        Required config: ``short_description``.
        Optional: ``description``, ``priority``, ``severity``,
            ``category``, ``assignment_group``, ``additional_fields``.
        """
        start = self._measure()
        short_desc = config.get("short_description", "")

        if not short_desc:
            return ActionResult(
                success=False,
                data={"operation": "create_incident"},
                error="short_description is required for create_incident",
                duration_ms=self._elapsed_ms(start),
            )

        # Build incident payload
        payload: Dict[str, Any] = {
            "short_description": short_desc,
        }

        for field_name in ("description", "priority", "severity", "category", "assignment_group"):
            value = config.get(field_name)
            if value is not None:
                payload[field_name] = value

        # Merge additional fields
        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        url = self._build_url(instance_url, "incident")
        resp = await self._snow_request("POST", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            incident_number = result_data.get("number", "unknown")
            logger.info(
                "ServiceNowExecutor: created incident %s (sys_id=%s)",
                incident_number, result_data.get("sys_id", ""),
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "create_incident",
                    "incident_number": incident_number,
                    "sys_id": result_data.get("sys_id", ""),
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: create_incident failed — %s", error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "create_incident", "status": status, "response": body},
            error=f"Failed to create incident: {error_msg}",
            duration_ms=elapsed,
        )

    async def _update_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Update an existing ServiceNow incident.

        Required config: ``incident_id``.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "update_incident"},
                error="incident_id is required for update_incident",
                duration_ms=self._elapsed_ms(start),
            )

        # Build update payload from provided fields
        payload: Dict[str, Any] = {}

        for field_name in (
            "short_description", "description", "priority", "severity",
            "category", "assignment_group", "state",
        ):
            value = config.get(field_name)
            if value is not None:
                payload[field_name] = value

        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        if not payload:
            return ActionResult(
                success=False,
                data={"operation": "update_incident", "incident_id": incident_id},
                error="No fields provided to update",
                duration_ms=self._elapsed_ms(start),
            )

        url = self._build_url(instance_url, "incident", sys_id=incident_id)
        resp = await self._snow_request("PATCH", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            logger.info(
                "ServiceNowExecutor: updated incident %s",
                incident_id,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "update_incident",
                    "incident_id": incident_id,
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: update_incident failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "update_incident", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to update incident {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _close_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Close a ServiceNow incident.

        Required config: ``incident_id``.
        Sets ``state`` to 7 (Closed) by default; can be overridden via
        ``state`` in config.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "close_incident"},
                error="incident_id is required for close_incident",
                duration_ms=self._elapsed_ms(start),
            )

        close_state = config.get("state", _STATE_CLOSED)

        payload: Dict[str, Any] = {
            "state": close_state,
        }

        # Include close notes if provided
        close_notes = config.get("close_notes", config.get("comment", ""))
        if close_notes:
            payload["close_notes"] = close_notes

        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        url = self._build_url(instance_url, "incident", sys_id=incident_id)
        resp = await self._snow_request("PATCH", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            logger.info(
                "ServiceNowExecutor: closed incident %s (state=%s)",
                incident_id, result_data.get("state", close_state),
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "close_incident",
                    "incident_id": incident_id,
                    "state": result_data.get("state", close_state),
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: close_incident failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "close_incident", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to close incident {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _get_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Retrieve a single ServiceNow incident by ID.

        Required config: ``incident_id``.
        Optional: ``fields`` — list of field names to return.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "get_incident"},
                error="incident_id is required for get_incident",
                duration_ms=self._elapsed_ms(start),
            )

        url = self._build_url(instance_url, "incident", sys_id=incident_id)

        # Add sysparm_fields if specified
        fields = config.get("fields", [])
        if fields and isinstance(fields, (list, tuple)):
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sysparm_fields={','.join(str(f) for f in fields)}"

        resp = await self._snow_request("GET", url, headers)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            logger.info(
                "ServiceNowExecutor: retrieved incident %s",
                incident_id,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "get_incident",
                    "incident_id": incident_id,
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: get_incident failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "get_incident", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to get incident {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _search_incidents(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Search ServiceNow incidents using an encoded query.

        Required config: ``search_query`` (ServiceNow encoded query string).
        Optional: ``fields`` — list of field names to return.
        """
        start = self._measure()
        search_query = config.get("search_query", "")

        if not search_query:
            return ActionResult(
                success=False,
                data={"operation": "search_incidents"},
                error="search_query is required for search_incidents",
                duration_ms=self._elapsed_ms(start),
            )

        url = self._build_url(instance_url, "incident")

        # Build query parameters
        params: List[str] = [
            f"sysparm_query={urllib.parse.quote(search_query, safe='')}",
        ]

        fields = config.get("fields", [])
        if fields and isinstance(fields, (list, tuple)):
            params.append(f"sysparm_fields={','.join(str(f) for f in fields)}")

        # Limit results to prevent huge responses
        limit = config.get("limit", 100)
        if isinstance(limit, int) and limit > 0:
            params.append(f"sysparm_limit={min(limit, 1000)}")

        url = f"{url}?{'&'.join(params)}"

        resp = await self._snow_request("GET", url, headers)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            results = body["result"]
            count = len(results) if isinstance(results, list) else 1
            logger.info(
                "ServiceNowExecutor: search returned %d incidents",
                count,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "search_incidents",
                    "query": search_query,
                    "count": count,
                    "records": results,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: search_incidents failed — %s", error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "search_incidents", "query": search_query, "status": status, "response": body},
            error=f"Failed to search incidents: {error_msg}",
            duration_ms=elapsed,
        )

    async def _add_comment(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Add a comment (journal entry) to a ServiceNow incident.

        Required config: ``incident_id``, ``comment``.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")
        comment = config.get("comment", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "add_comment"},
                error="incident_id is required for add_comment",
                duration_ms=self._elapsed_ms(start),
            )

        if not comment:
            return ActionResult(
                success=False,
                data={"operation": "add_comment", "incident_id": incident_id},
                error="comment is required for add_comment",
                duration_ms=self._elapsed_ms(start),
            )

        # ServiceNow: comments are added via the `comments` field on the incident
        payload: Dict[str, Any] = {
            "comments": comment,
        }

        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        url = self._build_url(instance_url, "incident", sys_id=incident_id)
        resp = await self._snow_request("PATCH", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            logger.info(
                "ServiceNowExecutor: added comment to incident %s",
                incident_id,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "add_comment",
                    "incident_id": incident_id,
                    "comment": comment,
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: add_comment failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "add_comment", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to add comment to {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _create_change_request(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Create a new ServiceNow change request.

        Required config: ``short_description``.
        Optional: ``description``, ``priority``, ``category``,
            ``assignment_group``, ``additional_fields``.
        """
        start = self._measure()
        short_desc = config.get("short_description", "")

        if not short_desc:
            return ActionResult(
                success=False,
                data={"operation": "create_change_request"},
                error="short_description is required for create_change_request",
                duration_ms=self._elapsed_ms(start),
            )

        payload: Dict[str, Any] = {
            "short_description": short_desc,
        }

        for field_name in ("description", "priority", "category", "assignment_group"):
            value = config.get(field_name)
            if value is not None:
                payload[field_name] = value

        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        url = self._build_url(instance_url, "change_request")
        resp = await self._snow_request("POST", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            change_number = result_data.get("number", "unknown")
            logger.info(
                "ServiceNowExecutor: created change request %s (sys_id=%s)",
                change_number, result_data.get("sys_id", ""),
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "create_change_request",
                    "change_number": change_number,
                    "sys_id": result_data.get("sys_id", ""),
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: create_change_request failed — %s", error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "create_change_request", "status": status, "response": body},
            error=f"Failed to create change request: {error_msg}",
            duration_ms=elapsed,
        )

    # ──────────────────────────────────────────────────────────
    #  DRY-RUN MODE
    # ──────────────────────────────────────────────────────────

    def _dry_run(self, config: Dict[str, Any]) -> ActionResult:
        """Return a simulated result when no instance URL is configured.

        Logs the operation that would have been performed and returns
        ``ActionResult(success=True)`` with ``dry_run=True`` in data.
        """
        operation = config.get("operation", "unknown")
        incident_id = config.get("incident_id", "")
        short_desc = config.get("short_description", "")
        search_query = config.get("search_query", "")

        logger.info(
            "ServiceNowExecutor [DRY-RUN]: %s — incident_id=%s, "
            "short_description='%s', search_query='%s'",
            operation, incident_id, short_desc, search_query,
        )

        dry_run_data: Dict[str, Any] = {
            "dry_run": True,
            "operation": operation,
            "message": (
                "Dry-run: no ServiceNow instance configured. "
                "Set instance_url in config or SERVICENOW_INSTANCE_URL env-var."
            ),
        }

        # Include relevant config keys for observability
        if incident_id:
            dry_run_data["incident_id"] = incident_id
        if short_desc:
            dry_run_data["short_description"] = short_desc
        if search_query:
            dry_run_data["search_query"] = search_query
        if config.get("comment"):
            dry_run_data["comment"] = config["comment"]

        # Simulate expected result structure
        if operation == "create_incident":
            dry_run_data["simulated_incident_number"] = "DRY-INC0000001"
            dry_run_data["simulated_sys_id"] = "dry-run-sys-id"
        elif operation == "create_change_request":
            dry_run_data["simulated_change_number"] = "DRY-CHG0000001"
            dry_run_data["simulated_sys_id"] = "dry-run-sys-id"
        elif operation == "search_incidents":
            dry_run_data["simulated_count"] = 0
            dry_run_data["simulated_records"] = []

        return ActionResult(
            success=True,
            data=dry_run_data,
            duration_ms=0.0,
        )

    # ──────────────────────────────────────────────────────────
    #  PUBLIC HELPERS
    # ──────────────────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Return executor statistics (thread-safe snapshot)."""
        with self._lock:
            return {
                **self._stats,
                "rate_limits": dict(self._rate_limits),
                "oauth_cached_instances": list(self._oauth_cache.keys()),
            }

    def reset_stats(self) -> None:
        """Reset executor statistics."""
        with self._lock:
            self._stats = {
                "requests_total": 0,
                "requests_success": 0,
                "requests_failed": 0,
                "retries_total": 0,
                "dry_run_ops": 0,
            }
            self._rate_limits.clear()

    def clear_oauth_cache(self) -> None:
        """Clear cached OAuth2 tokens."""
        with self._lock:
            self._oauth_cache.clear()
        logger.debug("ServiceNowExecutor: OAuth token cache cleared")
