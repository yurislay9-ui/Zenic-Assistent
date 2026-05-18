"""
ZENIC-AGENTS — Replay Queue Types

Enums, dataclasses, constants, and serialization for the replay queue.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
DB_PATH = os.path.join(DB_DIR, "replay_queue.sqlite")

# Retry configuration
DEFAULT_MAX_RETRIES = 3
BACKOFF_BASE = 1.0  # seconds — yields 1s, 2s, 4s


# ─── Enums ──────────────────────────────────────────────────────

class DeadLetterStatus(str, Enum):
    """Status of a dead-letter event."""
    PENDING = "pending"
    RETRYING = "retrying"
    SUCCEEDED = "succeeded"
    EXHAUSTED = "exhausted"


# ─── Dataclasses ────────────────────────────────────────────────

@dataclass
class DeadLetterEvent:
    """
    A failed event stored in the dead-letter queue.

    Attributes:
        dlq_id: Unique identifier.
        event_type: The event type that failed.
        event_data: The original event payload.
        error: Description of the failure.
        tenant_id: Owner tenant.
        retry_count: Number of retry attempts so far.
        max_retries: Maximum allowed retries (default 3).
        last_retry_at: Timestamp of last retry attempt, or 0.0.
        created_at: Unix timestamp when enqueued.
        status: Current status.
    """
    dlq_id: str
    event_type: str
    event_data: dict[str, Any]
    error: str
    tenant_id: str
    retry_count: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    last_retry_at: float = 0.0
    created_at: float = field(default_factory=time.time)
    status: DeadLetterStatus = DeadLetterStatus.PENDING


@dataclass
class RetryResult:
    """
    Result of retrying a single dead-letter event.

    Attributes:
        success: Whether the retry dispatch succeeded.
        dlq_id: The event's DLQ identifier.
        event_type: The event type.
        retry_count: Updated retry count.
        status: Updated status.
        error: Error message if retry failed, empty string otherwise.
    """
    success: bool
    dlq_id: str
    event_type: str
    retry_count: int = 0
    status: DeadLetterStatus = DeadLetterStatus.PENDING
    error: str = ""


@dataclass
class BatchRetryResult:
    """
    Result of retrying a batch of dead-letter events.

    Attributes:
        total_attempted: Number of events selected for retry.
        succeeded: Number that dispatched successfully.
        failed: Number that failed again.
        exhausted: Number that hit max retries.
        details: Per-event RetryResult list.
    """
    total_attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    exhausted: int = 0
    details: list[RetryResult] = field(default_factory=list)


# ─── Serialization ──────────────────────────────────────────────

def event_from_row(row: sqlite3.Row) -> DeadLetterEvent:
    """Deserialize a DeadLetterEvent from a SQLite row."""
    event_data_raw = row["event_data_json"]
    try:
        event_data = json.loads(event_data_raw)
    except (json.JSONDecodeError, TypeError):
        event_data = {}

    return DeadLetterEvent(
        dlq_id=row["dlq_id"],
        event_type=row["event_type"],
        event_data=event_data,
        error=row["error"],
        tenant_id=row["tenant_id"],
        retry_count=row["retry_count"],
        max_retries=row["max_retries"],
        last_retry_at=row["last_retry_at"],
        created_at=row["created_at"],
        status=DeadLetterStatus(row["status"]),
    )
