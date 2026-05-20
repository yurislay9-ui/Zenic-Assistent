"""
ZENIC-AGENTS — Email ActionExecutor Core (Phase 2)

Enhanced email executor supporting both SMTP and Microsoft Graph API.

Modes:
  - "smtp"       → Sends via SMTP (aiosmtplib preferred, smtplib fallback)
  - "graph_api"  → Sends via Microsoft Graph API (OAuth2 + aiohttp)
  - "auto"       → Tries Graph API first, falls back to SMTP

Features:
  - Template rendering via EmailTemplateEngine
  - Per-recipient and global rate limiting via EmailRateLimiter
  - CC / BCC / reply-to / importance / attachments
  - Environment variable fallbacks for all SMTP and Graph API config
  - Dry-run mode when nothing is configured
  - Thread-safe statistics

Design invariants:
  1. Never raises from execute() — always returns ActionResult.
  2. Uses aiosmtplib when available; falls back to smtplib.
  3. Uses aiohttp for Graph API when available.
  4. Dry-run when neither SMTP nor Graph API is configured.
  5. Thread-safe counters via threading.Lock.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
import threading
import time
from typing import Any, Dict, List, Optional

from ..base import ActionExecutor, ActionResult, _validate_email, _HAS_AIOHTTP
from ..email_parts import EmailTemplateEngine, EmailRateLimiter
from ..email_parts.graph_api import GraphAPIEmailProvider
from ..email_parts.oauth2 import OAuth2TokenManager

from ._composer import (
    build_mime_message,
    resolve_recipients,
    build_dry_run_result,
    _HAS_AIOSMTPLIB_LOCAL,
    _VALID_MODES,
    _SMTP_TIMEOUT,
)

logger = logging.getLogger(__name__)


class EmailExecutor(ActionExecutor):
    """Enhanced email executor supporting SMTP and Microsoft Graph API.

    Config keys accepted by ``execute()``:
        mode           – "smtp", "graph_api", or "auto" (default: "auto")
        # SMTP fields
        host           – SMTP server host (or env SMTP_HOST)
        port           – SMTP server port (or env SMTP_PORT, default 587)
        user           – SMTP username (or env SMTP_USER)
        password       – SMTP password (or env SMTP_PASSWORD)
        use_tls        – Use TLS (default True for port 587)
        # Email fields
        to             – Recipient(s): str or List[str] (required unless dry-run)
        subject        – Email subject line
        body           – Plain text body
        html           – HTML body
        cc             – CC recipients (List[str])
        bcc            – BCC recipients (List[str])
        from_email     – Sender email address
        attachments    – List of attachment dicts: [{name, content_bytes, content_type}]
        reply_to       – Reply-to email address
        importance     – "low", "normal", "high" (default "normal")
        # Template fields
        template       – Template name (e.g. "alert", "invoice")
        template_vars  – Dict of template variables
        # Graph API fields (auto-detected from env)
        #   MSGRAPH_CLIENT_ID, MSGRAPH_CLIENT_SECRET, MSGRAPH_TENANT_ID
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._template_engine = EmailTemplateEngine()
        self._rate_limiter = EmailRateLimiter()
        self._graph_provider: Optional[GraphAPIEmailProvider] = None
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
    ) -> ActionResult:
        """Execute an email send operation.

        Never raises — always returns an ActionResult.
        """
        start = self._measure()

        # ── Resolve mode ────────────────────────────────────────
        mode = config.get("mode", "auto").lower()
        if mode not in _VALID_MODES:
            return ActionResult(
                False,
                {"mode": mode},
                f"Invalid mode: '{mode}'. Must be one of {sorted(_VALID_MODES)}",
                self._elapsed_ms(start),
            )

        # ── Resolve recipients ──────────────────────────────────
        recipients = resolve_recipients(config)
        if not recipients:
            return ActionResult(
                False,
                {"recipients": []},
                "No recipients specified (config.to is required)",
                self._elapsed_ms(start),
            )

        # Validate email addresses
        invalid = [r for r in recipients if not _validate_email(r)]
        if invalid:
            return ActionResult(
                False,
                {"invalid_recipients": invalid},
                f"Invalid email addresses: {invalid}",
                self._elapsed_ms(start),
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
                {
                    "rate_limited": True,
                    "denied_recipients": [
                        {"recipient": r.recipient, "reason": r.reason}
                        for r in denied
                    ],
                },
                f"Rate limited: {reasons}",
                self._elapsed_ms(start),
            )

        # ── Render template ─────────────────────────────────────
        rendered = self._template_engine.render_from_config(config)
        subject = rendered["subject"]
        body = rendered["body"]
        html = rendered["html"]

        # Config-level body/html override template if explicitly set
        # (only if template wasn't used)
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
                result = await self._execute_graph_api(
                    config, recipients, subject, body, html,
                )
            else:  # auto
                result = await self._execute_auto(
                    config, recipients, subject, body, html,
                )
        except Exception as exc:
            logger.error(
                "EmailExecutor: unhandled exception: %s", exc, exc_info=True,
            )
            with self._lock:
                self._failure_count += 1
            result = ActionResult(
                False,
                {"mode": mode, "recipients": recipients},
                f"Unexpected error: {exc}",
                self._elapsed_ms(start),
            )

        # Record rate limit counters on success
        if result.success:
            self._rate_limiter.record_send(recipients)

        # Ensure duration is set
        if result.duration_ms == 0.0:
            result.duration_ms = self._elapsed_ms(start)

        return result

    # ── Property: Executor Name ───────────────────────────────────

    @property
    def executor_name(self) -> str:
        return "EmailExecutor"

    # ── SMTP Implementation ────────────────────────────────────────

    async def _execute_smtp(
        self,
        config: Dict[str, Any],
        recipients: List[str],
        subject: str,
        body: str,
        html: str,
    ) -> ActionResult:
        """Send email via SMTP (aiosmtplib preferred, smtplib fallback)."""
        host = config.get("host", "") or os.environ.get("SMTP_HOST", "")
        port = config.get("port") or int(os.environ.get("SMTP_PORT", "587"))
        user = config.get("user", "") or os.environ.get("SMTP_USER", "")
        password = config.get("password", "") or os.environ.get("SMTP_PASSWORD", "")
        use_tls = config.get("use_tls", True)
        from_email = config.get("from_email", "") or user

        # Nothing configured → dry-run
        if not host:
            with self._lock:
                self._dry_run_count += 1
            return build_dry_run_result(recipients, subject, "smtp_not_configured")

        # Build MIME message
        msg = build_mime_message(
            from_email=from_email,
            recipients=recipients,
            subject=subject,
            body=body,
            html=html,
            cc=config.get("cc", []),
            bcc=config.get("bcc", []),
            reply_to=config.get("reply_to", ""),
            importance=config.get("importance", "normal"),
            attachments=config.get("attachments", []),
        )

        # Send via aiosmtplib or smtplib
        if _HAS_AIOSMTPLIB_LOCAL:
            success, error = await self._send_aiosmtplib(
                host, port, user, password, use_tls, from_email, recipients, msg,
            )
        else:
            success, error = await self._send_smtplib_sync(
                host, port, user, password, use_tls, from_email, recipients, msg,
            )

        if success:
            with self._lock:
                self._smtp_send_count += 1
            logger.info(
                "EmailExecutor: SMTP send success to %s (subject='%s')",
                recipients, subject[:50],
            )
            return ActionResult(
                True,
                {
                    "mode": "smtp",
                    "recipients": recipients,
                    "subject": subject,
                    "from": from_email,
                },
            )
        else:
            with self._lock:
                self._failure_count += 1
            return ActionResult(
                False,
                {"mode": "smtp", "recipients": recipients},
                f"SMTP send failed: {error}",
            )

    # ── Graph API Implementation ───────────────────────────────────

    async def _execute_graph_api(
        self,
        config: Dict[str, Any],
        recipients: List[str],
        subject: str,
        body: str,
        html: str,
    ) -> ActionResult:
        """Send email via Microsoft Graph API."""
        provider = self._get_or_create_graph_provider(config)
        from_email = config.get("from_email", "") or os.environ.get("MSGRAPH_FROM_EMAIL", "")

        result = await provider.send_email(
            to=recipients,
            subject=subject,
            body=body,
            html=html,
            cc=config.get("cc"),
            bcc=config.get("bcc"),
            from_email=from_email,
            attachments=config.get("attachments"),
            reply_to=[config["reply_to"]] if config.get("reply_to") else None,
            importance=config.get("importance", "normal"),
        )

        if result.get("success"):
            is_dry_run = result.get("dry_run", False)
            with self._lock:
                if is_dry_run:
                    self._dry_run_count += 1
                else:
                    self._graph_send_count += 1
            logger.info(
                "EmailExecutor: Graph API send %s to %s (subject='%s')",
                "dry-run" if is_dry_run else "success",
                recipients, subject[:50],
            )
            return ActionResult(
                True,
                {
                    "mode": "graph_api",
                    "recipients": recipients,
                    "subject": subject,
                    "message_id": result.get("message_id", ""),
                    "dry_run": is_dry_run,
                },
            )
        else:
            with self._lock:
                self._failure_count += 1
            return ActionResult(
                False,
                {"mode": "graph_api", "recipients": recipients},
                f"Graph API send failed: {result.get('error', 'unknown')}",
            )

    # ── Auto Mode Implementation ───────────────────────────────────

    async def _execute_auto(
        self,
        config: Dict[str, Any],
        recipients: List[str],
        subject: str,
        body: str,
        html: str,
    ) -> ActionResult:
        """Try Graph API first, fall back to SMTP."""
        # Check if Graph API is available
        provider = self._get_or_create_graph_provider(config)
        if provider.is_configured and _HAS_AIOHTTP:
            graph_result = await self._execute_graph_api(
                config, recipients, subject, body, html,
            )
            if graph_result.success:
                graph_result.data["mode"] = "auto (graph_api)"
                return graph_result
            logger.info(
                "EmailExecutor: Graph API failed, falling back to SMTP: %s",
                graph_result.error,
            )

        # Fall back to SMTP
        smtp_config = {**config, "mode": "smtp"}
        smtp_result = await self._execute_smtp(
            smtp_config, recipients, subject, body, html,
        )
        if smtp_result.success:
            smtp_result.data["mode"] = "auto (smtp)"
        return smtp_result

    # ── SMTP Helpers ───────────────────────────────────────────────

    async def _send_aiosmtplib(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        use_tls: bool,
        from_email: str,
        recipients: List[str],
        msg: email.mime.multipart.MIMEMultipart,
    ) -> tuple[bool, str]:
        """Send via aiosmtplib (async). Returns (success, error_message)."""
        import aiosmtplib  # type: ignore[import-unresolved]
        try:
            if use_tls:
                await aiosmtplib.send(
                    msg,
                    hostname=host,
                    port=port,
                    username=user or None,
                    password=password or None,
                    use_tls=True,
                    timeout=_SMTP_TIMEOUT,
                )
            else:
                await aiosmtplib.send(
                    msg,
                    hostname=host,
                    port=port,
                    username=user or None,
                    password=password or None,
                    start_tls=True,
                    timeout=_SMTP_TIMEOUT,
                )
            return True, ""
        except Exception as exc:
            return False, str(exc)

    async def _send_smtplib_sync(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        use_tls: bool,
        from_email: str,
        recipients: List[str],
        msg: email.mime.multipart.MIMEMultipart,
    ) -> tuple[bool, str]:
        """Send via smtplib (sync, wrapped in asyncio.to_thread)."""
        import email.mime.multipart  # ensure available in closure

        def _sync_send() -> tuple[bool, str]:
            try:
                if use_tls:
                    context = ssl.create_default_context()
                    with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT) as server:
                        server.ehlo()
                        server.starttls(context=context)
                        server.ehlo()
                        if user and password:
                            server.login(user, password)
                        server.sendmail(from_email, recipients, msg.as_string())
                else:
                    with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT) as server:
                        server.ehlo()
                        if user and password:
                            server.login(user, password)
                        server.sendmail(from_email, recipients, msg.as_string())
                return True, ""
            except Exception as exc:
                return False, str(exc)

        return await asyncio.to_thread(_sync_send)

    # ── Graph API Helpers ──────────────────────────────────────────

    def _get_or_create_graph_provider(
        self, config: Dict[str, Any],
    ) -> GraphAPIEmailProvider:
        """Get or create the GraphAPIEmailProvider instance."""
        with self._lock:
            if self._graph_provider is None:
                token_manager = OAuth2TokenManager()
                from_email = config.get("from_email", "") or os.environ.get("MSGRAPH_FROM_EMAIL", "")
                self._graph_provider = GraphAPIEmailProvider(
                    token_manager=token_manager,
                    service_name="msgraph",
                    from_email=from_email,
                )
            return self._graph_provider

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
                "aiosmtplib_available": _HAS_AIOSMTPLIB_LOCAL,
                "aiohttp_available": _HAS_AIOHTTP,
            }


__all__ = ["EmailExecutor"]
