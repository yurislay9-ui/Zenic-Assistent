"""
ZENIC-AGENTS — Confirm Manager Types

Constants and status values for the confirmation/approval flow.
"""

from __future__ import annotations

import os

# ─── Constants ────────────────────────────────────────────────

DEFAULT_TTL_SECONDS = 300  # 5 minutes
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "_confirm_state.db",
)

# Status constants
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"
STATUS_APPROVED = "approved"
STATUS_DENIED = "denied"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"
