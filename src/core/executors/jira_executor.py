"""
ZENIC-AGENTS — Jira ActionExecutor (Phase 2 Channel Integration)

Jira REST API executor for issue management operations. Supports:

Operations:
  - create_issue     → POST   /rest/api/2/issue
  - update_issue     → PUT    /rest/api/2/issue/{issueKey}
  - transition_issue → POST   /rest/api/2/issue/{issueKey}/transitions
  - get_issue        → GET    /rest/api/2/issue/{issueKey}
  - search_issues    → POST   /rest/api/2/search  (JQL)
  - add_comment      → POST   /rest/api/2/issue/{issueKey}/comment
  - get_transitions  → GET    /rest/api/2/issue/{issueKey}/transitions
  - link_issues      → POST   /rest/api/2/issueLink
  - get_issue_types  → GET    /rest/api/2/issuetype
  - get_priorities   → GET    /rest/api/2/priority

Authentication:
  - API Token  → Basic base64(email:api_token)
  - Bearer     → Authorization: Bearer <token>  (OAuth2)

Resilience:
  - Per-instance rate-limit tracking from response headers
  - Exponential backoff (3 retries, base 0.5 s)
  - Dry-run mode when base_url is not configured
  - aiohttp preferred, urllib fallback

Design invariants:
  1. Never raises from execute() — always returns ActionResult.
  2. Uses aiohttp when available; falls back to urllib.
  3. Dry-run when base_url is absent.
  4. Thread-safe statistics.
  5. No heavy SDK dependencies — pure HTTP.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

from .base import ActionExecutor, ActionResult, _validate_url, _HAS_AIOHTTP

logger = logging.getLogger(__name__)

# ── Optional urllib fallback ───────────────────────────────────

try:
    import urllib.request
    import urllib.error
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

# ── Constants ─────────────────────────────────────────────────

_API_V2 = "/rest/api/2"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.5  # seconds
_HTTP_TIMEOUT = 30  # seconds

_VALID_OPERATIONS = frozenset({
    "create_issue",
    "update_issue",
    "transition_issue",
    "get_issue",
    "search_issues",
    "add_comment",
    "get_transitions",
    "link_issues",
    "get_issue_types",
    "get_priorities",
})

# Environment variable names
_ENV_BASE_URL = "JIRA_BASE_URL"
_ENV_EMAIL = "JIRA_EMAIL"
_ENV_API_TOKEN = "JIRA_API_TOKEN"
_ENV_BEARER_TOKEN = "JIRA_BEARER_TOKEN"


class JiraExecutor(ActionExecutor):
    """Jira REST API executor for issue management.

    Supports API Token (Basic Auth) and Bearer (OAuth2) authentication,
    rate-limit tracking, exponential backoff retries, and dry-run mode.

    Config keys accepted by ``execute()``:
        operation        – Required. One of _VALID_OPERATIONS.
        base_url         – Jira instance URL (or env JIRA_BASE_URL).
        auth_type        – "api_token" (default) or "bearer".
        email            – For API token auth (or env JIRA_EMAIL).
        api_token        – For API token auth (or env JIRA_API_TOKEN).
        bearer_token     – For bearer auth (or env JIRA_BEARER_TOKEN).
        project_key      – Project key (e.g. "PROJ").
        issue_type       – Issue type name (e.g. "Bug", "Task").
        summary          – Issue summary / title.
        description      – Issue description.
        priority         – Priority name (e.g. "High").
        labels           – List of label strings.
        assignee         – Assignee email or accountId.
        issue_key        – Issue key (e.g. "PROJ-123").
        transition_id    – Transition ID for transition_issue.
        transition_name  – Transition name (alternative to ID).
        comment          – Comment body text.
        jql              – JQL query string.
        fields           – List of fields to return.
        max_results      – Max results for search (default 50).
        link_type        – Link type name (e.g. "Blocks").
        inward_issue     – Inward issue key for link.
        outward_issue    – Outward issue key for link.
        additional_fields – Dict of extra Jira fields to merge.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_count: int = 0
        self._success_count: int = 0
        self._failure_count: int = 0
        self._dry_run_count: int = 0
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_reset_at: Optional[float] = None

    # ── ActionExecutor Interface ───────────────────────────────

    async def execute(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ActionResult:
        """Execute a Jira operation.

        Never raises — always returns an ActionResult.
        """
        start = self._measure()
        operation = config.get("operation", "").lower()

        # Validate operation
        if not operation:
            return ActionResult(
                False,
                {"operation": ""},
                "Missing required config key: operation",
                self._elapsed_ms(start),
            )

        if operation not in _VALID_OPERATIONS:
            return ActionResult(
                False,
                {"operation": operation},
                f"Invalid Jira operation: '{operation}'. "
                f"Must be one of {sorted(_VALID_OPERATIONS)}",
                self._elapsed_ms(start),
            )

        # Resolve base URL
        base_url = self._get_base_url(config)
        if not base_url:
            with self._lock:
                self._dry_run_count += 1
            result = self._dry_run(config)
            result.duration_ms = self._elapsed_ms(start)
            return result

        # Validate URL
        if not _validate_url(base_url):
            return ActionResult(
                False,
                {"base_url": base_url},
                f"Invalid Jira base URL: '{base_url}'",
                self._elapsed_ms(start),
            )

        # Build auth headers
        try:
            headers = self._get_auth_headers(config)
        except ValueError as exc:
            return ActionResult(
                False,
                {"auth_type": config.get("auth_type", "api_token")},
                str(exc),
                self._elapsed_ms(start),
            )

        # Dispatch to operation handler
        handler = {
            "create_issue": self._create_issue,
            "update_issue": self._update_issue,
            "transition_issue": self._transition_issue,
            "get_issue": self._get_issue,
            "search_issues": self._search_issues,
            "add_comment": self._add_comment,
            "get_transitions": self._get_transitions,
            "link_issues": self._link_issues,
            "get_issue_types": self._get_issue_types,
            "get_priorities": self._get_priorities,
        }[operation]

        try:
            result = await handler(config, headers, base_url)
        except Exception as exc:
            elapsed = self._elapsed_ms(start)
            logger.error(
                "JiraExecutor: unhandled exception in %s: %s",
                operation, exc,
            )
            result = ActionResult(
                False,
                {"operation": operation},
                f"Unexpected error: {exc}",
                elapsed,
            )

        # Update stats
        with self._lock:
            self._request_count += 1
            if result.success:
                self._success_count += 1
            else:
                self._failure_count += 1

        # Ensure duration is set
        if result.duration_ms == 0.0:
            result.duration_ms = self._elapsed_ms(start)

        return result

    # ── Property: Executor Name ────────────────────────────────

    @property
    def executor_name(self) -> str:
        return "JiraExecutor"

    # ── Config Helpers ─────────────────────────────────────────

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

    async def _jira_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute an HTTP request against the Jira REST API.

        Uses aiohttp when available, falls back to urllib.
        Implements exponential backoff retry (up to _MAX_RETRIES).

        Returns:
            Dict with keys: status, body, headers.
        """
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if _HAS_AIOHTTP:
                    return await self._jira_request_aiohttp(
                        method, url, headers, json_data, params,
                    )
                elif _HAS_URLLIB:
                    return await self._jira_request_urllib(
                        method, url, headers, json_data, params,
                    )
                else:
                    return {
                        "status": 0,
                        "body": {"errorMessages": ["No HTTP library available"]},
                        "headers": {},
                    }
            except Exception as exc:
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "JiraExecutor: attempt %d/%d failed for %s %s: %s",
                        attempt, _MAX_RETRIES, method, url, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        "JiraExecutor: all %d attempts failed for %s %s: %s",
                        _MAX_RETRIES, method, url, exc,
                    )
                    return {
                        "status": 0,
                        "body": {
                            "errorMessages": [
                                f"HTTP error after {_MAX_RETRIES} attempts: {exc}"
                            ],
                        },
                        "headers": {},
                    }

        # Should not be reached, but defensive
        return {
            "status": 0,
            "body": {"errorMessages": ["Unexpected retry loop exit"]},
            "headers": {},
        }

    async def _jira_request_aiohttp(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute request via aiohttp."""
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=_HTTP_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(
                method,
                url,
                headers=headers,
                json=json_data,
                params=params,
            ) as resp:
                # Track rate limits from response headers
                remaining = resp.headers.get("X-RateLimit-Remaining")
                if remaining is not None:
                    with self._lock:
                        self._rate_limit_remaining = int(remaining)
                        reset_val = resp.headers.get("X-RateLimit-Reset", "0")
                        try:
                            self._rate_limit_reset_at = float(reset_val)
                        except (ValueError, TypeError):
                            self._rate_limit_reset_at = None

                # Handle 429 rate limiting
                if resp.status == 429:
                    retry_after = float(resp.headers.get("Retry-After", "5"))
                    logger.warning(
                        "JiraExecutor: rate limited, retry after %.1fs",
                        retry_after,
                    )
                    await asyncio.sleep(retry_after)
                    # Raise to trigger retry
                    raise RuntimeError(f"Rate limited, retry after {retry_after}s")

                body = await resp.json()
                return {
                    "status": resp.status,
                    "body": body,
                    "headers": dict(resp.headers),
                }

    async def _jira_request_urllib(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        json_data: Optional[Dict[str, Any]],
        params: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Execute request via urllib (sync, wrapped in asyncio.to_thread)."""

        # Append query params to URL
        if params:
            filtered = {k: v for k, v in params.items() if v is not None}
            if filtered:
                from urllib.parse import urlencode
                separator = "&" if "?" in url else "?"
                url = f"{url}{separator}{urlencode(filtered)}"

        def _sync_request() -> Dict[str, Any]:
            data = (
                json.dumps(json_data).encode("utf-8") if json_data else None
            )
            req = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method=method.upper(),
            )
            try:
                with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                    body_text = resp.read().decode("utf-8")
                    body = json.loads(body_text) if body_text else {}
                    return {
                        "status": resp.status,
                        "body": body,
                        "headers": dict(resp.headers),
                    }
            except urllib.error.HTTPError as exc:
                body_text = ""
                try:
                    body_text = exc.read().decode("utf-8")[:2000]
                except Exception:
                    pass
                body: Dict[str, Any] = {}
                try:
                    body = json.loads(body_text) if body_text else {}
                except json.JSONDecodeError:
                    body = {"errorMessages": [body_text]}

                if exc.code == 429:
                    retry_after = float(exc.headers.get("Retry-After", "5"))
                    raise RuntimeError(
                        f"Rate limited, retry after {retry_after}s"
                    )

                return {
                    "status": exc.code,
                    "body": body,
                    "headers": dict(exc.headers),
                }
            except Exception as exc:
                return {
                    "status": 0,
                    "body": {"errorMessages": [str(exc)]},
                    "headers": {},
                }

        return await asyncio.to_thread(_sync_request)

    # ── Operation: create_issue ────────────────────────────────

    async def _create_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Create a new Jira issue.

        POST /rest/api/2/issue
        """
        project_key = config.get("project_key", "")
        if not project_key:
            return ActionResult(
                False, {"operation": "create_issue"},
                "Missing required config key: project_key",
            )

        summary = config.get("summary", "")
        if not summary:
            return ActionResult(
                False, {"operation": "create_issue"},
                "Missing required config key: summary",
            )

        issue_type = config.get("issue_type", "Task")
        description = config.get("description", "")
        priority = config.get("priority", "")
        labels = config.get("labels", [])
        assignee = config.get("assignee", "")
        additional = config.get("additional_fields", {})

        # Build fields dict
        fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        # Description — plain text for v2 API
        if description:
            fields["description"] = description

        # Priority
        if priority:
            fields["priority"] = {"name": priority}

        # Labels
        if labels and isinstance(labels, list):
            fields["labels"] = labels

        # Assignee
        if assignee:
            fields["assignee"] = {"name": assignee}

        # Merge additional fields (can override above)
        if additional and isinstance(additional, dict):
            fields.update(additional)

        url = f"{base_url}{_API_V2}/issue"
        resp = await self._jira_request("POST", url, headers, {"fields": fields})

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300 and body.get("key"):
            logger.info(
                "JiraExecutor: created issue %s in project %s",
                body["key"], project_key,
            )
            return ActionResult(
                True,
                {
                    "operation": "create_issue",
                    "issue_key": body.get("key", ""),
                    "issue_id": body.get("id", ""),
                    "self_link": body.get("self", ""),
                },
            )
        else:
            errors = body.get("errors", {})
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else str(errors)
            logger.warning(
                "JiraExecutor: create_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "create_issue", "status": status},
                f"Failed to create issue: {error_msg}",
            )

    # ── Operation: update_issue ────────────────────────────────

    async def _update_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Update fields on an existing Jira issue.

        PUT /rest/api/2/issue/{issueKey}
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "update_issue"},
                "Missing required config key: issue_key",
            )

        fields: Dict[str, Any] = {}

        # Optional updatable fields
        for key in ("summary", "description"):
            val = config.get(key)
            if val is not None:
                fields[key] = val

        priority = config.get("priority")
        if priority:
            fields["priority"] = {"name": priority}

        labels = config.get("labels")
        if labels and isinstance(labels, list):
            fields["labels"] = labels

        assignee = config.get("assignee")
        if assignee:
            fields["assignee"] = {"name": assignee}

        issue_type = config.get("issue_type")
        if issue_type:
            fields["issuetype"] = {"name": issue_type}

        # Merge additional fields
        additional = config.get("additional_fields", {})
        if additional and isinstance(additional, dict):
            fields.update(additional)

        if not fields:
            return ActionResult(
                False, {"operation": "update_issue", "issue_key": issue_key},
                "No fields provided to update",
            )

        url = f"{base_url}{_API_V2}/issue/{issue_key}"
        resp = await self._jira_request("PUT", url, headers, {"fields": fields})

        status = resp.get("status", 0)

        if 200 <= status < 300:
            logger.info("JiraExecutor: updated issue %s", issue_key)
            return ActionResult(
                True,
                {"operation": "update_issue", "issue_key": issue_key},
            )
        else:
            body = resp.get("body", {})
            errors = body.get("errors", {})
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else str(errors)
            logger.warning(
                "JiraExecutor: update_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "update_issue", "issue_key": issue_key, "status": status},
                f"Failed to update issue: {error_msg}",
            )

    # ── Operation: transition_issue ────────────────────────────

    async def _transition_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Transition an issue to a new status.

        POST /rest/api/2/issue/{issueKey}/transitions

        Accepts either transition_id or transition_name.
        When transition_name is provided, the available transitions
        are fetched first and matched by name.
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "transition_issue"},
                "Missing required config key: issue_key",
            )

        transition_id = config.get("transition_id", "")
        transition_name = config.get("transition_name", "")

        if not transition_id and not transition_name:
            return ActionResult(
                False, {"operation": "transition_issue", "issue_key": issue_key},
                "Either transition_id or transition_name is required",
            )

        # If only name given, resolve to ID
        if not transition_id and transition_name:
            trans_resp = await self._jira_request(
                "GET",
                f"{base_url}{_API_V2}/issue/{issue_key}/transitions",
                headers,
            )
            body = trans_resp.get("body", {})
            transitions = body.get("transitions", [])
            found_id = self._find_transition_by_name(transitions, transition_name)
            if found_id is None:
                available = [
                    {"id": t.get("id"), "name": t.get("name")}
                    for t in transitions
                ]
                return ActionResult(
                    False,
                    {
                        "operation": "transition_issue",
                        "issue_key": issue_key,
                        "available_transitions": available,
                    },
                    f"Transition '{transition_name}' not found for issue {issue_key}",
                )
            transition_id = found_id

        payload: Dict[str, Any] = {
            "transition": {"id": transition_id},
        }

        # Optional fields on transition (e.g. resolution)
        additional = config.get("additional_fields", {})
        if additional and isinstance(additional, dict):
            payload["fields"] = additional

        url = f"{base_url}{_API_V2}/issue/{issue_key}/transitions"
        resp = await self._jira_request("POST", url, headers, payload)

        status = resp.get("status", 0)

        if 200 <= status < 300:
            logger.info(
                "JiraExecutor: transitioned issue %s with transition %s",
                issue_key, transition_id,
            )
            return ActionResult(
                True,
                {
                    "operation": "transition_issue",
                    "issue_key": issue_key,
                    "transition_id": transition_id,
                },
            )
        else:
            body = resp.get("body", {})
            messages = body.get("errorMessages", [])
            errors = body.get("errors", {})
            error_msg = "; ".join(messages) if messages else str(errors)
            logger.warning(
                "JiraExecutor: transition_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "transition_issue",
                    "issue_key": issue_key,
                    "status": status,
                },
                f"Failed to transition issue: {error_msg}",
            )

    # ── Operation: get_issue ───────────────────────────────────

    async def _get_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Retrieve a single Jira issue by key.

        GET /rest/api/2/issue/{issueKey}
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "get_issue"},
                "Missing required config key: issue_key",
            )

        fields_param = config.get("fields", [])
        params: Optional[Dict[str, Any]] = None
        if fields_param and isinstance(fields_param, list):
            params = {"fields": ",".join(fields_param)}

        url = f"{base_url}{_API_V2}/issue/{issue_key}"
        resp = await self._jira_request("GET", url, headers, params=params)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300 and body.get("key"):
            logger.info("JiraExecutor: retrieved issue %s", issue_key)
            return ActionResult(
                True,
                {
                    "operation": "get_issue",
                    "issue_key": body.get("key", ""),
                    "issue_id": body.get("id", ""),
                    "fields": body.get("fields", {}),
                    "self_link": body.get("self", ""),
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "get_issue", "issue_key": issue_key, "status": status},
                f"Failed to get issue: {error_msg}",
            )

    # ── Operation: search_issues ───────────────────────────────

    async def _search_issues(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Search for issues using JQL.

        POST /rest/api/2/search
        """
        jql = config.get("jql", "")
        if not jql:
            return ActionResult(
                False, {"operation": "search_issues"},
                "Missing required config key: jql",
            )

        max_results = config.get("max_results", 50)
        fields_param = config.get("fields", ["summary", "status", "priority"])
        start_at = config.get("start_at", 0)

        payload: Dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
            "fields": fields_param if isinstance(fields_param, list) else ["*all"],
        }

        url = f"{base_url}{_API_V2}/search"
        resp = await self._jira_request("POST", url, headers, payload)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300:
            issues = body.get("issues", [])
            total = body.get("total", 0)
            logger.info(
                "JiraExecutor: search returned %d/%d issues",
                len(issues), total,
            )
            return ActionResult(
                True,
                {
                    "operation": "search_issues",
                    "issues": issues,
                    "total": total,
                    "max_results": max_results,
                    "start_at": start_at,
                    "returned": len(issues),
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: search_issues failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "search_issues", "status": status},
                f"Failed to search issues: {error_msg}",
            )

    # ── Operation: add_comment ─────────────────────────────────

    async def _add_comment(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Add a comment to an existing issue.

        POST /rest/api/2/issue/{issueKey}/comment
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "add_comment"},
                "Missing required config key: issue_key",
            )

        comment = config.get("comment", "")
        if not comment:
            return ActionResult(
                False, {"operation": "add_comment", "issue_key": issue_key},
                "Missing required config key: comment",
            )

        payload: Dict[str, Any] = {"body": comment}

        url = f"{base_url}{_API_V2}/issue/{issue_key}/comment"
        resp = await self._jira_request("POST", url, headers, payload)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300:
            comment_id = body.get("id", "")
            logger.info(
                "JiraExecutor: added comment %s to issue %s",
                comment_id, issue_key,
            )
            return ActionResult(
                True,
                {
                    "operation": "add_comment",
                    "issue_key": issue_key,
                    "comment_id": comment_id,
                    "comment_self": body.get("self", ""),
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: add_comment failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "add_comment",
                    "issue_key": issue_key,
                    "status": status,
                },
                f"Failed to add comment: {error_msg}",
            )

    # ── Operation: get_transitions ─────────────────────────────

    async def _get_transitions(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Get available transitions for an issue.

        GET /rest/api/2/issue/{issueKey}/transitions
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "get_transitions"},
                "Missing required config key: issue_key",
            )

        url = f"{base_url}{_API_V2}/issue/{issue_key}/transitions"
        resp = await self._jira_request("GET", url, headers)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300:
            transitions = body.get("transitions", [])
            logger.info(
                "JiraExecutor: retrieved %d transitions for issue %s",
                len(transitions), issue_key,
            )
            return ActionResult(
                True,
                {
                    "operation": "get_transitions",
                    "issue_key": issue_key,
                    "transitions": [
                        {
                            "id": t.get("id", ""),
                            "name": t.get("name", ""),
                            "to": t.get("to", {}).get("name", ""),
                        }
                        for t in transitions
                    ],
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_transitions failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "get_transitions",
                    "issue_key": issue_key,
                    "status": status,
                },
                f"Failed to get transitions: {error_msg}",
            )

    # ── Operation: link_issues ─────────────────────────────────

    async def _link_issues(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Create a link between two issues.

        POST /rest/api/2/issueLink
        """
        link_type = config.get("link_type", "Blocks")
        inward_issue = config.get("inward_issue", "")
        outward_issue = config.get("outward_issue", "")

        if not inward_issue:
            return ActionResult(
                False, {"operation": "link_issues"},
                "Missing required config key: inward_issue",
            )
        if not outward_issue:
            return ActionResult(
                False, {"operation": "link_issues"},
                "Missing required config key: outward_issue",
            )

        payload: Dict[str, Any] = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_issue},
            "outwardIssue": {"key": outward_issue},
        }

        comment = config.get("comment", "")
        if comment:
            payload["comment"] = {"body": comment}

        url = f"{base_url}{_API_V2}/issueLink"
        resp = await self._jira_request("POST", url, headers, payload)

        status = resp.get("status", 0)

        if 200 <= status < 300:
            logger.info(
                "JiraExecutor: linked %s -> %s (%s)",
                inward_issue, outward_issue, link_type,
            )
            return ActionResult(
                True,
                {
                    "operation": "link_issues",
                    "link_type": link_type,
                    "inward_issue": inward_issue,
                    "outward_issue": outward_issue,
                },
            )
        else:
            body = resp.get("body", {})
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: link_issues failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "link_issues",
                    "status": status,
                    "inward_issue": inward_issue,
                    "outward_issue": outward_issue,
                },
                f"Failed to link issues: {error_msg}",
            )

    # ── Operation: get_issue_types ─────────────────────────────

    async def _get_issue_types(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Get all issue types available to the user.

        GET /rest/api/2/issuetype
        """
        url = f"{base_url}{_API_V2}/issuetype"
        resp = await self._jira_request("GET", url, headers)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        # Body may be a list directly
        if isinstance(body, list):
            issue_types = body
        else:
            issue_types = []

        if 200 <= status < 300 and isinstance(issue_types, list):
            logger.info(
                "JiraExecutor: retrieved %d issue types",
                len(issue_types),
            )
            return ActionResult(
                True,
                {
                    "operation": "get_issue_types",
                    "issue_types": [
                        {
                            "id": it.get("id", ""),
                            "name": it.get("name", ""),
                            "subtask": it.get("subtask", False),
                            "description": it.get("description", ""),
                        }
                        for it in issue_types
                    ],
                },
            )
        else:
            messages = body.get("errorMessages", []) if isinstance(body, dict) else []
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_issue_types failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "get_issue_types", "status": status},
                f"Failed to get issue types: {error_msg}",
            )

    # ── Operation: get_priorities ──────────────────────────────

    async def _get_priorities(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Get all priorities.

        GET /rest/api/2/priority
        """
        url = f"{base_url}{_API_V2}/priority"
        resp = await self._jira_request("GET", url, headers)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if isinstance(body, list):
            priorities = body
        else:
            priorities = []

        if 200 <= status < 300 and isinstance(priorities, list):
            logger.info(
                "JiraExecutor: retrieved %d priorities",
                len(priorities),
            )
            return ActionResult(
                True,
                {
                    "operation": "get_priorities",
                    "priorities": [
                        {
                            "id": p.get("id", ""),
                            "name": p.get("name", ""),
                            "statusColor": p.get("statusColor", ""),
                        }
                        for p in priorities
                    ],
                },
            )
        else:
            messages = body.get("errorMessages", []) if isinstance(body, dict) else []
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_priorities failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "get_priorities", "status": status},
                f"Failed to get priorities: {error_msg}",
            )

    # ── Utility: find transition by name ───────────────────────

    @staticmethod
    def _find_transition_by_name(
        transitions: List[Dict[str, Any]],
        name: str,
    ) -> Optional[str]:
        """Find a transition ID by its name (case-insensitive).

        Args:
            transitions: List of transition dicts from the API.
            name: Transition name to search for.

        Returns:
            Transition ID if found, else None.
        """
        name_lower = name.lower()
        for t in transitions:
            t_name = t.get("name", "")
            if t_name.lower() == name_lower:
                return t.get("id")
        return None

    # ── Dry-Run Mode ──────────────────────────────────────────

    def _dry_run(self, config: Dict[str, Any]) -> ActionResult:
        """Return a simulated result when Jira is not configured.

        Logs the intended operation and returns success with dry_run flag.
        """
        operation = config.get("operation", "unknown")
        project_key = config.get("project_key", "")
        issue_key = config.get("issue_key", "")
        summary = config.get("summary", "")
        jql = config.get("jql", "")
        comment = config.get("comment", "")

        logger.info(
            "[JIRA DRY-RUN] operation=%s project=%s issue=%s "
            "summary=%.80s jql=%.80s comment=%.80s",
            operation, project_key, issue_key, summary, jql, comment,
        )

        data: Dict[str, Any] = {
            "operation": operation,
            "mode": "dry_run",
        }

        # Add operation-specific preview data
        if operation == "create_issue":
            data["would_create"] = {
                "project_key": project_key,
                "summary": summary,
                "issue_type": config.get("issue_type", "Task"),
                "priority": config.get("priority", ""),
            }
        elif operation in ("update_issue", "transition_issue", "get_issue",
                           "add_comment", "get_transitions"):
            data["issue_key"] = issue_key
        elif operation == "search_issues":
            data["jql"] = jql
        elif operation == "link_issues":
            data["inward_issue"] = config.get("inward_issue", "")
            data["outward_issue"] = config.get("outward_issue", "")
            data["link_type"] = config.get("link_type", "Blocks")

        return ActionResult(True, data)

    # ── Statistics ─────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Executor statistics for monitoring."""
        with self._lock:
            return {
                "executor": "JiraExecutor",
                "request_count": self._request_count,
                "success_count": self._success_count,
                "failure_count": self._failure_count,
                "dry_run_count": self._dry_run_count,
                "rate_limit_remaining": self._rate_limit_remaining,
                "rate_limit_reset_at": self._rate_limit_reset_at,
                "has_aiohttp": _HAS_AIOHTTP,
                "has_urllib": _HAS_URLLIB,
                "operations": sorted(_VALID_OPERATIONS),
            }


__all__ = ["JiraExecutor"]
