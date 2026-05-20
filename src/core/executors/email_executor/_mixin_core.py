"""email_executor — Core mixin (execute, mode dispatch, dry run)."""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any, Dict, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _send_via_smtp, _send_via_graph_api, _dry_run_send, _intercept_smtp, _intercept_http, _intercept_db, _intercept_file, _record_operation


class EmailExecutorCoreMixin:
    """Core execution and mode dispatch for EmailExecutor."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._template_engine = EmailTemplateEngine()  # noqa: F821
        self._rate_limiter = EmailRateLimiter()  # noqa: F821
        self._graph_provider: Optional[GraphAPIEmailProvider] = None  # noqa: F821
        self._smtp_send_count: int = 0
        self._graph_send_count: int = 0
        self._dry_run_count: int = 0
        self._failure_count: int = 0
        self._rate_limited_count: int = 0

    # ── ActionExecutor Interface ──────────────────────────────────

    async def execute(
        self,
        config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> ActionResult:  # noqa: F821
        """Execute an email send operation.

        Never raises — always returns an ActionResult.
        """
        start = self._measure()  # noqa: F821

        # ── Resolve mode ────────────────────────────────────────
        mode = config.get("mode", "auto").lower()
        if mode not in _VALID_MODES:  # noqa: F821
            return ActionResult(
                False, {"mode": mode},
                f"Invalid mode: '{mode}'. Must be one of {sorted(_VALID_MODES)}",  # noqa: F821
                self._elapsed_ms(start),  # noqa: F821
            )

        # ── Resolve recipients ──────────────────────────────────
        recipients = self._resolve_recipients(config)
        if not recipients:
            return ActionResult(
                False, {"recipients": []},
                "No recipients specified (config.to is required)",
                self._elapsed_ms(start),  # noqa: F821
            )

        # Validate email addresses
        invalid = [r for r in recipients if not _validate_email(r)]  # noqa: F821
        if invalid:
            return ActionResult(
                False, {"invalid_recipients": invalid},
                f"Invalid email addresses: {invalid}",
                self._elapsed_ms(start),  # noqa: F821
            )

        # ── Rate limiting ───────────────────────────────────────
        rate_results = self._rate_limiter.check(recipients)
        denied = [r for r in rate_results if not r.allowed]
        if denied:
            reasons = "; ".join(r.reason for r in denied)
            with self._lock:
                self._rate_limited_count += 1
            return ActionResult(
                False,
                {"rate_limited": True, "denied_recipients": [
                    {"recipient": r.recipient, "reason": r.reason} for r in denied
                ]},
                f"Rate limited: {reasons}",
                self._elapsed_ms(start),  # noqa: F821
            )

        # ── Render template ─────────────────────────────────────
        rendered = self._template_engine.render_from_config(config)
        subject = rendered["subject"]
        body = rendered["body"]
        html = rendered["html"]

        if not config.get("template"):
            if config.get("body"):
                body = config["body"]
            if config.get("html"):
                html = config["html"]
            if config.get("subject"):
                subject = config["subject"]

        # ── Dispatch to mode ────────────────────────────────────
        try:
            if mode == "smtp":
                result = await self._execute_smtp(config, recipients, subject, body, html)
            elif mode == "graph_api":
                result = await self._execute_graph_api(config, recipients, subject, body, html)
            else:  # auto
                result = await self._execute_auto(config, recipients, subject, body, html)
        except Exception as exc:
            __import__("logging").getLogger("zenic_agents.executors.email_executor").error(
                "EmailExecutor: unhandled exception: %s", exc, exc_info=True,
            )
            with self._lock:
                self._failure_count += 1
            result = ActionResult(
                False, {"mode": mode, "recipients": recipients},
                f"Unexpected error: {exc}",
                self._elapsed_ms(start),  # noqa: F821
            )

        if result.success:
            self._rate_limiter.record_send(recipients)

        if result.duration_ms == 0.0:
            result.duration_ms = self._elapsed_ms(start)  # noqa: F821

        return result

    @property
    def executor_name(self) -> str:
        return "EmailExecutor"

    # ── Auto Mode Implementation ───────────────────────────────────

    async def _execute_auto(
        self,
        config: Dict[str, Any],
        recipients: List[str],
        subject: str,
        body: str,
        html: str,
    ) -> ActionResult:  # noqa: F821
        """Try Graph API first, fall back to SMTP."""
        provider = self._get_or_create_graph_provider(config)
        if provider.is_configured and _HAS_AIOHTTP:  # noqa: F821
            graph_result = await self._execute_graph_api(config, recipients, subject, body, html)
            if graph_result.success:
                graph_result.data["mode"] = "auto (graph_api)"
                return graph_result

        smtp_config = {**config, "mode": "smtp"}
        smtp_result = await self._execute_smtp(smtp_config, recipients, subject, body, html)
        if smtp_result.success:
            smtp_result.data["mode"] = "auto (smtp)"
        return smtp_result

    # ── Recipient Resolution ───────────────────────────────────────

    @staticmethod
    def _resolve_recipients(config: Dict[str, Any]) -> List[str]:
        """Resolve recipients from config, normalizing to a list."""
        to = config.get("to", [])
        if isinstance(to, str):
            return [to.strip()] if to.strip() else []
        if isinstance(to, (list, tuple)):
            return [r.strip() for r in to if r and r.strip()]
        return []

    # ── Dry Run ────────────────────────────────────────────────────

    def _dry_run_result(
        self,
        recipients: List[str],
        subject: str,
        reason: str,
    ) -> ActionResult:  # noqa: F821
        """Build a dry-run ActionResult."""
        dry_run_id = f"dry-run-{uuid.uuid4().hex[:12]}"
        __import__("logging").getLogger("zenic_agents.executors.email_executor").info(
            "EmailExecutor: Dry-run (reason=%s) to=%s subject='%s'",
            reason, recipients, subject[:50],
        )
        return ActionResult(
            True,
            {
                "mode": "dry_run", "recipients": recipients,
                "subject": subject, "dry_run": True,
                "dry_run_reason": reason, "message_id": dry_run_id,
            },
        )

    # ── Statistics ─────────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Get executor statistics."""
        with self._lock:
            return {
                "executor": "EmailExecutor",
                "smtp_send_count": self._smtp_send_count,
                "graph_send_count": self._graph_send_count,
                "dry_run_count": self._dry_run_count,
                "failure_count": self._failure_count,
                "rate_limited_count": self._rate_limited_count,
                "template_engine": self._template_engine.stats,
                "rate_limiter": self._rate_limiter.stats,
                "aiosmtplib_available": _HAS_AIOSMTPLIB_LOCAL,  # noqa: F821
                "aiohttp_available": _HAS_AIOHTTP,  # noqa: F821
            }
