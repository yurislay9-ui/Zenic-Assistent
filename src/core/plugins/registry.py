from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .types import PluginCapability, PluginInstance, PluginManifest, PluginState

logger = logging.getLogger("zenic_agents.core.plugins.registry")

DB_DIR = Path.home() / ".zenic_agents" / "db"
DB_PATH = DB_DIR / "plugins.sqlite"


def _retry(func: Any, max_retries: int = 3, base_delay: float = 1.0) -> Any:
    for attempt in range(max_retries):
        try:
            return func()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


class PluginRegistry:
    """Thread-safe plugin registry with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._plugins: Dict[str, PluginInstance] = {}
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        DB_DIR.mkdir(parents=True, exist_ok=True)

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS plugins (
                    plugin_id TEXT PRIMARY KEY,
                    manifest_json TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'unloaded',
                    loaded_at TEXT,
                    error_message TEXT,
                    config_json TEXT NOT NULL DEFAULT '{}',
                    updated_at REAL NOT NULL
                )"""
            )
            conn.commit()
            conn.close()

        _retry(_create)
        self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM plugins").fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
            conn.close()
            for row in rows:
                manifest_data = json.loads(row["manifest_json"])
                manifest = PluginManifest(
                    id=manifest_data.get("id", ""),
                    name=manifest_data.get("name", ""),
                    version=manifest_data.get("version", ""),
                    description=manifest_data.get("description", ""),
                    author=manifest_data.get("author", ""),
                    capabilities={PluginCapability(c) for c in manifest_data.get("capabilities", [])},
                    dependencies=manifest_data.get("dependencies", []),
                    min_core_version=manifest_data.get("min_core_version", "0.1.0"),
                    entry_point=manifest_data.get("entry_point", ""),
                    config_schema=manifest_data.get("config_schema", {}),
                )
                instance = PluginInstance(
                    manifest=manifest,
                    state=PluginState(row["state"]),
                    loaded_at=row["loaded_at"],
                    error_message=row["error_message"],
                    config=json.loads(row["config_json"]),
                )
                self._plugins[manifest.id] = instance
        except Exception as exc:
            logger.error("Failed to load plugins from DB: %s", exc)

    def _save_to_db(self, instance: PluginInstance) -> None:
        manifest_data = {
            "id": instance.manifest.id,
            "name": instance.manifest.name,
            "version": instance.manifest.version,
            "description": instance.manifest.description,
            "author": instance.manifest.author,
            "capabilities": [c.value for c in instance.manifest.capabilities],
            "dependencies": instance.manifest.dependencies,
            "min_core_version": instance.manifest.min_core_version,
            "entry_point": instance.manifest.entry_point,
            "config_schema": instance.manifest.config_schema,
        }

        def _upsert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO plugins
                   (plugin_id, manifest_json, state, loaded_at, error_message, config_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    instance.manifest.id,
                    json.dumps(manifest_data),
                    instance.state.value,
                    instance.loaded_at,
                    instance.error_message,
                    json.dumps(instance.config),
                    time.time(),
                ),
            )
            conn.commit()
            conn.close()

        _retry(_upsert)

    def _delete_from_db(self, plugin_id: str) -> None:
        def _del() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM plugins WHERE plugin_id = ?", (plugin_id,))  # nosemgrep: sqlalchemy-execute-raw-query
            conn.commit()
            conn.close()

        _retry(_del)

    def register(self, manifest: PluginManifest, config: Optional[Dict[str, Any]] = None) -> str:
        """Register a plugin and return its ID."""
        with self._lock:
            valid, errors = self.validate_manifest(manifest)
            if not valid:
                raise ValueError(f"Invalid manifest: {errors}")

            if manifest.id in self._plugins:
                raise ValueError(f"Plugin already registered: {manifest.id}")

            instance = PluginInstance(
                manifest=manifest,
                state=PluginState.UNLOADED,
                config=config or {},
            )
            self._plugins[manifest.id] = instance
            self._save_to_db(instance)
            logger.info("Plugin registered: %s v%s", manifest.id, manifest.version)
            return manifest.id

    def unregister(self, plugin_id: str) -> bool:
        """Unregister a plugin."""
        with self._lock:
            if plugin_id not in self._plugins:
                return False
            instance = self._plugins[plugin_id]
            if instance.state == PluginState.ACTIVE:
                logger.warning("Cannot unregister active plugin: %s", plugin_id)
                return False
            del self._plugins[plugin_id]
            self._delete_from_db(plugin_id)
            logger.info("Plugin unregistered: %s", plugin_id)
            return True

    def get_plugin(self, plugin_id: str) -> Optional[PluginInstance]:
        with self._lock:
            return self._plugins.get(plugin_id)

    def list_plugins(
        self,
        state: Optional[PluginState] = None,
        capability: Optional[PluginCapability] = None,
    ) -> List[PluginInstance]:
        with self._lock:
            result = list(self._plugins.values())
            if state is not None:
                result = [p for p in result if p.state == state]
            if capability is not None:
                result = [p for p in result if capability in p.manifest.capabilities]
            return result

    def resolve_dependencies(self, plugin_id: str) -> List[str]:
        """Topological sort of plugin dependencies."""
        with self._lock:
            visited: Set[str] = set()
            order: List[str] = []
            visiting: Set[str] = set()

            def _visit(pid: str) -> None:
                if pid in visited:
                    return
                if pid in visiting:
                    raise ValueError(f"Circular dependency detected at: {pid}")
                visiting.add(pid)
                instance = self._plugins.get(pid)
                if instance is not None:
                    for dep in instance.manifest.dependencies:
                        if dep in self._plugins:
                            _visit(dep)
                visiting.discard(pid)
                visited.add(pid)
                order.append(pid)

            _visit(plugin_id)
            return order

    def validate_manifest(self, manifest: PluginManifest) -> Tuple[bool, List[str]]:
        """Validate a plugin manifest."""
        errors: List[str] = []
        if not manifest.id or not re.match(r'^[a-zA-Z0-9_][a-zA-Z0-9_-]*$', manifest.id):
            errors.append("Plugin ID must be non-empty alphanumeric with underscores/hyphens")
        if not manifest.name:
            errors.append("Plugin name is required")
        if not manifest.version or not re.match(r'^\d+\.\d+\.\d+', manifest.version):
            errors.append("Version must follow semver (x.y.z)")
        if not manifest.entry_point:
            errors.append("Entry point is required")
        if self.check_circular_dependencies(manifest.id, manifest.dependencies):
            errors.append("Circular dependency detected")
        for dep in manifest.dependencies:
            if dep not in self._plugins and dep != manifest.id:
                logger.warning("Dependency not yet registered: %s", dep)
        return (len(errors) == 0, errors)

    def set_state(
        self, plugin_id: str, state: PluginState, error: Optional[str] = None
    ) -> bool:
        with self._lock:
            instance = self._plugins.get(plugin_id)
            if instance is None:
                return False
            instance.state = state
            if error is not None:
                instance.error_message = error
            if state == PluginState.LOADED or state == PluginState.ACTIVE:
                instance.loaded_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._save_to_db(instance)
            return True

    def get_plugins_by_capability(self, cap: PluginCapability) -> List[PluginInstance]:
        with self._lock:
            return [p for p in self._plugins.values() if cap in p.manifest.capabilities]

    def check_circular_dependencies(
        self, plugin_id: str, dependencies: List[str]
    ) -> bool:
        """Return True if circular dependency detected."""
        visited: Set[str] = set()
        stack: Set[str] = set()

        def _visit(pid: str) -> bool:
            if pid in stack:
                return True
            if pid in visited:
                return False
            visited.add(pid)
            stack.add(pid)
            instance = self._plugins.get(pid)
            if instance is not None:
                for dep in instance.manifest.dependencies:
                    if _visit(dep):
                        return True
            stack.discard(pid)
            return False

        for dep in dependencies:
            if dep == plugin_id:
                return True
            if _visit(dep):
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            state_counts: Dict[str, int] = defaultdict(int)
            cap_counts: Dict[str, int] = defaultdict(int)
            for p in self._plugins.values():
                state_counts[p.state.value] += 1
                for c in p.manifest.capabilities:
                    cap_counts[c.value] += 1
            return {
                "total_plugins": len(self._plugins),
                "by_state": dict(state_counts),
                "by_capability": dict(cap_counts),
            }


_registry_instance: Optional[PluginRegistry] = None
_registry_lock = threading.Lock()


def get_plugin_registry(db_path: Optional[str] = None) -> PluginRegistry:
    global _registry_instance
    with _registry_lock:
        if _registry_instance is None:
            _registry_instance = PluginRegistry(db_path=db_path)
        return _registry_instance


def reset_plugin_registry() -> None:
    global _registry_instance
    with _registry_lock:
        _registry_instance = None
