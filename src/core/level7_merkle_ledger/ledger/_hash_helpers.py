"""
ZENIC-AGENTS - Merkle Ledger v17 (Tenant-Aware + Sandbox Isolated)

Ledger con arbol Merkle real para integridad criptografica.
Soporta snapshots, commits con verificacion, y rollbacks atomicos.

v17 - TENANT-AWARE:
- Todas las operaciones filtran por tenant_id para aislar datos entre tenants
- Columna tenant_id con default '__anonymous__' para compatibilidad retroactiva
- purge_tenant_ledger() para GDPR / deprovisioning
- set_tenant_id() para cambio dinamico de contexto de tenant
- Thread-local TenantContext para obtener tenant_id automaticamente

v16 - AISLAMIENTO:
- Los commits se escriben en el workspace AISLADO del sandbox
- NUNCA escribe directamente en el filesystem del proyecto real
- Los snapshots y rollbacks operan dentro del workspace aislado
- Las DBs del ledger son INDEPENDIENTES cuando opera en sandbox

FIX (Phase 2): Added retry with exponential backoff for DB operations.
SQLite can fail transiently (database locked, busy timeout) especially
under concurrent write access.

Sin dependencias externas. Compatible con Android.
"""

import hashlib
import shutil
import sqlite3
import time
import logging
from pathlib import Path
from src.core.shared.contracts import MerkleNode
from src.core.shared.db_initializer import get_data_dir, get_connection
from src.core.shared.retry import with_retry
from src.core.shared.db_utils import purge_tenant_rows
from src.core.shared.tenant_utils import resolve_tenant_id

