"""
ZENIC-AGENTS — Shared Memory Bus: Shared State.

Thread-safe key-value store for pipeline context with ReadWriteLock,
TTL support, change notification callbacks, and atomic get-and-set.
"""

import json
import logging
import time
from typing import Any, Callable, Dict, List, Tuple

from src.core.patterns.concurrency.read_write_lock import ReadWriteLock

logger = logging.getLogger(__name__)


class SharedState:
    """Thread-safe key-value store for pipeline context.

    Features:
        - ReadWriteLock for concurrent reads / exclusive writes
        - Namespaced by agent_id and tenant_id
        - TTL support (auto-expire stale context)
        - Change notification via callback registration
        - Atomic get-and-set for conditional updates

    Internal structure::

        _data[namespace][key] = (value, updated_at, ttl_seconds)
    """

    def __init__(self) -> None:
        self._rw_lock = ReadWriteLock()
        # namespace → key → (value, updated_at, ttl_seconds)
        self._data: Dict[str, Dict[str, Tuple[Any, float, float]]] = {}
        # Change callbacks: list of (namespace_pattern, callback)
        self._callbacks: List[Tuple[str, Callable[[str, str, Any], None]]] = []

    # ── Core Operations ──

    def set(self, namespace: str, key: str, value: Any,
            ttl: float = 0, tenant_id: str = "default") -> None:
        """Set a value. Overwrites existing. O(1) in-memory."""
        ns_key = f"{tenant_id}:{namespace}"
        now = time.monotonic()
        with self._rw_lock.acquire_write():
            if ns_key not in self._data:
                self._data[ns_key] = {}
            self._data[ns_key][key] = (value, now, ttl)
        self._notify_callbacks(namespace, key, value)

    def get(self, namespace: str, key: str, default: Any = None,
            tenant_id: str = "default") -> Any:
        """Get a value. Returns *default* if missing or expired. O(1)."""
        ns_key = f"{tenant_id}:{namespace}"
        with self._rw_lock.acquire_read():
            ns = self._data.get(ns_key)
            if ns is None:
                return default
            entry = ns.get(key)
            if entry is None:
                return default
            value, updated_at, ttl = entry
            if ttl > 0:
                if time.monotonic() - updated_at > ttl:
                    # Expired — caller should clean up via delete
                    return default
            return value

    def get_and_set(self, namespace: str, key: str, value: Any,
                    ttl: float = 0, tenant_id: str = "default") -> Any:
        """Atomic get-and-set. Returns the previous value (or *default*)."""
        ns_key = f"{tenant_id}:{namespace}"
        now = time.monotonic()
        old_value = None
        with self._rw_lock.acquire_write():
            if ns_key not in self._data:
                self._data[ns_key] = {}
            old_entry = self._data[ns_key].get(key)
            if old_entry is not None:
                old_value = old_entry[0]
            self._data[ns_key][key] = (value, now, ttl)
        self._notify_callbacks(namespace, key, value)
        return old_value

    def delete(self, namespace: str, key: str,
               tenant_id: str = "default") -> None:
        """Delete a key from the namespace."""
        ns_key = f"{tenant_id}:{namespace}"
        with self._rw_lock.acquire_write():
            ns = self._data.get(ns_key)
            if ns is not None and key in ns:
                del ns[key]

    def list_keys(self, namespace: str, prefix: str = "",
                  tenant_id: str = "default") -> List[str]:
        """List keys in a namespace, optionally filtered by *prefix*."""
        ns_key = f"{tenant_id}:{namespace}"
        with self._rw_lock.acquire_read():
            ns = self._data.get(ns_key)
            if ns is None:
                return []
            if prefix:
                return [k for k in ns.keys() if k.startswith(prefix)]
            return list(ns.keys())

    # ── Callbacks ──

    def register_callback(self, namespace: str,
                          callback: Callable[[str, str, Any], None]) -> None:
        """Register a callback invoked when a key in *namespace* changes."""
        self._callbacks.append((namespace, callback))

    def _notify_callbacks(self, namespace: str, key: str, value: Any) -> None:
        """Fire registered callbacks (outside write lock)."""
        for ns_pattern, cb in self._callbacks:
            if ns_pattern == "*" or ns_pattern == namespace:
                try:
                    cb(namespace, key, value)
                except Exception:
                    logger.exception("SharedState callback error for ns=%s key=%s",
                                     namespace, key)

    # ── Expiry ──

    def purge_expired(self) -> int:
        """Remove all expired entries across all namespaces.

        Returns:
            Number of entries purged.
        """
        purged = 0
        now = time.monotonic()
        with self._rw_lock.acquire_write():
            for ns_key in list(self._data.keys()):
                ns = self._data[ns_key]
                for k in list(ns.keys()):
                    _, updated_at, ttl = ns[k]
                    if ttl > 0 and now - updated_at > ttl:
                        del ns[k]
                        purged += 1
        return purged

    # ── Snapshot for Persistence ──

    def snapshot(self) -> List[Tuple[str, str, str, str, float, float]]:
        """Return all non-expired entries for persistence.

        Returns:
            List of (namespace, key, json_value, tenant_id, updated_at, ttl).
        """
        result: List[Tuple[str, str, str, str, float, float]] = []
        now = time.monotonic()
        with self._rw_lock.acquire_read():
            for ns_key, ns in self._data.items():
                # ns_key = "tenant_id:namespace"
                parts = ns_key.split(":", 1)
                tenant_id = parts[0] if len(parts) == 2 else "default"
                namespace = parts[1] if len(parts) == 2 else ns_key
                for k, (v, updated_at, ttl) in ns.items():
                    if ttl > 0 and now - updated_at > ttl:
                        continue
                    result.append((
                        namespace, k,
                        json.dumps(v, default=str),
                        tenant_id, updated_at, ttl,
                    ))
        return result
