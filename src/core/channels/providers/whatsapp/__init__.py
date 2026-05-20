"""
ZENIC-AGENTS — WhatsApp Business Channel Provider

Outbound: Cloud API (Graph API) REST calls
Inbound:  Webhook callbacks with HMAC-SHA256 signature verification

Supports:
  - Text messages with URL previews
  - Interactive button messages (up to 3 buttons)
  - Message templates
  - Media messages (image, document, video, audio) via URLs
  - Webhook signature verification (HMAC-SHA256)
  - Rate limit tracking (WhatsApp API limits)
  - Retry with exponential backoff
  - Dry-run mode when no access token configured

Configuration (env vars or constructor):
  - WHATSAPP_ACCESS_TOKEN:  Meta access token
  - WHATSAPP_PHONE_NUMBER_ID: Business phone number ID
  - WHATSAPP_VERIFY_TOKEN:  Webhook verification token (for inbound setup)
  - WHATSAPP_APP_SECRET:    App secret for HMAC signature verification

⚠️ REQUIRES: Meta Business Account + Phone Number ID + Access Token

Design invariants:
  1. Never raises — always returns ChannelResponse.
  2. HMAC-SHA256 verification for all inbound webhooks.
  3. Uses aiohttp when available, falls back to urllib.
  4. Dry-run mode when unconfigured.
  5. Thread-safe stats.
  6. No heavy SDK dependencies — pure HTTP.
"""

from __future__ import annotations

from ._sender import WhatsAppChannelProviderBase
from ._webhook import WhatsAppWebhookMixin


class WhatsAppChannelProvider(WhatsAppChannelProviderBase, WhatsAppWebhookMixin):
    """WhatsApp Business Cloud API channel provider.

    Combines outbound (send) and inbound (webhook) functionality.

    Supports:
      - Outbound: Text, interactive buttons, media, templates
      - Inbound: Webhook callbacks with HMAC verification
      - Dry-run mode when unconfigured
    """


__all__ = ["WhatsAppChannelProvider"]
