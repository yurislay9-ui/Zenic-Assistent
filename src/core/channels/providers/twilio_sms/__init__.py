"""
ZENIC-AGENTS — Twilio SMS Channel Provider

Outbound: Twilio REST API (SMS/MMS)
Inbound:  Twilio webhook callbacks with signature verification

Supports:
  - SMS (160 chars/segment, auto-splitting)
  - MMS (media attachments via URL)
  - Webhook signature verification (Twilio HMAC-SHA1)
  - From/To number management
  - Rate limit awareness (Twilio API limits)
  - Retry with exponential backoff
  - Dry-run mode when no credentials configured

Configuration (env vars or constructor):
  - TWILIO_ACCOUNT_SID:  Account SID (ACxxxx)
  - TWILIO_AUTH_TOKEN:   Auth token
  - TWILIO_PHONE_NUMBER: From phone number (+1xxx)

Design invariants:
  1. Never raises — always returns ChannelResponse.
  2. HMAC-SHA1 verification for inbound webhooks (Twilio standard).
  3. Uses aiohttp when available, falls back to urllib.
  4. SMS text auto-truncated to 160 chars per segment.
  5. Dry-run mode when unconfigured.
  6. Thread-safe stats.
  7. No heavy SDK dependencies — pure HTTP.
"""

from __future__ import annotations

from ._sender import TwilioSMSChannelProviderBase
from ._webhook import TwilioWebhookMixin


class TwilioSMSChannelProvider(TwilioSMSChannelProviderBase, TwilioWebhookMixin):
    """Twilio SMS/MMS channel provider.

    Combines outbound (send) and inbound (webhook) functionality.

    Supports:
      - Outbound: SMS and MMS via Twilio REST API
      - Inbound: Webhook callbacks with signature verification
      - Auto-splitting long messages into segments
      - Dry-run mode when unconfigured

    Complexity: 🟢 Low — straightforward REST API with form-encoded POSTs.
    """


__all__ = ["TwilioSMSChannelProvider"]
