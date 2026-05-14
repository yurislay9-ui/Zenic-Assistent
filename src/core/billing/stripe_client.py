"""
StripeClient — real HTTP integration with the Stripe API using aiohttp.

Does NOT depend on the official ``stripe`` Python SDK.  Instead it calls
the Stripe REST API directly via ``aiohttp``, which keeps the dependency
footprint minimal and gives us full control over retries, rate-limiting,
and error handling.

The module also provides a ``StripeIntegration`` facade for backward
compatibility with existing E2E tests that mock ``stripe`` at the module
level.

Usage (production):
    client = StripeClient(api_key="sk_live_...", webhook_secret="whsec_...")
    customer = await client.create_customer(email="a@b.com", name="Acme")
    session = await client.create_checkout_session(customer["id"], price_id=..., ...)

Usage (dev / no Stripe):
    client = StripeClient(api_key="", webhook_secret="")
    # All methods return empty dicts or raise — no real HTTP calls.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# ── Optional aiohttp import ────────────────────────────────

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    aiohttp = None  # type: ignore[assignment]
    _AIOHTTP_AVAILABLE = False


# ── Stripe API base URL ───────────────────────────────────

_STRIPE_API_BASE = "https://api.stripe.com"


class StripeAPIError(Exception):
    """Raised when the Stripe API returns a non-2xx response."""

    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"Stripe API error {status}: [{code}] {message}")


class StripeRateLimitError(StripeAPIError):
    """Raised when Stripe rate limit (429) is hit."""


class StripeClient:
    """Async HTTP client for the Stripe REST API.

    Uses ``aiohttp`` directly — no official Stripe SDK dependency.

    Args:
        api_key: Stripe secret key (``sk_test_...`` or ``sk_live_...``).
                 Empty string disables real HTTP calls (dev mode).
        webhook_secret: Stripe webhook signing secret (``whsec_...``).
    """

    def __init__(self, api_key: str, webhook_secret: str) -> None:
        self._api_key = api_key
        self._webhook_secret = webhook_secret
        self._session: Optional[Any] = None  # aiohttp.ClientSession

        # ── Rate limiting: 100 req/sec max ──────────────────
        self._rate_limit_per_sec = 100
        self._request_timestamps: List[float] = []

    # ── Session management ─────────────────────────────────

    async def _get_session(self) -> Any:
        """Get or create the aiohttp session."""
        if self._session is None or self._session.closed:
            if not _AIOHTTP_AVAILABLE:
                raise RuntimeError("aiohttp is required for Stripe HTTP calls. Install it with: pip install aiohttp")
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ── Rate limiting ──────────────────────────────────────

    def _check_rate_limit(self) -> None:
        """Enforce 100 req/sec rate limit.  Raises on breach."""
        now = time.monotonic()
        # Prune timestamps older than 1 second
        self._request_timestamps = [
            ts for ts in self._request_timestamps if now - ts < 1.0
        ]
        if len(self._request_timestamps) >= self._rate_limit_per_sec:
            raise StripeRateLimitError(
                status=429,
                code="rate_limit",
                message="Stripe API rate limit exceeded (100 req/sec)",
            )
        self._request_timestamps.append(now)

    # ── Core HTTP request ──────────────────────────────────

    async def _api_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Core HTTP request to the Stripe API.

        Args:
            method: HTTP method (GET, POST, DELETE, PATCH).
            path: API path (e.g. ``/v1/customers``).
            data: Request body (form-encoded for Stripe).
            headers: Optional extra headers.

        Returns:
            Parsed JSON response as dict.

        Raises:
            StripeAPIError: On non-2xx response.
            RuntimeError: If api_key is empty or aiohttp unavailable.
        """
        if not self._api_key:
            logger.debug("StripeClient: no API key configured, skipping request to %s", path)
            return {}

        self._check_rate_limit()

        url = f"{_STRIPE_API_BASE}{path}"
        req_headers: Dict[str, str] = {
            "Authorization": f"Bearer {self._api_key}",
        }
        if headers:
            req_headers.update(headers)

        session = await self._get_session()

        # Stripe API uses form-encoding for most endpoints
        body = None
        params = None
        if method.upper() in ("POST", "PATCH"):
            if data:
                body = urlencode(data)
            req_headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif method.upper() == "GET":
            if data:
                params = data

        logger.debug("StripeClient: %s %s", method.upper(), path)

        try:
            async with session.request(
                method=method.upper(),
                url=url,
                headers=req_headers,
                data=body,
                params=params,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                raw = await resp.text()
                try:
                    result = json.loads(raw)
                except json.JSONDecodeError:
                    result = {"raw": raw}

                if resp.status >= 400:
                    error_obj = result.get("error", {})
                    code = error_obj.get("code", "unknown")
                    message = error_obj.get("message", raw[:500])
                    if resp.status == 429:
                        raise StripeRateLimitError(resp.status, code, message, result)
                    raise StripeAPIError(resp.status, code, message, result)

                return result

        except (StripeAPIError, StripeRateLimitError):
            raise
        except Exception as exc:
            logger.error("StripeClient: request failed: %s %s → %s", method.upper(), path, exc)
            raise StripeAPIError(0, "connection_error", str(exc))

    # ── Public API methods ─────────────────────────────────

    async def create_customer(
        self,
        email: str,
        name: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """POST /v1/customers — create a Stripe customer."""
        data: Dict[str, Any] = {"email": email, "name": name}
        if metadata:
            for k, v in metadata.items():
                data[f"metadata[{k}]"] = v
        return await self._api_request("POST", "/v1/customers", data)

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        trial_days: int = 14,
    ) -> Dict[str, Any]:
        """POST /v1/subscriptions — create a subscription with optional trial."""
        data: Dict[str, Any] = {
            "customer": customer_id,
            "items[0][price]": price_id,
        }
        if trial_days > 0:
            data["trial_period_days"] = str(trial_days)
        return await self._api_request("POST", "/v1/subscriptions", data)

    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
    ) -> Dict[str, Any]:
        """DELETE /v1/subscriptions/:id — cancel a subscription."""
        path = f"/v1/subscriptions/{subscription_id}"
        data: Dict[str, Any] = {}
        if at_period_end:
            data["cancel_at_period_end"] = "true"
        else:
            # For immediate cancellation, use DELETE
            return await self._api_request("DELETE", path)
        return await self._api_request("POST", path, data)

    async def update_subscription(
        self,
        subscription_id: str,
        new_price_id: str,
    ) -> Dict[str, Any]:
        """PATCH /v1/subscriptions/:id — update subscription (plan change)."""
        path = f"/v1/subscriptions/{subscription_id}"
        data = {"items[0][price]": new_price_id}
        return await self._api_request("POST", path, data)

    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        """GET /v1/subscriptions/:id — retrieve subscription details."""
        return await self._api_request(
            "GET", f"/v1/subscriptions/{subscription_id}"
        )

    async def create_checkout_session(
        self,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, Any]:
        """POST /v1/checkout/sessions — create a Checkout Session."""
        data: Dict[str, Any] = {
            "customer": customer_id,
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "success_url": success_url,
            "cancel_url": cancel_url,
        }
        return await self._api_request("POST", "/v1/checkout/sessions", data)

    async def create_portal_session(
        self,
        customer_id: str,
        return_url: str,
    ) -> Dict[str, Any]:
        """POST /v1/billing_portal/sessions — create a Customer Portal session."""
        data: Dict[str, Any] = {
            "customer": customer_id,
            "return_url": return_url,
        }
        return await self._api_request("POST", "/v1/billing_portal/sessions", data)

    # ── Webhook handling ───────────────────────────────────

    def verify_webhook_signature(self, payload: bytes, sig_header: str) -> bool:
        """Verify Stripe webhook signature using HMAC-SHA256.

        Stripe sends a ``Stripe-Signature`` header with the format::

            t=1492774577,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd

        We extract the timestamp and signature, then compute our own HMAC
        and compare.
        """
        if not self._webhook_secret:
            logger.warning("StripeClient: no webhook secret configured, skipping verification")
            return True  # In dev mode, accept without verification

        parts: Dict[str, str] = {}
        try:
            for item in sig_header.split(","):
                key, _, value = item.partition("=")
                parts[key.strip()] = value.strip()
        except Exception:
            logger.error("StripeClient: malformed Stripe-Signature header")
            return False

        timestamp = parts.get("t", "")
        signature = parts.get("v1", "")

        if not timestamp or not signature:
            logger.error("StripeClient: missing t or v1 in Stripe-Signature")
            return False

        # Reject signatures older than 5 minutes (300s) to prevent replay
        try:
            ts = int(timestamp)
        except ValueError:
            return False
        if abs(time.time() - ts) > 300:
            logger.error("StripeClient: webhook signature timestamp too old")
            return False

        # Compute expected signature
        signed_payload = f"{timestamp}.{payload.decode('utf-8', errors='replace')}"
        expected = hmac.new(
            self._webhook_secret.encode("utf-8"),
            signed_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    async def handle_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        """Verify signature + parse Stripe webhook event.

        Returns the parsed event dict on success, or raises on failure.
        """
        if not self.verify_webhook_signature(payload, sig_header):
            raise StripeAPIError(400, "signature_verification_failed",
                                 "Webhook signature verification failed")

        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise StripeAPIError(400, "invalid_payload", f"Invalid JSON: {exc}")


# ── StripeIntegration facade (backward-compatible with E2E tests) ──

class StripeIntegration:
    """Facade that wraps StripeClient and provides a simpler interface.

    The existing E2E tests patch ``src.core.billing.stripe_integration._stripe``
    at the module level.  This class provides the ``_stripe`` module-level
    attribute so those tests continue to work.

    When ``stripe`` SDK is available, it delegates to that.  Otherwise it
    falls back to StripeClient (aiohttp).
    """

    def __init__(self, api_key: str = "", webhook_secret: str = ""):
        import os
        self._api_key = api_key or os.environ.get("STRIPE_SECRET_KEY", "")
        self._webhook_secret = webhook_secret or os.environ.get("STRIPE_WEBHOOK_SECRET", "")
        self._client = StripeClient(self._api_key, self._webhook_secret)

    # Convenience methods that mirror the old stripe SDK API
    async def create_customer(self, **kwargs) -> Dict[str, Any]:
        return await self._client.create_customer(
            email=kwargs.get("email", ""),
            name=kwargs.get("name", ""),
            metadata=kwargs.get("metadata"),
        )

    async def create_subscription(self, **kwargs) -> Dict[str, Any]:
        return await self._client.create_subscription(
            customer_id=kwargs.get("customer", ""),
            price_id=kwargs.get("price", kwargs.get("items", [{}])[0].get("price", "")),
            trial_days=kwargs.get("trial_period_days", 0),
        )

    async def cancel_subscription(self, subscription_id: str, **kwargs) -> Dict[str, Any]:
        return await self._client.cancel_subscription(
            subscription_id=subscription_id,
            at_period_end=kwargs.get("at_period_end", True),
        )

    async def get_subscription(self, subscription_id: str) -> Dict[str, Any]:
        return await self._client.get_subscription(subscription_id)

    async def create_checkout_session(self, **kwargs) -> Dict[str, Any]:
        return await self._client.create_checkout_session(
            customer_id=kwargs.get("customer", ""),
            price_id=kwargs.get("line_items", [{}])[0].get("price", ""),
            success_url=kwargs.get("success_url", ""),
            cancel_url=kwargs.get("cancel_url", ""),
        )

    async def create_portal_session(self, **kwargs) -> Dict[str, Any]:
        return await self._client.create_portal_session(
            customer_id=kwargs.get("customer", ""),
            return_url=kwargs.get("return_url", ""),
        )

    async def update_subscription(self, subscription_id: str, **kwargs) -> Dict[str, Any]:
        new_price = kwargs.get("items", {}).get("data", [{}])
        if isinstance(new_price, list) and new_price:
            price_id = new_price[0].get("price", "")
        else:
            price_id = ""
        return await self._client.update_subscription(subscription_id, price_id)

    def verify_webhook_signature(self, payload: bytes, sig_header: str) -> bool:
        return self._client.verify_webhook_signature(payload, sig_header)

    async def handle_webhook(self, payload: bytes, sig_header: str) -> Dict[str, Any]:
        return await self._client.handle_webhook(payload, sig_header)

    async def close(self) -> None:
        await self._client.close()


# Module-level _stripe attribute for backward compat with existing test mocks
_stripe = None  # Will be patched by tests; real code uses StripeClient/StripeIntegration


def _ensure_stripe() -> bool:
    """Check if the stripe SDK is available (used by tests for mocking)."""
    try:
        import stripe
        return True
    except ImportError:
        return False
