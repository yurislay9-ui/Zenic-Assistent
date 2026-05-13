"""
ZENIC-AGENTS - Structural Pattern: Proxy

Lazy-loading and caching proxies for resource-constrained environments.

  - LazyProxy: Defers object creation until first attribute access.
  - CacheProxy: Caches method results with a TTL.

Designed for Android/Termux (500MB RAM).
"""

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LazyProxy:
    """
    Proxy that defers the creation of an expensive object until its
    first attribute access.

    The *factory_fn* is called **once** (lazily) to produce the real
    object.  All subsequent attribute accesses are delegated transparently.

    Usage::

        proxy = LazyProxy(lambda: ExpensiveObject())
        # ExpensiveObject is NOT created yet
        proxy.do_work()   # created on first access, then delegated
        proxy.is_loaded   # True
        proxy.unload()    # release the real object
    """

    def __init__(self, factory_fn: Callable[[], Any]) -> None:
        """
        Args:
            factory_fn: Zero-argument callable that creates the real object.

        Raises:
            ValueError: If *factory_fn* is not callable.
        """
        if not callable(factory_fn):
            raise ValueError("LazyProxy: factory_fn must be callable")
        self._factory_fn = factory_fn
        self._real_object: Any = None
        self._loaded: bool = False
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Attribute delegation (lazy init)
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Private attributes managed by the proxy itself (_factory_fn,
        # _real_object, _loaded, _lock) are found via normal attribute
        # lookup and never reach __getattr__.  All other attribute
        # accesses — including underscore-prefixed methods on the real
        # object like _call_llm — are delegated transparently.
        if not self._loaded:
            with self._lock:
                # Double-checked locking
                if not self._loaded:
                    logger.debug("LazyProxy: initializing real object on first access to '%s'", name)
                    self._real_object = self._factory_fn()
                    self._loaded = True
        return getattr(self._real_object, name)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """Return True if the real object has been created."""
        return self._loaded

    def unload(self) -> None:
        """
        Release the real object so it can be garbage-collected.

        The next attribute access will re-invoke the factory function,
        creating a fresh instance.
        """
        with self._lock:
            if self._loaded:
                logger.debug("LazyProxy: unloading real object")
                self._real_object = None
                self._loaded = False

    # ------------------------------------------------------------------
    # Representations
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        if self._loaded:
            return f"LazyProxy(loaded={self._real_object!r})"
        return "LazyProxy(loaded=False)"


class CacheProxy:
    """
    Proxy that caches method results with a per-call TTL.

    Only **callable** attribute accesses are cached; property / data
    accesses are delegated directly.

    Usage::

        proxy = CacheProxy(expensive_service, ttl=60.0)
        proxy.compute(x=1)  # cached for 60s
        proxy.invalidate("compute")
        proxy.invalidate()   # clear all caches
    """

    def __init__(self, real_object: Any, ttl: float = 300.0) -> None:
        """
        Args:
            real_object: The real object to wrap.
            ttl: Default time-to-live for cached results (seconds).

        Raises:
            ValueError: If *real_object* is None.
        """
        if real_object is None:
            raise ValueError("CacheProxy: real_object must not be None")
        self._real_object = real_object
        self._ttl = ttl
        # _cache: method_name -> (args_key, result, timestamp)
        self._cache: Dict[str, Tuple[str, Any, float]] = {}
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

    # ------------------------------------------------------------------
    # Attribute delegation (with caching for callables)
    # ------------------------------------------------------------------

    def __getattr__(self, name: str) -> Any:
        # Same rationale as LazyProxy: the proxy's own internal attrs
        # are resolved before __getattr__; everything else is delegated.
        attr = getattr(self._real_object, name)
        if not callable(attr):
            # Non-callable: delegate directly, no caching
            return attr

        # Return a wrapper that caches results
        def _cached_call(*args: Any, **kwargs: Any) -> Any:
            cache_key = self._make_cache_key(args, kwargs)
            now = time.monotonic()
            with self._lock:
                cached = self._cache.get(name)
                if cached is not None:
                    stored_key, result, ts = cached
                    if stored_key == cache_key and (now - ts) < self._ttl:
                        self._hits += 1
                        logger.debug("CacheProxy: cache HIT for '%s'", name)
                        return result
                self._misses += 1

            # Compute outside lock to avoid blocking other readers
            result = attr(*args, **kwargs)

            with self._lock:
                self._cache[name] = (cache_key, result, now)
                logger.debug("CacheProxy: cache MISS for '%s', stored", name)
            return result

        return _cached_call

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def invalidate(self, method_name: Optional[str] = None) -> None:
        """
        Clear cached results.

        Args:
            method_name: If given, clear only that method's cache entry.
                         If None, clear the entire cache.
        """
        with self._lock:
            if method_name is not None:
                self._cache.pop(method_name, None)
                logger.debug("CacheProxy: invalidated cache for '%s'", method_name)
            else:
                self._cache.clear()
                logger.debug("CacheProxy: invalidated entire cache")

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def cache_stats(self) -> Dict[str, Any]:
        """Return cache hit/miss statistics and entry count."""
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / max(total, 1),
                "entries": len(self._cache),
                "ttl": self._ttl,
                "cached_methods": list(self._cache.keys()),
            }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_cache_key(args: tuple, kwargs: dict) -> str:
        """Produce a deterministic string key from args and kwargs."""
        try:
            return repr((args, sorted(kwargs.items())))
        except Exception:
            return str(id(args)) + str(id(kwargs))

    def __repr__(self) -> str:
        return f"CacheProxy(real={type(self._real_object).__name__}, entries={len(self._cache)})"
