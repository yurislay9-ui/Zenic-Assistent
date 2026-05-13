"""
ZENIC-AGENTS — WebhookIngestionEngine (B1: Event-driven Actions Engine)

Inbound webhook handler that receives external HTTP webhooks,
verifies HMAC signatures, validates payloads, and dispatches
events through the TriggerMap.

Usage:
    engine = WebhookIngestionEngine()
    eid = engine.register_endpoint("/webhooks/stripe", "tenant_1", "payment.received", secret="whsec_abc")
    result = engine.process_inbound(
        "/webhooks/stripe",
        {"X-Hub-Signature-256": "sha256=abcdef..."},
        b'{"event": "payment.success"}',
        "tenant_1",
    )
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from .schema_registry import EventSchemaRegistry, get_schema_registry
from .trigger_map import TriggerMap, get_trigger_map

logger = logging.getLogger("zenic_agents.events.webhook_ingestion")

DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
DB_PATH = os.path.join(DB_DIR, "webhook_ingestion.sqlite")

# Retry configuration for event dispatch
_MAX_DISPATCH_RETRIES = 3
_DISPATCH_RETRY_BACKOFF_BASE = 1.0  # seconds


# ─── Dataclasses ────────────────────────────────────────────────

@dataclass
class InboundEvent:
    """
    An event extracted from an inbound webhook, ready for dispatch.

    Attributes:
        event_type: The event type to emit.
        event_data: The parsed payload.
        source: Origin description (e.g. "webhook:/webhooks/stripe").
    """
    event_type: str
    event_data: dict[str, Any]
    source: str = ""


@dataclass
class InboundWebhookResult:
    """
    Result of processing an inbound webhook request.

    Attributes:
        success: Whether processing completed without fatal errors.
        endpoint_id: The matched endpoint ID (empty if no match).
        event_type: The resolved event type.
        events_dispatched: Number of automations triggered.
        errors: List of error messages encountered.
    """
    success: bool
    endpoint_id: str = ""
    event_type: str = ""
    events_dispatched: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class WebhookEndpoint:
    """
    A registered inbound webhook endpoint.

    Attributes:
        endpoint_id: Unique identifier.
        path: URL path (e.g. "/webhooks/stripe").
        tenant_id: Owner tenant.
        event_type: Event type to emit when webhook received.
        secret: Optional HMAC secret for signature verification.
        enabled: Whether the endpoint is active.
        created_at: Unix timestamp.
        call_count: Number of times this endpoint has been called.
        last_call_at: Timestamp of last call, or 0.0.
    """
    endpoint_id: str
    path: str
    tenant_id: str
    event_type: str
    secret: str | None = None
    enabled: bool = True
    created_at: float = field(default_factory=time.time)
    call_count: int = 0
    last_call_at: float = 0.0


# ─── HMAC Verification ─────────────────────────────────────────

def _verify_hmac_sha256(
    secret: str,
    body: bytes,
    signature_header: str,
) -> bool:
    """
    Verify an HMAC-SHA256 signature using timing-safe comparison.

    Expected header format: "sha256=<hex_digest>"
    """
    if not signature_header.startswith("sha256="):
        logger.warning("WebhookIngestion: signature header missing 'sha256=' prefix")
        return False

    provided_sig = signature_header[7:]
    # Reject excessively long signatures (security: prevent memory exhaustion)
    if len(provided_sig) > 256:
        logger.warning(
            "WebhookIngestion: signature too long (%d chars)", len(provided_sig),
        )
        return False

    expected_sig = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, provided_sig)


# ─── Endpoint Serialization ─────────────────────────────────────

def _endpoint_from_row(row: sqlite3.Row) -> WebhookEndpoint:
    """Deserialize a WebhookEndpoint from a SQLite row."""
    return WebhookEndpoint(
        endpoint_id=row["endpoint_id"],
        path=row["path"],
        tenant_id=row["tenant_id"],
        event_type=row["event_type"],
        secret=row["secret"] if row["secret"] else None,
        enabled=bool(row["enabled"]),
        created_at=row["created_at"],
        call_count=row["call_count"],
        last_call_at=row["last_call_at"],
    )


# ─── WebhookIngestionEngine ────────────────────────────────────

class WebhookIngestionEngine:
    """
    Inbound webhook handler that receives external webhooks as triggers.

    Process:
      1. Match path to registered endpoint
      2. Verify HMAC signature if secret is configured
      3. Parse JSON body
      4. Validate payload via EventSchemaRegistry
      5. Emit event via TriggerMap
      6. Retry on dispatch failures (3 retries, 1s backoff)

    Thread-safe with RLock. Persisted to SQLite.
    Singleton pattern via get_webhook_ingestion() / reset_webhook_ingestion().
    """

    def __init__(
        self,
        db_path: str | None = None,
        trigger_map: TriggerMap | None = None,
        schema_registry: EventSchemaRegistry | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or DB_PATH
        self._endpoints: dict[str, WebhookEndpoint] = {}
        self._path_index: dict[str, WebhookEndpoint] = {}  # path → endpoint
        self._trigger_map = trigger_map
        self._schema_registry = schema_registry
        self._initialized = False
        self._init_db()
        self._load_from_db()

    # ── Lazy dependency injection ───────────────────────────────

    @property
    def trigger_map(self) -> TriggerMap:
        if self._trigger_map is None:
            self._trigger_map = get_trigger_map()
        return self._trigger_map

    @property
    def schema_registry(self) -> EventSchemaRegistry:
        if self._schema_registry is None:
            self._schema_registry = get_schema_registry()
        return self._schema_registry

    # ── DB Setup ────────────────────────────────────────────────

    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS webhook_endpoints (
                    endpoint_id  TEXT PRIMARY KEY,
                    path         TEXT NOT NULL,
                    tenant_id    TEXT NOT NULL,
                    event_type   TEXT NOT NULL,
                    secret       TEXT DEFAULT '',
                    enabled      INTEGER NOT NULL DEFAULT 1,
                    created_at   REAL NOT NULL,
                    call_count   INTEGER NOT NULL DEFAULT 0,
                    last_call_at REAL NOT NULL DEFAULT 0.0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_wh_path
                ON webhook_endpoints(path, tenant_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_wh_tenant
                ON webhook_endpoints(tenant_id)
            """)
            conn.commit()
        finally:
            conn.close()
        self._initialized = True

    def _load_from_db(self) -> None:
        """Load all endpoints from SQLite into memory."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT * FROM webhook_endpoints"
            ).fetchall()
            with self._lock:
                for row in rows:
                    ep = _endpoint_from_row(row)
                    self._endpoints[ep.endpoint_id] = ep
                    self._path_index[ep.path] = ep
        finally:
            conn.close()
        logger.info(
            "WebhookIngestion: loaded %d endpoints from %s",
            len(self._endpoints), self._db_path,
        )

    def _persist_endpoint(self, ep: WebhookEndpoint) -> None:
        """Write or update an endpoint in SQLite."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO webhook_endpoints
                    (endpoint_id, path, tenant_id, event_type, secret,
                     enabled, created_at, call_count, last_call_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ep.endpoint_id,
                    ep.path,
                    ep.tenant_id,
                    ep.event_type,
                    ep.secret or "",
                    int(ep.enabled),
                    ep.created_at,
                    ep.call_count,
                    ep.last_call_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    # ── Register Endpoint ───────────────────────────────────────

    def register_endpoint(
        self,
        path: str,
        tenant_id: str,
        event_type: str,
        secret: str | None = None,
    ) -> str:
        """
        Register a new inbound webhook endpoint.

        Args:
            path: URL path (e.g. "/webhooks/stripe").
            tenant_id: Owner tenant.
            event_type: Event type to emit.
            secret: Optional HMAC-SHA256 secret for signature verification.

        Returns:
            endpoint_id (unique string).
        """
        if not path or not isinstance(path, str):
            raise ValueError("path must be a non-empty string")
        if not tenant_id or not isinstance(tenant_id, str):
            raise ValueError("tenant_id must be a non-empty string")
        if not event_type or not isinstance(event_type, str):
            raise ValueError("event_type must be a non-empty string")

        endpoint_id = f"wh_{uuid.uuid4().hex[:12]}"

        ep = WebhookEndpoint(
            endpoint_id=endpoint_id,
            path=path,
            tenant_id=tenant_id,
            event_type=event_type,
            secret=secret,
            enabled=True,
            created_at=time.time(),
        )

        with self._lock:
            self._endpoints[endpoint_id] = ep
            self._path_index[path] = ep
        self._persist_endpoint(ep)

        logger.info(
            "WebhookIngestion: registered endpoint %s at %s "
            "for event_type=%s (tenant=%s)",
            endpoint_id, path, event_type, tenant_id,
        )
        return endpoint_id

    # ── Unregister Endpoint ─────────────────────────────────────

    def unregister_endpoint(self, endpoint_id: str) -> bool:
        """
        Unregister a webhook endpoint.

        Returns:
            True if found and removed, False otherwise.
        """
        with self._lock:
            ep = self._endpoints.pop(endpoint_id, None)
            if ep is None:
                return False
            # Clean up path index
            if self._path_index.get(ep.path) is ep:
                del self._path_index[ep.path]

        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                "DELETE FROM webhook_endpoints WHERE endpoint_id = ?",
                (endpoint_id,),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info("WebhookIngestion: unregistered endpoint %s", endpoint_id)
        return True

    # ── Process Inbound Webhook ─────────────────────────────────

    def process_inbound(
        self,
        path: str,
        headers: dict[str, str],
        body: bytes,
        tenant_id: str,
    ) -> InboundWebhookResult:
        """
        Process an incoming webhook request.

        Steps:
          1. Find matching endpoint by path
          2. Verify HMAC signature if secret configured
          3. Parse JSON body
          4. Validate against schema_registry
          5. Dispatch via trigger_map with retry

        Args:
            path: The URL path of the incoming request.
            headers: Request headers (case-insensitive lookup).
            body: Raw request body bytes.
            tenant_id: The tenant making the request.

        Returns:
            InboundWebhookResult with success status and details.
        """
        errors: list[str] = []

        # 1. Find matching endpoint
        with self._lock:
            ep = self._path_index.get(path)

        if ep is None:
            msg = f"No endpoint registered for path: {path}"
            logger.warning("WebhookIngestion: %s", msg)
            return InboundWebhookResult(
                success=False,
                errors=[msg],
            )

        if not ep.enabled:
            msg = f"Endpoint {ep.endpoint_id} is disabled"
            logger.warning("WebhookIngestion: %s", msg)
            return InboundWebhookResult(
                success=False,
                endpoint_id=ep.endpoint_id,
                event_type=ep.event_type,
                errors=[msg],
            )

        if ep.tenant_id != tenant_id:
            msg = (
                f"Tenant mismatch: endpoint belongs to {ep.tenant_id}, "
                f"request from {tenant_id}"
            )
            logger.warning("WebhookIngestion: %s", msg)
            return InboundWebhookResult(
                success=False,
                endpoint_id=ep.endpoint_id,
                event_type=ep.event_type,
                errors=[msg],
            )

        # 2. Verify HMAC signature if secret configured
        if ep.secret:
            sig_header = headers.get("X-Hub-Signature-256", "")
            if not sig_header:
                msg = "Missing X-Hub-Signature-256 header for secured endpoint"
                logger.warning("WebhookIngestion: %s", msg)
                return InboundWebhookResult(
                    success=False,
                    endpoint_id=ep.endpoint_id,
                    event_type=ep.event_type,
                    errors=[msg],
                )
            if not _verify_hmac_sha256(ep.secret, body, sig_header):
                msg = "HMAC signature verification failed"
                logger.warning("WebhookIngestion: %s", msg)
                return InboundWebhookResult(
                    success=False,
                    endpoint_id=ep.endpoint_id,
                    event_type=ep.event_type,
                    errors=[msg],
                )

        # 3. Parse JSON body
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            msg = f"Failed to parse JSON body: {exc}"
            logger.warning("WebhookIngestion: %s", msg)
            return InboundWebhookResult(
                success=False,
                endpoint_id=ep.endpoint_id,
                event_type=ep.event_type,
                errors=[msg],
            )

        if not isinstance(payload, dict):
            msg = f"Expected JSON object, got {type(payload).__name__}"
            logger.warning("WebhookIngestion: %s", msg)
            return InboundWebhookResult(
                success=False,
                endpoint_id=ep.endpoint_id,
                event_type=ep.event_type,
                errors=[msg],
            )

        # 4. Validate against schema_registry
        validation = self.schema_registry.validate(ep.event_type, payload)
        if not validation.valid:
            val_errors = [
                f"{iss.field}: {iss.message}" for iss in validation.issues
            ]
            msg = f"Schema validation failed: {'; '.join(val_errors)}"
            logger.warning("WebhookIngestion: %s", msg)
            # Non-fatal: still attempt dispatch but record the errors
            errors.append(msg)

        # 5. Dispatch via TriggerMap with retry
        inbound_event = InboundEvent(
            event_type=ep.event_type,
            event_data=payload,
            source=f"webhook:{path}",
        )

        events_dispatched = self._dispatch_with_retry(inbound_event)

        # Update endpoint stats
        with self._lock:
            ep.call_count += 1
            ep.last_call_at = time.time()
        self._persist_endpoint(ep)

        success = events_dispatched >= 0  # -1 means total failure
        return InboundWebhookResult(
            success=success,
            endpoint_id=ep.endpoint_id,
            event_type=ep.event_type,
            events_dispatched=max(events_dispatched, 0),
            errors=errors,
        )

    # ── Dispatch with Retry ─────────────────────────────────────

    def _dispatch_with_retry(self, event: InboundEvent) -> int:
        """
        Dispatch an event through the TriggerMap with retry logic.

        Retries up to _MAX_DISPATCH_RETRIES times with exponential backoff.

        Returns:
            Number of automations dispatched, or -1 on total failure.
        """
        last_error: str = ""
        for attempt in range(1, _MAX_DISPATCH_RETRIES + 1):
            try:
                matches = self.trigger_map.lookup(
                    event.event_type, event.event_data,
                )
                if matches:
                    logger.info(
                        "WebhookIngestion: dispatching event %s to %d automation(s) "
                        "(attempt %d)",
                        event.event_type, len(matches), attempt,
                    )
                else:
                    logger.debug(
                        "WebhookIngestion: no automations matched event %s",
                        event.event_type,
                    )
                return len(matches)
            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "WebhookIngestion: dispatch attempt %d/%d failed for %s: %s",
                    attempt, _MAX_DISPATCH_RETRIES, event.event_type, exc,
                )
                if attempt < _MAX_DISPATCH_RETRIES:
                    backoff = _DISPATCH_RETRY_BACKOFF_BASE * (2 ** (attempt - 1))
                    time.sleep(backoff)

        logger.error(
            "WebhookIngestion: all %d dispatch attempts failed for %s: %s",
            _MAX_DISPATCH_RETRIES, event.event_type, last_error,
        )
        return -1

    # ── Query ───────────────────────────────────────────────────

    def list_endpoints(
        self,
        tenant_id: str | None = None,
    ) -> list[WebhookEndpoint]:
        """List registered endpoints, optionally filtered by tenant_id."""
        with self._lock:
            endpoints = list(self._endpoints.values())
        if tenant_id is not None:
            endpoints = [ep for ep in endpoints if ep.tenant_id == tenant_id]
        return sorted(endpoints, key=lambda ep: ep.path)

    def get_endpoint(self, endpoint_id: str) -> WebhookEndpoint | None:
        """Get a specific endpoint by ID, or None if not found."""
        with self._lock:
            return self._endpoints.get(endpoint_id)


# ─── Singleton ──────────────────────────────────────────────────

_instance: WebhookIngestionEngine | None = None
_instance_lock = threading.Lock()


def get_webhook_ingestion_engine() -> WebhookIngestionEngine:
    """Return the singleton WebhookIngestionEngine instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = WebhookIngestionEngine()
    return _instance

# Alias for backward compatibility
get_webhook_ingestion = get_webhook_ingestion_engine


def reset_webhook_ingestion_engine() -> None:
    """Reset the singleton (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None

# Alias for backward compatibility
reset_webhook_ingestion = reset_webhook_ingestion_engine


__all__ = [
    "WebhookIngestionEngine",
    "WebhookEndpoint",
    "InboundWebhookResult",
    "InboundEvent",
    "get_webhook_ingestion_engine",
    "reset_webhook_ingestion_engine",
    # Aliases
    "get_webhook_ingestion",
    "reset_webhook_ingestion",
]
