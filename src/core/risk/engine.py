from __future__ import annotations

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    BlastRadiusReport,
    CompositeRiskReport,
    CriticalPathReport,
    RiskLevel,
    RiskPropagationReport,
)

logger = logging.getLogger("zenic_agents.core.risk.engine")

try:
    from src.core.native import (
        calculate_blast_radius,
        propagate_risks,
        find_critical_path,
        compute_reachability,
        multi_node_blast_radius,
        HAS_NATIVE,
    )
except ImportError:
    HAS_NATIVE = False
    calculate_blast_radius = None  # type: ignore[assignment]
    propagate_risks = None  # type: ignore[assignment]
    find_critical_path = None  # type: ignore[assignment]
    compute_reachability = None  # type: ignore[assignment]
    multi_node_blast_radius = None  # type: ignore[assignment]


class RiskPredictionEngine:
    """Thread-safe risk prediction engine with Rust integration."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._analysis_count = 0

    def analyze_node(
        self, node_id: str, edges: List[Tuple[str, str]]
    ) -> BlastRadiusReport:
        """Single node blast radius analysis."""
        with self._lock:
            self._analysis_count += 1
            try:
                if HAS_NATIVE and calculate_blast_radius is not None:
                    result = calculate_blast_radius(node_id, edges)
                    risk_level = self._determine_risk_level(result.get("blast_radius_size", 0))
                    report = BlastRadiusReport(
                        source_node=node_id,
                        affected_nodes=result.get("blast_radius", []),
                        direct_dependents=result.get("direct_dependents", []),
                        transitive_dependents=result.get("transitive_dependents", []),
                        risk_level=risk_level,
                        blast_radius_size=result.get("blast_radius_size", 0),
                    )
                else:
                    report = self._py_blast_radius(node_id, edges)
                report.recommendations = self._generate_recommendations(report)
                return report
            except Exception as exc:
                logger.error("Blast radius analysis failed for %s: %s", node_id, exc)
                return BlastRadiusReport(
                    source_node=node_id, risk_level=RiskLevel.HIGH,
                    recommendations=["Analysis failed — treat as high risk"],
                )

    def analyze_propagation(
        self,
        nodes: List[str],
        edges: List[Tuple[str, str]],
        base_risks: Dict[str, float],
        decay: float = 0.7,
    ) -> RiskPropagationReport:
        """Analyze risk propagation through the DAG."""
        with self._lock:
            self._analysis_count += 1
            try:
                if HAS_NATIVE and propagate_risks is not None:
                    result = propagate_risks(nodes, edges, base_risks, decay)
                    return RiskPropagationReport(
                        effective_risks=result.get("effective_risks", {}),
                        max_effective_risk=result.get("max_effective_risk", 0.0),
                        high_risk_nodes=result.get("high_risk_nodes", []),
                        risk_paths=result.get("risk_paths", {}),
                    )
                return self._py_propagate_risks(nodes, edges, base_risks, decay)
            except Exception as exc:
                logger.error("Risk propagation analysis failed: %s", exc)
                return RiskPropagationReport()

    def find_critical(
        self,
        nodes: List[str],
        edges: List[Tuple[str, str]],
        durations: Dict[str, int],
    ) -> CriticalPathReport:
        """Find the critical path in the DAG."""
        with self._lock:
            self._analysis_count += 1
            try:
                if HAS_NATIVE and find_critical_path is not None:
                    result = find_critical_path(nodes, edges, durations)
                    return CriticalPathReport(
                        critical_path=result.get("critical_path", []),
                        total_duration_ms=result.get("total_duration_ms", 0),
                        is_on_critical_path=result.get("is_on_critical_path", {}),
                    )
                return self._py_find_critical_path(nodes, edges, durations)
            except Exception as exc:
                logger.error("Critical path analysis failed: %s", exc)
                return CriticalPathReport()

    def composite_analysis(
        self,
        failed_nodes: List[str],
        edges: List[Tuple[str, str]],
        base_risks: Dict[str, float],
        durations: Dict[str, int],
        decay: float = 0.7,
    ) -> CompositeRiskReport:
        """Full composite risk analysis."""
        with self._lock:
            self._analysis_count += 1
            try:
                # Blast radius for all failed nodes
                if len(failed_nodes) == 1:
                    blast = self.analyze_node(failed_nodes[0], edges)
                else:
                    blast = self._multi_node_blast(failed_nodes, edges)

                # Get all affected + failed nodes for propagation
                all_nodes = list(set(failed_nodes + blast.affected_nodes))
                if not all_nodes:
                    all_nodes = failed_nodes

                propagation = self.analyze_propagation(all_nodes, edges, base_risks, decay)
                critical = self.find_critical(all_nodes, edges, durations)

                # Compute overall risk score
                blast_score = min(blast.blast_radius_size / 20.0, 1.0)
                prop_score = propagation.max_effective_risk
                overall = (blast_score + prop_score) / 2.0
                overall = min(max(overall, 0.0), 1.0)

                # Generate summary
                level = self._determine_risk_level(overall * 20)
                summary = (
                    f"Composite risk: {level.value} "
                    f"(blast={blast.blast_radius_size} nodes, "
                    f"max_propagation={prop_score:.2f}, "
                    f"overall={overall:.2f})"
                )

                return CompositeRiskReport(
                    blast_radius=blast,
                    propagation=propagation,
                    critical_path=critical,
                    overall_risk_score=overall,
                    summary=summary,
                )
            except Exception as exc:
                logger.error("Composite analysis failed: %s", exc)
                return CompositeRiskReport(
                    overall_risk_score=1.0,
                    summary=f"Analysis failed: {exc}",
                )

    def get_risk_hotspots(
        self,
        edges: List[Tuple[str, str]],
        base_risks: Dict[str, float],
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Find high-risk nodes above the threshold."""
        with self._lock:
            hotspots: List[Dict[str, Any]] = []
            for node_id, risk in base_risks.items():
                if risk >= threshold:
                    blast = self.analyze_node(node_id, edges)
                    hotspots.append({
                        "node_id": node_id,
                        "risk_score": risk,
                        "blast_radius_size": blast.blast_radius_size,
                        "risk_level": blast.risk_level.value,
                    })
            hotspots.sort(key=lambda x: x["risk_score"], reverse=True)
            return hotspots

    def simulate_mitigation(
        self,
        node_id: str,
        edges: List[Tuple[str, str]],
        base_risks: Dict[str, float],
        mitigation_factor: float = 0.5,
    ) -> Dict[str, Any]:
        """Simulate reducing a node's risk."""
        with self._lock:
            original = base_risks.get(node_id, 0.0)
            mitigated_risks = dict(base_risks)
            mitigated_risks[node_id] = original * (1.0 - mitigation_factor)

            # Get all node IDs from edges
            all_nodes = list(set(
                [src for src, _ in edges] + [dst for _, dst in edges] + list(base_risks.keys())
            ))

            before = self.analyze_propagation(all_nodes, edges, base_risks)
            after = self.analyze_propagation(all_nodes, edges, mitigated_risks)

            return {
                "node_id": node_id,
                "original_risk": original,
                "mitigated_risk": mitigated_risks[node_id],
                "mitigation_factor": mitigation_factor,
                "before_max_risk": before.max_effective_risk,
                "after_max_risk": after.max_effective_risk,
                "risk_reduction": before.max_effective_risk - after.max_effective_risk,
                "before_high_risk_count": len(before.high_risk_nodes),
                "after_high_risk_count": len(after.high_risk_nodes),
            }

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "analysis_count": self._analysis_count,
                "has_native": HAS_NATIVE,
            }

    def _determine_risk_level(self, score: float) -> RiskLevel:
        if score <= 0:
            return RiskLevel.NEGLIGIBLE
        elif score <= 3:
            return RiskLevel.LOW
        elif score <= 10:
            return RiskLevel.MEDIUM
        elif score <= 20:
            return RiskLevel.HIGH
        return RiskLevel.CRITICAL

    def _generate_recommendations(self, report: BlastRadiusReport) -> List[str]:
        recs: List[str] = []
        if report.blast_radius_size == 0:
            recs.append("Node has no downstream dependents — low priority")
            return recs
        if report.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            recs.append("Add redundancy or circuit breaker around this node")
            recs.append("Implement graceful degradation for dependent nodes")
        if report.blast_radius_size > 10:
            recs.append("Consider splitting this node into smaller units")
            recs.append("Add monitoring and alerting for this node")
        if report.blast_radius_size > 5:
            recs.append("Implement fallback paths for critical dependents")
        return recs

    def _multi_node_blast(
        self, failed_nodes: List[str], edges: List[Tuple[str, str]]
    ) -> BlastRadiusReport:
        """Blast radius for multiple failing nodes."""
        try:
            if HAS_NATIVE and multi_node_blast_radius is not None:
                result = multi_node_blast_radius(failed_nodes, edges)
                return BlastRadiusReport(
                    source_node=",".join(failed_nodes),
                    affected_nodes=result.get("combined_blast_radius", []),
                    blast_radius_size=result.get("blast_radius_size", 0),
                    risk_level=self._determine_risk_level(result.get("blast_radius_size", 0)),
                )
        except Exception:
            pass
        return self._py_multi_blast(failed_nodes, edges)

    # ── Pure Python fallbacks ──

    def _py_blast_radius(
        self, node_id: str, edges: List[Tuple[str, str]]
    ) -> BlastRadiusReport:
        forward: Dict[str, List[str]] = {}
        for src, dst in edges:
            forward.setdefault(src, []).append(dst)

        direct = set(forward.get(node_id, []))
        visited: set = set()
        stack = list(direct)
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            for neighbor in forward.get(n, []):
                if neighbor not in visited:
                    stack.append(neighbor)
        transitive = visited - direct
        size = len(visited)
        return BlastRadiusReport(
            source_node=node_id,
            affected_nodes=list(visited),
            direct_dependents=list(direct),
            transitive_dependents=list(transitive),
            risk_level=self._determine_risk_level(size),
            blast_radius_size=size,
        )

    def _py_propagate_risks(
        self,
        nodes: List[str],
        edges: List[Tuple[str, str]],
        base_risks: Dict[str, float],
        decay: float,
    ) -> RiskPropagationReport:
        reverse_adj: Dict[str, List[str]] = {}
        for src, dst in edges:
            reverse_adj.setdefault(dst, []).append(src)

        effective: Dict[str, float] = {}
        risk_paths: Dict[str, List[str]] = {}
        for node in nodes:
            own = base_risks.get(node, 0.0)
            incoming = reverse_adj.get(node, [])
            max_prop = 0.0
            max_src = ""
            for src in incoming:
                src_eff = effective.get(src, 0.0)
                prop = src_eff * decay
                if prop > max_prop:
                    max_prop = prop
                    max_src = src
            eff = max(own, max_prop)
            effective[node] = eff
            if max_src and max_prop > own:
                risk_paths[node] = risk_paths.get(max_src, [])[:] + [node]
            else:
                risk_paths[node] = [node]

        max_eff = max(effective.values()) if effective else 0.0
        high = [n for n, r in effective.items() if r >= 0.7]
        return RiskPropagationReport(
            effective_risks=effective,
            max_effective_risk=max_eff,
            high_risk_nodes=high,
            risk_paths=risk_paths,
        )

    def _py_find_critical_path(
        self,
        nodes: List[str],
        edges: List[Tuple[str, str]],
        durations: Dict[str, int],
    ) -> CriticalPathReport:
        predecessors: Dict[str, List[str]] = {n: [] for n in nodes}
        for src, dst in edges:
            if dst in predecessors:
                predecessors[dst].append(src)

        earliest: Dict[str, int] = {}
        pred_on_path: Dict[str, Optional[str]] = {}
        for node in nodes:
            dur = durations.get(node, 0)
            max_pred = 0
            best = None
            for p in predecessors[node]:
                pf = earliest.get(p, 0)
                if pf > max_pred:
                    max_pred = pf
                    best = p
            earliest[node] = max_pred + dur
            pred_on_path[node] = best

        end = max(earliest, key=earliest.get) if earliest else ""
        total = earliest.get(end, 0)
        path: List[str] = []
        cur: Optional[str] = end
        while cur:
            path.append(cur)
            cur = pred_on_path.get(cur)
        path.reverse()
        crit_set = set(path)
        return CriticalPathReport(
            critical_path=path,
            total_duration_ms=total,
            is_on_critical_path={n: n in crit_set for n in nodes},
        )

    def _py_multi_blast(
        self, failed_nodes: List[str], edges: List[Tuple[str, str]]
    ) -> BlastRadiusReport:
        forward: Dict[str, List[str]] = {}
        for src, dst in edges:
            forward.setdefault(src, []).append(dst)

        failed_set = set(failed_nodes)
        visited: set = set()
        stack = list(failed_nodes)
        while stack:
            n = stack.pop()
            if n in visited:
                continue
            visited.add(n)
            for nb in forward.get(n, []):
                if nb not in visited:
                    stack.append(nb)
        affected = [n for n in visited if n not in failed_set]
        size = len(affected)
        return BlastRadiusReport(
            source_node=",".join(failed_nodes),
            affected_nodes=affected,
            blast_radius_size=size,
            risk_level=self._determine_risk_level(size),
        )


_engine_instance: Optional[RiskPredictionEngine] = None
_engine_lock = threading.Lock()


def get_risk_prediction_engine() -> RiskPredictionEngine:
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = RiskPredictionEngine()
        return _engine_instance


def reset_risk_prediction_engine() -> None:
    global _engine_instance
    with _engine_lock:
        _engine_instance = None
