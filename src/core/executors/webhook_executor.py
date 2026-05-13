"""
ZENIC-AGENTS - WebhookExecutor (Phase 7.1)

Ejecutor de envío y verificación de webhooks con HMAC-SHA256.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

from .base import ActionExecutor, ActionResult, _validate_url
from .http_executor import HttpExecutor

logger = logging.getLogger(__name__)


class WebhookExecutor(ActionExecutor):
    """Ejecutor de envío y verificación de webhooks con HMAC-SHA256.

    Config: {action, url, method, payload, secret, verify_signature, verify_body}
    Actions: send, verify
    """

    def __init__(self, http_executor: Optional[HttpExecutor] = None) -> None:
        # Reuse a single HttpExecutor instance instead of creating new ones per call
        self._http_executor = http_executor or HttpExecutor()

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        action = config.get("action", "send").lower()
        try:
            if action == "send":
                result_data = await self._send_webhook(config)
            elif action == "verify":
                result_data = self._verify_webhook(config)
            else:
                return ActionResult(False, {"action": action},
                                    f"Invalid webhook action: {action}. Must be 'send' or 'verify'", self._elapsed_ms(start))
            return ActionResult(True, result_data, duration_ms=self._elapsed_ms(start))
        except Exception as e:
            return ActionResult(False, {"action": action}, str(e), self._elapsed_ms(start))

    async def _send_webhook(self, config):
        """Envía un webhook saliente con firma HMAC opcional."""
        url = config.get("url", "")
        method = config.get("method", "POST").upper()
        payload = config.get("payload", {})
        secret = config.get("secret", "")

        if not url: raise ValueError("Webhook URL is required for send action")
        if not _validate_url(url): raise ValueError(f"Invalid webhook URL: {url}")

        headers = {"Content-Type": "application/json"}
        body = json.dumps(payload) if isinstance(payload, (dict, list)) else str(payload)

        signature = ""
        if secret:
            signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"
            headers["X-Webhook-Timestamp"] = str(int(time.time()))

        result = await self._http_executor.execute({"url": url, "method": method, "body": payload,
                                                "headers": headers, "timeout": 30}, {})
        return {"action": "send", "url": url, "method": method,
                "signature": signature[:16] + "..." if signature else "",
                "response_status": result.data.get("status"),
                "response_body": result.data.get("body", "")[:500], "http_success": result.success}

    def _verify_webhook(self, config):
        """Verifica la firma HMAC-SHA256 de un webhook entrante.

        SECURITY (H-06 fix): Added max-length validation on signature
        to prevent memory exhaustion attacks with extremely long signatures.
        """
        secret = config.get("secret", "")
        signature = config.get("verify_signature", "")
        body = config.get("verify_body", "")

        if not secret: raise ValueError("Secret is required for webhook verification")
        if not signature: raise ValueError("Signature to verify is required")

        # SECURITY: Reject extremely long signatures to prevent memory exhaustion
        MAX_SIGNATURE_LENGTH = 256  # SHA-256 hex is 64 chars; allow some overhead
        if len(signature) > MAX_SIGNATURE_LENGTH:
            logger.warning("WebhookExecutor: Signature rejected (length=%d, max=%d)",
                           len(signature), MAX_SIGNATURE_LENGTH)
            raise ValueError(
                f"Signature too long: {len(signature)} chars (max {MAX_SIGNATURE_LENGTH})"
            )

        if signature.startswith("sha256="): signature = signature[7:]
        expected = hmac.new(secret.encode(), str(body).encode(), hashlib.sha256).hexdigest()
        is_valid = hmac.compare_digest(expected, signature)

        if is_valid: logger.info("WebhookExecutor: Signature verified successfully")
        else: logger.warning("WebhookExecutor: Signature verification FAILED")
        return {"action": "verify", "valid": is_valid, "algorithm": "HMAC-SHA256"}
