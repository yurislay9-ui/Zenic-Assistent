"""Helper methods extracted from chain."""

from __future__ import annotations

import json
import sqlite3
from ._types import ApprovalStatus, ApprovalPriority

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)



# ── Singleton ─────────────────────────────────────────────

_approval_chain_instance: Optional[ApprovalChain] = None
_approval_chain_lock = threading.Lock()


def get_approval_chain(db_path: str = "approval_chain.sqlite") -> ApprovalChain:
    """Get or create the global ApprovalChain instance."""
    global _approval_chain_instance
    with _approval_chain_lock:
        if _approval_chain_instance is None:
            _approval_chain_instance = ApprovalChain(db_path=db_path)
        return _approval_chain_instance


def reset_approval_chain() -> None:
    """Reset the global ApprovalChain (for testing)."""
    global _approval_chain_instance
    _approval_chain_instance = None