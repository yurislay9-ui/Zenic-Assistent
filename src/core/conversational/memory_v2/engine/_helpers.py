"""Helpers for engine."""

from __future__ import annotations
import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from .types import ContextWindow, MemoryQuery, MemoryRecord, MemorySearchResult, MemoryTier, MemoryType

logger = logging.getLogger(__name__)

def _new_id(prefix: str = "mem") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"



def _now_iso() -> str:
    return datetime.utcnow().isoformat()



def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]



def _retry(func: Any, max_retries: int = 3, base_delay: float = 0.1) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


