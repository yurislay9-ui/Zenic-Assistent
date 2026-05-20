"""
compat._business — BusinessLogicAgentCompat v1→v2 wrapper.
"""

from __future__ import annotations

from typing import Any

from src.core.agents.business import OperationRouter


class BusinessLogicAgentCompat:
    """v1-compatible BusinessLogicAgent wrapper around v2 OperationRouter."""

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._router = OperationRouter(**kwargs)
        self._call_count = 0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "BusinessLogicAgentCompat",
            "call_count": self._call_count,
            "router": self._router.stats,
        }
