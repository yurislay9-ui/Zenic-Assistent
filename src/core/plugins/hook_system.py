from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.core.plugins.hook_system")

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


class HookType(str, Enum):
    PRE_EXECUTE = "pre_execute"
    POST_EXECUTE = "post_execute"
    ON_ERROR = "on_error"
    ON_SUCCESS = "on_success"
    ON_APPROVAL = "on_approval"
    ON_ROLLBACK = "on_rollback"
    CUSTOM = "custom"


@dataclass
class HookRegistration:
    id: str
    plugin_id: str
    hook_type: HookType
    hook_name: str
    priority: int = 50
    callback_ref: str = ""
    active: bool = True


class PluginHookSystem:
    """Thread-safe hook/event system for plugins with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._hooks: Dict[str, HookRegistration] = {}
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        DB_DIR.mkdir(parents=True, exist_ok=True)

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS plugin_hooks (
                    hook_id TEXT PRIMARY KEY,
                    plugin_id TEXT NOT NULL,
                    hook_type TEXT NOT NULL,
                    hook_name TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 50,
                    callback_ref TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL
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
            rows = conn.execute("SELECT * FROM plugin_hooks").fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
            conn.close()
            for row in rows:
                reg = HookRegistration(
                    id=row["hook_id"],
                    plugin_id=row["plugin_id"],
                    hook_type=HookType(row["hook_type"]),
                    hook_name=row["hook_name"],
                    priority=row["priority"],
                    callback_ref=row["callback_ref"],
                    active=bool(row["active"]),
                )
                self._hooks[reg.id] = reg
        except Exception as exc:
            logger.error("Failed to load hooks from DB: %s", exc)

    def _save_to_db(self, reg: HookRegistration) -> None:
        def _upsert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO plugin_hooks
                   (hook_id, plugin_id, hook_type, hook_name, priority, callback_ref, active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (reg.id, reg.plugin_id, reg.hook_type.value, reg.hook_name,
                 reg.priority, reg.callback_ref, int(reg.active), time.time()),
            )
            conn.commit()
            conn.close()

        _retry(_upsert)

    def _delete_from_db(self, hook_id: str) -> None:
        def _del() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM plugin_hooks WHERE hook_id = ?", (hook_id,))  # nosemgrep: sqlalchemy-execute-raw-query
            conn.commit()
            conn.close()

        _retry(_del)

    def register_hook(
        self,
        plugin_id: str,
        hook_type: HookType,
        hook_name: str,
        callback_ref: str,
        priority: int = 50,
    ) -> str:
        """Register a hook and return its ID."""
        with self._lock:
            hook_id = str(uuid.uuid4())
            reg = HookRegistration(
                id=hook_id,
                plugin_id=plugin_id,
                hook_type=hook_type,
                hook_name=hook_name,
                priority=priority,
                callback_ref=callback_ref,
                active=True,
            )
            self._hooks[hook_id] = reg
            self._save_to_db(reg)
            logger.info("Hook registered: %s (%s/%s)", hook_id, hook_type.value, hook_name)
            return hook_id

    def unregister_hook(self, hook_id: str) -> bool:
        """Unregister a hook."""
        with self._lock:
            if hook_id not in self._hooks:
                return False
            del self._hooks[hook_id]
            self._delete_from_db(hook_id)
            return True

    def fire_hook(
        self,
        hook_type: HookType,
        hook_name: str,
        context: Dict[str, Any],
    ) -> List[Any]:
        """Fire hooks matching type/name and collect results."""
        with self._lock:
            matching = [
                h for h in self._hooks.values()
                if h.hook_type == hook_type
                and h.hook_name == hook_name
                and h.active
            ]
            matching.sort(key=lambda h: h.priority)

        results: List[Any] = []
        for hook in matching:
            try:
                # Attempt to call the callback via lifecycle manager
                from .lifecycle import get_plugin_lifecycle
                lifecycle = get_plugin_lifecycle()
                result = lifecycle._call_hook(hook.plugin_id, hook.callback_ref, context)
                if result is not None:
                    results.append(result)
            except Exception as exc:
                logger.error(
                    "Hook %s (%s) failed: %s", hook.id, hook.callback_ref, exc,
                )
        return results

    def get_hooks(
        self,
        hook_type: Optional[HookType] = None,
        plugin_id: Optional[str] = None,
    ) -> List[HookRegistration]:
        with self._lock:
            result = list(self._hooks.values())
            if hook_type is not None:
                result = [h for h in result if h.hook_type == hook_type]
            if plugin_id is not None:
                result = [h for h in result if h.plugin_id == plugin_id]
            return result

    def disable_hook(self, hook_id: str) -> bool:
        with self._lock:
            hook = self._hooks.get(hook_id)
            if hook is None:
                return False
            hook.active = False
            self._save_to_db(hook)
            return True

    def enable_hook(self, hook_id: str) -> bool:
        with self._lock:
            hook = self._hooks.get(hook_id)
            if hook is None:
                return False
            hook.active = True
            self._save_to_db(hook)
            return True


_hook_system_instance: Optional[PluginHookSystem] = None
_hook_system_lock = threading.Lock()


def get_plugin_hook_system(db_path: Optional[str] = None) -> PluginHookSystem:
    global _hook_system_instance
    with _hook_system_lock:
        if _hook_system_instance is None:
            _hook_system_instance = PluginHookSystem(db_path=db_path)
        return _hook_system_instance


def reset_plugin_hook_system() -> None:
    global _hook_system_instance
    with _hook_system_lock:
        _hook_system_instance = None
