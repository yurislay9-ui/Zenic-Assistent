"""
SandboxWorkspace — isolated workspace for sandbox execution.
"""

import os
import shutil
import threading
import time
import uuid
import logging
from pathlib import Path

from ._imports import logger


class SandboxWorkspace:
    """
    Workspace aislado para una ejecucion de sandbox.

    Crea un directorio temporal con estructura completa donde:
    - El codigo se ejecuta SIN acceso al filesystem del proyecto
    - Los builtins son reemplazados por versiones seguras
    - Las escrituras de archivos se redirigen al workspace
    - Las bases de datos son independientes
    """

    def __init__(self, sandbox_id=None, auto_cleanup=True, ttl_seconds=3600, client_id='default'):
        """
        Args:
            sandbox_id: ID unico del workspace. Si None, se genera uno.
            auto_cleanup: Si True, elimina el workspace al hacer close().
            ttl_seconds: Tiempo de vida maximo antes de cleanup automatico.
            client_id: Brecha B: Client identifier for multi-client isolation.
        """
        self.sandbox_id = sandbox_id or uuid.uuid4().hex[:12]
        self.auto_cleanup = auto_cleanup
        self.ttl_seconds = ttl_seconds
        self._closed = False
        self._created_at = time.time()
        self.client_id = client_id  # Brecha B: Multi-client isolation

        # Directorio raiz del sandbox
        self.sandbox_root = self._get_sandbox_root()
        self.workspace_dir = self.sandbox_root / f"workspace_{self.sandbox_id}_{self.client_id}"

        # Subdirectorios del workspace
        self.code_dir = self.workspace_dir / "code"
        self.projects_dir = self.workspace_dir / "projects"
        self.db_dir = self.workspace_dir / "db"
        self.logs_dir = self.workspace_dir / "logs"
        self.tmp_dir = self.workspace_dir / "tmp"

        # Crear estructura completa
        self._create_workspace()

        # Lock para operaciones concurrentes
        self._lock = threading.Lock()

        logger.info("SandboxWorkspace creado: %s (client_id=%s, auto_cleanup=%s)",
                     self.sandbox_id, self.client_id, auto_cleanup)

    def _get_sandbox_root(self) -> Path:
        """Obtiene el directorio raiz del sandbox (separado de data/)."""
        if 'ANDROID_ARGUMENT' in os.environ:
            try:
                from android.storage import app_storage_path
                return Path(app_storage_path()) / "zenic_sandbox"
            except Exception as e:
                logger.debug(f"SandboxWorkspace: Android storage path detection failed: {e}")
        return Path.home() / ".zenic_agents" / "sandbox"

    def _create_workspace(self):
        """Crea la estructura completa del workspace aislado."""
        for d in [self.code_dir, self.projects_dir, self.db_dir,
                  self.logs_dir, self.tmp_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Escribir archivo de metadatos del workspace
        meta = {
            "sandbox_id": self.sandbox_id,
            "client_id": self.client_id,
            "created_at": self._created_at,
            "ttl_seconds": self.ttl_seconds,
            "pid": os.getpid(),
            "auto_cleanup": self.auto_cleanup,
        }
        meta_path = self.workspace_dir / ".sandbox_meta"
        meta_path.write_text(
            "\n".join(f"{k}={v}" for k, v in meta.items()),
            encoding="utf-8"
        )

    def write_code(self, code: str, filename: str = "sandbox_code.py") -> Path:
        """
        Write code to the sandbox code directory with path traversal protection.

        Returns:
            Path al archivo creado dentro del workspace
        """
        # Sanitize filename to prevent path traversal
        if not filename:
            raise ValueError("Filename cannot be empty")
        clean = filename.replace("..", "").replace("/", "").replace("\\", "")
        if clean != filename:
            raise ValueError(f"Invalid filename (path traversal detected): {filename!r}")
        code_path = self.code_dir / filename
        # Verify the resolved path stays within the sandbox
        if not code_path.resolve().is_relative_to(self.workspace_dir.resolve()):
            raise ValueError(f"Path escape detected: {filename!r}")
        code_path.write_text(code, encoding="utf-8")
        logger.debug("Codigo escrito en: %s", code_path)
        return code_path

    def read_code(self, filename: str = "sandbox_code.py") -> str:
        """Lee codigo del workspace aislado.

        Security: Path traversal protection on filename.
        """
        code_path = self._validate_path_in_workspace(self.code_dir, filename)
        if code_path.exists():
            return code_path.read_text(encoding="utf-8")
        return ""

    def _validate_path_in_workspace(self, base_dir: Path, rel_path: str) -> Path:
        """Validate that rel_path resolves within the workspace to prevent path traversal.

        Security: Prevents ../../etc/passwd style attacks by resolving the
        full path and verifying it stays within the workspace boundary.

        Args:
            base_dir: Base directory within workspace (e.g. projects_dir, tmp_dir).
            rel_path: Relative path to validate.

        Returns:
            Resolved Path object guaranteed to be within workspace.

        Raises:
            ValueError: If rel_path escapes the workspace boundary.
        """
        target = base_dir / rel_path
        resolved = target.resolve()
        workspace_resolved = self.workspace_dir.resolve()
        if not resolved.is_relative_to(workspace_resolved):
            raise ValueError(
                f"Sandbox path traversal detected: '{rel_path}' resolves to "
                f"'{resolved}' which is outside the workspace "
                f"'{workspace_resolved}'"
            )
        return resolved

    def write_project_file(self, rel_path: str, content: str) -> Path:
        """
        Escribe un archivo de proyecto en el workspace aislado.
        NUNCA toca el directorio de proyectos real del sistema.

        Security: Path traversal protection ensures rel_path cannot escape
        the workspace boundary (e.g. ../../etc/crontab).
        """
        file_path = self._validate_path_in_workspace(self.projects_dir, rel_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def read_project_file(self, rel_path: str) -> str:
        """Lee un archivo de proyecto del workspace aislado.

        Security: Path traversal protection prevents reading files outside workspace.
        """
        file_path = self._validate_path_in_workspace(self.projects_dir, rel_path)
        if file_path.exists():
            return file_path.read_text(encoding="utf-8")
        return ""

    def project_file_exists(self, rel_path: str) -> bool:
        """Verifica si un archivo existe en el workspace aislado.

        Security: Path traversal protection.
        """
        try:
            file_path = self._validate_path_in_workspace(self.projects_dir, rel_path)
            return file_path.exists()
        except ValueError:
            return False

    def snapshot_project_file(self, rel_path: str, source_content: str) -> Path:
        """
        Crea un snapshot (backup) de un archivo en el workspace aislado.
        Equivalente a MerkleLedger.snapshot() pero dentro del sandbox.

        Security: Validates rel_path stays within workspace before creating backup.
        """
        import hashlib as _hashlib
        import json as _json

        # Validate that the source rel_path is within workspace
        self._validate_path_in_workspace(self.projects_dir, rel_path)
        bk_dir = self.workspace_dir / "backups"
        bk_dir.mkdir(exist_ok=True)
        # Use a safe backup name: hash the rel_path to avoid collisions and traversal
        safe_name = _hashlib.sha256(rel_path.encode()).hexdigest()[:16] + ".bak"
        bk_path = bk_dir / safe_name
        bk_path.write_text(source_content, encoding="utf-8")
        # Store mapping from rel_path to backup name for rollback lookup
        map_path = bk_dir / "_map"
        mapping = {}
        if map_path.exists():
            try:
                mapping = _json.loads(map_path.read_text(encoding="utf-8"))
            except Exception:
                mapping = {}
        mapping[rel_path] = safe_name
        map_path.write_text(_json.dumps(mapping), encoding="utf-8")
        return bk_path

    def rollback_project_file(self, rel_path: str) -> bool:
        """
        Restaura un archivo desde el backup en el workspace aislado.

        Security: Path traversal protection on both source and target paths.
        """
        # Validate target path
        target_path = self._validate_path_in_workspace(self.projects_dir, rel_path)
        bk_dir = self.workspace_dir / "backups"
        # Look up backup name from mapping file
        map_path = bk_dir / "_map"
        safe_name = None
        if map_path.exists():
            try:
                import json as _json
                mapping = _json.loads(map_path.read_text(encoding="utf-8"))
                safe_name = mapping.get(rel_path)
            except Exception:
                pass
        if safe_name is None:
            # Fallback: try legacy naming for backwards compatibility
            safe_name = rel_path.replace("/", "_")
        bk_path = self._validate_path_in_workspace(bk_dir, safe_name)
        if bk_path.exists():
            shutil.copy2(bk_path, target_path)
            return True
        return False

    def get_db_path(self, db_name: str) -> str:
        """
        Retorna la ruta a una base de datos DENTRO del sandbox.
        Las DBs del sandbox son INDEPENDIENTES de las del sistema.
        """
        return str(self.db_dir / db_name)

    def get_tmp_path(self, filename: str) -> Path:
        """Retorna una ruta temporal dentro del sandbox.

        Security: Path traversal protection prevents escaping tmp directory.
        """
        return self._validate_path_in_workspace(self.tmp_dir, filename)

    def write_log(self, log_content: str, log_name: str = "execution.log"):
        """Escribe un log de ejecucion dentro del workspace.

        Security: Path traversal protection on log_name.
        """
        log_path = self._validate_path_in_workspace(self.logs_dir, log_name)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {log_content}\n")

    def is_expired(self) -> bool:
        """Verifica si el workspace ha excedido su TTL."""
        return (time.time() - self._created_at) > self.ttl_seconds

    def get_size_mb(self) -> float:
        """Retorna el tamaño total del workspace en MB."""
        total = 0
        if self.workspace_dir.exists():
            for f in self.workspace_dir.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
        return total / (1024 * 1024)

    def close(self):
        """
        Cierra el workspace. Si auto_cleanup=True, elimina todo el directorio.
        """
        if self._closed:
            return
        self._closed = True

        if self.auto_cleanup and self.workspace_dir.exists():
            try:
                # Measure size BEFORE cleanup so we report accurate freed bytes
                freed_mb = self.get_size_mb()
                shutil.rmtree(self.workspace_dir, ignore_errors=True)
                logger.info("SandboxWorkspace limpiado: %s (%.2f MB liberados)",
                            self.sandbox_id, freed_mb)
            except Exception as e:
                logger.warning("Error limpiando workspace %s: %s",
                               self.sandbox_id, e)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __repr__(self):
        return (f"SandboxWorkspace(id={self.sandbox_id}, "
                f"path={self.workspace_dir}, closed={self._closed})")
