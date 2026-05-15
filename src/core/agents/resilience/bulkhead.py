"""
Bulkhead pattern for v18 agents — limits concurrent executions per agent.

Prevents one slow agent from consuming all system resources.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

try:
    from typing import Self
except ImportError:
    Self = None  # type: ignore[misc,assignment]  # Fallback for Python <3.11


class BulkheadFullError(Exception):
    """Raised when bulkhead is at capacity."""
    pass


class AgentBulkhead:
    """Concurrency limiter for a single agent."""

    def __init__(
        self,
        name: str,
        max_concurrent: int = 4,
        max_queue: int = 20,
        timeout: float = 30.0,
    ) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self.timeout = timeout

        self._semaphore = threading.Semaphore(max_concurrent)
        self._queue_count = 0
        self._lock = threading.Lock()
        self._active_count = 0

        # Stats
        self._total_rejected = 0
        self._total_executed = 0
        self._total_timed_out = 0

    def acquire(self, timeout: Optional[float] = None) -> bool:
        """Acquire a execution slot. Returns True if acquired, False if timed out."""
        if timeout is None:
            timeout = self.timeout

        with self._lock:
            if self._queue_count >= self.max_queue:
                self._total_rejected += 1
                return False
            self._queue_count += 1

        acquired = self._semaphore.acquire(timeout=timeout)

        with self._lock:
            self._queue_count -= 1
            if acquired:
                self._active_count += 1
                self._total_executed += 1
            else:
                self._total_timed_out += 1

        return acquired

    def release(self) -> None:
        """Release an execution slot."""
        with self._lock:
            self._active_count = max(0, self._active_count - 1)
        self._semaphore.release()

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "max_concurrent": self.max_concurrent,
            "active_count": self._active_count,
            "queue_count": self._queue_count,
            "total_rejected": self._total_rejected,
            "total_executed": self._total_executed,
            "total_timed_out": self._total_timed_out,
        }

    # Context manager support
    def __enter__(self) -> Self:
        if not self.acquire():
            raise BulkheadFullError(f"Bulkhead {self.name} is at capacity")
        return self

    def __exit__(self, *args) -> None:
        self.release()


# Bulkhead configs per agent group
BULKHEAD_CONFIGS = {
    "understanding": {"max_concurrent": 4},
    "memory": {"max_concurrent": 8},
    "business": {"max_concurrent": 2},
    "code": {"max_concurrent": 4},
    "validation": {"max_concurrent": 8},
    "automation": {"max_concurrent": 4},
    "reasoning": {"max_concurrent": 4},
    "verdict": {"max_concurrent": 1},  # Most critical — single concurrent
    "infrastructure": {"max_concurrent": 2},
}


class BulkheadManager:
    """Manages per-agent bulkhead instances."""

    def __init__(self) -> None:
        self._bulkheads: dict[str, AgentBulkhead] = {}
        self._lock = threading.Lock()

    def get_bulkhead(self, agent_name: str) -> AgentBulkhead:
        with self._lock:
            if agent_name not in self._bulkheads:
                group = self._classify_agent(agent_name)
                config = BULKHEAD_CONFIGS.get(group, {"max_concurrent": 4})
                self._bulkheads[agent_name] = AgentBulkhead(
                    name=agent_name, **config
                )
            return self._bulkheads[agent_name]

    def all_stats(self) -> dict[str, dict]:
        with self._lock:
            return {name: b.stats for name, b in self._bulkheads.items()}

    def _classify_agent(self, name: str) -> str:
        name_lower = name.lower()
        if any(k in name_lower for k in ["intent", "entity", "target", "criticality", "bilingual"]):
            return "understanding"
        elif any(k in name_lower for k in ["memory", "relevance", "compressor", "prefetch"]):
            return "memory"
        elif any(k in name_lower for k in ["invoice", "inventory", "crm", "task", "report", "notification", "analytics", "router"]):
            return "business"
        elif any(k in name_lower for k in ["code_gen", "refactor", "optim", "fixer", "scaffold", "defensive"]):
            return "code"
        elif any(k in name_lower for k in ["security", "syntax", "chain_valid", "config_valid", "risk", "fix_suggest"]):
            return "validation"
        elif any(k in name_lower for k in ["trigger", "action_inf", "schedule", "condition", "namer", "workflow"]):
            return "automation"
        elif any(k in name_lower for k in ["problem", "step", "template_r", "confidence", "conclusion"]):
            return "reasoning"
        elif any(k in name_lower for k in ["verdict", "evidence", "consensus", "pipeline"]):
            return "verdict"
        else:
            return "infrastructure"
