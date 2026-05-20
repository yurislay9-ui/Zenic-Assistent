"""email — Core implementation (class definition + lifecycle)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from ._types import *  # noqa: F403
from ._helpers import (
    _render_fields_table, _build_confirmation_html,
    _build_confirmation_text, _dry_run_send, _dry_run_confirmation,
)
from ._transport import EmailTransportMixin


class EmailChannelProvider(EmailTransportMixin):
    """Email channel provider implementing the ChannelProvider protocol.

    Wraps EmailExecutor functionality as a channel provider for the
    unified channel system. Supports SMTP, Microsoft Graph API, and
    auto mode (tries Graph API first, falls back to SMTP).

    Capabilities:
      - SEND_TEXT          → Plain text emails
      - SEND_RICH          → Template-based rich emails with fields table
      - SEND_HTML          → HTML body emails
      - SEND_FILE          → File attachments
      - SEND_CONFIRMATION  → Confirmation emails with action links
    """

    def __init__(
        self,
        mode: str = "auto",
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        graph_client_id: Optional[str] = None,
        graph_client_secret: Optional[str] = None,
        graph_tenant_id: Optional[str] = None,
        graph_from_email: Optional[str] = None,
    ) -> None:
        """Initialize the email channel provider."""
        mode = mode.lower()
        if mode not in _VALID_MODES:  # noqa: F821
            mode = "auto"
        self._mode = mode

        # SMTP config (env fallbacks)
        self._smtp_host = smtp_host or os.environ.get("SMTP_HOST", "")
        self._smtp_port = smtp_port or int(os.environ.get("SMTP_PORT", "587"))
        self._smtp_user = smtp_user or os.environ.get("SMTP_USER", "")
        self._smtp_password = smtp_password or os.environ.get("SMTP_PASSWORD", "")

        # Graph API config (env fallbacks)
        self._graph_client_id = graph_client_id or os.environ.get("MSGRAPH_CLIENT_ID", "")
        self._graph_client_secret = graph_client_secret or os.environ.get("MSGRAPH_CLIENT_SECRET", "")
        self._graph_tenant_id = graph_tenant_id or os.environ.get("MSGRAPH_TENANT_ID", "")
        self._graph_from_email = graph_from_email or os.environ.get("MSGRAPH_FROM_EMAIL", "")

        # Internal state
        import threading
        self._lock = threading.Lock()
        self._sent_count: int = 0
        self._failed_count: int = 0
        self._confirmation_count: int = 0
        self._dry_run_count: int = 0
        self._started: bool = False
        self._rate_limit_info = RateLimitInfo()  # noqa: F821
        self._executor: Optional[Any] = None  # Lazy-initialized EmailExecutor

    async def start(self) -> None:
        """Initialize the provider. Idempotent."""
        if self._started:
            return
        self._get_executor()
        self._started = True
        __import__("logging").getLogger("zenic_agents.channels.email").info(
            "EmailChannelProvider: started (mode=%s, smtp=%s, graph_api=%s)",
            self._mode, self._is_smtp_configured(), self._is_graph_api_configured(),
        )

    async def stop(self) -> None:
        """Gracefully shut down the provider. Idempotent."""
        self._started = False
        __import__("logging").getLogger("zenic_agents.channels.email").info("EmailChannelProvider: stopped")

    @property
    def stats(self) -> Dict[str, Any]:
        """Provider statistics for monitoring and health checks."""
        with self._lock:
            return {
                "name": "email",
                "mode": self._mode,
                "sent_count": self._sent_count,
                "failed_count": self._failed_count,
                "confirmation_count": self._confirmation_count,
                "dry_run_count": self._dry_run_count,
                "is_available": self.is_available,
                "smtp_configured": self._is_smtp_configured(),
                "graph_api_configured": self._is_graph_api_configured(),
                "started": self._started,
            }

    @property
    def rate_limit_info(self) -> "RateLimitInfo":  # noqa: F821
        """Current rate limit status."""
        return self._rate_limit_info


__all__ = ["EmailChannelProvider"]
