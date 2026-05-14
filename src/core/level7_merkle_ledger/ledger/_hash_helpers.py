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

FIX (E-04): Hash canonical changed from SHA-256 to BLAKE3 to match
the Rust native extension (hash.rs). The Rust side uses blake3::hash()
exclusively for integrity verification and Merkle tree computation.
SHA-256 hashes computed before this fix are stored with a "sha256:"
prefix in the database and are still readable for backward compatibility,
but all NEW hashes use BLAKE3.

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

# ── BLAKE3 hash — canonical hash, matches Rust hash.rs ──────────────
# BLAKE3 is mandatory for integrity: the Rust native extension uses
# blake3::hash() exclusively. SHA-256 is kept ONLY as a fallback when
# the native extension is not compiled (e.g., during development).

try:
    from src.core.native._zenic_native import blake3_hash as _native_blake3_hash
    _HAS_NATIVE_BLAKE3 = True
except ImportError:
    _HAS_NATIVE_BLAKE3 = False


def _blake3_hash(data: bytes) -> str:
    """Compute BLAKE3 hash of bytes, returning 64-char hex string.

    Uses the native Rust extension when available (zero-copy, parallel).
    Falls back to pure-Python blake3 package, then to SHA-256 with a
    ``sha256:`` prefix for transparent identification.

    This function is the SINGLE SOURCE OF TRUTH for all hashing in the
    Merkle ledger. It MUST produce the same output as Rust ``blake3_hash()``.
    """
    if _HAS_NATIVE_BLAKE3:
        return _native_blake3_hash(data)

    # Fallback: try pure-Python blake3 package
    try:
        import blake3 as _blake3_pure
        return _blake3_pure.blake3(data).hexdigest()
    except ImportError:
        pass

    # Last resort: SHA-256 with prefix (NOT BLAKE3-compatible!)
    # This exists so the system can still function during development
    # without native extensions. Hashes produced this way are prefixed
    # with "sha256:" to distinguish them from BLAKE3 hashes.
    return "sha256:" + hashlib.sha256(data).hexdigest()


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
        """Compute BLAKE3 hash of string or bytes content.

        All new hashes use BLAKE3 to match the Rust native extension.
        Legacy SHA-256 hashes in the database are readable but new
        writes always produce BLAKE3 hashes.

        Args:
            content: String or bytes to hash.

        Returns:
            Hex-encoded BLAKE3 digest string (64 chars).
            If native extension is unavailable, returns "sha256:" + hex digest.
        """
        if isinstance(content, bytes):
            return _blake3_hash(content)
        return _blake3_hash(content.encode('utf-8'))

    def _merkle_root(self, hashes):
        """Compute Merkle root hash from a list of leaf hashes.

        Pairs hashes and computes BLAKE3 of concatenated pairs,
        repeating until a single root hash remains. This matches
        the Rust ``merkle_root()`` function in hash.rs exactly:
        leaves are hashed with BLAKE3, then paired and re-hashed
        using RAW BYTE concatenation (not hex string concatenation).

        E-04 FIX: Previously, this method concatenated hex strings
        encoded as UTF-8 before hashing: ``((left + right).encode('utf-8'))``.
        The Rust side concatenates raw bytes: ``combined = left_bytes + right_bytes``.
        These produce DIFFERENT Merkle roots for the same input, which
        breaks cross-language integrity verification.

        Args:
            hashes: List of hex-encoded hash strings.

        Returns:
            Single root hash string, or hash of b'empty' if no hashes.
        """
        if not hashes:
            return _blake3_hash(b'empty')
        if len(hashes) == 1:
            return hashes[0]

        # E-04 FIX: Convert hex strings to raw bytes for Merkle tree computation.
        # This matches the Rust merkle_root() which operates on raw bytes.
        # Previously, hex strings were concatenated and re-encoded as UTF-8,
        # producing different results than Rust.
        try:
            current_level: list[bytes] = [
                bytes.fromhex(h.removeprefix("sha256:")) for h in hashes
            ]
        except ValueError:
            # Fallback: if a hash is not valid hex, hash it first
            current_level = [_blake3_hash(h.encode('utf-8')).encode() if not h.startswith("sha256:") else bytes.fromhex(h.removeprefix("sha256:"))
                             for h in hashes]

        # Hash each leaf with BLAKE3 (matches Rust: blake3::hash(leaf))
        current_level = [bytes.fromhex(_blake3_hash(leaf)) for leaf in current_level]

        while len(current_level) > 1:
            # If odd number of nodes, duplicate the last one
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])
            next_level = []
            for i in range(0, len(current_level), 2):
                # E-04 FIX: Concatenate raw bytes (not hex strings).
                # Rust: combined = left_bytes + right_bytes; blake3(combined)
                left = current_level[i]
                right = current_level[i + 1]
                combined = left + right
                next_level.append(bytes.fromhex(_blake3_hash(combined)))
            current_level = next_level

        # Convert final root from bytes back to hex string
        return current_level[0].hex()

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
