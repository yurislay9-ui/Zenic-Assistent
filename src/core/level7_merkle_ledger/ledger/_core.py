"""ZENIC-AGENTS - Merkle Ledger v17 (Tenant-Aware + Sandbox Isolated) — Operations

Snapshot, commit, rollback, and purge operations for the Merkle Ledger.
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
from ._hash_helpers import MerkleLedgerHelpersMixin

_BACKUP_HASH_LENGTH = 16

logger = logging.getLogger(__name__)


class MerkleLedger(MerkleLedgerHelpersMixin):
    """Ledger con arbol Merkle para integridad criptografica. Tenant-aware + sandbox-isolated."""

    def __init__(self):
        self.bk_dir = get_data_dir() / "backups"
        self.bk_dir.mkdir(exist_ok=True)
        self._tenant_id: str = resolve_tenant_id()
        logger.debug("MerkleLedger initialized with tenant_id='%s'", self._tenant_id)
        self._init_db()

    def snapshot(self, rel_path: str, project_dir, workspace=None) -> None:
        """
        Crea un snapshot (backup) de un archivo.

        Si se proporciona workspace, opera DENTRO del workspace aislado.
        Si no, opera en el directorio de proyectos del sistema (legacy).

        Todas las operaciones se registran con el tenant_id actual.
        """
        tid = self._tenant_id
        if workspace is not None:
            # MODO AISLADO: operar dentro del workspace del sandbox
            content = workspace.read_project_file(rel_path)
            if content:
                workspace.snapshot_project_file(rel_path, content)
                content_hash = self._hash_content(content)
                parent_hash = self._get_last_hash(rel_path, workspace.get_db_path("merkle_ledger.sqlite"), tenant_id=tid)
                self._ensure_sandbox_db(workspace)
                self._record_operation(
                    rel_path, content_hash, parent_hash, "SNAPSHOT",
                    workspace.get_db_path("merkle_ledger.sqlite"), tenant_id=tid
                )
                logger.debug("Snapshot (sandbox): %s in workspace %s [tenant=%s]", rel_path, workspace.sandbox_id, tid)
            else:
                logger.debug(
                    "Snapshot (sandbox): %s does not exist in workspace %s — "
                    "no backup needed (new file) [tenant=%s]",
                    rel_path, workspace.sandbox_id, tid,
                )
        else:
            # MODO LEGACY: operar en el filesystem del sistema
            try:
                project_path = Path(project_dir).resolve()
                p = self._validate_rel_path(rel_path, project_path)
            except ValueError as e:
                logger.warning("Snapshot rejected (path traversal): %s", e)
                return
            if p.exists():
                content = p.read_text(encoding="utf-8")
                safe_bk_name = hashlib.sha256(rel_path.encode()).hexdigest()[:_BACKUP_HASH_LENGTH] + ".bak"
                bk_path = self.bk_dir / safe_bk_name
                shutil.copy2(p, bk_path)
                content_hash = self._hash_content(content)
                parent_hash = self._get_last_hash(rel_path, tenant_id=tid)
                self._record_operation(rel_path, content_hash, parent_hash, "SNAPSHOT", tenant_id=tid)

    def commit(self, rel_path: str, content: str, project_dir, workspace=None) -> 'MerkleNode':
        """
        Escribe contenido y registra el commit en el ledger.

        Si se proporciona workspace, escribe DENTRO del workspace aislado.

        Returns:
            MerkleNode con el hash del commit
        """
        tid = self._tenant_id
        if workspace is not None:
            workspace.write_project_file(rel_path, content)
            content_hash = self._hash_content(content)
            self._ensure_sandbox_db(workspace)
            parent_hash = self._get_last_hash(rel_path, workspace.get_db_path("merkle_ledger.sqlite"), tenant_id=tid)

            all_hashes = list(self._get_all_file_hashes(
                workspace.get_db_path("merkle_ledger.sqlite"), tenant_id=tid).values())
            all_hashes.append(content_hash)

            root_hash = self._merkle_root(all_hashes) if len(all_hashes) >= 2 else content_hash

            self._record_operation(
                rel_path, root_hash, parent_hash, "COMMIT",
                workspace.get_db_path("merkle_ledger.sqlite"), tenant_id=tid
            )
            logger.info("Commit (sandbox): %s -> %s in workspace %s [tenant=%s]",
                        rel_path, root_hash[:12], workspace.sandbox_id, tid)
        else:
            try:
                project_path = Path(project_dir).resolve()
                p = self._validate_rel_path(rel_path, project_path)
            except ValueError as e:
                logger.warning("Commit rejected (path traversal): %s", e)
                return MerkleNode(
                    file_path=rel_path, hash_sha256="REJECTED",
                    parent_hash="N/A", timestamp=int(time.time()), operation="REJECTED"
                )
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            content_hash = self._hash_content(content)
            parent_hash = self._get_last_hash(rel_path, tenant_id=tid)

            all_hashes = list(self._get_all_file_hashes(tenant_id=tid).values())
            all_hashes.append(content_hash)

            root_hash = self._merkle_root(all_hashes) if len(all_hashes) >= 2 else content_hash

            self._record_operation(rel_path, root_hash, parent_hash, "COMMIT", tenant_id=tid)

        return MerkleNode(
            file_path=rel_path, hash_sha256=root_hash,
            parent_hash=parent_hash, timestamp=int(time.time()), operation="COMMIT"
        )

    def rollback(self, rel_path: str, project_dir, workspace=None) -> bool:
        """
        Restaura un archivo desde el backup.

        Returns:
            bool: True si el rollback fue exitoso
        """
        tid = self._tenant_id
        if workspace is not None:
            success = workspace.rollback_project_file(rel_path)
            if success:
                content = workspace.read_project_file(rel_path)
                content_hash = self._hash_content(content)
                self._ensure_sandbox_db(workspace)
                parent_hash = self._get_last_hash(rel_path, workspace.get_db_path("merkle_ledger.sqlite"), tenant_id=tid)
                self._record_operation(
                    rel_path, content_hash, parent_hash, "ROLLBACK",
                    workspace.get_db_path("merkle_ledger.sqlite"), tenant_id=tid
                )
                logger.info("Rollback (sandbox): %s in workspace %s [tenant=%s]", rel_path, workspace.sandbox_id, tid)
            else:
                logger.warning("Rollback (sandbox): no backup for %s in workspace %s [tenant=%s]",
                               rel_path, workspace.sandbox_id, tid)
            return success
        else:
            try:
                project_path = Path(project_dir).resolve()
                p = self._validate_rel_path(rel_path, project_path)
            except ValueError as e:
                logger.warning("Rollback rejected (path traversal): %s", e)
                return False
            safe_bk_name = hashlib.sha256(rel_path.encode()).hexdigest()[:_BACKUP_HASH_LENGTH] + ".bak"
            bk = self.bk_dir / safe_bk_name
            if bk.exists():
                shutil.copy2(bk, p)
                content = p.read_text(encoding="utf-8")
                content_hash = self._hash_content(content)
                parent_hash = self._get_last_hash(rel_path, tenant_id=tid)
                self._record_operation(rel_path, content_hash, parent_hash, "ROLLBACK", tenant_id=tid)
                logger.info("Rollback successful: %s [tenant=%s]", rel_path, tid)
                return True
            elif p.exists():
                logger.warning("Rollback: no backup found for %s. Current file unchanged. [tenant=%s]", rel_path, tid)
                return False
        return False

    def _ensure_sandbox_db(self, workspace):
        """Asegura que la DB del ledger existe en el workspace del sandbox."""
        db_path = workspace.get_db_path("merkle_ledger.sqlite")
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        if not Path(db_path).exists():
            with sqlite3.connect(db_path) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS ledger (  # nosemgrep: sqlalchemy-execute-raw-query
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    hash_sha256 TEXT NOT NULL,
                    parent_hash TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    tenant_id TEXT NOT NULL DEFAULT '__anonymous__')""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_file ON ledger(file_path)")  # nosemgrep: sqlalchemy-execute-raw-query
                conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_tenant ON ledger(tenant_id)")  # nosemgrep: sqlalchemy-execute-raw-query

    def purge_tenant_ledger(self, tenant_id: str) -> int:
        """Delete all ledger entries for a specific tenant (GDPR / deprovisioning)."""
        try:
            conn = get_connection("merkle_ledger.sqlite")
            return purge_tenant_rows(conn, "ledger", tenant_id)
        except Exception as e:
            logger.error("MerkleLedger: purge failed for tenant '%s': %s", tenant_id, e)
            return 0
