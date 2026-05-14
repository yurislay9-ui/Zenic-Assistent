"""
ZENIC-AGENTS - Transaction Manager (Phase 3)

Transaction management with rollback support for database operations.
Provides:
  - Explicit transaction boundaries (begin, commit, rollback)
  - Savepoint support for partial rollbacks
  - Automatic rollback on errors
  - Transaction timeout
  - Nested transaction support via savepoints
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  TYPES
# ──────────────────────────────────────────────────────────────

@dataclass
class Transaction:
    """Represents an active database transaction."""
    transaction_id: str = ""
    db_path: str = ""
    status: str = "active"          # active, committed, rolled_back, timed_out
    started_at: float = 0.0
    savepoints: List[str] = field(default_factory=list)
    operations_count: int = 0
    last_operation: str = ""
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.transaction_id:
            self.transaction_id = uuid.uuid4().hex[:12]
        if not self.started_at:
            self.started_at = time.time()

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.started_at

    @property
    def is_timed_out(self) -> bool:
        return self.elapsed_seconds > self.timeout_seconds


# ──────────────────────────────────────────────────────────────
#  TRANSACTION MANAGER
# ──────────────────────────────────────────────────────────────

class TransactionManager:
    """Manages database transactions with rollback and savepoint support.

    Features:
      - Explicit transaction lifecycle (begin → commit/rollback)
      - Savepoints for partial rollbacks within a transaction
      - Automatic timeout detection and rollback
      - Operation tracking for audit
      - Connection management via SQLCipherAdapter

    Usage:
        tm = TransactionManager(adapter)
        tx = tm.begin(db_path="data.db")

        tm.execute(tx, "INSERT INTO users (name) VALUES (?)", ("Alice",))
        tm.savepoint(tx, "sp1")
        tm.execute(tx, "INSERT INTO orders (user_id) VALUES (?)", (1,))
        tm.rollback_to_savepoint(tx, "sp1")  # Undo the order insert
        tm.commit(tx)
    """

    def __init__(self, default_timeout: float = 30.0) -> None:
        self._default_timeout = default_timeout
        self._active_transactions: Dict[str, Transaction] = {}
        self._connections: Dict[str, Any] = {}  # tx_id → connection
        self._stats = {
            "begun": 0,
            "committed": 0,
            "rolled_back": 0,
            "timed_out": 0,
        }

    def begin(
        self,
        db_path: str = ":memory:",
        timeout_seconds: Optional[float] = None,
    ) -> Transaction:
        """Begin a new transaction.

        Returns a Transaction object that must be committed or rolled back.
        """
        tx = Transaction(
            db_path=db_path,
            timeout_seconds=timeout_seconds or self._default_timeout,
        )
        self._active_transactions[tx.transaction_id] = tx
        self._stats["begun"] += 1

        logger.info(
            "TransactionManager: Began transaction %s on %s (timeout=%0.1fs)",
            tx.transaction_id, db_path, tx.timeout_seconds,
        )
        return tx

    def execute(
        self,
        tx: Transaction,
        query: str,
        params: tuple = (),
        adapter: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute a query within a transaction.

        Uses the provided adapter or falls back to direct connection.
        """
        self._check_active(tx)

        if tx.is_timed_out:
            self.rollback(tx)
            raise TimeoutError(f"Transaction {tx.transaction_id} timed out")

        result: Dict[str, Any] = {}
        if adapter:
            result = adapter.execute(query, params, fetch=True)
        else:
            # Use stored connection
            conn = self._connections.get(tx.transaction_id)
            if conn:
                cursor = conn.execute(query, params)
                if query.strip().upper().startswith("SELECT"):
                    columns = [d[0] for d in cursor.description] if cursor.description else []
                    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    result = {"rows": rows, "row_count": len(rows)}
                else:
                    result = {"affected_rows": cursor.rowcount, "lastrowid": cursor.lastrowid}
            else:
                raise RuntimeError(f"No connection for transaction {tx.transaction_id}")

        tx.operations_count += 1
        tx.last_operation = query[:100]
        return result

    def savepoint(self, tx: Transaction, name: str) -> None:
        """Create a savepoint within the transaction."""
        self._check_active(tx)
        tx.savepoints.append(name)

        conn = self._connections.get(tx.transaction_id)
        if conn:
            conn.execute(f"SAVEPOINT {name}")
        logger.debug(
            "TransactionManager: Savepoint '%s' in tx %s", name, tx.transaction_id
        )

    def rollback_to_savepoint(self, tx: Transaction, name: str) -> None:
        """Rollback to a specific savepoint."""
        self._check_active(tx)

        if name not in tx.savepoints:
            raise ValueError(f"Savepoint '{name}' not found in transaction {tx.transaction_id}")

        conn = self._connections.get(tx.transaction_id)
        if conn:
            conn.execute(f"ROLLBACK TO SAVEPOINT {name}")
        # Remove savepoints created after this one
        idx = tx.savepoints.index(name) + 1
        tx.savepoints = tx.savepoints[:idx]
        logger.info(
            "TransactionManager: Rolled back to savepoint '%s' in tx %s",
            name, tx.transaction_id,
        )

    def commit(self, tx: Transaction) -> None:
        """Commit the transaction."""
        self._check_active(tx)

        conn = self._connections.get(tx.transaction_id)
        if conn:
            conn.commit()

        tx.status = "committed"
        self._cleanup(tx)
        self._stats["committed"] += 1
        logger.info(
            "TransactionManager: Committed tx %s (%d operations, %.1fms)",
            tx.transaction_id, tx.operations_count, tx.elapsed_seconds * 1000,
        )

    def rollback(self, tx: Transaction) -> None:
        """Rollback the entire transaction."""
        self._check_active(tx)

        conn = self._connections.get(tx.transaction_id)
        if conn:
            conn.rollback()

        tx.status = "rolled_back"
        self._cleanup(tx)
        self._stats["rolled_back"] += 1
        logger.info(
            "TransactionManager: Rolled back tx %s (%d operations)",
            tx.transaction_id, tx.operations_count,
        )

    def register_connection(self, tx: Transaction, connection: Any) -> None:
        """Register a database connection for a transaction."""
        self._connections[tx.transaction_id] = connection

    @contextmanager
    def transaction(
        self,
        db_path: str = ":memory:",
        timeout_seconds: Optional[float] = None,
        adapter: Optional[Any] = None,
    ) -> Generator[Transaction, None, None]:
        """Context manager for automatic transaction lifecycle.

        On success: COMMIT.
        On exception: ROLLBACK.
        """
        tx = self.begin(db_path, timeout_seconds)
        if adapter:
            with adapter.connection() as conn:
                self.register_connection(tx, conn)
                try:
                    yield tx
                    self.commit(tx)
                except Exception:
                    self.rollback(tx)
                    raise
        else:
            try:
                yield tx
                self.commit(tx)
            except Exception:
                self.rollback(tx)
                raise

    @property
    def stats(self) -> Dict[str, Any]:
        """Get transaction manager statistics."""
        return {
            **self._stats,
            "active_transactions": len(self._active_transactions),
        }

    def cleanup_stale(self, max_age_seconds: float = 300) -> int:
        """Rollback and clean up stale (timed out) transactions."""
        cleaned = 0
        for tx_id in list(self._active_transactions.keys()):
            tx = self._active_transactions[tx_id]
            if tx.elapsed_seconds > max_age_seconds:
                tx.status = "timed_out"
                self._cleanup(tx)
                self._stats["timed_out"] += 1
                cleaned += 1
                logger.warning("TransactionManager: Cleaned up stale tx %s", tx_id)
        return cleaned

    # ── Private methods ──────────────────────────────────────

    def _check_active(self, tx: Transaction) -> None:
        """Verify that a transaction is still active."""
        if tx.status != "active":
            raise RuntimeError(
                f"Transaction {tx.transaction_id} is not active (status={tx.status})"
            )

    def _cleanup(self, tx: Transaction) -> None:
        """Clean up transaction resources."""
        self._active_transactions.pop(tx.transaction_id, None)
        conn = self._connections.pop(tx.transaction_id, None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass
