"""
SandboxIsolationManager — central manager for sandbox isolation.
"""

import os
import time
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path

from ._imports import logger
from ._workspace import SandboxWorkspace

# Named constants (previously magic numbers)
_DEFAULT_TTL_SECONDS = 3600
_CLEANUP_INTERVAL_SECONDS = 60
_CLEANUP_OLDEST_COUNT = 2


class SandboxIsolationManager:
    """
    Gestor central de aislamiento del sandbox.

    Responsabilidades:
    1. Crear/destruir workspaces aislados
    2. Limpiar workspaces expirados automaticamente
    3. Verificar que el sandbox NUNCA escribe fuera de su workspace
    4. Proveer builtins restringidos para ejecucion segura
    5. Monitorear uso de recursos del sandbox

    FIX (Phase 3): __init__ previously created a full SandboxWorkspace
    object just to get the root path, which leaked directories and a
    workspace object. Now computes the path directly.
    """

    # Maximo de workspaces simultaneos para evitar consumir toda la RAM
    MAX_CONCURRENT_WORKSPACES = 10
    # Maximo tamaño total de todos los workspaces en MB
    MAX_TOTAL_SIZE_MB = 500

    def __init__(self):
        # FIX (Phase 3): Compute sandbox root directly instead of creating
        # a full SandboxWorkspace object just to get the path.
        # The old code: SandboxWorkspace(sandbox_id="init", auto_cleanup=False).sandbox_root
        # created leaked directories (workspace_init_*) that were never cleaned up.
        self.sandbox_root = self._compute_sandbox_root()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self._active_workspaces: Dict[str, SandboxWorkspace] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = None
        self._running = True

        # Crear entorno base reutilizable
        self._ensure_base_env()

        # Iniciar thread de cleanup automatico
        self._start_cleanup_thread()

        logger.info("SandboxIsolationManager iniciado (root=%s)", self.sandbox_root)

    @staticmethod
    def _compute_sandbox_root() -> Path:
        """Compute the sandbox root directory without creating a workspace.

        FIX (Phase 3): Previously, __init__ created a SandboxWorkspace
        with auto_cleanup=False just to get sandbox_root, which leaked
        a workspace directory on disk forever. Now we compute the same
        path directly, matching SandboxWorkspace._get_sandbox_root().
        """
        if 'ANDROID_ARGUMENT' in os.environ:
            try:
                from android.storage import app_storage_path
                return Path(app_storage_path()) / "zenic_sandbox"
            except Exception as e:
                logger.debug(f"SandboxIsolationManager: Android storage path detection failed: {e}")
        return Path.home() / ".zenic_agents" / "sandbox"

    def _ensure_base_env(self):
        """Crea el entorno base que se copia a cada workspace nuevo."""
        base_dir = self.sandbox_root / "base_env"
        base_dir.mkdir(parents=True, exist_ok=True)

        # Crear estructura base minima
        (base_dir / "code").mkdir(exist_ok=True)
        (base_dir / "projects").mkdir(exist_ok=True)
        (base_dir / "db").mkdir(exist_ok=True)
        (base_dir / "logs").mkdir(exist_ok=True)
        (base_dir / "tmp").mkdir(exist_ok=True)

    def create_workspace(self, sandbox_id=None, ttl_seconds=_DEFAULT_TTL_SECONDS, client_id='default') -> SandboxWorkspace:
        """
        Crea un nuevo workspace aislado para ejecucion de sandbox.

        Args:
            sandbox_id: ID opcional. Se genera uno si no se proporciona.
            ttl_seconds: Tiempo de vida del workspace antes de cleanup.

        Returns:
            SandboxWorkspace listo para usar.

        Raises:
            RuntimeError: Si se excede el limite de workspaces simultaneos.
        """
        with self._lock:
            # Verificar limites
            if len(self._active_workspaces) >= self.MAX_CONCURRENT_WORKSPACES:
                # Forzar cleanup de workspaces expirados
                self._cleanup_expired()
                if len(self._active_workspaces) >= self.MAX_CONCURRENT_WORKSPACES:
                    raise RuntimeError(
                        f"Maximo de workspaces simultaneos alcanzado "
                        f"({self.MAX_CONCURRENT_WORKSPACES}). "
                        f"Espera a que terminen las ejecuciones en curso."
                    )

            # Verificar tamaño total
            total_size = self._get_total_size_mb()
            if total_size >= self.MAX_TOTAL_SIZE_MB:
                self._cleanup_expired()
                self._cleanup_oldest(count=_CLEANUP_OLDEST_COUNT)
                total_size = self._get_total_size_mb()
                if total_size >= self.MAX_TOTAL_SIZE_MB:
                    raise RuntimeError(
                        f"Limite de almacenamiento del sandbox alcanzado "
                        f"({total_size:.0f}/{self.MAX_TOTAL_SIZE_MB} MB). "
                        f"Ejecuta cleanup_forced() para liberar espacio."
                    )

            workspace = SandboxWorkspace(
                sandbox_id=sandbox_id,
                auto_cleanup=False,  # El manager controla el ciclo de vida
                ttl_seconds=ttl_seconds,
                client_id=client_id,  # Brecha B: Pass client_id to workspace
            )
            self._active_workspaces[workspace.sandbox_id] = workspace

            logger.info("Workspace creado: %s (activos: %d/%d)",
                        workspace.sandbox_id,
                        len(self._active_workspaces),
                        self.MAX_CONCURRENT_WORKSPACES)

            return workspace

    def release_workspace(self, sandbox_id: str):
        """
        Libera un workspace, eliminandolo del disco.

        Args:
            sandbox_id: ID del workspace a liberar.
        """
        with self._lock:
            workspace = self._active_workspaces.pop(sandbox_id, None)
            if workspace:
                workspace.auto_cleanup = True
                workspace.close()
                logger.info("Workspace liberado: %s", sandbox_id)

    def get_workspace(self, sandbox_id: str) -> Optional[SandboxWorkspace]:
        """Obtiene un workspace activo por su ID."""
        return self._active_workspaces.get(sandbox_id)

    def list_active_workspaces(self) -> List[Dict[str, Any]]:
        """Lista todos los workspaces activos con su estado."""
        result = []
        for ws in self._active_workspaces.values():
            result.append({
                "sandbox_id": ws.sandbox_id,
                "client_id": ws.client_id,
                "path": str(ws.workspace_dir),
                "size_mb": ws.get_size_mb(),
                "age_seconds": int(time.time() - ws._created_at),
                "expired": ws.is_expired(),
                "closed": ws._closed,
            })
        return result

    def list_client_workspaces(self, client_id: str) -> List[Dict[str, Any]]:
        """Brecha B: Lista todos los workspaces activos para un client_id especifico."""
        result = []
        for ws in self._active_workspaces.values():
            if ws.client_id == client_id:
                result.append({
                    "sandbox_id": ws.sandbox_id,
                    "client_id": ws.client_id,
                    "path": str(ws.workspace_dir),
                    "size_mb": ws.get_size_mb(),
                    "age_seconds": int(time.time() - ws._created_at),
                    "expired": ws.is_expired(),
                    "closed": ws._closed,
                })
        return result

    def release_client_workspaces(self, client_id: str):
        """Brecha B: Libera todos los workspaces de un client_id especifico."""
        with self._lock:
            client_sids = [
                sid for sid, ws in self._active_workspaces.items()
                if ws.client_id == client_id
            ]
            for sid in client_sids:
                self._release_unsafe(sid)
            if client_sids:
                logger.info(
                    "Released %d workspaces for client_id='%s'",
                    len(client_sids), client_id
                )

    def cleanup_forced(self):
        """
        Fuerza la limpieza de TODOS los workspaces (incluso los no expirados).
        Se usa cuando el sistema necesita liberar memoria/disco urgentemente.
        """
        with self._lock:
            ids = list(self._active_workspaces.keys())
            for sid in ids:
                self._release_unsafe(sid)
            logger.warning("Cleanup forzado completado: %d workspaces eliminados", len(ids))

    def _cleanup_expired(self):
        """Elimina workspaces que han excedido su TTL."""
        expired_ids = [
            sid for sid, ws in self._active_workspaces.items()
            if ws.is_expired()
        ]
        for sid in expired_ids:
            self._release_unsafe(sid)
        if expired_ids:
            logger.info("Cleanup TTL: %d workspaces expirados eliminados", len(expired_ids))

    def _cleanup_oldest(self, count: int = 1):
        """Elimina los workspaces mas antiguos para liberar espacio."""
        sorted_ws = sorted(
            self._active_workspaces.items(),
            key=lambda x: x[1]._created_at
        )
        for sid, ws in sorted_ws[:count]:
            self._release_unsafe(sid)

    def _release_unsafe(self, sandbox_id: str):
        """Libera un workspace sin adquirir el lock (llamar dentro de _lock)."""
        workspace = self._active_workspaces.pop(sandbox_id, None)
        if workspace:
            workspace.auto_cleanup = True
            workspace.close()

    def _get_total_size_mb(self) -> float:
        """Calcula el tamaño total de todos los workspaces activos."""
        return sum(ws.get_size_mb() for ws in self._active_workspaces.values())

    def _start_cleanup_thread(self):
        """Inicia un thread daemon que limpia workspaces expirados periodicamente."""
        def _cleanup_loop():
            while self._running:
                try:
                    time.sleep(_CLEANUP_INTERVAL_SECONDS)  # Check periodically
                    with self._lock:
                        self._cleanup_expired()
                except Exception as e:
                    logger.error("Error en cleanup thread: %s", e)

        self._cleanup_thread = threading.Thread(
            target=_cleanup_loop, daemon=True, name="sandbox-cleanup"
        )
        self._cleanup_thread.start()

    def shutdown(self):
        """Detiene el manager y limpia todos los workspaces."""
        self._running = False
        self.cleanup_forced()
        logger.info("SandboxIsolationManager detenido")
