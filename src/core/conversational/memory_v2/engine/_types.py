"""Types and constants for engine."""

from __future__ import annotations
import hashlib
import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from .types import ContextWindow, MemoryQuery, MemoryRecord, MemorySearchResult, MemoryTier, MemoryType

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".zenic_agents" / "db"

DB_PATH = DB_DIR / "memory_v2.sqlite"

_TIER_ORDER = {
    MemoryTier.EPHEMERAL: 0,
    MemoryTier.SHORT_TERM: 1,
    MemoryTier.LONG_TERM: 2,
    MemoryTier.PERMANENT: 3,
}
