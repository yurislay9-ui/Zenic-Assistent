"""ZENIC-AGENTS - Jira Executor"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict, Optional

from ..base import ActionExecutor, ActionResult, _validate_url
from ._http import _HttpMixin
from ._auth import _AuthMixin
from ._operations import _OperationsMixin

logger = logging.getLogger(__name__)

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


class JiraExecutor(_HttpMixin, _AuthMixin, _OperationsMixin, ActionExecutor):
    """Jira REST API executor for issue management."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._request_count: int = 0
        self._success_count: int = 0
        self._failure_count: int = 0
        self._dry_run_count: int = 0
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_reset_at: Optional[float] = None

    # ── ActionExecutor Interface ───────────────────────────────

    # ── Property: Executor Name ────────────────────────────────

    @property
    def executor_name(self) -> str:
        return "JiraExecutor"

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


__all__ = ["JiraExecutor"]