class MerkleLedgerHelpersMixin:
    """Mixin providing hash computation, Merkle root, and DB helpers."""
    """Ledger con arbol Merkle para integridad criptografica. Tenant-aware + sandbox-isolated."""

    def __init__(self):
        self.bk_dir = get_data_dir() / "backups"
        self.bk_dir.mkdir(exist_ok=True)
        self._tenant_id: str = resolve_tenant_id()
        logger.debug("MerkleLedger initialized with tenant_id='%s'", self._tenant_id)
        self._init_db()

    def set_tenant_id(self, tenant_id: str) -> None:
        """Update the current tenant_id for this ledger instance.

        Args:
            tenant_id: New tenant identifier to scope all operations.
        """
        old = self._tenant_id
        self._tenant_id = tenant_id
        logger.info("MerkleLedger tenant_id changed: '%s' -> '%s'", old, tenant_id)

    def _init_db(self):
        conn = get_connection("merkle_ledger.sqlite")
        conn.execute("""CREATE TABLE IF NOT EXISTS ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            hash_sha256 TEXT NOT NULL,
            parent_hash TEXT NOT NULL,
            operation TEXT NOT NULL,
            timestamp REAL NOT NULL,
            tenant_id TEXT NOT NULL DEFAULT '__anonymous__')""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_file ON ledger(file_path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON ledger(tenant_id)")
        conn.commit()
        # Migrate: add tenant_id column if it doesn't exist (for existing databases)
        try:
            from src.core.tenant._isolation import TenantIsolation
            TenantIsolation.migrate_add_tenant_id(conn, "ledger", "__anonymous__")
        except Exception as e:
            logger.debug("Ledger tenant migration skipped: %s", e)

    def _hash_content(self, content):
        """Compute SHA-256 hash of string or bytes content.

        Args:
            content: String or bytes to hash.

        Returns:
            Hex-encoded SHA-256 digest string.
        """
        if isinstance(content, bytes):
            return hashlib.sha256(content).hexdigest()
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _merkle_root(self, hashes):
        """Compute Merkle root hash from a list of leaf hashes.

        Pairs hashes and computes SHA-256 of concatenated pairs,
        repeating until a single root hash remains.

        Args:
            hashes: List of hex-encoded hash strings.

        Returns:
            Single root hash string, or hash of b'empty' if no hashes.
        """
        if not hashes:
            return hashlib.sha256(b'empty').hexdigest()
        if len(hashes) == 1:
            return hashes[0]
        while len(hashes) > 1:
            new_level = []
            for i in range(0, len(hashes), 2):
                left = hashes[i]
                right = hashes[i + 1] if i + 1 < len(hashes) else left
                combined = hashlib.sha256((left + right).encode()).hexdigest()
                new_level.append(combined)
            hashes = new_level
        return hashes[0]

    def _get_all_file_hashes(self, db_path=None, tenant_id=None):
        """Obtiene los hashes mas recientes de todos los archivos para un tenant.

        Si db_path se proporciona, usa esa DB.
        Si tenant_id se proporciona, filtra por ese tenant; si no, usa self._tenant_id.
        """
        tid = tenant_id or self._tenant_id
        conn = None
        try:
            if db_path:
                conn = sqlite3.connect(db_path)
            else:
                conn = get_connection("merkle_ledger.sqlite")
            rows = conn.execute(
                "SELECT file_path, hash_sha256 FROM ledger WHERE tenant_id=? AND id IN "
                "(SELECT MAX(id) FROM ledger WHERE tenant_id=? GROUP BY file_path)",
                (tid, tid)
            ).fetchall()
            return {row[0]: row[1] for row in rows}
        except Exception as e:
            logger.warning("Ledger: Error getting all file hashes: %s", e)
            return {}
        finally:
            if db_path and conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _get_last_hash(self, file_path, db_path=None, tenant_id=None):
        """Obtiene el ultimo hash para un archivo y un tenant.

        Si db_path se proporciona, usa esa DB.
        Si tenant_id se proporciona, filtra por ese tenant; si no, usa self._tenant_id.
        """
        tid = tenant_id or self._tenant_id
        conn = None
        try:
            if db_path:
                conn = sqlite3.connect(db_path)
            else:
                conn = get_connection("merkle_ledger.sqlite")
            r = conn.execute(
                "SELECT hash_sha256 FROM ledger WHERE file_path=? AND tenant_id=? ORDER BY id DESC LIMIT 1",
                (file_path, tid)).fetchone()
            return r[0] if r else "GENESIS"
        except Exception as e:
            logger.warning("Ledger: Error getting last hash: %s", e)
            return "GENESIS"
        finally:
            if db_path and conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def _record_operation(self, file_path, content_hash, parent_hash, operation, db_path=None, tenant_id=None):
        """Register an operation in the ledger with tenant_id.

        If db_path is provided, uses that DB. Otherwise uses the pool.
        If tenant_id is provided, uses that; otherwise uses self._tenant_id.

        Uses shared retry utility for transient SQLite failures.
        """
        tid = tenant_id or self._tenant_id
        conn = None

        def _insert():
            nonlocal conn
            if db_path:
                conn = sqlite3.connect(db_path)
            else:
                conn = get_connection("merkle_ledger.sqlite")
            conn.execute(
                "INSERT INTO ledger (file_path, hash_sha256, parent_hash, operation, timestamp, tenant_id) VALUES (?,?,?,?,?,?)",
                (file_path, content_hash, parent_hash, operation, time.time(), tid))
            conn.commit()

        try:
            with_retry(_insert, label="MerkleLedger record_operation")
        except Exception:
            pass  # with_retry already logged the failure
        finally:
            if db_path and conn:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def _validate_rel_path(rel_path: str, base_dir: Path) -> Path:
        """Validate that rel_path resolves within base_dir to prevent path traversal.

        Security: Prevents ../../etc/passwd style attacks by resolving the
        full path and verifying it stays within the intended directory boundary.
        """
        target = base_dir / rel_path
        resolved = target.resolve()
        base_resolved = base_dir.resolve()
        if not resolved.is_relative_to(base_resolved):
            raise ValueError(
                f"Path traversal detected: '{rel_path}' resolves to "
                f"'{resolved}' which is outside '{base_resolved}'"
            )
        return resolved
