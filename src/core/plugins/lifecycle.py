from __future__ import annotations

import importlib
import logging
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .registry import PluginRegistry, get_plugin_registry
from .types import PluginInstance, PluginManifest, PluginState

logger = logging.getLogger("zenic_agents.core.plugins.lifecycle")


class PluginLifecycleManager:
    """Thread-safe plugin lifecycle manager."""

    def __init__(self, registry: Optional[PluginRegistry] = None) -> None:
        self._lock = threading.RLock()
        self._registry = registry or get_plugin_registry()
        self._loaded_modules: Dict[str, Any] = {}

    def load_plugin(self, plugin_id: str) -> Tuple[bool, Optional[str]]:
        """Load and activate a plugin."""
        with self._lock:
            instance = self._registry.get_plugin(plugin_id)
            if instance is None:
                return (False, f"Plugin not found: {plugin_id}")
            if instance.state == PluginState.DISABLED:
                return (False, f"Plugin is disabled: {plugin_id}")
            if instance.state == PluginState.ACTIVE:
                return (True, None)

            # Resolve and load dependencies first
            try:
                dep_order = self._registry.resolve_dependencies(plugin_id)
            except ValueError as exc:
                self._registry.set_state(plugin_id, PluginState.ERROR, str(exc))
                return (False, str(exc))

            for dep_id in dep_order:
                dep = self._registry.get_plugin(dep_id)
                if dep is not None and dep.state not in (PluginState.ACTIVE, PluginState.LOADED):
                    if dep_id != plugin_id:
                        ok, err = self.load_plugin(dep_id)
                        if not ok:
                            self._registry.set_state(
                                plugin_id, PluginState.ERROR,
                                f"Dependency {dep_id} failed: {err}",
                            )
                            return (False, f"Dependency {dep_id} failed: {err}")

            # Execute entry point
            success, error = self._execute_entry_point(instance.manifest)
            if not success:
                self._registry.set_state(plugin_id, PluginState.ERROR, error)
                return (False, error)

            self._registry.set_state(plugin_id, PluginState.ACTIVE)
            logger.info("Plugin loaded and activated: %s", plugin_id)
            return (True, None)

    def unload_plugin(self, plugin_id: str) -> bool:
        """Deactivate and unload a plugin."""
        with self._lock:
            instance = self._registry.get_plugin(plugin_id)
            if instance is None:
                return False
            if instance.state not in (PluginState.ACTIVE, PluginState.LOADED, PluginState.ERROR):
                return True

            # Check if other active plugins depend on this one
            all_plugins = self._registry.list_plugins(state=PluginState.ACTIVE)
            for p in all_plugins:
                if plugin_id in p.manifest.dependencies:
                    logger.warning(
                        "Cannot unload %s: active plugin %s depends on it",
                        plugin_id, p.manifest.id,
                    )
                    return False

            self._registry.set_state(plugin_id, PluginState.UNLOADED)
            self._loaded_modules.pop(plugin_id, None)
            logger.info("Plugin unloaded: %s", plugin_id)
            return True

    def reload_plugin(self, plugin_id: str) -> Tuple[bool, Optional[str]]:
        """Unload then load a plugin."""
        with self._lock:
            if not self.unload_plugin(plugin_id):
                return (False, f"Failed to unload plugin: {plugin_id}")
            return self.load_plugin(plugin_id)

    def enable_plugin(self, plugin_id: str) -> bool:
        """Enable a disabled plugin."""
        with self._lock:
            instance = self._registry.get_plugin(plugin_id)
            if instance is None:
                return False
            if instance.state != PluginState.DISABLED:
                return False
            self._registry.set_state(plugin_id, PluginState.UNLOADED)
            logger.info("Plugin enabled: %s", plugin_id)
            return True

    def disable_plugin(self, plugin_id: str) -> bool:
        """Disable a plugin (must be unloaded first)."""
        with self._lock:
            instance = self._registry.get_plugin(plugin_id)
            if instance is None:
                return False
            if instance.state == PluginState.ACTIVE:
                if not self.unload_plugin(plugin_id):
                    return False
            self._registry.set_state(plugin_id, PluginState.DISABLED)
            logger.info("Plugin disabled: %s", plugin_id)
            return True

    def load_all(self) -> Dict[str, bool]:
        """Load all registered plugins in dependency order."""
        with self._lock:
            results: Dict[str, bool] = {}
            all_plugins = self._registry.list_plugins()

            # Build a set of plugin IDs to load
            to_load = {p.manifest.id for p in all_plugins if p.state != PluginState.ACTIVE}
            loaded: set = set()

            # Try loading in multiple passes to handle dependencies
            for _ in range(len(to_load) + 1):
                if not to_load:
                    break
                progress = False
                for pid in list(to_load):
                    instance = self._registry.get_plugin(pid)
                    if instance is None:
                        to_load.discard(pid)
                        results[pid] = False
                        continue
                    deps_met = all(
                        d in loaded or self._registry.get_plugin(d) is None
                        or self._registry.get_plugin(d).state == PluginState.ACTIVE
                        for d in instance.manifest.dependencies
                    )
                    if deps_met:
                        ok, _ = self.load_plugin(pid)
                        results[pid] = ok
                        to_load.discard(pid)
                        if ok:
                            loaded.add(pid)
                        progress = True
                if not progress:
                    for pid in to_load:
                        results[pid] = False
                    break
            return results

    def unload_all(self) -> Dict[str, bool]:
        """Unload all active plugins in reverse dependency order."""
        with self._lock:
            results: Dict[str, bool] = {}
            active = self._registry.list_plugins(state=PluginState.ACTIVE)

            # Sort by reverse dependency order
            for p in reversed(active):
                results[p.manifest.id] = self.unload_plugin(p.manifest.id)
            return results

    def health_check(self, plugin_id: str) -> Dict[str, Any]:
        with self._lock:
            instance = self._registry.get_plugin(plugin_id)
            if instance is None:
                return {"healthy": False, "error": "Plugin not found"}
            return {
                "healthy": instance.state == PluginState.ACTIVE,
                "plugin_id": plugin_id,
                "state": instance.state.value,
                "loaded_at": instance.loaded_at,
                "error_message": instance.error_message,
            }

    def _execute_entry_point(
        self, manifest: PluginManifest
    ) -> Tuple[bool, Optional[str]]:
        """Execute a plugin's entry point module."""
        if not manifest.entry_point:
            return (True, None)

        try:
            module_path, _, attr = manifest.entry_point.partition(":")
            module = importlib.import_module(module_path)  # nosemgrep: non-literal-import  # SECURITY: module_path comes from validated plugin manifest
            if attr:
                initializer = getattr(module, attr, None)
                if initializer is not None and callable(initializer):
                    instance = self._registry.get_plugin(manifest.id)
                    config = instance.config if instance else {}
                    initializer(config)
            self._loaded_modules[manifest.id] = module
            return (True, None)
        except Exception as exc:
            logger.error("Entry point failed for %s: %s", manifest.id, exc)
            return (False, str(exc))

    def _call_hook(
        self, plugin_id: str, hook_name: str, data: Dict[str, Any]
    ) -> Any:
        """Call a hook on a loaded plugin module."""
        module = self._loaded_modules.get(plugin_id)
        if module is None:
            return None
        handler = getattr(module, hook_name, None)
        if handler is None or not callable(handler):
            return None
        try:
            return handler(data)
        except Exception as exc:
            logger.error("Hook %s on %s failed: %s", hook_name, plugin_id, exc)
            return None


_lifecycle_instance: Optional[PluginLifecycleManager] = None
_lifecycle_lock = threading.Lock()


def get_plugin_lifecycle(
    registry: Optional[PluginRegistry] = None,
) -> PluginLifecycleManager:
    global _lifecycle_instance
    with _lifecycle_lock:
        if _lifecycle_instance is None:
            _lifecycle_instance = PluginLifecycleManager(registry=registry)
        return _lifecycle_instance


def reset_plugin_lifecycle() -> None:
    global _lifecycle_instance
    with _lifecycle_lock:
        _lifecycle_instance = None
