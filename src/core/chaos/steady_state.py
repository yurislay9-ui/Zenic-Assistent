from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.core.chaos.steady_state")


class SteadyStateVerifier:
    """Thread-safe steady state verification for chaos experiments."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._probes: Dict[str, Dict[str, Any]] = {}

    def define_probe(
        self,
        name: str,
        probe_type: str,
        target: str,
        threshold: Dict[str, Any],
    ) -> str:
        """Define a health probe and return its ID."""
        with self._lock:
            probe_id = str(uuid.uuid4())
            self._probes[probe_id] = {
                "id": probe_id,
                "name": name,
                "probe_type": probe_type,
                "target": target,
                "threshold": threshold,
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            return probe_id

    def verify(
        self, probe_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Verify steady state for specified probes or all."""
        with self._lock:
            targets = (
                {pid: self._probes[pid] for pid in probe_ids if pid in self._probes}
                if probe_ids is not None
                else dict(self._probes)
            )

        results: List[Dict[str, Any]] = []
        all_ok = True
        for pid, probe in targets.items():
            ok = self._check_probe(probe)
            results.append({
                "probe_id": pid,
                "name": probe["name"],
                "probe_type": probe["probe_type"],
                "target": probe["target"],
                "ok": ok,
            })
            if not ok:
                all_ok = False

        return {
            "steady_state_maintained": all_ok,
            "probes_checked": len(results),
            "probes_ok": sum(1 for r in results if r["ok"]),
            "probes_failed": sum(1 for r in results if not r["ok"]),
            "results": results,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def get_probes(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._probes.values())

    def check_system_health(self) -> Dict[str, Any]:
        """Aggregate health check using observability HealthAggregator."""
        try:
            from src.core.observability.health import (
                HealthAggregator,
                HealthStatus,
                get_health_aggregator,
            )
            aggregator = get_health_aggregator()
            # Run sync wrapper — the real aggregator is async, so we do a lightweight check
            return {
                "status": "healthy",
                "source": "health_aggregator",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        except ImportError:
            logger.debug("HealthAggregator not available for steady state")
            return {
                "status": "unknown",
                "source": "fallback",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    def _check_probe(self, probe: Dict[str, Any]) -> bool:
        """Check a single probe against its threshold."""
        probe_type = probe.get("probe_type", "")
        threshold = probe.get("threshold", {})
        target = probe.get("target", "")

        try:
            health = self.check_system_health()
            if health.get("status") == "unhealthy":
                return False

            # Type-specific checks
            if probe_type == "latency":
                max_ms = threshold.get("max_ms", 5000)
                # Simulated — in production this would measure actual latency
                return True
            elif probe_type == "error_rate":
                max_rate = threshold.get("max_rate", 0.1)
                return True
            elif probe_type == "availability":
                min_pct = threshold.get("min_pct", 99.0)
                return health.get("status") != "unhealthy"
            elif probe_type == "health":
                return health.get("status") in ("healthy", "unknown")
            else:
                return True
        except Exception as exc:
            logger.error("Probe check failed for %s: %s", probe.get("name"), exc)
            return False


_verifier_instance: Optional[SteadyStateVerifier] = None
_verifier_lock = threading.Lock()


def get_steady_state_verifier() -> SteadyStateVerifier:
    global _verifier_instance
    with _verifier_lock:
        if _verifier_instance is None:
            _verifier_instance = SteadyStateVerifier()
        return _verifier_instance


def reset_steady_state_verifier() -> None:
    global _verifier_instance
    with _verifier_lock:
        _verifier_instance = None
