"""
ZENIC-AGENTS - NotificationExecutor (Phase 7.1)

Ejecutor de notificaciones multi-canal.
"""

import os, time, logging
from typing import Any, Dict, Optional

from .base import ActionExecutor, ActionResult
from .email_executor import EmailExecutor
from .http_executor import HttpExecutor

logger = logging.getLogger(__name__)


class NotificationExecutor(ActionExecutor):
    """Ejecutor de notificaciones multi-canal. Canales: log, email, telegram, webhook, discord.
    Delega a EmailExecutor para email y HttpExecutor para telegram/webhook.
    Fallback a logger.info() si no configurado.

    Config: {channel, recipient, message, subject, html}
    """

    def __init__(self, email_executor: Optional[EmailExecutor] = None,
                 webhook_executor: Optional["WebhookExecutor"] = None,
                 http_executor: Optional[HttpExecutor] = None) -> None:
        self._email_executor = email_executor
        self._webhook_executor = webhook_executor
        # Reuse a single HttpExecutor instance instead of creating new ones per call
        self._http_executor = http_executor or HttpExecutor()

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        channel = config.get("channel", "log").lower()
        recipient = config.get("recipient", "")
        message = config.get("message", "")
        subject = config.get("subject", "Notification")
        html = config.get("html", "")

        try:
            if channel == "log":
                result_data = self._notify_log(message, subject)
            elif channel == "email":
                result_data = await self._notify_email(recipient, message, subject, html)
            elif channel == "telegram":
                result_data = await self._notify_telegram(recipient, message)
            elif channel == "webhook":
                result_data = await self._notify_webhook(recipient, message, subject)
            else:
                logger.warning(f"NotificationExecutor: Unknown channel '{channel}', falling back to log")
                result_data = self._notify_log(message, subject)
                result_data["fallback"] = True; result_data["original_channel"] = channel

            return ActionResult(True, result_data, duration_ms=self._elapsed_ms(start))
        except Exception as e:
            logger.info(f"Notification [FALLBACK]: {message}")
            elapsed = self._elapsed_ms(start)
            return ActionResult(True, {"channel": "log", "fallback": True, "original_channel": channel},
                                f"Channel '{channel}' failed, fell back to log: {e}", elapsed)

    def _notify_log(self, message, subject=""):
        if subject: logger.info(f"Notification [{subject}]: {message}")
        else: logger.info(f"Notification: {message}")
        return {"channel": "log", "delivered": True}

    async def _notify_email(self, recipient, message, subject, html):
        if not self._email_executor:
            logger.info(f"Notification [email->log]: To: {recipient}, Subject: {subject}, Body: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True, "reason": "EmailExecutor not configured"}
        result = await self._email_executor.execute({"to": recipient, "subject": subject or "Notification",
                                                      "body": message, "html": html}, {})
        return {"channel": "email", "delivered": result.success, "email_result": result.data, "error": result.error}

    async def _notify_telegram(self, chat_id, message):
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        if not bot_token or not chat_id:
            logger.info(f"Notification [telegram->log]: Chat: {chat_id}, Msg: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True, "reason": "Telegram not configured"}
        try:
            result = await self._http_executor.execute({"url": f"https://api.telegram.org/bot{bot_token}/sendMessage",
                "method": "POST", "body": {"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
                "headers": {"Content-Type": "application/json"}, "timeout": 15}, {})
            return {"channel": "telegram", "delivered": result.success, "chat_id": chat_id}
        except Exception as e:
            logger.warning(f"NotificationExecutor: Telegram failed: {e}")
            logger.info(f"Notification [telegram->log]: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True}

    async def _notify_webhook(self, url, message, subject):
        if not url:
            logger.info(f"Notification [webhook->log]: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True, "reason": "No webhook URL"}
        try:
            result = await self._http_executor.execute({"url": url, "method": "POST",
                "body": {"message": message, "subject": subject, "timestamp": time.time()},
                "headers": {"Content-Type": "application/json"}, "timeout": 15}, {})
            return {"channel": "webhook", "delivered": result.success, "url": url,
                    "response_status": result.data.get("status")}
        except Exception as e:
            logger.warning(f"NotificationExecutor: Webhook failed: {e}")
            logger.info(f"Notification [webhook->log]: {message[:200]}")
            return {"channel": "log", "delivered": True, "fallback": True}
