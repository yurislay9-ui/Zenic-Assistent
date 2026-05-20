"""
High-Speed Event Bus (B1) — Low-latency dispatch.

Provides: wildcard_match, resolve_routes, batch_resolve_routes,
          deduplicate_events, sort_by_priority
"""

from __future__ import annotations

import fnmatch
from typing import Any, Dict, List, Set, Tuple

from ._loader import HAS_NATIVE


def wildcard_match(pattern: str, text: str) -> bool:
    """Fast wildcard pattern matching supporting * and ? wildcards."""
    if HAS_NATIVE:
        from ._loader import _rust_wildcard_match
        return _rust_wildcard_match(pattern, text)
    # Pure Python fallback using fnmatch
    return fnmatch.fnmatch(text, pattern)


def resolve_routes(
    event_topic: str, subscriptions: List[Dict[str, Any]],
) -> List[str]:
    """Resolve which handlers should receive an event."""
    if HAS_NATIVE:
        from ._loader import _rust_resolve_routes
        return _rust_resolve_routes(event_topic, subscriptions)
    # Pure Python fallback
    _priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    matched: List[Tuple[int, str]] = []
    for sub in subscriptions:
        if not sub.get("active", True):
            continue
        pattern = sub.get("pattern", "")
        handler_id = sub.get("handler_id", "")
        priority = sub.get("priority", "normal").lower()
        if fnmatch.fnmatch(event_topic, pattern):
            matched.append((_priority_order.get(priority, 2), handler_id))
    matched.sort(key=lambda x: x[0])
    return [hid for _, hid in matched]


def batch_resolve_routes(
    event_topics: List[str],
    subscriptions: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """Batch resolve routes for multiple events."""
    if HAS_NATIVE:
        from ._loader import _rust_batch_resolve_routes
        return _rust_batch_resolve_routes(event_topics, subscriptions)
    # Pure Python fallback
    return {topic: resolve_routes(topic, subscriptions) for topic in event_topics}


def deduplicate_events(
    new_fingerprints: List[str],
    seen_fingerprints: Set[str],
) -> Dict[str, Any]:
    """Deduplicate events by fingerprint."""
    if HAS_NATIVE:
        from ._loader import _rust_deduplicate_events
        return _rust_deduplicate_events(new_fingerprints, seen_fingerprints)
    # Pure Python fallback
    unique: List[str] = []
    duplicates: List[str] = []
    for fp in new_fingerprints:
        if fp in seen_fingerprints:
            duplicates.append(fp)
        else:
            unique.append(fp)
    return {"unique": unique, "duplicates": duplicates}


def sort_by_priority(
    events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Sort events by priority (critical first)."""
    if HAS_NATIVE:
        from ._loader import _rust_sort_by_priority
        return _rust_sort_by_priority(events)
    # Pure Python fallback
    _priority_order = {"critical": 0, "high": 1, "normal": 2, "low": 3}
    return sorted(events, key=lambda e: _priority_order.get(
        e.get("priority", "normal").lower(), 2))
