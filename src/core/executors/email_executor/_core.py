"""email_executor — Core implementation (composed from mixins)."""

from __future__ import annotations

from ._mixin_core import EmailExecutorCoreMixin
from ._mixin_send import EmailExecutorSendMixin


class EmailExecutor(EmailExecutorCoreMixin, EmailExecutorSendMixin):
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
        attachments    – List of attachment dicts
        reply_to       – Reply-to email address
        importance     – "low", "normal", "high"
        # Template fields
        template       – Template name (e.g. "alert", "invoice")
        template_vars  – Dict of template variables
    """


__all__ = ["EmailExecutor"]
