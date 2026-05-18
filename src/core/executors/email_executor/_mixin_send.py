"""email_executor — Send mixin (SMTP, Graph API, MIME)."""

from __future__ import annotations

import asyncio
import email
import email.encoders
import email.mime.base
import email.mime.multipart
import email.mime.text
import email.utils
import os
import ssl
import smtplib
from typing import Any, Dict, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _send_via_smtp, _send_via_graph_api, _dry_run_send, _intercept_smtp, _intercept_http, _intercept_db, _intercept_file, _record_operation


class EmailExecutorSendMixin:
    """SMTP, Graph API, and MIME building methods for EmailExecutor."""

    # ── SMTP Implementation ────────────────────────────────────────

    async def _execute_smtp(
        self,
        config: Dict[str, Any],
        recipients: List[str],
        subject: str,
        body: str,
        html: str,
    ) -> ActionResult:  # noqa: F821
        """Send email via SMTP (aiosmtplib preferred, smtplib fallback)."""
        host = config.get("host", "") or os.environ.get("SMTP_HOST", "")
        port = config.get("port") or int(os.environ.get("SMTP_PORT", "587"))
        user = config.get("user", "") or os.environ.get("SMTP_USER", "")
        password = config.get("password", "") or os.environ.get("SMTP_PASSWORD", "")
        use_tls = config.get("use_tls", True)
        from_email = config.get("from_email", "") or user

        if not host:
            with self._lock:
                self._dry_run_count += 1
            return self._dry_run_result(recipients, subject, "smtp_not_configured")

        msg = self._build_mime_message(
            from_email=from_email, recipients=recipients, subject=subject,
            body=body, html=html, cc=config.get("cc", []),
            bcc=config.get("bcc", []), reply_to=config.get("reply_to", ""),
            importance=config.get("importance", "normal"),
            attachments=config.get("attachments", []),
        )

        if _HAS_AIOSMTPLIB_LOCAL:  # noqa: F821
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
            __import__("logging").getLogger("zenic_agents.executors.email_executor").info(
                "EmailExecutor: SMTP send success to %s (subject='%s')",
                recipients, subject[:50],
            )
            return ActionResult(
                True,
                {"mode": "smtp", "recipients": recipients, "subject": subject, "from": from_email},
            )
        else:
            with self._lock:
                self._failure_count += 1
            return ActionResult(
                False, {"mode": "smtp", "recipients": recipients},
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
    ) -> ActionResult:  # noqa: F821
        """Send email via Microsoft Graph API."""
        provider = self._get_or_create_graph_provider(config)
        from_email = config.get("from_email", "") or os.environ.get("MSGRAPH_FROM_EMAIL", "")

        result = await provider.send_email(
            to=recipients, subject=subject, body=body, html=html,
            cc=config.get("cc"), bcc=config.get("bcc"),
            from_email=from_email, attachments=config.get("attachments"),
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
            __import__("logging").getLogger("zenic_agents.executors.email_executor").info(
                "EmailExecutor: Graph API send %s to %s (subject='%s')",
                "dry-run" if is_dry_run else "success",
                recipients, subject[:50],
            )
            return ActionResult(
                True,
                {"mode": "graph_api", "recipients": recipients, "subject": subject,
                 "message_id": result.get("message_id", ""), "dry_run": is_dry_run},
            )
        else:
            with self._lock:
                self._failure_count += 1
            return ActionResult(
                False, {"mode": "graph_api", "recipients": recipients},
                f"Graph API send failed: {result.get('error', 'unknown')}",
            )

    # ── SMTP Helpers ───────────────────────────────────────────────

    @staticmethod
    def _build_mime_message(
        from_email: str,
        recipients: List[str],
        subject: str,
        body: str,
        html: str,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: str = "",
        importance: str = "normal",
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> email.mime.multipart.MIMEMultipart:
        """Build a MIME message for SMTP sending."""
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = from_email
        msg["To"] = ", ".join(recipients)
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = ", ".join(cc)
        if reply_to:
            msg["Reply-To"] = reply_to
        if importance and importance != "normal":
            msg["X-Priority"] = {"low": "5", "high": "1"}.get(importance, "3")
            msg["Importance"] = importance

        msg["Message-ID"] = email.utils.make_msgid(
            domain=from_email.split("@")[-1] if "@" in from_email else "localhost"
        )

        if body:
            msg.attach(email.mime.text.MIMEText(body, "plain", "utf-8"))
        if html:
            msg.attach(email.mime.text.MIMEText(html, "html", "utf-8"))
        if not body and not html:
            msg.attach(email.mime.text.MIMEText(" ", "plain", "utf-8"))

        for att in (attachments or []):
            part = email.mime.base.MIMEBase(
                "application", att.get("content_type", "octet-stream"),
            )
            content = att.get("content_bytes", b"")
            if isinstance(content, str):
                content = content.encode("utf-8")
            part.set_payload(content)
            email.encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{att.get("name", "attachment")}"',
            )
            msg.attach(part)

        return msg

    async def _send_aiosmtplib(
        self,
        host: str, port: int, user: str, password: str,
        use_tls: bool, from_email: str, recipients: List[str],
        msg: email.mime.multipart.MIMEMultipart,
    ) -> tuple[bool, str]:
        """Send via aiosmtplib (async)."""
        try:
            if use_tls:
                await aiosmtplib.send(  # noqa: F821
                    msg, hostname=host, port=port,
                    username=user or None, password=password or None,
                    use_tls=True, timeout=_SMTP_TIMEOUT,  # noqa: F821
                )
            else:
                await aiosmtplib.send(
                    msg, hostname=host, port=port,
                    username=user or None, password=password or None,
                    start_tls=True, timeout=_SMTP_TIMEOUT,  # noqa: F821
                )
            return True, ""
        except Exception as exc:
            return False, str(exc)

    async def _send_smtplib_sync(
        self,
        host: str, port: int, user: str, password: str,
        use_tls: bool, from_email: str, recipients: List[str],
        msg: email.mime.multipart.MIMEMultipart,
    ) -> tuple[bool, str]:
        """Send via smtplib (sync, wrapped in asyncio.to_thread)."""

        def _sync_send() -> tuple[bool, str]:
            try:
                if use_tls:
                    context = ssl.create_default_context()
                    with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT) as server:  # noqa: F821
                        server.ehlo()
                        server.starttls(context=context)
                        server.ehlo()
                        if user and password:
                            server.login(user, password)
                        server.sendmail(from_email, recipients, msg.as_string())
                else:
                    with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT) as server:  # noqa: F821
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
    ) -> "GraphAPIEmailProvider":  # noqa: F821
        """Get or create the GraphAPIEmailProvider instance."""
        with self._lock:
            if self._graph_provider is None:
                from ..email_parts.graph_api import GraphAPIEmailProvider, OAuth2TokenManager
                token_manager = OAuth2TokenManager()
                from_email = config.get("from_email", "") or os.environ.get("MSGRAPH_FROM_EMAIL", "")
                self._graph_provider = GraphAPIEmailProvider(
                    token_manager=token_manager, service_name="msgraph",
                    from_email=from_email,
                )
            return self._graph_provider
