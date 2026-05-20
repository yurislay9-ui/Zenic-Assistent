"""
ZENIC-AGENTS — Channel Providers

Phase 1 implementations:
  - TeamsChannelProvider    — Microsoft Teams (Incoming Webhooks + Adaptive Cards)
  - SlackChannelProvider    — Slack (Block Kit + Events API / Socket Mode)
  - WhatsAppChannelProvider — WhatsApp Business Cloud API
  - TwilioSMSChannelProvider — SMS/MMS via Twilio

Phase 2 implementations:
  - PushChannelProvider     — Push Notifications (Web Push VAPID + FCM HTTP v1)
  - EmailChannelProvider    — Email (SMTP + Microsoft Graph API)
"""

from .teams import TeamsChannelProvider
from .slack import SlackChannelProvider
from .whatsapp import WhatsAppChannelProvider
from .twilio_sms import TwilioSMSChannelProvider
from .push import PushChannelProvider
from .email import EmailChannelProvider

__all__ = [
    "TeamsChannelProvider",
    "SlackChannelProvider",
    "WhatsAppChannelProvider",
    "TwilioSMSChannelProvider",
    "PushChannelProvider",
    "EmailChannelProvider",
]
