from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class PluginState(str, Enum):
    UNLOADED = "unloaded"
    LOADED = "loaded"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


class PluginCapability(str, Enum):
    EXECUTOR = "executor"
    AGENT = "agent"
    MIDDLEWARE = "middleware"
    HOOK = "hook"
    PROVIDER = "provider"


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    capabilities: Set[PluginCapability] = field(default_factory=set)
    dependencies: List[str] = field(default_factory=list)
    min_core_version: str = "0.1.0"
    entry_point: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginInstance:
    manifest: PluginManifest
    state: PluginState = PluginState.UNLOADED
    loaded_at: Optional[str] = None
    error_message: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
