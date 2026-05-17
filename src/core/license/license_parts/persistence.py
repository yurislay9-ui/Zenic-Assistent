"""
Zenic-Agents Asistente - License Persistence (Phase 6.3)

Database operations for license storage.
Extracted from manager.py for the 400-line limit.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, Optional

from ..types import (
    LicenseInfo, LicenseStatus, LicenseTier, HardwareBindingStrength,
)

logger = logging.getLogger(__name__)


class LicenseDB:
    """Database operations for license storage."""

    def __init__(self, db_path: str = "license_store.sqlite") -> None:
        self._db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the license storage database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS licenses (
                    license_id TEXT PRIMARY KEY,
                    tier TEXT NOT NULL, status TEXT NOT NULL,
                    issued_to TEXT, issued_at REAL, expires_at REAL,
                    features TEXT, max_users INTEGER DEFAULT 1,
                    hardware_id TEXT, binding_strength TEXT DEFAULT 'soft',
                    signature TEXT, metadata TEXT DEFAULT '{}', cached_at REAL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS kill_switch_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    active INTEGER NOT NULL, reason TEXT,
                    activated_at REAL, source TEXT
                )
            """)
            conn.commit()
            conn.close()
            logger.info("LicenseDB: Database initialized")
        except Exception as exc:
            logger.error("LicenseDB: DB init failed: %s", exc)

    def load_cached_license(self) -> Optional[LicenseInfo]:
        """Load the most recently cached active license."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM licenses WHERE status = 'active' ORDER BY cached_at DESC LIMIT 1",
            ).fetchone()
            conn.close()
            if row:
                return LicenseInfo(
                    license_id=row["license_id"],
                    tier=LicenseTier(row["tier"]),
                    status=LicenseStatus(row["status"]),
                    issued_to=row["issued_to"] or "",
                    issued_at=row["issued_at"] or 0.0,
                    expires_at=row["expires_at"] or 0.0,
                    features=json.loads(row["features"] or "[]"),
                    max_users=row["max_users"] or 1,
                    hardware_id=row["hardware_id"] or "",
                    binding_strength=HardwareBindingStrength(row["binding_strength"] or "soft"),
                    signature=row["signature"] or "",
                    metadata=json.loads(row["metadata"] or "{}"),
                )
        except Exception:
            pass
        return None

    def persist_license(self, info: LicenseInfo) -> None:
        """Persist a license to the database."""
        import time
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "INSERT OR REPLACE INTO licenses "
                "(license_id,tier,status,issued_to,issued_at,expires_at,"
                "features,max_users,hardware_id,binding_strength,"
                "signature,metadata,cached_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (info.license_id, info.tier.value, info.status.value,
                 info.issued_to, info.issued_at, info.expires_at,
                 json.dumps(info.features), info.max_users, info.hardware_id,
                 info.binding_strength.value, info.signature,
                 json.dumps(info.metadata), time.time()),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("LicenseDB: Persist failed: %s", exc)

    def persist_kill_switch(self, active: bool, reason: str, activated_at: float, source: str) -> None:
        """Persist kill switch state."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "INSERT INTO kill_switch_log (active,reason,activated_at,source) VALUES (?,?,?,?)",
                (1 if active else 0, reason, activated_at, source),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
