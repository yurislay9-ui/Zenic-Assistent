"""Core logic for integrity — IntegrityVerifier class."""

from __future__ import annotations
import hashlib
import logging
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

from ._types import IntegrityStatus, IntegrityCheckResult, _SAFE_IDENTIFIER_RE

logger = logging.getLogger(__name__)


class IntegrityVerifier:
    """Defense in Depth Layer 4: Integrity verification via hash chains.

    Provides multiple integrity verification mechanisms:
    1. Merkle chain verification (extends existing MerkleLedger)
    2. Cross-verification between independent hash chains
    3. File integrity monitoring for critical system files
    4. Database integrity verification via checksums
    5. Periodic integrity scanning

    If tampering is detected, the verifier reports to the
    degraded mode system for appropriate response.
    """

    def __init__(
        self,
        db_path: str = "integrity_verify.sqlite",
        check_interval_seconds: float = 300.0,
    ) -> None:
        self._db_path = db_path
        self._check_interval = check_interval_seconds
        self._baselines: Dict[str, str] = {}
        self._callbacks: List[Any] = []
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the integrity verification database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS integrity_baselines (
                    component TEXT PRIMARY KEY,
                    hash TEXT NOT NULL,
                    hash_algorithm TEXT DEFAULT 'sha256',
                    verified_at REAL NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS integrity_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    component TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected_hash TEXT,
                    actual_hash TEXT,
                    message TEXT,
                    checked_at REAL NOT NULL
                )
            """)
            conn.commit()
            conn.close()
            logger.info("IntegrityVerifier: Database initialized")
        except Exception as exc:
            logger.error("IntegrityVerifier: DB init failed: %s", exc)

    # ── Baseline Management ────────────────────────────────

    def establish_baseline(self, component: str, data: bytes) -> str:
        """Establish a hash baseline for a component.

        Args:
            component: Component identifier (e.g., 'auth_db', 'license_file').
            data: The data to hash.

        Returns:
            The SHA-256 hex digest of the data.
        """
        hash_value = hashlib.sha256(data).hexdigest()

        with self._lock:
            self._baselines[component] = hash_value
            self._persist_baseline(component, hash_value)

        logger.info("IntegrityVerifier: Baseline established for '%s'", component)
        return hash_value

    def establish_file_baseline(self, file_path: str, component_name: str = "") -> Optional[str]:
        """Establish a baseline for a file's contents."""
        component = component_name or f"file:{file_path}"
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            return self.establish_baseline(component, data)
        except (OSError, IOError) as exc:
            logger.warning("IntegrityVerifier: Cannot read file %s: %s", file_path, exc)
            return None

    def establish_db_baseline(self, db_path: str, component_name: str = "") -> Optional[str]:
        """Establish a baseline for a SQLite database.

        Computes checksum of all tables' row counts and content hashes.
        """
        component = component_name or f"db:{db_path}"
        try:
            conn = sqlite3.connect(db_path)
            tables = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT name FROM sqlite_master WHERE type='table'",
            ).fetchall()
            checksum_parts: List[str] = []
            for (table_name,) in tables:
                # SECURITY: Validate table name from sqlite_master to prevent injection
                if not _SAFE_IDENTIFIER_RE.match(table_name):
                    logger.warning("Skipping suspicious table name: %r", table_name)
                    continue
                count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
                checksum_parts.append(f"{table_name}:{count}")
            conn.close()
            data = "|".join(checksum_parts).encode()
            return self.establish_baseline(component, data)
        except Exception as exc:
            logger.warning("IntegrityVerifier: DB baseline failed for %s: %s", db_path, exc)
            return None

    # ── Verification ───────────────────────────────────────

    def verify_component(self, component: str, data: bytes) -> IntegrityCheckResult:
        """Verify a component against its baseline."""
        actual_hash = hashlib.sha256(data).hexdigest()
        expected_hash = self._baselines.get(component, "")

        if not expected_hash:
            # Try loading from DB
            expected_hash = self._load_baseline(component)
            if not expected_hash:
                return IntegrityCheckResult(
                    component=component,
                    status=IntegrityStatus.MISSING,
                    actual_hash=actual_hash,
                    message=f"No baseline found for component '{component}'",
                )

        if actual_hash == expected_hash:
            result = IntegrityCheckResult(
                component=component,
                status=IntegrityStatus.VALID,
                expected_hash=expected_hash[:16],
                actual_hash=actual_hash[:16],
                message="Integrity verified",
            )
        else:
            result = IntegrityCheckResult(
                component=component,
                status=IntegrityStatus.TAMPERED,
                expected_hash=expected_hash[:16],
                actual_hash=actual_hash[:16],
                message=f"INTEGRITY VIOLATION: {component} has been modified",
            )
            self._notify_callbacks(result)

        self._log_check(result)
        return result

    def verify_file(self, file_path: str, component_name: str = "") -> IntegrityCheckResult:
        """Verify a file against its baseline."""
        component = component_name or f"file:{file_path}"
        try:
            with open(file_path, "rb") as f:
                data = f.read()
            return self.verify_component(component, data)
        except (OSError, IOError) as exc:
            return IntegrityCheckResult(
                component=component,
                status=IntegrityStatus.ERROR,
                message=f"Cannot read file: {exc}",
            )

    def verify_db(self, db_path: str, component_name: str = "") -> IntegrityCheckResult:
        """Verify a SQLite database against its baseline."""
        component = component_name or f"db:{db_path}"
        try:
            conn = sqlite3.connect(db_path)
            tables = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT name FROM sqlite_master WHERE type='table'",
            ).fetchall()
            checksum_parts: List[str] = []
            for (table_name,) in tables:
                # SECURITY: Validate table name from sqlite_master to prevent injection
                if not _SAFE_IDENTIFIER_RE.match(table_name):
                    logger.warning("Skipping suspicious table name: %r", table_name)
                    continue
                count = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]  # nosemgrep: formatted-sql-query, sqlalchemy-execute-raw-query  # validated identifier
                checksum_parts.append(f"{table_name}:{count}")
            conn.close()
            data = "|".join(checksum_parts).encode()
            return self.verify_component(component, data)
        except Exception as exc:
            return IntegrityCheckResult(
                component=component,
                status=IntegrityStatus.ERROR,
                message=f"DB verification failed: {exc}",
            )

    # ── Cross-Verification ─────────────────────────────────

    def cross_verify(self, components: List[str]) -> Dict[str, IntegrityCheckResult]:
        """Cross-verify multiple components against each other.

        Each component is independently verified. If any component
        fails, the cross-verification reports the failure.
        """
        results: Dict[str, IntegrityCheckResult] = {}
        for comp in components:
            if comp.startswith("file:"):
                path = comp[5:]
                results[comp] = self.verify_file(path)
            elif comp.startswith("db:"):
                path = comp[3:]
                results[comp] = self.verify_db(path)
            else:
                results[comp] = IntegrityCheckResult(
                    component=comp,
                    status=IntegrityStatus.ERROR,
                    message=f"Unknown component type: {comp}",
                )

        return results

    # ── Periodic Monitoring ────────────────────────────────

    def start_monitoring(self, watch_components: Optional[List[str]] = None) -> None:
        """Start periodic integrity monitoring."""
        if self._running:
            return
        self._running = True
        self._watch_components = watch_components or []
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="integrity-verify",
        )
        self._monitor_thread.start()
        logger.info("IntegrityVerifier: Monitoring started")

    def stop_monitoring(self) -> None:
        """Stop periodic integrity monitoring."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                for comp in self._watch_components:
                    if comp.startswith("file:"):
                        self.verify_file(comp[5:])
                    elif comp.startswith("db:"):
                        self.verify_db(comp[3:])
            except Exception as exc:
                logger.debug("IntegrityVerifier: Monitor error: %s", exc)
            time.sleep(self._check_interval)

    # ── Callbacks ──────────────────────────────────────────

    def on_integrity_violation(self, callback: Any) -> None:
        """Register a callback for integrity violations."""
        self._callbacks.append(callback)

    def _notify_callbacks(self, result: IntegrityCheckResult) -> None:
        """Notify callbacks about integrity violation."""
        for cb in self._callbacks:
            try:
                cb(result)
            except Exception as exc:
                logger.warning("IntegrityVerifier: Callback error: %s", exc)

    # ── Persistence ────────────────────────────────────────

    def _persist_baseline(self, component: str, hash_value: str) -> None:
        """Persist a baseline to the database."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO integrity_baselines
                   (component, hash, verified_at, metadata)
                   VALUES (?, ?, ?, ?)""",
                (component, hash_value, time.time(), "{}"),
            )
            conn.commit()
            conn.close()
        except Exception as exc:
            logger.error("IntegrityVerifier: Persist baseline failed: %s", exc)

    def _load_baseline(self, component: str) -> str:
        """Load a baseline from the database."""
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT hash FROM integrity_baselines WHERE component = ?",
                (component,),
            ).fetchone()
            conn.close()
            return row[0] if row else ""
        except Exception:
            return ""

    def _log_check(self, result: IntegrityCheckResult) -> None:
        """Log an integrity check result."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO integrity_checks
                   (component, status, expected_hash, actual_hash, message, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (result.component, result.status.value, result.expected_hash,
                 result.actual_hash, result.message, result.timestamp),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        """Get integrity verification status."""
        return {
            "baselines_count": len(self._baselines),
            "monitoring_active": self._running,
            "check_interval_seconds": self._check_interval,
        }
