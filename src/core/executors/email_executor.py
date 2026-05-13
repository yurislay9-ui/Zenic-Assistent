"""
ZENIC-AGENTS - EmailExecutor (Phase 7.1)

Ejecutor de envío de emails reales vía SMTP.
"""

import asyncio
import logging
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Any, Dict

from .base import ActionExecutor, ActionResult, _validate_email, _HAS_AIOSMTPLIB

logger = logging.getLogger(__name__)


class EmailExecutor(ActionExecutor):
    """Ejecutor de envío de emails reales vía SMTP.

    Usa aiosmtplib si disponible, sino smtplib (sync). Soporta HTML, CC, BCC, attachments.
    Si SMTP no configurado, funciona en modo dry-run (log).

    Config: {host, port, user, password, to, subject, body, html, cc, bcc, from_email, attachments}
    """
    def __init__(self):
        pass

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        host = config.get("host", os.environ.get("SMTP_HOST", ""))
        port = config.get("port", int(os.environ.get("SMTP_PORT", "587")))
        user = config.get("user", os.environ.get("SMTP_USER", ""))
        password = config.get("password", os.environ.get("SMTP_PASSWORD", ""))
        to_emails = config.get("to", [])
        subject = config.get("subject", "No Subject")
        body = config.get("body", "")
        html = config.get("html", "")
        cc = config.get("cc", [])
        bcc = config.get("bcc", [])
        from_email = config.get("from_email", user or "noreply@zenic-agents.local")
        attachments = config.get("attachments", [])

        # Normalizar destinatarios a listas
        if isinstance(to_emails, str): to_emails = [to_emails]
        if isinstance(cc, str): cc = [cc]
        if isinstance(bcc, str): bcc = [bcc]

        # Validar emails
        all_recipients = to_emails + cc + bcc
        invalid = [e for e in all_recipients if not _validate_email(e)]
        if invalid:
            return ActionResult(False, {"invalid_emails": invalid},
                                f"Invalid email format: {invalid}", self._elapsed_ms(start))
        if not to_emails:
            return ActionResult(False, {}, "No recipient emails provided", self._elapsed_ms(start))

        # Modo dry-run si no hay SMTP configurado
        if not host or not user:
            return await self._dry_run(from_email, to_emails, subject, body, html, cc, bcc, start)

        # Construir y enviar mensaje
        msg = self._build_message(from_email, to_emails, subject, body, html, cc, bcc, attachments)
        result = await self._send_with_retry(host, port, user, password, to_emails, msg)
        elapsed = self._elapsed_ms(start)

        if result:
            logger.info(f"EmailExecutor: Email sent to {to_emails} - '{subject}'")
            return ActionResult(True, {"recipients": to_emails, "subject": subject, "cc": cc, "bcc": bcc}, duration_ms=elapsed)
        return ActionResult(False, {"recipients": to_emails},
                            f"Failed to send email after retries to {to_emails}", elapsed)

    def _build_message(self, from_email, to_emails, subject, body, html, cc, bcc, attachments):
        """Construye el mensaje MIME para el email."""
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject
        if cc: msg["Cc"] = ", ".join(cc)

        if html: msg.attach(MIMEText(html, "html"))
        if body: msg.attach(MIMEText(body, "plain"))
        elif not html: msg.attach(MIMEText("", "plain"))

        for att_path in attachments:
            try:
                with open(att_path, "rb") as f:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f"attachment; filename={os.path.basename(att_path)}")
                    msg.attach(part)
            except Exception as e:
                logger.warning(f"EmailExecutor: Could not attach {att_path}: {e}")
        return msg

    async def _send_with_retry(self, host, port, user, password, to_emails, msg, max_retries=3):
        """Envía email con retry y exponential backoff."""
        all_rcpts = to_emails + [e for e in msg.get("Cc", "").split(", ") if e]
        for attempt in range(max_retries):
            try:
                if _HAS_AIOSMTPLIB:
                    import aiosmtplib
                    await aiosmtplib.send(msg.as_string(), hostname=host, port=port,
                                          username=user, password=password, start_tls=True)
                else:
                    await asyncio.to_thread(self._send_sync, host, port, user, password, all_rcpts, msg)
                return True
            except Exception as e:
                wait = (2 ** attempt) * 0.5
                logger.warning(f"EmailExecutor: Attempt {attempt+1}/{max_retries} failed: {e}. Retry in {wait}s")
                if attempt < max_retries - 1: await asyncio.sleep(wait)
        return False

    def _send_sync(self, host, port, user, password, recipients, msg):
        """Envío síncrono con smtplib (fallback)."""
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(msg["From"], recipients, msg.as_string())

    async def _dry_run(self, from_email, to_emails, subject, body, html, cc, bcc, start):
        """Modo dry-run: loguea el contenido del email sin enviarlo."""
        elapsed = self._elapsed_ms(start)
        logger.info(f"EmailExecutor [DRY-RUN]: From={from_email}, To={to_emails}, Subject={subject}")
        logger.info(f"  Body: {body[:200]}{'...' if len(body)>200 else ''}")
        if html: logger.info(f"  HTML: {html[:200]}{'...' if len(html)>200 else ''}")
        return ActionResult(True, {"mode": "dry_run", "from": from_email, "to": to_emails,
                                   "subject": subject, "cc": cc, "bcc": bcc}, duration_ms=elapsed)
