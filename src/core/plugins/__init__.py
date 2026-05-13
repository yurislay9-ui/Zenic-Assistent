from __future__ import annotations

try:
    from .types import PluginState, PluginCapability, PluginManifest, PluginInstance
except ImportError:
    PluginState = None  # type: ignore[assignment,misc]
    PluginCapability = None  # type: ignore[assignment,misc]
    PluginManifest = None  # type: ignore[assignment,misc]
    PluginInstance = None  # type: ignore[assignment,misc]

try:
    from .registry import PluginRegistry, get_plugin_registry, reset_plugin_registry
except ImportError:
    PluginRegistry = None  # type: ignore[assignment,misc]
    get_plugin_registry = None  # type: ignore[assignment,misc]
    reset_plugin_registry = None  # type: ignore[assignment,misc]

try:
    from .lifecycle import PluginLifecycleManager, get_plugin_lifecycle, reset_plugin_lifecycle
except ImportError:
    PluginLifecycleManager = None  # type: ignore[assignment,misc]
    get_plugin_lifecycle = None  # type: ignore[assignment,misc]
    reset_plugin_lifecycle = None  # type: ignore[assignment,misc]

try:
    from .hook_system import (
        HookType,
        HookRegistration,
        PluginHookSystem,
        get_plugin_hook_system,
        reset_plugin_hook_system,
    )
except ImportError:
    HookType = None  # type: ignore[assignment,misc]
    HookRegistration = None  # type: ignore[assignment,misc]
    PluginHookSystem = None  # type: ignore[assignment,misc]
    get_plugin_hook_system = None  # type: ignore[assignment,misc]
    reset_plugin_hook_system = None  # type: ignore[assignment,misc]

__all__ = [
    "PluginState", "PluginCapability", "PluginManifest", "PluginInstance",
    "PluginRegistry", "get_plugin_registry", "reset_plugin_registry",
    "PluginLifecycleManager", "get_plugin_lifecycle", "reset_plugin_lifecycle",
    "HookType", "HookRegistration", "PluginHookSystem",
    "get_plugin_hook_system", "reset_plugin_hook_system",
]
