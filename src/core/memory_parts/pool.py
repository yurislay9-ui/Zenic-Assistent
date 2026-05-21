"""
SmartMemory FastPool instance.

Provides a single, unified connection pool for SmartMemory,
replacing the raw sqlite3.connect() calls that bypass pooling.

FASE 1.1/1.2 Performance Fix:
- All SmartMemory components (DatabaseMixin, CacheMixin, etc.) now share
  a single FastPool instance instead of creating competing connections.
- This eliminates SQLITE_BUSY errors caused by concurrent raw connections
  that bypass the centralized pool.
- FastPool applies optimized PRAGMAs (WAL, cache_size=-8192, synchronous=NORMAL,
  temp_store=MEMORY, mmap_size, wal_autocheckpoint, busy_timeout, foreign_keys)
  automatically on every new connection, so SmartMemory no longer needs to
  apply PRAGMAs manually.
"""

import os
from src.core.shared.fast_connection_pool import FastPool

# SmartMemory uses ~/.zenic_agents/db/ as its data directory
# (NOT the default ~/.zenic_agents/data/ that FastPool uses)
_SM_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
os.makedirs(_SM_DB_DIR, exist_ok=True)

# Module-level singleton pool for SmartMemory.
# This ensures all SmartMemory components share the same pool,
# eliminating competing connection systems that cause SQLITE_BUSY errors.
smart_memory_pool = FastPool(max_shared_per_db=5, idle_timeout_s=300.0)

# Override the data directory to match SmartMemory's location (~/.zenic_agents/db/)
# instead of FastPool's default (~/.zenic_agents/data/).
# This way, passing "smart_memory.sqlite" as db_name resolves to the correct path.
smart_memory_pool._data_dir = _SM_DB_DIR

# The DB name used by SmartMemory (filename only; path is resolved by the pool)
SMART_MEMORY_DB = "smart_memory.sqlite"
