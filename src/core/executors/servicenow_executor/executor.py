"""ZENIC-AGENTS - ServiceNow Executor"""

from __future__ import annotations

import logging
import threading
from typing import Any, Dict

from ..base import ActionExecutor, ActionResult, _validate_url
from ._http import _HttpMixin
from ._auth import _AuthMixin
from ._operations import _OperationsMixin

logger = logging.getLogger(__name__)

_VALID_OPERATIONS = frozenset({
    "create_incident",
    "update_incident",
    "close_incident",
    "get_incident",
    "search_incidents",
    "add_comment",
    "create_change_request",
})


class ServiceNowExecutor(_HttpMixin, _AuthMixin, _OperationsMixin, ActionExecutor):
    """ServiceNow REST API executor for ticket management."""

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

    # ── ActionExecutor INTERFACE ─────────────────────────────

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



__all__ = ["ServiceNowExecutor"]
